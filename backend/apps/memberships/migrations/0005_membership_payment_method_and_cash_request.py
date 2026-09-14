from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("memberships", "0004_membership_memberships_seat_id_c66a57_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="membership",
            name="cash_request_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="membership",
            name="payment_method",
            field=models.CharField(
                choices=[("upi", "UPI"), ("cash", "Cash")],
                default="upi",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending_payment", "Pending Payment"),
                    ("pending_cash", "Pending Cash"),
                    ("active", "Active"),
                    ("expired", "Expired"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending_payment",
                max_length=20,
            ),
        ),
    ]
