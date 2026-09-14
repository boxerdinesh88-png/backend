from django.core.management.base import BaseCommand

from apps.memberships.services import run_reminder_cycle


class Command(BaseCommand):
    help = "Run the daily membership reminder cycle (expire overdue + send renewal reminders)."

    def handle(self, *args, **options):
        result = run_reminder_cycle()
        self.stdout.write(self.style.SUCCESS(
            f"Expired: {result['expired']} | Cash expired: {result['cash_expired']} "
            f"| Warnings: {result['warnings_sent']} "
            f"| Reminders: {result['reminders_sent']}"
        ))
