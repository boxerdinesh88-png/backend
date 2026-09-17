from decimal import Decimal

from django.db import models

SEAT_SECTIONS = (
    ("male", "Male Section"),
    ("female", "Female Section"),
    ("common", "Common Section"),
)


class Section(models.Model):
    """A physical zone of the reading hall (A–D), used by the 3D seat map.

    Zones map 1:1 onto the floor plan: A is the single row on the west wall,
    B the two facing columns, C the east wall + girls row, D the two rows
    below the divider. Gender access is still enforced via ``Seat.section``
    and ``Seat.is_girls_only``.
    """

    code = models.CharField(max_length=4, unique=True)
    name = models.CharField(max_length=60)
    description = models.TextField(blank=True, default="")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "code")
        indexes = [
            models.Index(fields=["sort_order"]),
        ]

    def __str__(self):
        return f"Section {self.code} · {self.name}"


class Shift(models.Model):
    """A daily time block sold as a day pass.

    Shifts are non-overlapping products; wider blocks (e.g. 06:00–14:00)
    are separate shifts that overlap their parts and are priced accordingly.
    """

    name = models.CharField(max_length=40, unique=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("start_time",)
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["start_time", "end_time"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.start_time:%H:%M}–{self.end_time:%H:%M}) · ₹{self.price}"

    def overlaps(self, other):
        """True when this shift's time window overlaps another's."""
        return self.start_time < other.end_time and self.end_time > other.start_time


class Seat(models.Model):
    """A single physical seat in the reading room.

    ``section`` is the gender access tag (male/female/common) that drives
    ``User.allowed_sections``; ``zone`` locates the seat on the floor plan
    (A–D) and ``grid_col``/``grid_row`` give its position on the reference
    grid (1 unit = 1.6 m) used by the 3D seat map. ``is_girls_only`` marks
    the girls-only block (seats 21–31) and is enforced server-side.
    """

    seat_number = models.CharField(max_length=20, unique=True)
    section = models.CharField(max_length=10, choices=SEAT_SECTIONS)
    zone = models.ForeignKey(
        Section, null=True, blank=True, on_delete=models.SET_NULL, related_name="seats"
    )
    grid_col = models.FloatField(null=True, blank=True)
    grid_row = models.FloatField(null=True, blank=True)
    is_girls_only = models.BooleanField(default=False)
    is_premium = models.BooleanField(default=False)
    premium_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("10.00"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("seat_number",)
        indexes = [
            models.Index(fields=["section", "is_active"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["zone"]),
        ]

    def __str__(self):
        return f"{self.seat_number} ({self.get_section_display()})"
