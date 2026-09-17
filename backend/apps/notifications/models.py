import uuid

from django.db import models

NOTIFICATION_TYPES = (
    ("confirmation", "Confirmation"),
    ("renewal", "Renewal"),
    ("cash_request", "Cash Request"),
    ("expiry_warning", "Expiry Warning (7 days)"),
    ("reminder_3day", "Renewal Reminder (3 days)"),
    ("reminder_1day", "Renewal Reminder (1 day)"),
)

NOTIFICATION_CHANNELS = (
    ("email", "Email"),
    ("sms", "SMS"),
)


class NotificationLog(models.Model):
    """Audit trail of every membership notification that was sent."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    membership = models.ForeignKey(
        "memberships.Membership", on_delete=models.CASCADE, related_name="notification_logs"
    )
    type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    channel = models.CharField(max_length=10, choices=NOTIFICATION_CHANNELS)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-sent_at",)
        indexes = [
            models.Index(fields=["membership", "type", "sent_at"]),
        ]

    def __str__(self):
        return f"{self.get_type_display()} via {self.get_channel_display()} · {self.membership_id}"
