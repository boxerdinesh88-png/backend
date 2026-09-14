"""Seed demo data: admin + member, day-pass shifts, seats and a sample paid
membership so the dashboard and flows are immediately usable.
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.library.models import Seat, Shift
from apps.memberships.models import Membership, Payment
from apps.seats.management.commands.seed_seats import seed_sections_and_seats

SHIFTS = [
    ("06:00 AM – 10:00 AM", "06:00", "10:00", 250),
    ("10:00 AM – 02:00 PM", "10:00", "14:00", 300),
    ("02:00 PM – 06:00 PM", "14:00", "18:00", 300),
    ("06:00 PM – 10:00 PM", "18:00", "22:00", 300),
    ("06:00 AM – 02:00 PM", "06:00", "14:00", 500),
    ("02:00 PM – 10:00 PM", "14:00", "22:00", 550),
    ("06:00 AM – 10:00 PM", "06:00", "22:00", 1000),
]


class Command(BaseCommand):
    help = "Seed the study library with day-pass shifts, seats and demo users."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding study library demo data…")

        admin, _ = User.objects.get_or_create(
            email="admin@library.app",
            defaults={
                "name": "Library Admin",
                "role": "admin",
                "gender": "male",
                "is_staff": True,
                "is_superuser": True,
                "is_email_verified": True,
            },
        )
        admin.set_password("Admin@123")
        admin.save()

        member, _ = User.objects.get_or_create(
            email="demo@student.edu",
            defaults={
                "name": "Aarav Sharma",
                "phone": "+91 98765 43210",
                "gender": "male",
                "wifi_device_name": "Aarav-MacBook",
                "ip_address": "192.168.1.42",
                "is_email_verified": True,
            },
        )
        member.set_password("Demo@123")
        member.save()

        for name, start, end, price in SHIFTS:
            Shift.objects.get_or_create(
                name=name,
                defaults={"start_time": start, "end_time": end, "price": price},
            )

        seed_sections_and_seats()

        if not Membership.objects.exists():
            shift = Shift.objects.get(name="10:00 AM – 02:00 PM")
            seat = Seat.objects.get(seat_number="01")
            today = date.today()
            amount = shift.price
            membership = Membership.objects.create(
                member=member,
                shift=shift,
                seat=seat,
                duration_months=1,
                amount=amount,
                start_date=today,
                end_date=today + timedelta(days=30),
                status="active",
            )
            Payment.objects.create(
                membership=membership,
                razorpay_order_id="mock_seed_order",
                razorpay_payment_id="pay_seed_0001",
                razorpay_signature="seed",
                amount=amount,
                method="upi",
                status="paid",
                paid_at=timezone.now(),
            )

        self.stdout.write(self.style.SUCCESS("Seed complete."))
        self.stdout.write(f"  Admin:  admin@library.app / Admin@123")
        self.stdout.write(f"  Member: demo@student.edu / Demo@123")
        self.stdout.write(f"  Reminders: python manage.py send_membership_reminders")
