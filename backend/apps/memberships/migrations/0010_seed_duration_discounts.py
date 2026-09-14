from django.db import migrations


def seed_duration_discounts(apps, schema_editor):
    DurationDiscount = apps.get_model("memberships", "DurationDiscount")
    for min_months, percent in ((2, 2), (3, 4), (4, 6)):
        DurationDiscount.objects.get_or_create(
            min_months=min_months,
            defaults={"discount_percent": percent, "is_active": True},
        )


def unseed_duration_discounts(apps, schema_editor):
    DurationDiscount = apps.get_model("memberships", "DurationDiscount")
    DurationDiscount.objects.filter(min_months__in=(2, 3, 4)).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("memberships", "0009_durationdiscount_membership_discount_percent"),
    ]

    operations = [
        migrations.RunPython(seed_duration_discounts, unseed_duration_discounts),
    ]