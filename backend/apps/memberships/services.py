"""Membership business logic: pricing, seat assignment, activation, payments.

Seat availability rule (§6 of the spec): a seat is available for a given
shift + date range when no other *active* membership occupies that seat with
an overlapping shift AND an overlapping date range. The same physical seat
may therefore be sold to different members for non-overlapping shifts.
"""
import hashlib
import hmac
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("libseat.memberships")

CASH_REQUEST_TTL = timedelta(days=3)


def amount_paise(amount) -> int:
    return int(round(float(amount) * 100))


def membership_amount(shift, months: int, plan_type: str = "monthly",
                      is_premium: bool = False, premium_extra=0):
    """Calculate price for a plan.

    Fixed daily/weekly prices come from PLAN_PRICES; monthly is
    ``shift.price * months``. A duration discount is applied for multi-month
    bookings (monthly plan only), then a premium surcharge is added when
    applicable.
    """
    from .models import PLAN_PRICES, get_discount_percent

    extra = Decimal(str(premium_extra or 0)) if is_premium else Decimal("0")
    if plan_type in PLAN_PRICES:
        base = Decimal(PLAN_PRICES[plan_type])
        if is_premium and extra:
            if plan_type == "daily":
                base += (extra / Decimal(30)).quantize(Decimal("1"))
            else:
                base += (extra * Decimal(7) / Decimal(30)).quantize(Decimal("1"))
        return base
    price = shift.price * Decimal(int(months))
    if is_premium and extra:
        price += extra * Decimal(int(months))
    discount_pct = get_discount_percent(months)
    if discount_pct > 0:
        discount = (price * discount_pct / Decimal(100)).quantize(Decimal("0.01"))
        price -= discount
    return price


def effective_premium(membership) -> bool:
    """Whether a membership is actually premium (chosen upgrade or premium seat)."""
    seat = membership.seat
    return bool(membership.is_premium or (seat is not None and seat.is_premium))


def recompute_membership_amount(membership):
    """Recalculate a membership's amount from its current seat/plan/premium state."""
    from .models import get_discount_percent

    seat = membership.seat
    premium = effective_premium(membership)
    extra = seat.premium_extra if (premium and seat is not None) else 0
    amount = membership_amount(
        membership.shift,
        membership.duration_months,
        membership.plan_type,
        is_premium=premium,
        premium_extra=extra,
    )
    discount = (
        get_discount_percent(membership.duration_months)
        if membership.plan_type == "monthly"
        else Decimal("0")
    )
    if membership.amount != amount or membership.discount_percent != discount:
        membership.amount = amount
        membership.discount_percent = discount
        membership.save(update_fields=["amount", "discount_percent"])
    return amount


def seat_is_available(seat, shift, start_date, end_date, exclude_membership=None, user=None):
    """True when no active membership *or* active seat booking blocks `seat`.

    Bookings (held/confirmed by someone else) lock the seat for the requested
    shift + date range, mirroring what the 3D map shows in real time.
    """
    from .models import Membership

    overlapping = Membership.objects.filter(
        seat=seat,
        status="active",
        start_date__lte=end_date,
        end_date__gte=start_date,
    ).select_related("shift")
    if exclude_membership:
        overlapping = overlapping.exclude(pk=exclude_membership.pk)
    for membership in overlapping:
        if membership.shift.overlaps(shift):
            return False

    from apps.seats.services import booking_blocks_seat

    if booking_blocks_seat(seat, shift, start_date, end_date, user=user):
        return False
    return True


def seats_availability(seats, shift, start_date, end_date, user=None):
    """Set-based ``available`` + ``held`` flags for a whole seat queryset.

    Replaces the per-seat ``seat_is_available``/``held_by_other`` loops (2-3
    queries per seat, each with a row lock on a read path) with two
    set-based queries, so the seat-map endpoint drops from ~111 queries to ~5.
    Semantics are identical to the per-seat helpers:

    - a seat is unavailable when an overlapping *active* membership on the
      same seat has an overlapping shift and date range (own memberships count
      too, matching the existing behaviour);
    - a seat is unavailable when someone else holds a live booking (held with
      ``held_until`` in the future) or has a confirmed booking for the slot.

    ``held`` is True only when another user is *currently holding* the seat.
    """
    from apps.seats.models import Booking
    from django.utils import timezone

    from .models import Membership

    now = timezone.now()
    seat_ids = [seat.id for seat in seats]
    available = {str(seat.id): True for seat in seats}
    held = {str(seat.id): False for seat in seats}

    overlapping = Membership.objects.filter(
        seat_id__in=seat_ids,
        status="active",
        start_date__lte=end_date,
        end_date__gte=start_date,
    ).values_list("seat_id", "shift__start_time", "shift__end_time")
    for seat_id, shift_start, shift_end in overlapping:
        if shift_start < shift.end_time and shift_end > shift.start_time:
            available[str(seat_id)] = False

    bookings = Booking.objects.filter(
        seat_id__in=seat_ids,
        shift__start_time__lt=shift.end_time,
        shift__end_time__gt=shift.start_time,
        start_date__lte=end_date,
        end_date__gte=start_date,
        status__in=("held", "confirmed"),
    ).values_list("seat_id", "status", "held_until")
    if user is not None and user.is_authenticated:
        bookings = bookings.exclude(user=user)
    for seat_id, booking_status, held_until in bookings:
        key = str(seat_id)
        if booking_status == "confirmed" or (
            booking_status == "held" and held_until and held_until > now
        ):
            available[key] = False
            if booking_status == "held":
                held[key] = True

    return available, held


def auto_assign_seat(membership):
    """Assign the first available seat matching the member's gender section."""
    from apps.library.models import Seat

    candidates = Seat.objects.filter(
        is_active=True, section__in=membership.member.allowed_sections
    ).order_by("seat_number")
    for seat in candidates:
        if seat_is_available(
            seat,
            membership.shift,
            membership.start_date,
            membership.end_date,
            exclude_membership=membership,
            user=membership.member,
        ):
            membership.seat = seat
            membership.save(update_fields=["seat"])
            return seat
    return None


def assign_seat(membership, seat):
    """Try to assign a specific seat; returns (ok, reason)."""
    from apps.library.models import Seat

    if not membership.start_date or not membership.end_date:
        membership.compute_dates()
    if not seat.is_active:
        return False, "This seat is inactive."
    if seat.section not in membership.member.allowed_sections:
        return False, "This seat is not in your section."
    if not seat_is_available(
        seat, membership.shift, membership.start_date, membership.end_date,
        exclude_membership=membership, user=membership.member,
    ):
        return False, "This seat is already taken for your shift and dates."
    membership.seat = seat
    membership.save(update_fields=["seat"])
    return True, ""


def activate_membership(membership):
    """Mark a membership active, compute dates and lock its seat.

    Any other active membership of the same member is superseded (cancelled)
    so a member never holds two live memberships at once.
    """
    if membership.status == "active":
        return membership

    membership.compute_dates()
    membership.status = "active"
    membership.save(update_fields=["start_date", "end_date", "status"])

    _supersede_prior_memberships(membership)

    if membership.seat_id:
        ok, _ = assign_seat(membership, membership.seat)
        if not ok:
            logger.info("member %s seat %s no longer available; auto-assigning",
                        membership.member_id, membership.seat_id)
            auto_assign_seat(membership)
    else:
        auto_assign_seat(membership)

    _send_confirmation(membership)
    _confirm_matching_booking(membership)
    return membership


def _confirm_matching_booking(membership):
    """Lock in the member's held booking once the seat is paid & active."""
    from apps.seats.services import confirm_for_membership

    try:
        confirm_for_membership(membership)
    except Exception:
        logger.exception("could not confirm booking for membership %s", membership.id)


def _release_membership_booking(membership):
    """Release any live seat hold tied to this membership's slot.

    Both ``held`` (live hold from checkout) and ``confirmed`` (locked in once
    the membership became active) bookings are cancelled. A confirmed booking
    would otherwise keep blocking the seat forever after the membership
    expires, gets superseded or is cancelled.
    """
    from apps.seats.models import Booking

    Booking.objects.filter(
        user=membership.member,
        seat=membership.seat,
        shift=membership.shift,
        start_date=membership.start_date,
        end_date=membership.end_date,
        status__in=("held", "confirmed"),
    ).update(status="cancelled", held_until=None)


def request_cash_payment(membership):
    """Switch a pending membership to a cash request.

    The seat stays held for 3 days (``CASH_REQUEST_TTL``) while the library
    confirms the cash payment. Only an admin approving the membership (or the
    member paying cash at the desk) converts it into an active pass.
    """
    from apps.seats.models import Booking
    from apps.seats.services import SeatHoldError, hold_seat

    membership.payment_method = "cash"
    membership.status = "pending_cash"
    membership.cash_request_expires_at = timezone.now() + CASH_REQUEST_TTL
    membership.save(
        update_fields=["payment_method", "status", "cash_request_expires_at"]
    )

    if membership.seat_id and membership.start_date and membership.end_date:
        booking = Booking.objects.filter(
            user=membership.member,
            seat=membership.seat,
            shift=membership.shift,
            start_date=membership.start_date,
            end_date=membership.end_date,
            status="held",
        ).first()
        if booking is None:
            try:
                booking = hold_seat(
                    membership.member,
                    membership.seat,
                    membership.shift,
                    membership.start_date,
                    membership.end_date,
                )
            except SeatHoldError:
                logger.warning(
                    "cash request %s could not re-hold seat %s",
                    membership.id,
                    membership.seat_id,
                )
                booking = None
        if booking is not None:
            booking.held_until = timezone.now() + CASH_REQUEST_TTL
            booking.save(update_fields=["held_until"])

    _send_cash_request_ack(membership)
    return membership


def expire_cash_requests():
    """Cancel cash requests not approved by the library within 3 days.

    Releases the held seat and marks the membership cancelled so the slot
    frees up for other members.
    """
    from .models import Membership

    now = timezone.now()
    stale = Membership.objects.filter(
        status="pending_cash",
        cash_request_expires_at__isnull=False,
        cash_request_expires_at__lte=now,
    )
    count = 0
    for membership in stale:
        _release_membership_booking(membership)
        membership.status = "cancelled"
        membership.cash_request_expires_at = None
        membership.save(update_fields=["status", "cash_request_expires_at"])
        count += 1
    if count:
        logger.info("expired %s cash request(s)", count)
    return count


def _send_cash_request_ack(membership):
    from apps.notifications.emails import build_cash_request_acknowledgement
    from apps.notifications.service import notify_membership

    try:
        subject, body, html = build_cash_request_acknowledgement(membership)
    except Exception:
        logger.exception("could not build cash-request ack for membership %s", membership.id)
        return
    notify_membership(
        membership,
        type_="cash_request",
        subject=subject,
        body=body,
        html=html,
    )


def _supersede_prior_memberships(membership):
    from .models import Membership

    prior = Membership.objects.filter(
        member=membership.member, status="active",
    ).exclude(pk=membership.pk).select_related("seat", "shift")
    for old in prior:
        _release_membership_booking(old)
    prior.update(status="cancelled")


def _send_confirmation(membership):
    from apps.notifications.emails import build_membership_confirmation
    from apps.notifications.service import notify_membership

    try:
        subject, body, html = build_membership_confirmation(membership)
    except Exception:
        logger.exception("could not build confirmation email for membership %s", membership.id)
        return
    notify_membership(
        membership,
        type_="confirmation",
        subject=subject,
        body=body,
        html=html,
    )


# ----------------------------------------------------------------- Payments

class PaymentGatewayError(Exception):
    """The external payment gateway rejected or failed to answer a request."""

    def __init__(self, message="The payment gateway is temporarily unavailable."):
        self.message = message
        super().__init__(message)


class WebhookSignatureError(Exception):
    """A webhook delivery failed HMAC validation."""


RAZORPAY_TIMEOUT_SECONDS = 30
# Live status sync must stay fast enough to answer inside a normal request.
RAZORPAY_STATUS_TIMEOUT_SECONDS = 8


def razorpay_configured() -> bool:
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def _razorpay_client():
    import razorpay

    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def schedule_activation(membership_id) -> None:
    """Queue membership activation on a background worker when available.

    With Celery configured the heavy work (seat assignment, superseding old
    passes, emails) leaves the request path entirely; without a broker the
    caller is expected to run it inline so free-tier behaviour is unchanged.
    """
    from .tasks import activate_membership_task

    if getattr(settings, "USE_CELERY", False):
        activate_membership_task.delay(str(membership_id))


def activate_after_payment(membership):
    """Run activation inline with a guaranteed background retry safety net.

    The payment itself is already committed as paid before this runs, so a
    failure here can never lose money state — only the seat/email side effects,
    which the Celery task (or admin override) recovers.
    """
    try:
        return activate_membership(membership)
    except Exception:
        logger.exception(
            "activation_after_payment membership=%s failed; scheduling retry",
            membership.id,
        )
        schedule_activation(membership.id)
        membership.refresh_from_db()
        return membership


def create_payment_order(membership):
    """Create a Razorpay order (or a dev mock when unconfigured).

    Concurrency-safe: the Payment row is locked while deciding whether a
    gateway order already exists, and the Razorpay API call happens *outside*
    the transaction so no row lock is ever held across a network call. A lost
    race between two simultaneous requests converges on one order id instead
    of creating duplicate gateway orders. Never raises: gateway failures
    surface as ``PaymentGatewayError`` so the view can answer 502 not 500.
    """
    from django.db import transaction

    from .models import Payment

    payment = Payment.objects.filter(membership=membership).first()
    if payment is None:
        try:
            payment = Payment.objects.create(
                membership=membership, amount=membership.amount, method="upi"
            )
        except Exception:
            # Concurrent first-click already created it — fetch the winner.
            payment = Payment.objects.get(membership=membership)

    if payment.status == "paid":
        logger.info(
            "payment_order membership=%s user=%s amount=%s already_paid",
            membership.id, membership.member.email, membership.amount,
        )
        return {"already_paid": True}

    with transaction.atomic():
        locked = Payment.objects.select_for_update().get(pk=payment.pk)
        if locked.status == "paid":
            logger.info(
                "payment_order membership=%s user=%s already_paid_locked",
                membership.id, membership.member.email,
            )
            return {"already_paid": True}
        order_id = locked.razorpay_order_id or None

    created_new_order = False
    if order_id is None:
        # Network call deliberately outside any atomic block / row lock.
        order_id = _razorpay_create_order(membership)
        created_new_order = True

    if created_new_order:
        with transaction.atomic():
            locked = Payment.objects.select_for_update().get(pk=payment.pk)
            if locked.razorpay_order_id and locked.razorpay_order_id != order_id:
                # Another request won the race; keep its order so checkout and
                # verification always reference the single gateway order.
                logger.warning(
                    "payment_order membership=%s concurrent_order kept=%s dropped=%s",
                    membership.id, locked.razorpay_order_id, order_id,
                )
                order_id = locked.razorpay_order_id
            else:
                locked.razorpay_order_id = order_id
                locked.transition_to("created")
                locked.save(update_fields=["razorpay_order_id", "status"])
        logger.info(
            "payment_order membership=%s user=%s amount=%s order=%s status=created",
            membership.id, membership.member.email, membership.amount, order_id,
        )
    else:
        logger.info(
            "payment_order membership=%s user=%s amount=%s order=%s status=reused",
            membership.id, membership.member.email, membership.amount, order_id,
        )

    return {
        "membership_id": str(membership.id),
        "order_id": order_id,
        "key_id": settings.RAZORPAY_KEY_ID,
        "amount": amount_paise(membership.amount),
        "currency": "INR",
        "requires_remote": razorpay_configured(),
        "mock": not razorpay_configured(),
    }


def _razorpay_create_order(membership):
    """Create an order at Razorpay. Returns the gateway order id.

    Raises PaymentGatewayError on any gateway/network failure so callers can
    answer 502. Never logs API credentials.
    """
    if not razorpay_configured():
        return "mock_order_" + str(membership.id).replace("-", "")

    client = _razorpay_client()
    payload = {
        "amount": amount_paise(membership.amount),
        "currency": "INR",
        "receipt": f"LS-{str(membership.id)[:8]}",
        "payment_capture": 1,
        "notes": {"membership_id": str(membership.id)},
    }
    try:
        order = client.order.create(payload, timeout=RAZORPAY_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.exception(
            "razorpay_order membership=%s user=%s amount=%s status=gateway_error",
            membership.id, membership.member.email, membership.amount,
        )
        raise PaymentGatewayError(
            "The payment gateway is temporarily unavailable. Please try again."
        ) from exc

    order_id = order.get("id") if isinstance(order, dict) else None
    if not order_id:
        logger.error(
            "razorpay_order membership=%s user=%s amount=%s status=missing_order_id response=%s",
            membership.id, membership.member.email, membership.amount,
            {k: v for k, v in order.items() if k in ("id", "status", "amount", "currency")}
            if isinstance(order, dict) else type(order).__name__,
        )
        raise PaymentGatewayError(
            "The payment gateway returned an invalid response. Please try again."
        )
    return order_id


def verify_payment_signature(order_id, payment_id, signature):
    secret = settings.RAZORPAY_KEY_SECRET
    if not secret:
        return False
    message = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """Validate the X-Razorpay-Signature header of a webhook delivery."""
    secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def mark_payment_captured(payment, payment_id="", signature="", source="verify"):
    """Flip a payment to `paid` exactly once, under a row lock.

    Returns True when this call performed the transition; False when another
    request/webhook got there first (or the transition is not allowed).
    Callers must wrap this in their own transaction.atomic().
    """
    from .models import Payment

    locked = Payment.objects.select_for_update().select_related("membership").get(pk=payment.pk)
    if locked.status == "paid":
        if payment_id and not locked.razorpay_payment_id:
            locked.razorpay_payment_id = payment_id
            locked.save(update_fields=["razorpay_payment_id"])
        return False
    if not locked.transition_to("paid"):
        logger.warning(
            "payment_capture_refused payment=%s from=%s source=%s",
            locked.pk, locked.status, source,
        )
        return False
    if payment_id:
        locked.razorpay_payment_id = payment_id
    if signature:
        locked.razorpay_signature = signature
    locked.paid_at = timezone.now()
    locked.save(update_fields=["status", "razorpay_payment_id", "razorpay_signature", "paid_at"])
    logger.info(
        "payment_captured payment=%s membership=%s source=%s",
        locked.pk, locked.membership_id, source,
    )
    return True


def verify_and_activate(membership, payment_id, signature, order_id=None):
    """Verify the Razorpay signature, then activate the membership.

    Idempotent and concurrency-safe: the money-state flip happens under a row
    lock inside one short transaction; the heavy activation work runs after
    commit so no DB lock is held during seat assignment or email dispatch.

    Returns the (possibly just-activated) membership, or None when the
    signature check fails / the callback contradicts the stored order.
    """
    from .models import Payment
    from django.db import transaction

    with transaction.atomic():
        payment = (
            Payment.objects.select_for_update()
            .filter(membership=membership)
            .first()
        )
        if payment is None:
            payment = Payment.objects.create(
                membership=membership, amount=membership.amount, method="upi"
            )
            payment = Payment.objects.select_for_update().get(pk=payment.pk)

        if payment.status == "paid":
            # Browser refresh / retry after success — never re-process.
            logger.info(
                "payment_verify membership=%s already_paid idempotent_noop", membership.id
            )
            return membership

        stored_order = payment.razorpay_order_id or (
            "mock_order_" + str(membership.id).replace("-", "")
        )
        if order_id and payment.razorpay_order_id and order_id != payment.razorpay_order_id:
            # Checkout response for a different order — possible tampering.
            logger.error(
                "payment_verify membership=%s order_mismatch stored=%s got=%s",
                membership.id, payment.razorpay_order_id, order_id,
            )
            return None

        razorpay_ready = razorpay_configured()
        mock_payment = settings.ALLOW_MOCK_PAYMENTS and not razorpay_ready

        if not verify_payment_signature(stored_order, payment_id, signature):
            if not mock_payment:
                logger.warning(
                    "payment_verify membership=%s invalid_signature", membership.id
                )
                if payment.transition_to("failed"):
                    payment.save(update_fields=["status"])
                return None
            signature = signature or "mock_signature"

        if not mark_payment_captured(payment, payment_id, signature, source="verify"):
            return membership.refresh_from_db() or membership

    membership.refresh_from_db()
    return activate_after_payment(membership)


def sync_payment_with_razorpay(payment) -> bool:
    """Ask Razorpay for the live state of an unsettled order (recovery path).

    Used by the payment-status endpoint after a frontend timeout. Returns True
    when the payment was newly captured as a result. Never raises.
    """
    if not (razorpay_configured() and payment.razorpay_order_id):
        return False
    if payment.status in ("paid", "refunded"):
        return False

    client = _razorpay_client()
    try:
        payments = client.order.payments(
            payment.razorpay_order_id, timeout=RAZORPAY_STATUS_TIMEOUT_SECONDS
        )
    except Exception:
        logger.warning(
            "razorpay_status_sync payment=%s order=%s unreachable",
            payment.pk, payment.razorpay_order_id,
        )
        return False

    captured = None
    for item in payments if isinstance(payments, list) else []:
        status = (item or {}).get("status")
        if status == "captured":
            captured = item
            break
    if captured is None:
        return False

    from django.db import transaction

    with transaction.atomic():
        changed = mark_payment_captured(
            payment, captured.get("id", ""), "", source="status_sync"
        )
    if changed:
        activate_after_payment(payment.membership)
    return changed


def payment_status_report(membership, refresh=False):
    """Clean, owner-safe payment status for polling endpoints."""
    payment = getattr(membership, "payment", None)
    if refresh and payment is not None:
        sync_payment_with_razorpay(payment)
        membership.refresh_from_db()

    payment = getattr(membership, "payment", None)
    return {
        "payment_status": payment.status if payment else "created",
        "membership_status": membership.status,
        "activated": membership.status == "active",
    }


def process_webhook_event(raw_body: bytes, signature: str) -> str:
    """Handle one Razorpay webhook delivery: validate → dedupe → act.

    Idempotent: deliveries are keyed by `<event>:<entity id>` in WebhookEvent;
    replays short-circuit at the database level, and every business action is
    additionally guarded by the Payment state machine. Heavy activation work
    is queued to Celery when available so this returns almost immediately.
    """
    import json

    from django.db import transaction

    from .models import WebhookEvent

    if not verify_webhook_signature(raw_body, signature):
        logger.warning("webhook_rejected reason=invalid_signature")
        raise WebhookSignatureError()

    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        logger.warning("webhook_rejected reason=malformed_json")
        raise WebhookSignatureError()

    event_type = str(event.get("event", ""))
    payload = event.get("payload") or {}
    payment_entity = (payload.get("payment") or {}).get("entity") or {}
    refund_entity = (payload.get("refund") or {}).get("entity") or {}
    entity_key = payment_entity.get("id") or refund_entity.get("id") or ""
    dedupe_key = f"{event_type}:{entity_key}"[:120]

    # Insert-first idempotency: the PK collision is what stops duplicates.
    webhook_event, created = WebhookEvent.objects.get_or_create(
        id=dedupe_key,
        defaults={
            "event_type": event_type,
            "payload": {"event": event_type, "created_at": event.get("created_at")},
        },
    )
    if not created and webhook_event.processed:
        logger.info("webhook_duplicate key=%s ignored", dedupe_key)
        return "duplicate"

    outcome = "ignored"
    if event_type in ("payment.captured", "order.paid"):
        outcome = _webhook_handle_captured(payment_entity)
    elif event_type == "payment.authorized":
        outcome = _webhook_handle_authorized(payment_entity)
    elif event_type == "payment.failed":
        outcome = _webhook_handle_failed(payment_entity)
    elif event_type.startswith("refund."):
        outcome = _webhook_handle_refund(payment_entity)

    webhook_event.processed = True
    webhook_event.save(update_fields=["processed"])
    logger.info("webhook_processed key=%s outcome=%s", dedupe_key, outcome)
    return outcome


def _payment_by_gateway_ids(entity):
    from .models import Payment

    order_id = entity.get("order_id") or ""
    payment_id = entity.get("id") or ""
    qs = Payment.objects.select_related("membership")
    if order_id:
        return qs.filter(razorpay_order_id=order_id).first(), payment_id
    if payment_id:
        return qs.filter(razorpay_payment_id=payment_id).first(), payment_id
    return None, payment_id


def _webhook_handle_captured(entity):
    from django.db import transaction

    from .models import Payment

    payment, payment_id = _payment_by_gateway_ids(entity)
    if payment is None:
        logger.warning("webhook_captured_unknown_order order=%s", entity.get("order_id"))
        return "unknown_order"

    expected_paise = amount_paise(payment.amount)
    received_paise = int(entity.get("amount") or 0)
    if received_paise and received_paise != expected_paise:
        logger.error(
            "webhook_amount_mismatch payment=%s expected=%s received=%s",
            payment.pk, expected_paise, received_paise,
        )

    with transaction.atomic():
        changed = mark_payment_captured(payment, payment_id, "", source="webhook")
    if changed:
        membership = payment.membership
        if getattr(settings, "USE_CELERY", False):
            schedule_activation(membership.id)
        else:
            activate_after_payment(membership)
    return "captured" if changed else "already_paid"


def _webhook_handle_authorized(entity):
    from django.db import transaction

    from .models import Payment

    payment, payment_id = _payment_by_gateway_ids(entity)
    if payment is None:
        return "unknown_order"
    with transaction.atomic():
        locked = Payment.objects.select_for_update().get(pk=payment.pk)
        if locked.transition_to("authorized"):
            if payment_id and not locked.razorpay_payment_id:
                locked.razorpay_payment_id = payment_id
            locked.save(update_fields=["status", "razorpay_payment_id"])
    return "authorized"


def _webhook_handle_failed(entity):
    from django.db import transaction

    from .models import Payment

    payment, _ = _payment_by_gateway_ids(entity)
    if payment is None:
        return "unknown_order"
    with transaction.atomic():
        locked = Payment.objects.select_for_update().get(pk=payment.pk)
        if locked.transition_to("failed"):
            locked.save(update_fields=["status"])
            logger.info("webhook_failed payment=%s marked_failed", locked.pk)
    return "failed"


def _webhook_handle_refund(entity):
    from django.db import transaction

    from .models import Payment

    payment, _ = _payment_by_gateway_ids(entity)
    if payment is None:
        return "unknown_order"
    with transaction.atomic():
        locked = Payment.objects.select_for_update().get(pk=payment.pk)
        if locked.transition_to("refunded"):
            locked.save(update_fields=["status"])
            logger.info("webhook_refund payment=%s refunded", locked.pk)
    return "refunded"


def expire_overdue_memberships():
    """Mark active memberships past their end_date as expired."""
    from .models import Membership

    today = timezone.localdate()
    expired = Membership.objects.filter(
        status="active", end_date__lt=today
    ).select_related("seat", "shift")
    count = 0
    for membership in expired:
        _release_membership_booking(membership)
        membership.status = "expired"
        membership.save(update_fields=["status"])
        count += 1
    return count


# --------------------------------------------------------- Reminder cycle

def run_reminder_cycle():
    """Daily scheduled job (Celery beat or cron).

    - expires memberships past their end date
    - sends renewal reminders before expiry, each exactly once:
        * expiry_warning (7 days out) — window 7..4 days so a missed run
          can't silently drop the notice;
        * reminder_3day — window 3..2 days;
        * reminder_1day — on the final day.
      Deduping is per type in NotificationLog, so running the job any number
      of times a day (free-host friendly) never duplicates emails; only a run
      that picks up the note inside its window delivers it.
    """
    from apps.notifications.models import NotificationLog

    from .models import Membership

    expired = expire_overdue_memberships()
    cash_expired = expire_cash_requests()
    today = timezone.localdate()
    warnings_sent = reminders_sent = 0

    active = (
        Membership.objects.filter(status="active")
        .select_related("member", "shift")
    )
    for membership in active:
        # Day passes expire the same day and do not need renewal reminders.
        if membership.end_date == membership.start_date:
            continue
        days_left = (membership.end_date - today).days
        if days_left <= 0:
            continue

        if not NotificationLog.objects.filter(
            membership=membership, type="expiry_warning"
        ).exists() and 4 <= days_left <= 7:
            _send_reminder(membership, "expiry_warning")
            warnings_sent += 1

        if not NotificationLog.objects.filter(
            membership=membership, type="reminder_3day"
        ).exists() and 2 <= days_left <= 3:
            _send_reminder(membership, "reminder_3day")
            reminders_sent += 1

        if not NotificationLog.objects.filter(
            membership=membership, type="reminder_1day"
        ).exists() and days_left == 1:
            _send_reminder(membership, "reminder_1day")
            reminders_sent += 1

    return {
        "expired": expired,
        "cash_expired": cash_expired,
        "warnings_sent": warnings_sent,
        "reminders_sent": reminders_sent,
    }


def _send_reminder(membership, type_):
    from apps.notifications.emails import build_membership_reminder
    from apps.notifications.service import notify_membership

    subject, body, html = build_membership_reminder(membership, type_)
    notify_membership(membership, type_=type_, subject=subject, body=body, html=html)


def serialize_amount(amount) -> float:
    return float(Decimal(str(amount)))
