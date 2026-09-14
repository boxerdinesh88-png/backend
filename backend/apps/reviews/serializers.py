from rest_framework import serializers

from .models import Review

TEXT_MAX = 400
NAME_MAX = 60


class ReviewSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = Review
        fields = (
            "id", "name", "display_name",
            "rating", "atmosphere", "facilities",
            "liked_most", "suggestion",
            "is_approved", "created_at",
        )
        read_only_fields = ("id", "is_approved", "created_at")

    def validate_name(self, value):
        value = value.strip()
        if len(value) > NAME_MAX:
            raise serializers.ValidationError("Name is too long.")
        return value

    def _clean_text(self, value):
        value = (value or "").strip()
        if len(value) > TEXT_MAX:
            raise serializers.ValidationError(f"Keep it under {TEXT_MAX} characters.")
        return value

    def validate_liked_most(self, value):
        return self._clean_text(value)

    def validate_suggestion(self, value):
        return self._clean_text(value)
