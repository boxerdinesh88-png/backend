"""Expire cash booking requests that were not approved within 3 days."""
from django.core.management.base import BaseCommand

from apps.memberships.services import expire_cash_requests


class Command(BaseCommand):
    help = "Cancel pending cash requests past their 3-day window and release their seats."

    def handle(self, *args, **options):
        count = expire_cash_requests()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} cash request(s)."))
