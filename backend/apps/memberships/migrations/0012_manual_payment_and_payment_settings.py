from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("memberships", "0011_extend_duration_discounts_to_12_months"),
    ]

    operations = [
        migrations.AlterField(
            model_name="membership",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending_payment", "Pending Payment"),
                    ("pending_cash", "Pending Cash"),
                    ("pending_approval", "Pending Approval"),
                    ("active", "Active"),
                    ("expired", "Expired"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending_payment",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("upi", "UPI"),
                    ("cash", "Cash"),
                    ("manual", "QR / Manual"),
                ],
                default="upi",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="admin_note",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="payment",
            name="receipt",
            field=models.FileField(blank=True, null=True, upload_to="payment_receipts/"),
        ),
        migrations.AddField(
            model_name="payment",
            name="transaction_id",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.CreateModel(
            name="PaymentSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("upi_id", models.CharField(blank=True, default="", max_length=80)),
                ("upi_name", models.CharField(blank=True, default="", max_length=80)),
                (
                    "qr_image",
                    models.ImageField(blank=True, null=True, upload_to="payment_qr/"),
                ),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"verbose_name_plural": "Payment settings"},
        ),
    ]