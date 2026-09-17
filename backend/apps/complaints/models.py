import uuid

from django.db import models


def generate_reference() -> str:
    """Short, human-quotable reference like PBL-3F9A2C1D."""
    return f"PBL-{uuid.uuid4().hex[:8].upper()}"


CATEGORY_CHOICES = (
    ("seat", "Seat / Booking"),
    ("ac", "AC / Ventilation"),
    ("cleanliness", "Cleanliness / Hygiene"),
    ("power", "Power / Charging"),
    ("wifi", "Wi-Fi / Internet"),
    ("staff", "Staff Behaviour"),
    ("facility", "Facility / Furniture"),
    ("other", "Other"),
)


class Complaint(models.Model):
    """A complaint raised by a member from the public complaint form.

    Anyone can submit without an account. Every complaint gets a short
    `reference` (PBL-XXXXXXXX) that is shown as a confirmation on screen so the
    library and the member can quote it. The library resolves complaints within
    one week; `is_resolved` tracks that in Django admin.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(
        max_length=16, unique=True, default=generate_reference, editable=False
    )

    name = models.CharField(max_length=60, blank=True, default="")
    contact = models.CharField(max_length=120, blank=True, default="")

    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default="other"
    )
    subject = models.CharField(max_length=120)
    description = models.TextField()

    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["is_resolved", "-created_at"]),
        ]

    @property
    def display_name(self) -> str:
        return self.name.strip() or "Anonymous"

    def __str__(self):
        return f"{self.reference} · {self.get_category_display()}"
