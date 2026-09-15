import uuid
from datetime import date
from decimal import Decimal

from django.db import models

MEMBERSHIP_STATUS = (
    ("pending_payment", "Pending Payment"),
    ("pending_cash", "Pending Cash"),
    ("pending_approval", "Pending Approval"),
    ("active", "Active"),
    ("expired", "Expired"),
    ("cancelled", "Cancelled"),
)

PLAN_TYPES = (
    ("daily", "One Day"),
    ("weekly", "One Week"),
    ("monthly", "Monthly"),
)

PLAN_PRICES = {
    "daily": 40,
    "weekly": 250,
}

PAYMENT_METHODS = (
    ("upi", "UPI"),
    ("cash", "Cash"),
    ("manual", "QR / Manual"),
)

# Lifecycle: created → (authorized →) paid | failed. A late webhook may move
# failed → paid (money was actually captured); `paid` is only ever left via an
# explicit refund. Never regress paid/failed to pending states.
PAYMENT_STATUS = (
    ("created", "Created"),
    ("authorized", "Authorized"),
    ("paid", "Paid"),
    ("failed", "Failed"),
    ("refunded", "Refunded"),
)

PAYMENT_TRANSITIONS = {
    "created": {"authorized", "paid", "failed"},
    "authorized": {"authorized", "paid", "failed"},
    "failed": {"paid"},
    "paid": {"refunded"},
    "refunded": set(),
}

DAYS_PER_MONTH = 30


class Membership(models.Model):
    """A paid pass for one time block for a chosen duration.

    Supports daily, weekly, and monthly plans.
    Price is fixed for daily/weekly, or shift's monthly price × duration months.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="memberships"
    )
    shift = models.ForeignKey(
        "library.Shift", on_delete=models.PROTECT, related_name="memberships"
    )
    seat = models.ForeignKey(
        "library.Seat",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="memberships",
    )
    plan_type = models.CharField(
        max_length=10, choices=PLAN_TYPES, default="monthly"
    )
    duration_months = models.PositiveSmallIntegerField(default=1)
    is_premium = models.BooleanField(default=False)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=MEMBERSHIP_STATUS, default="pending_payment"
    )
    payment_method = models.CharField(
        max_length=10, choices=PAYMENT_METHODS, default="upi"
    )
    cash_request_expires_at = models.DateTimeField(null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "end_date"]),
            models.Index(fields=["member", "status"]),
            models.Index(fields=["seat", "status", "start_date", "end_date"]),
        ]

    def __str__(self):
        return f"{self.member.email} · {self.shift.name} · {self.start_date} · {self.status}"

    @property
    def days_left(self):
        if not self.end_date:
            return None
        return (self.end_date - date.today()).days

    def compute_dates(self, start=None):
        from datetime import timedelta

        start = start or date.today()
        self.start_date = start
        if self.plan_type == "daily":
            self.end_date = start + timedelta(days=1)
        elif self.plan_type == "weekly":
            self.end_date = start + timedelta(days=7)
        else:
            self.end_date = start + timedelta(days=DAYS_PER_MONTH * self.duration_months)
        return self.start_date, self.end_date


class Payment(models.Model):
    """Razorpay UPI payment tied 1:1 to a membership."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    membership = models.OneToOneField(
        Membership, on_delete=models.CASCADE, related_name="payment"
    )
    razorpay_order_id = models.CharField(max_length=100, blank=True, default="")
    razorpay_payment_id = models.CharField(max_length=120, blank=True, default="")
    razorpay_signature = models.CharField(max_length=255, blank=True, default="")
    transaction_id = models.CharField(max_length=120, blank=True, default="")
    receipt = models.FileField(upload_to="payment_receipts/", blank=True, null=True)
    admin_note = models.CharField(max_length=255, blank=True, default="")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, default="upi")
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default="created")
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            # Webhook lookups arrive by gateway order/payment id.
            models.Index(fields=["razorpay_order_id"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            # DB-level duplicate protection: the same gateway order / payment
            # can never be recorded on two Payment rows (empty values exempt).
            models.UniqueConstraint(
                fields=["razorpay_order_id"],
                condition=~models.Q(razorpay_order_id=""),
                name="uniq_payment_razorpay_order_id",
            ),
            models.UniqueConstraint(
                fields=["razorpay_payment_id"],
                condition=~models.Q(razorpay_payment_id=""),
                name="uniq_payment_razorpay_payment_id",
            ),
        ]

    def transition_to(self, new_status):
        """Apply a guarded status change. Returns True when applied.

        Invalid transitions (e.g. a stale webhook trying to move a captured
        payment back to pending/failed) are refused and logged by callers.
        """
        if new_status == self.status:
            return False
        if new_status not in PAYMENT_TRANSITIONS.get(self.status, set()):
            return False
        self.status = new_status
        return True

    def __str__(self):
        return f"Payment {self.amount} {self.status} · {self.membership_id}"


class DurationDiscount(models.Model):
    """Configurable discount tiers for multi-month bookings.

    Admin-managed: add/edit rows in Django admin to change pricing.
    Tiers are matched by min_months descending; the first tier whose
    min_months ≤ the selected duration wins.
    """

    min_months = models.PositiveSmallIntegerField(
        unique=True,
        help_text="Minimum months for this discount to apply (e.g. 2 = applies from 2 months onward).",
    )
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Percentage discount per month (e.g. 2 means each month's price is reduced by 2%).",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("min_months",)

    def __str__(self):
        return f"{self.discount_percent}% off from {self.min_months} months"


def get_discount_percent(months):
    """Return the best active discount percent for a given duration."""
    tier = (
        DurationDiscount.objects
        .filter(min_months__lte=months, is_active=True)
        .order_by("-min_months")
        .first()
    )
    return tier.discount_percent if tier else Decimal("0")


class PaymentSettings(models.Model):
    """Library-owned UPI details shown on the QR/manual payment screen.

    A single row exists (get_singleton). The admin uploads the scan-to-pay QR
    image and the member-facing pay step renders it with the exact amount.
    """

    upi_id = models.CharField(max_length=80, blank=True, default="")
    upi_name = models.CharField(max_length=80, blank=True, default="")
    qr_image = models.ImageField(upload_to="payment_qr/", blank=True, null=True)
    bank_account_number = models.CharField(max_length=30, blank=True, default="")
    bank_ifsc = models.CharField(max_length=20, blank=True, default="")
    bank_name = models.CharField(max_length=60, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Payment settings"

    def __str__(self):
        return self.upi_id or f"Payment settings #{self.pk}"

    @classmethod
    def get_singleton(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj


class WebhookEvent(models.Model):
    """Idempotency store for Razorpay webhook deliveries.

    The primary key is a stable dedupe key (`<event>:<payment_id>`), so a
    repeated delivery collides at the database level and is answered from the
    existing row instead of re-running business logic.
    """

    id = models.CharField(primary_key=True, max_length=120)
    event_type = models.CharField(max_length=100, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    processed = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-received_at",)

    def __str__(self):
        return f"{self.id} ({'processed' if self.processed else 'pending'})"
