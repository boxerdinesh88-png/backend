"""Seed the reading hall with the real 36-seat floor plan (sections A–D).

Reference grid (1 unit = 1.6 m), per the physical hall:
  Section A (1–5):   col = 5-i, row = 0            (single row, west wall)
  Section B (6–10):  col = 6,   row = i-6          (facing column 1)
  Section B (11–15): col = 7,   row = 15-i         (facing column 2)
  Section C (16–20): col = 9,   row = i-16         (east wall)
  Section C (21–26): col = 9+(i-21), row = 5       (girls row)
  Section D (27–31): col = 14-(i-27), row = 7      (girls row, upper)
  Section D (32–36): col = 10+(i-32), row = 8.5    (open row)

Girls-only block = seats 21–31.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.library.models import Seat, Section
from apps.seats.models import Booking


def layout():
    seats = []
    for i in range(1, 6):        # A
        seats.append((i, "A", 5 - i, 0))
    for i in range(6, 11):       # B facing columns
        seats.append((i, "B", 6, i - 6))
    for i in range(11, 16):
        seats.append((i, "B", 7, 15 - i))
    for i in range(16, 21):      # C east wall
        seats.append((i, "C", 9, i - 16))
    for i in range(21, 27):      # C girls row
        seats.append((i, "C", 9 + (i - 21), 5))
    for i in range(27, 32):      # D upper girls row
        seats.append((i, "D", 14 - (i - 27), 7))
    for i in range(32, 37):      # D lower open row
        seats.append((i, "D", 10 + (i - 32), 8.5))
    return seats


def seed_sections_and_seats():
    """Create sections A–D and replace seats with the 36-seat floor plan."""
    sections = {}
    for code, name, order in (
        ("A", "West Wall", 1),
        ("B", "Facing Columns", 2),
        ("C", "East Wing", 3),
        ("D", "Lower Hall", 4),
    ):
        section, _ = Section.objects.get_or_create(
            code=code, defaults={"name": name, "sort_order": order}
        )
        section.name = name
        section.sort_order = order
        section.save(update_fields=["name", "sort_order"])
        sections[code] = section

    Booking.objects.all().delete()
    Seat.objects.all().delete()

    for number, zone_code, col, row in layout():
        girls_only = 21 <= number <= 31
        Seat.objects.create(
            seat_number=f"{number:02d}",
            section="female" if girls_only else "common",
            zone=sections[zone_code],
            grid_col=col,
            grid_row=row,
            is_girls_only=girls_only,
        )
    return sections


class Command(BaseCommand):
    help = "Replace seats with the 36-seat physical layout (sections A–D)."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding the 36-seat reading-hall layout…")

        old_count = Seat.objects.count()
        seed_sections_and_seats()

        self.stdout.write(
            self.style.SUCCESS(
                f"Removed {old_count} old seats; created {Seat.objects.count()} seats "
                f"across {Section.objects.count()} sections (girls-only: 21–31)."
            )
        )
