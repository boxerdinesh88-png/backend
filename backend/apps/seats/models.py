"""Booking: a short-lived reservation that keeps a seat locked while a member
completes checkout, then converts into a confirmed seat assignment.

Lifecycle: HELD → CONFIRMED (payment verified) / EXPIRED (stale hold, Celery)
/ CANCELLED (user or admin releases it). The slot is (shift, date range);
only one *active* booking (held or confirmed) may overlap a given seat+shift,
enforced in the service under a row lock.
"""
import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone

HOLD_TTL = timedelta(minutes=10)

BOOKING_STATUS = (
    ("held", "Held"),
    ("confirmed", "Confirmed"),
    ("cancelled", "Cancelled"),
    ("expired", "Expired"),
)


class Booking(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="bookings"
    )
    seat = models.ForeignKey(
        "library.Seat", on_delete=models.CASCADE, related_name="bookings"
    )
    shift = models.ForeignKey(
        "library.Shift", on_delete=models.PROTECT, related_name="bookings"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=12, choices=BOOKING_STATUS, default="held")
    held_until = models.DateTimeField(null=True, blank=True)
    razorpay_order_id = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["seat", "shift", "status"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "held_until"]),
        ]

    def __str__(self):
        return (
            f"{self.seat.seat_number} · {self.shift.name} · "
            f"{self.start_date}–{self.end_date} · {self.status}"
        )

    @property
    def is_active_hold(self):
        return (
            self.status == "held"
            and self.held_until is not None
            and self.held_until > timezone.now()
        )

    def overlaps(self, start, end):
        return self.start_date <= end and self.end_date >= start
