"""Merge user accounts that differ only by email case.

The User.email column has a case-sensitive UNIQUE constraint, so accounts like
``Name@x.com`` and ``name@x.com`` could both be created. OTP/login lookups are
case-insensitive, which then crashed with ``MultipleObjectsReturned`` (HTTP 500).

For each group of users sharing the same lowercase email this keeps the oldest
account, moves every related object (bookings, memberships, OTPs, audit logs,
…) onto it, lowercases its email, and deletes the rest.

Usage:
    python manage.py dedupe_users          # dry run, prints what would change
    python manage.py dedupe_users --apply  # actually merge
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Merge user accounts that differ only by email case."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Perform the merge. Without it this is a dry run.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        duplicates = []
        seen = {}
        for user in User.objects.order_by("date_joined", "id"):
            key = user.email.strip().lower()
            seen.setdefault(key, []).append(user)
        for key, users in seen.items():
            if len(users) > 1:
                duplicates.append((key, users))

        if not duplicates:
            self.stdout.write(self.style.SUCCESS("No duplicate users found."))
            return

        rel_fields = []
        for r in User._meta.related_objects:
            if r.related_model is User:
                continue
            if r.field.related_model is not User:
                continue
            rel_fields.append((r.related_model, r.field))

        with transaction.atomic():
            for key, users in duplicates:
                keeper, *rest = users
                for model, field in rel_fields:
                    total = model.objects.filter(
                        **{f"{field.name}__in": rest}
                    ).update(**{field.name: keeper})
                    if total:
                        self.stdout.write(
                            f"  {model._meta.label}: {total} row(s) moved to {keeper.email}"
                        )

                keeper.email = key
                keeper.save(update_fields=["email"])

                if apply:
                    for dup in rest:
                        dup.delete()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  Merged {len(rest)} duplicate(s) of {key} into {keeper.id}"
                        )
                    )
                else:
                    self.stdout.write(
                        f"  [dry run] would delete {len(rest)} duplicate(s) of {key}"
                    )

        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    "Dry run complete. Re-run with --apply to perform the merge."
                )
            )
