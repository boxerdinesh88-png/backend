from django.db import migrations

# Discount grows by 2% per month starting from 2 months, capping at 12 months:
#   2m → 2%, 3m → 4%, 4m → 6% … 12m → 22% (per-month discount on monthly plan).
DEFAULTS = {m: (m - 1) * 2 for m in range(2, 13)}


def seed_all_duration_discounts(apps, schema_editor):
    DurationDiscount = apps.get_model("memberships", "DurationDiscount")
    for min_months, percent in DEFAULTS.items():
        DurationDiscount.objects.update_or_create(
            min_months=min_months,
            defaults={"discount_percent": percent, "is_active": True},
        )
    # Remove any tiers beyond 12 months (discount stops at one year).
    DurationDiscount.objects.filter(min_months__gt=12).delete()


def unseed_all_duration_discounts(apps, schema_editor):
    DurationDiscount = apps.get_model("memberships", "DurationDiscount")
    for min_months, percent in DEFAULTS.items():
        DurationDiscount.objects.filter(min_months=min_months).delete()
    for min_months, percent in ((2, 2), (3, 4), (4, 6)):
        DurationDiscount.objects.get_or_create(
            min_months=min_months,
            defaults={"discount_percent": percent, "is_active": True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("memberships", "0010_seed_duration_discounts"),
    ]

    operations = [
        migrations.RunPython(seed_all_duration_discounts, unseed_all_duration_discounts),
    ]