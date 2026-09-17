import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from .managers import UserManager

GENDERS = (
    ("male", "Male"),
    ("female", "Female"),
    ("other", "Other"),
)

ROLES = (
    ("member", "Member"),
    ("admin", "Admin"),
)


class User(AbstractBaseUser, PermissionsMixin):
    """A study-library member (or admin staff user)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, default="")
    gender = models.CharField(max_length=10, choices=GENDERS, default="other")
    aadhar_document = models.FileField(upload_to="aadhar_docs/", blank=True, null=True)
    aadhar_document_back = models.FileField(upload_to="aadhar_docs/", blank=True, null=True)
    photo = models.ImageField(upload_to="profile_photos/", blank=True, null=True)
    purpose = models.CharField(max_length=120, blank=True, default="")
    class_name = models.CharField(max_length=50, blank=True, default="")
    # Device details captured at registration (used for router whitelisting,
    # which is a network-side task outside this app — stored here as data).
    wifi_device_name = models.CharField(max_length=160, blank=True, default="")
    wifi_device_name_2 = models.CharField(max_length=160, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    # Voluntary consent to use the member's name, photograph, testimonials and
    # academic achievements for library promotions. Timestamped as proof and
    # withdrawable later by written request to the library management.
    promo_consent = models.BooleanField(default=False)
    promo_consent_at = models.DateTimeField(null=True, blank=True)

    role = models.CharField(max_length=20, choices=ROLES, default="member")
    is_email_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()

    class Meta:
        ordering = ("-date_joined",)
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["is_email_verified"]),
            models.Index(fields=["role", "is_active"]),
            models.Index(fields=["date_joined"]),
        ]

    @property
    def is_admin(self):
        return self.role == "admin" or self.is_superuser

    @property
    def allowed_sections(self):
        """Seat sections this member may sit in.

        Gender-segregated: female members are restricted to the girls-only
        (female) section, male/other members to the common section.
        """
        if self.gender == "female":
            return ["female"]
        if self.gender == "male":
            return ["male", "common"]
        return ["common"]

    def __str__(self):
        return f"{self.name} <{self.email}>"


class OTPCode(models.Model):
    """Single-use, short-lived OTP for email verification & password reset."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otps")
    purpose = models.CharField(max_length=30, default="verify_email")
    code = models.CharField(max_length=10)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    delivery_error = models.TextField(blank=True, default="")
    send_attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "purpose", "is_used"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.user.email} / {self.purpose}"


class AuditLog(models.Model):
    """Immutable-ish record of security & admin actions."""

    user = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="audit_logs"
    )
    actor_email = models.EmailField(blank=True)
    action = models.CharField(max_length=120)
    ip = models.GenericIPAddressField(null=True, blank=True)
    path = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=10, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["actor_email", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.actor_email} {self.action}"
