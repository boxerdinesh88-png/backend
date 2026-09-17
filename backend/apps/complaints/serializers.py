import re

from rest_framework import serializers

from .models import Complaint

NAME_MAX = 60
CONTACT_MAX = 120
SUBJECT_MAX = 120
DESCRIPTION_MAX = 2000

# Accept either an email address or a phone number (with optional +, spaces,
# dashes or brackets) as the follow-up contact.
CONTACT_RE = re.compile(
    r"^(?:[^@\s]+@[^@\s]+\.[^@\s]+|(?:\+?\d[\d\s\-()]{6,}\d))$"
)


class ComplaintSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = Complaint
        fields = (
            "id", "reference", "name", "display_name",
            "contact", "category",
            "subject", "description",
            "is_resolved", "created_at",
        )
        read_only_fields = ("id", "reference", "is_resolved", "created_at")

    def validate_name(self, value):
        value = (value or "").strip()
        if len(value) > NAME_MAX:
            raise serializers.ValidationError("Name is too long.")
        return value

    def validate_contact(self, value):
        value = (value or "").strip()
        if not value:
            return value
        if len(value) > CONTACT_MAX:
            raise serializers.ValidationError("Contact is too long.")
        if not CONTACT_RE.match(value):
            raise serializers.ValidationError(
                "Enter a valid email address or phone number."
            )
        return value

    def validate_subject(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Please add a short subject.")
        if len(value) > SUBJECT_MAX:
            raise serializers.ValidationError(
                f"Keep the subject under {SUBJECT_MAX} characters."
            )
        return value

    def validate_description(self, value):
        value = (value or "").strip()
        if len(value) < 10:
            raise serializers.ValidationError(
                "Please describe the issue in a little more detail."
            )
        if len(value) > DESCRIPTION_MAX:
            raise serializers.ValidationError(
                f"Keep the description under {DESCRIPTION_MAX} characters."
            )
        return value
