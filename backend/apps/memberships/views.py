import csv
import logging
from datetime import date

from django.db.models import Q
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import error_response
from apps.core.permissions import IsAdmin
from apps.library.models import Seat, Shift

from .models import DurationDiscount, Membership, PaymentSettings, get_discount_percent, plan_duration
from .serializers import (
    DurationDiscountSerializer,
    ManualPaymentSubmitSerializer,
    MembershipAdminSerializer,
    MembershipCreateSerializer,
    MembershipSerializer,
)
from .services import (
    _release_membership_booking,
    PaymentGatewayError,
    WebhookSignatureError,
    active_running_membership,
    create_payment_order,
    membership_amount,
    payment_status_report,
    process_webhook_event,
    request_cash_payment,
    request_manual_payment,
    seat_is_available,
    verify_and_activate,
)

logger = logging.getLogger("libseat.memberships")


class AdminDiscountViewSet(viewsets.ModelViewSet):
    """Admin CRUD for duration-discount tiers."""

    permission_classes = (IsAdmin,)
    serializer_class = DurationDiscountSerializer
    lookup_field = "min_months"
    queryset = DurationDiscount.objects.all().order_by("min_months")


class MembershipViewSet(viewsets.GenericViewSet):
    """Member-facing membership lifecycle."""

    permission_classes = (IsAuthenticated,)
    serializer_class = MembershipSerializer

    def get_queryset(self):
        # Schema generation runs without a real request; self.request.user is
        # then an AnonymousUser whose pk is not a valid UUID and would crash.
        if getattr(self, "swagger_fake_view", False):
            return Membership.objects.none()
        return Membership.objects.filter(member=self.request.user).select_related("shift", "seat", "seat__zone", "payment")

    def get_object(self):
        qs = self.get_queryset()
        obj = qs.filter(pk=self.kwargs["pk"]).first()
        if not obj and self.request.user.is_admin:
            obj = Membership.objects.select_related("shift", "seat", "seat__zone", "payment").filter(
                pk=self.kwargs["pk"]
            ).first()
        if not obj:
            from rest_framework.exceptions import NotFound

            raise NotFound("Membership not found.")
        return obj

    def list(self, request):
        memberships = self.get_queryset()
        return Response(MembershipSerializer(memberships, many=True).data)

    def retrieve(self, request, pk=None):
        membership = self.get_object()
        return Response(MembershipSerializer(membership).data)

    @action(detail=False, methods=["get"])
    def my(self, request):
        memberships = self.get_queryset()
        return Response(MembershipSerializer(memberships, many=True).data)

    def create(self, request):
        serializer = MembershipCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Please fix the highlighted fields.",
                code="validation_error",
                fields=serializer.errors,
            )
        data = serializer.validated_data
        shift = data["shift"]
        if not shift.is_active:
            return error_response("Invalid or inactive shift.", code="invalid_shift")

        plan_type = data.get("plan_type", "monthly")
        months = data.get("duration_months", 1) if plan_type == "monthly" else 1
        is_renewal = bool(data.get("renew", False))

        start_date = date.today()
        end_date = start_date + plan_duration(plan_type, months)
        # "Renew / extend" on the same time block adds that pass's leftover
        # days; a plain "New membership" — and a renewal of any other block —
        # always starts fresh. A member can hold several passes at once, one
        # per time block, so any block can be picked without error; a new pass
        # simply replaces an earlier pass on that same block once it is paid.
        if is_renewal:
            carry = active_running_membership(request.user, shift=shift)
            if carry and carry.end_date and carry.end_date > start_date:
                end_date += carry.end_date - start_date

        seat = data.get("seat")
        if seat:
            ok, reason = _check_seat(seat, shift, start_date, end_date, user=request.user)
            if not ok:
                return error_response(reason, code="seat_unavailable")

        # A member never keeps stale unpaid drafts around.
        stale = Membership.objects.filter(
            member=request.user, status__in=("pending_payment", "pending_cash", "pending_approval")
        )
        for membership in stale:
            _release_membership_booking(membership)
        stale.update(status="cancelled")

        is_premium = bool(data.get("is_premium", False)) or bool(seat and seat.is_premium)
        discount_percent = get_discount_percent(months)
        amount = membership_amount(
            shift, months, plan_type,
            is_premium=is_premium,
            premium_percent=seat.premium_percent if seat else 0,
        )
        membership = Membership.objects.create(
            member=request.user,
            shift=shift,
            seat=seat,
            plan_type=plan_type,
            duration_months=months,
            is_premium=is_premium,
            is_renewal=is_renewal,
            discount_percent=discount_percent,
            amount=amount,
            start_date=start_date,
            end_date=end_date,
        )
        return Response(
            MembershipSerializer(membership).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def create_payment_order(self, request, pk=None):
        membership = self.get_object()
        if membership.status != "pending_payment":
            return error_response(
                "Membership is not awaiting payment.", code="bad_state",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        logger.info(
            "payment_order_start membership=%s user=%s amount=%s",
            membership.id, request.user.email, membership.amount,
        )
        try:
            order = create_payment_order(membership)
        except PaymentGatewayError as exc:
            return error_response(
                exc.message, code="payment_gateway_error",
                status_code=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(order)

    @action(detail=True, methods=["post"])
    def verify_payment(self, request, pk=None):
        membership = self.get_object()
        if membership.status != "pending_payment":
            return error_response(
                "Membership is not awaiting payment.", code="bad_state"
            )
        payment_id = request.data.get("razorpay_payment_id", "")
        signature = request.data.get("razorpay_signature", "")
        order_id = request.data.get("razorpay_order_id", "")
        if not payment_id:
            return error_response(
                "razorpay_payment_id is required.", code="missing_payment_id"
            )
        activated = verify_and_activate(
            membership, payment_id, signature, order_id=order_id
        )
        if activated is None:
            return error_response(
                "Payment verification failed.", code="payment_failed",
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
            )
        if activated.status == "active":
            message = "Payment verified. Membership activated."
        else:
            message = (
                "Payment confirmed. Activation is being processed — "
                "check your pass in a moment."
            )
        return Response(
            {
                "membership": MembershipSerializer(activated).data,
                "message": message,
            }
        )

    @action(detail=True, methods=["get"])
    def payment_status(self, request, pk=None):
        """Pollable payment/membership status for checkout recovery.

        `?refresh=1` additionally asks Razorpay for the live order state, so a
        payment that succeeded despite a dropped verify callback self-heals.
        """
        membership = self.get_object()
        refresh = str(request.query_params.get("refresh", "")).lower() in ("1", "true")
        report = payment_status_report(membership, refresh=refresh)
        return Response(report)

    @action(detail=True, methods=["post"])
    def request_cash(self, request, pk=None):
        membership = self.get_object()
        if membership.status != "pending_payment":
            return error_response(
                "Membership is not awaiting payment.", code="bad_state"
            )
        if membership.payment_method == "cash":
            return error_response(
                "A cash request already exists for this membership.", code="bad_state"
            )
        request_cash_payment(membership)
        return Response(MembershipSerializer(membership).data)

    @action(detail=True, methods=["post"])
    def submit_manual_payment(self, request, pk=None):
        membership = self.get_object()
        if membership.status != "pending_payment":
            return error_response(
                "Membership is not awaiting payment.", code="bad_state"
            )
        if membership.payment_method == "manual":
            return error_response(
                "A manual payment is already submitted for this membership.",
                code="bad_state",
            )
        serializer = ManualPaymentSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Please fix the highlighted fields.",
                code="validation_error",
                fields=serializer.errors,
            )
        receipt = serializer.validated_data["receipt"]
        if getattr(receipt, "size", 0) > 3 * 1024 * 1024:
            return error_response(
                "Receipt screenshot must be under 3 MB.", code="receipt_too_large"
            )
        request_manual_payment(
            membership,
            serializer.validated_data["transaction_id"],
            receipt,
        )
        return Response(MembershipSerializer(membership).data)

    @action(detail=True, methods=["post"])
    def select_seat(self, request, pk=None):
        membership = self.get_object()
        if membership.status not in ("pending_payment", "active"):
            return error_response(
                "Seat can only be chosen for a pending or active membership.",
                code="bad_state",
            )
        seat_id = request.data.get("seat_id")
        seat = Seat.objects.filter(pk=seat_id).first()
        if not seat:
            return error_response("Invalid seat.", code="invalid_seat")
        if not membership.start_date or not membership.end_date:
            membership.compute_dates()
        ok, reason = _check_seat(
            seat, membership.shift, membership.start_date, membership.end_date,
            exclude=membership, user=request.user,
        )
        if not ok:
            return error_response(reason, code="seat_unavailable")
        membership.seat = seat
        membership.save(update_fields=["seat"])
        from .services import recompute_membership_amount

        recompute_membership_amount(membership)
        return Response(MembershipSerializer(membership).data)


class DurationDiscountView(APIView):
    """Public list of active duration-discount tiers (used for pricing display)."""

    permission_classes = (AllowAny,)
    authentication_classes = ()

    def get(self, request):
        tiers = DurationDiscount.objects.filter(is_active=True).order_by("min_months")
        return Response(DurationDiscountSerializer(tiers, many=True).data)


class PaymentSettingsView(APIView):
    """Public QR/manual UPI payment details shown on the checkout screen.

    `is_active` is only true when the library has configured a UPI id and QR
    image and enabled the setting; otherwise the member UI falls back to cash.
    """

    permission_classes = (AllowAny,)
    authentication_classes = ()

    def get(self, request):
        settings = PaymentSettings.get_singleton()
        configured = bool(settings.upi_id and settings.qr_image)
        return Response({
            "upi_id": settings.upi_id,
            "upi_name": settings.upi_name,
            "qr_image": (
                request.build_absolute_uri(settings.qr_image.url)
                if settings.qr_image else None
            ),
            "bank_account_number": settings.bank_account_number,
            "bank_ifsc": settings.bank_ifsc,
            "bank_name": settings.bank_name,
            "is_active": settings.is_active and configured,
        })


class RazorpayWebhookView(APIView):
    """Server-to-server Razorpay webhook — the independent confirmation path.

    Deliberately unauthenticated and unthrottled: Razorpay cannot log in, and
    throttling deliveries would silently drop payment confirmations. Security
    comes from the HMAC-SHA256 signature over the raw request body.
    """

    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = ()
    # Raw body is required for signature verification — no DRF parsing.
    parser_classes = ()

    def post(self, request):
        raw_body = request.body
        signature = request.headers.get("X-Razorpay-Signature", "")
        try:
            process_webhook_event(raw_body, signature)
        except WebhookSignatureError:
            logger.warning("webhook_rejected ip=%s", request.META.get("REMOTE_ADDR"))
            return error_response(
                "Invalid webhook signature.", code="invalid_signature",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            # 500 makes Razorpay retry the delivery later.
            logger.exception("razorpay_webhook processing error")
            return Response({"status": "error"}, status=500)
        return Response({"status": "ok"})


def _check_seat(seat, shift, start_date, end_date, exclude=None, user=None):
    if not seat.is_active:
        return False, "This seat is inactive."
    if user and seat.section not in user.allowed_sections:
        return False, "This seat is outside your section."
    if not seat_is_available(
        seat, shift, start_date, end_date, exclude_membership=exclude, user=user
    ):
        return False, "This seat is already taken for your shift and dates."
    return True, ""


class AdminMembershipViewSet(viewsets.ModelViewSet):
    """Admin management: list/filter all memberships, override status/seat."""

    permission_classes = (IsAdmin,)
    serializer_class = MembershipAdminSerializer
    queryset = Membership.objects.select_related(
        "member", "shift", "seat", "seat__zone", "payment"
    ).all()

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        status_filter = params.get("status")
        shift = params.get("shift")
        search = params.get("search")
        if status_filter:
            statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
            qs = qs.filter(status__in=statuses)
        if shift:
            qs = qs.filter(shift_id=shift)
        if search:
            qs = qs.filter(
                Q(member__name__icontains=search) | Q(member__email__icontains=search)
            )
        return qs

    def partial_update(self, request, *args, **kwargs):
        membership = self.get_object()
        data = request.data

        seat_id = data.get("seat_id", "keep")
        if seat_id is not None and seat_id != "keep":
            if seat_id == "":
                membership.seat = None
                membership.save(update_fields=["seat"])
            else:
                seat = Seat.objects.filter(pk=seat_id).first()
                if not seat:
                    return error_response("Invalid seat.", code="invalid_seat")
                ok, reason = _check_seat(
                    seat, membership.shift, membership.start_date, membership.end_date,
                    exclude=membership,
                )
                if not ok:
                    return error_response(reason, code="seat_unavailable")
                membership.seat = seat
                membership.save(update_fields=["seat"])

        if "status" in data and data["status"] != membership.status:
            new_status = data["status"]
            if new_status not in ("active", "expired", "cancelled", "pending_payment"):
                return error_response("Invalid status.", code="invalid_status")
            if new_status == "active":
                from .services import activate_membership

                activate_membership(membership)
            else:
                if new_status in ("expired", "cancelled", "pending_payment"):
                    _release_membership_booking(membership)
                membership.status = new_status
                membership.save(update_fields=["status"])

        serializer = MembershipAdminSerializer(membership, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        from .services import recompute_membership_amount

        recompute_membership_amount(membership)
        return Response(MembershipAdminSerializer(membership).data)

    @action(detail=True, methods=["post"])
    def approve_payment(self, request, pk=None):
        """Approve a cash or QR/manual payment review and activate the pass."""
        membership = self.get_object()
        if membership.status not in ("pending_cash", "pending_approval"):
            return error_response(
                "This membership is not awaiting payment approval.",
                code="bad_state",
            )
        from .services import approve_pending_payment

        approve_pending_payment(membership)
        return Response(MembershipAdminSerializer(membership).data)

    @action(detail=True, methods=["post"])
    def reject_payment(self, request, pk=None):
        """Reject a cash or QR/manual payment review.

        Optionally pass a `reason` (shown in the member-facing email). The
        membership is cancelled and the held seat released.
        """
        membership = self.get_object()
        if membership.status not in ("pending_cash", "pending_approval"):
            return error_response(
                "This membership is not awaiting payment approval.",
                code="bad_state",
            )
        from .services import reject_pending_payment

        reason = request.data.get("reason", "") or ""
        reject_pending_payment(membership, reason)
        return Response(MembershipAdminSerializer(membership).data)

    @action(detail=False, methods=["get"])
    def export(self, request):
        memberships = self.get_queryset().order_by("-created_at")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="memberships.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "membership_id", "member_name", "email", "phone", "gender",
            "wifi_device_name", "ip_address",
            "shift", "plan_type", "duration_months", "seat", "start_date", "end_date",
            "status", "amount", "payment_status", "created_at",
        ])
        for m in memberships:
            writer.writerow([
                m.id, m.member.name, m.member.email, m.member.phone, m.member.gender,
                m.member.wifi_device_name, m.member.ip_address,
                m.shift.name, m.get_plan_type_display(), m.duration_months,
                m.seat.seat_number if m.seat else "",
                m.start_date, m.end_date, m.status, m.amount,
                m.payment.status if hasattr(m, "payment") else "",
                m.created_at,
            ])
        return response
