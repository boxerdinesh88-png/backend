"""Configure the member-facing UPI QR / bank transfer payment details.

Run once on any fresh deployment (the checkout screen falls back to cash-only
until PaymentSettings has a UPI id and QR image):

    python manage.py seed_payment_settings [--qr /path/to/library-qr.jpg]

Values come from PAYMENT_* env vars (with the library's real details as
defaults). The optional --qr path copies a scan-to-pay QR image into MEDIA_ROOT
and attaches it. Idempotent — safe to re-run.
"""
import os

from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.memberships.models import PaymentSettings


class Command(BaseCommand):
    help = "Seed PaymentSettings (UPI id, bank details and QR image) for the checkout screen."

    def add_arguments(self, parser):
        parser.add_argument(
            "--qr",
            default=os.getenv("PAYMENT_QR_PATH", ""),
            help="Path to the scan-to-pay QR image to upload (default: $PAYMENT_QR_PATH).",
        )
        parser.add_argument(
            "--disable",
            action="store_true",
            help="Persist the settings row but leave is_active=False.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        settings = PaymentSettings.get_singleton()

        settings.upi_id = os.getenv("PAYMENT_UPI_ID", "Phagendrababulibrary@indianbk")
        settings.upi_name = os.getenv("PAYMENT_UPI_NAME", "Phagendra Babu Library")
        settings.bank_account_number = os.getenv("PAYMENT_BANK_ACCOUNT", "8199961593")
        settings.bank_ifsc = os.getenv("PAYMENT_BANK_IFSC", "IDIB000M585")
        settings.bank_name = os.getenv("PAYMENT_BANK_NAME", "Indian Bank")
        settings.is_active = not options["disable"]

        qr_path = (options["qr"] or "").strip()
        if qr_path:
            if not os.path.exists(qr_path):
                self.stderr.write(self.style.ERROR(f"QR image not found: {qr_path}"))
                raise SystemExit(1)
            if settings.qr_image:
                settings.qr_image.delete(save=False)
            with open(qr_path, "rb") as fh:
                settings.qr_image.save(f"payment_qr_{settings.pk or 1}.jpg", File(fh), save=False)

        settings.save()

        self.stdout.write(self.style.SUCCESS("PaymentSettings configured:"))
        self.stdout.write(f"  UPI: {settings.upi_id} ({settings.upi_name})")
        self.stdout.write(f"  Bank: {settings.bank_account_number} @ {settings.bank_ifsc} ({settings.bank_name})")
        self.stdout.write(f"  QR image: {settings.qr_image.name if settings.qr_image else '—'}")
        self.stdout.write(f"  is_active: {settings.is_active}")