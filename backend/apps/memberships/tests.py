"""Payment reliability tests: order idempotency, verify safety, webhooks.

Covers the production guarantees:
- order creation never duplicates a gateway order
- verification is idempotent and refuses tampered callbacks
- webhooks are signature-checked, deduped, and can recover a payment the
  browser lost (the "money taken, pass not issued" failure mode)
- status transitions are guarded by the state machine + DB constraints
"""
import hashlib
import hmac as hmac_lib
import json
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.library.models import Seat, Shift

from .models import Membership, Payment, WebhookEvent
from .services import (
    WebhookSignatureError,
    create_payment_order,
    mark_payment_captured,
    process_webhook_event,
    verify_and_activate,
)

TEST_KEY = "rzp_test_key"
TEST_SECRET = "key_secret_test"
WEBHOOK_SECRET = "whsec_test"


def checkout_signature(order_id, payment_id):
    msg = f"{order_id}|{payment_id}".encode()
    return hmac_lib.new(TEST_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def webhook_signature(body: bytes):
    return hmac_lib.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def captured_event(order_id, payment_id="pay_wh_1", amount=150000):
    return {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {"id": payment_id, "order_id": order_id, "amount": amount}
            }
        },
    }


@override_settings(
    RAZORPAY_KEY_ID=TEST_KEY,
    RAZORPAY_KEY_SECRET=TEST_SECRET,
    RAZORPAY_WEBHOOK_SECRET=WEBHOOK_SECRET,
    ALLOW_MOCK_PAYMENTS=False,
    EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
)
class PaymentFlowTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="member@example.com", password="pass1234", name="Test Member"
        )
        self.shift = Shift.objects.create(
            name="Morning", start_time="06:00", end_time="10:00", price=500
        )
        self.seat = Seat.objects.create(seat_number="T1", section="common")
        self.membership = Membership.objects.create(
            member=self.user,
            shift=self.shift,
            seat=self.seat,
            duration_months=3,
            amount=self.shift.price * 3,
        )

    def make_order(self, order_id="order_test_1"):
        with mock.patch("apps.memberships.services._razorpay_client") as client:
            client.return_value.order.create.return_value = {"id": order_id}
            return create_payment_order(self.membership)

    # ------------------------------------------------------- order creation

    def test_create_payment_order_returns_gateway_payload(self):
        result = self.make_order()
        self.assertEqual(result["order_id"], "order_test_1")
        self.assertEqual(result["amount"], 150000)
        self.assertEqual(result["currency"], "INR")
        self.assertFalse(result["mock"])
        payment = Payment.objects.get(membership=self.membership)
        self.assertEqual(payment.razorpay_order_id, "order_test_1")

    def test_create_payment_order_is_idempotent(self):
        first = self.make_order()
        second = self.make_order(order_id="order_test_2")  # no second API call path
        self.assertEqual(first["order_id"], second["order_id"])
        self.assertEqual(Payment.objects.filter(membership=self.membership).count(), 1)

    def test_paid_membership_short_circuits_order_creation(self):
        self.make_order()
        payment = Payment.objects.get(membership=self.membership)
        payment.status = "paid"
        payment.save(update_fields=["status"])
        result = self.make_order(order_id="order_never_created")
        self.assertTrue(result.get("already_paid"))

    # ------------------------------------------------------------ verify API

    def test_verify_success_activates_and_marks_paid(self):
        self.make_order()
        sig = checkout_signature("order_test_1", "pay_ok_1")
        activated = verify_and_activate(self.membership, "pay_ok_1", sig)
        self.assertIsNotNone(activated)
        self.assertEqual(activated.status, "active")
        payment = Payment.objects.get(membership=self.membership)
        self.assertEqual(payment.status, "paid")
        self.assertEqual(payment.razorpay_payment_id, "pay_ok_1")
        self.assertIsNotNone(payment.paid_at)

    def test_verify_invalid_signature_fails_without_charging_state(self):
        self.make_order()
        result = verify_and_activate(self.membership, "pay_bad", "deadbeef")
        self.assertIsNone(result)
        payment = Payment.objects.get(membership=self.membership)
        self.assertEqual(payment.status, "failed")
        self.assertNotEqual(self.membership.status, "active")

    def test_verify_rejects_mismatched_order_id(self):
        self.make_order()
        sig = checkout_signature("order_OTHER", "pay_x")  # signed for another order
        result = verify_and_activate(
            self.membership, "pay_x", sig, order_id="order_OTHER"
        )
        self.assertIsNone(result)
        self.assertEqual(Payment.objects.get(membership=self.membership).status, "created")

    def test_verify_is_idempotent_on_browser_refresh(self):
        self.make_order()
        sig = checkout_signature("order_test_1", "pay_ok_1")
        first = verify_and_activate(self.membership, "pay_ok_1", sig)
        paid_at = Payment.objects.get(membership=self.membership).paid_at
        again = verify_and_activate(self.membership, "pay_ok_1", sig)
        self.assertIsNotNone(first)
        self.assertIsNotNone(again)
        self.assertEqual(again.status, "active")
        self.assertEqual(Payment.objects.get(membership=self.membership).paid_at, paid_at)

    # ---------------------------------------------------------------- webhooks

    def deliver(self, event_dict):
        body = json.dumps(event_dict).encode()
        return process_webhook_event(body, webhook_signature(body))

    def test_webhook_captures_payment_without_browser_verify(self):
        self.make_order()
        outcome = self.deliver(captured_event("order_test_1"))
        self.assertEqual(outcome, "captured")
        payment = Payment.objects.get(membership=self.membership)
        self.assertEqual(payment.status, "paid")
        membership = Membership.objects.get(pk=self.membership.pk)
        self.assertEqual(membership.status, "active")

    def test_webhook_recovers_a_failed_verification(self):
        """Money was real even though the browser callback failed."""
        self.make_order()
        verify_and_activate(self.membership, "pay_bad", "wrong_sig")
        self.assertEqual(Payment.objects.get(membership=self.membership).status, "failed")
        outcome = self.deliver(captured_event("order_test_1"))
        self.assertEqual(outcome, "captured")
        self.assertEqual(Payment.objects.get(membership=self.membership).status, "paid")
        self.assertEqual(Membership.objects.get(pk=self.membership.pk).status, "active")

    def test_webhook_duplicate_delivery_is_processed_once(self):
        self.make_order()
        event = captured_event("order_test_1")
        self.assertEqual(self.deliver(event), "captured")
        self.assertEqual(self.deliver(event), "duplicate")
        self.assertEqual(WebhookEvent.objects.count(), 1)

    def test_webhook_after_verify_is_a_noop(self):
        self.make_order()
        verify_and_activate(
            self.membership,
            "pay_ok_1",
            checkout_signature("order_test_1", "pay_ok_1"),
        )
        outcome = self.deliver(captured_event("order_test_1", payment_id="pay_late"))
        self.assertEqual(outcome, "already_paid")
        # The late webhook must NOT overwrite the verified payment id.
        payment = Payment.objects.get(membership=self.membership)
        self.assertEqual(payment.razorpay_payment_id, "pay_ok_1")

    def test_webhook_unknown_order_is_ignored_gracefully(self):
        outcome = self.deliver(captured_event("order_does_not_exist"))
        self.assertEqual(outcome, "unknown_order")

    def test_webhook_bad_signature_raises(self):
        body = json.dumps(captured_event("order_test_1")).encode()
        with self.assertRaises(WebhookSignatureError):
            process_webhook_event(body, "0" * 64)
        payment = Payment.objects.filter(membership=self.membership).first()
        if payment is not None:
            self.assertNotEqual(payment.status, "paid")

    def test_webhook_amount_mismatch_still_records_but_logs(self):
        self.make_order()
        # Amount differs from the stored membership amount; capture is accepted
        # (gateway truth) but the mismatch is logged for reconciliation.
        outcome = self.deliver(captured_event("order_test_1", amount=999))
        self.assertIn(outcome, ("captured", "already_paid"))

    # ------------------------------------------------------ state machine

    def test_transition_guard_refuses_illegal_moves(self):
        payment = Payment.objects.create(
            membership=self.membership, amount=1500, method="upi"
        )
        self.assertTrue(payment.transition_to("paid"))  # created → paid
        self.assertFalse(payment.transition_to("failed"))  # paid → failed ✗
        self.assertTrue(payment.transition_to("refunded"))  # paid → refunded ✓
        self.assertFalse(payment.transition_to("paid"))  # refunded → paid ✗

    def test_mark_captured_twice_reports_single_change(self):
        self.make_order()
        payment = Payment.objects.get(membership=self.membership)
        from django.db import transaction as db_transaction

        with db_transaction.atomic():
            first = mark_payment_captured(payment, "pay_once", "", source="test")
        with db_transaction.atomic():
            second = mark_payment_captured(payment, "pay_once", "", source="test")
        self.assertTrue(first)
        self.assertFalse(second)

    def test_unique_constraints_block_duplicate_gateway_ids(self):
        Payment.objects.create(
            membership=self.membership,
            amount=1500,
            razorpay_payment_id="pay_dup",
        )
        other = User.objects.create_user(
            email="other@example.com", password="pass1234", name="Other"
        )
        m2 = Membership.objects.create(
            member=other, shift=self.shift, duration_months=1, amount=500
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payment.objects.create(
                    membership=m2, amount=500, razorpay_payment_id="pay_dup"
                )


@override_settings(
    RAZORPAY_KEY_ID=TEST_KEY,
    RAZORPAY_KEY_SECRET=TEST_SECRET,
    RAZORPAY_WEBHOOK_SECRET=WEBHOOK_SECRET,
    ALLOW_MOCK_PAYMENTS=False,
    EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
)
class PaymentEndpointsAPITestCase(APITestCase):
    """HTTP surface: status polling endpoint ownership + webhook view."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="api@example.com", password="pass1234", name="API Member"
        )
        self.shift = Shift.objects.create(
            name="Evening", start_time="16:00", end_time="21:00", price=400
        )
        self.membership = Membership.objects.create(
            member=self.user, shift=self.shift, duration_months=1, amount=400
        )
        self.client.force_authenticate(self.user)

    def test_payment_status_endpoint_reports_pending(self):
        res = self.client.get(
            f"/api/v1/memberships/{self.membership.id}/payment_status/"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["payment_status"], "created")
        self.assertEqual(res.data["membership_status"], "pending_payment")
        self.assertFalse(res.data["activated"])

    def test_payment_status_is_owner_scoped(self):
        stranger = User.objects.create_user(
            email="stranger@example.com", password="pass1234", name="Stranger"
        )
        self.client.force_authenticate(stranger)
        res = self.client.get(
            f"/api/v1/memberships/{self.membership.id}/payment_status/"
        )
        self.assertEqual(res.status_code, 404)

    def test_webhook_view_accepts_valid_delivery(self):
        with mock.patch("apps.memberships.services._razorpay_client") as client:
            client.return_value.order.create.return_value = {"id": "order_api_1"}
            self.client.post(
                f"/api/v1/memberships/{self.membership.id}/create_payment_order/"
            )
        event = captured_event("order_api_1")
        body = json.dumps(event).encode()
        res = self.client.post(
            "/api/v1/memberships/webhooks/razorpay/",
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=webhook_signature(body),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "ok")
        payment = Payment.objects.get(membership=self.membership)
        self.assertEqual(payment.status, "paid")

    def test_webhook_view_rejects_bad_signature(self):
        res = self.client.post(
            "/api/v1/memberships/webhooks/razorpay/",
            data=b"{}",
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE="0" * 64,
        )
        self.assertEqual(res.status_code, 400)

    def test_webhook_view_works_unauthenticated(self):
        self.client.force_authenticate(None)
        res = self.client.post(
            "/api/v1/memberships/webhooks/razorpay/",
            data=json.dumps({"event": "ping"}).encode(),
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=webhook_signature(b'{"event": "ping"}'),
        )
        self.assertEqual(res.status_code, 200)
