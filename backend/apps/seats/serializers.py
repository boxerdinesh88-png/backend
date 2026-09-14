from rest_framework import serializers

from apps.library.models import Seat, Shift
from apps.library.serializers import SeatSerializer, ShiftSerializer

from .models import Booking


class HoldSerializer(serializers.Serializer):
    seat = serializers.PrimaryKeyRelatedField(queryset=Seat.objects.all())
    shift = serializers.PrimaryKeyRelatedField(queryset=Shift.objects.all())
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)

    def validate(self, attrs):
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": "end_date must be on or after start_date."}
            )
        return attrs


class BookingSerializer(serializers.ModelSerializer):
    seat = SeatSerializer(read_only=True)
    shift = ShiftSerializer(read_only=True)
    expires_at = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = (
            "id", "seat", "shift", "start_date", "end_date", "status",
            "held_until", "expires_at", "created_at",
        )
        read_only_fields = fields

    def get_expires_at(self, obj):
        return obj.held_until if obj.status == "held" else None
