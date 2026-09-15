from rest_framework import serializers

from apps.accounts.serializers import DataURLFileField
from apps.library.models import Seat, Shift
from apps.library.serializers import SeatSerializer, ShiftSerializer

from .models import DurationDiscount, Membership, Payment


class DurationDiscountSerializer(serializers.ModelSerializer):
    class Meta:
        model = DurationDiscount
        fields = ("min_months", "discount_percent", "is_active")


class PaymentSerializer(serializers.ModelSerializer):
    receipt_url = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = (
            "id", "razorpay_order_id", "razorpay_payment_id",
            "amount", "method", "status", "transaction_id", "receipt_url",
            "admin_note", "created_at", "paid_at",
        )

    def get_receipt_url(self, obj):
        request = self.context.get("request")
        if obj.receipt and request:
            return request.build_absolute_uri(obj.receipt.url)
        if obj.receipt:
            return obj.receipt.url
        return None


class ManualPaymentSubmitSerializer(serializers.Serializer):
    transaction_id = serializers.CharField(max_length=120, write_only=True)
    receipt = DataURLFileField(write_only=True)

    def validate_transaction_id(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Please enter the UPI transaction ID.")
        return value


class MembershipCreateSerializer(serializers.Serializer):
    shift = serializers.PrimaryKeyRelatedField(queryset=Shift.objects.all())
    seat = serializers.PrimaryKeyRelatedField(
        queryset=Seat.objects.all(), required=False, allow_null=True
    )
    plan_type = serializers.ChoiceField(
        choices=("daily", "weekly", "monthly"), default="monthly"
    )
    duration_months = serializers.IntegerField(min_value=1, max_value=12, default=1)
    is_premium = serializers.BooleanField(required=False, default=False)

    def validate_seat(self, seat):
        if seat and not seat.is_active:
            raise serializers.ValidationError("This seat is inactive.")
        return seat


class MembershipSerializer(serializers.ModelSerializer):
    shift = ShiftSerializer(read_only=True)
    seat = SeatSerializer(read_only=True)
    payment = PaymentSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = (
            "id", "shift", "seat", "plan_type", "duration_months", "is_premium",
            "discount_percent", "start_date", "end_date", "status", "payment_method",
            "cash_request_expires_at", "amount", "days_left", "created_at", "payment",
        )
        read_only_fields = fields


class MembershipAdminSerializer(serializers.ModelSerializer):
    member = serializers.SerializerMethodField()
    shift = ShiftSerializer(read_only=True)
    seat = SeatSerializer(read_only=True)
    payment = PaymentSerializer(read_only=True)
    member_name = serializers.CharField(source="member.name", read_only=True)
    notification_logs = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = (
            "id", "member", "member_name", "shift",
            "seat", "plan_type", "duration_months", "is_premium",
            "discount_percent", "start_date", "end_date", "status",
            "payment_method", "cash_request_expires_at", "amount",
            "days_left", "created_at", "payment", "notification_logs",
        )
        read_only_fields = ("id", "member", "amount", "created_at", "payment")

    def get_notification_logs(self, obj):
        logs = obj.notification_logs.order_by("sent_at")
        return [
            {"type": log.type, "channel": log.channel, "sent_at": log.sent_at}
            for log in logs
        ]

    def get_member(self, obj):
        request = self.context.get("request")
        member = obj.member
        aadhar_url = None
        if member.aadhar_document:
            aadhar_url = (
                request.build_absolute_uri(member.aadhar_document.url)
                if request
                else member.aadhar_document.url
            )
        return {
            "id": str(member.id),
            "name": member.name,
            "email": member.email,
            "phone": member.phone,
            "gender": member.gender,
            "aadhar_document_url": aadhar_url,
            "wifi_device_name": member.wifi_device_name,
            "ip_address": member.ip_address,
        }
