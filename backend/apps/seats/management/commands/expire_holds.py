"""Manually expire stale holds (runs without Celery)."""
from django.core.management.base import BaseCommand

from apps.seats.services import expire_stale_holds


class Command(BaseCommand):
    help = "Release held bookings past their 10-minute timer."

    def handle(self, *args, **options):
        count = expire_stale_holds()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} stale hold(s)."))
