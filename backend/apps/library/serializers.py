from rest_framework import serializers

from .models import Seat, Section, Shift


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ("id", "code", "name", "description", "sort_order")


class ShiftSerializer(serializers.ModelSerializer):
    start_time = serializers.TimeField(format="%H:%M")
    end_time = serializers.TimeField(format="%H:%M")

    class Meta:
        model = Shift
        fields = ("id", "name", "start_time", "end_time", "price", "is_active")


class SeatSerializer(serializers.ModelSerializer):
    available = serializers.SerializerMethodField()
    selectable = serializers.SerializerMethodField()
    held = serializers.SerializerMethodField()
    zone = SectionSerializer(read_only=True)

    class Meta:
        model = Seat
        fields = (
            "id", "seat_number", "section", "zone", "grid_col", "grid_row",
            "is_girls_only", "is_premium", "premium_extra", "is_active",
            "available", "selectable", "held",
        )
        read_only_fields = ("id",)

    def get_available(self, obj):
        context = getattr(self, "context", {})
        value = context.get("available")
        if isinstance(value, dict):
            return value.get(str(obj.id), True)
        return True

    def get_selectable(self, obj):
        context = getattr(self, "context", {})
        value = context.get("selectable")
        if isinstance(value, dict):
            return value.get(str(obj.id), True)
        return True

    def get_held(self, obj):
        context = getattr(self, "context", {})
        value = context.get("held")
        if isinstance(value, dict):
            return value.get(str(obj.id), False)
        return False


class SeatAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Seat
        fields = (
            "id", "seat_number", "section", "zone", "grid_col", "grid_row",
            "is_girls_only", "is_premium", "premium_extra", "is_active",
        )
        read_only_fields = ("id",)
