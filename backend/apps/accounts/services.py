"""Business logic for accounts: OTP generation/verification + email delivery.

Designed to stay reliable under bursts of simultaneous signups:

* `issue_otp` / `verify_otp` run inside a transaction and lock the user row,
  so 20 concurrent requests for the same person are serialized (no duplicate
  codes, no double-redeems, cooldown is exact).
* `send_otp_email` records the delivery outcome on the code row and returns
  whether it was accepted, so API responses can honestly tell the member
  "queued" vs "failed — try resend" instead of claiming success blindly.
"""
import hmac
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.utils import generate_otp
from apps.notifications.tasks import dispatch_email

logger = logging.getLogger(__name__)

OTP_COOLDOWN_SECONDS = 30
OTP_TTL_MINUTES = 10


class OTPCooldownError(Exception):
    """Raised when a fresh unused code already exists for this user/purpose.

    ``retry_after`` (seconds) tells the caller how long to wait before the
    next send is allowed.
    """

    def __init__(self, retry_after=0):
        self.retry_after = retry_after
        super().__init__(retry_after)


@transaction.atomic
def issue_otp(user, purpose="verify_email", ttl_minutes=OTP_TTL_MINUTES, cooldown_seconds=OTP_COOLDOWN_SECONDS):
    """Create a fresh single-use OTP, or raise ``OTPCooldownError``.

    The user row is locked so concurrent resends for one account serialize.
    """
    from .models import OTPCode, User

    User.objects.select_for_update().filter(pk=user.pk).first()
    existing = (
        OTPCode.objects.filter(user=user, purpose=purpose, is_used=False)
        .order_by("-created_at")
        .first()
    )
    if existing:
        elapsed = (timezone.now() - existing.created_at).total_seconds()
        if elapsed < cooldown_seconds:
            raise OTPCooldownError(max(1, int(cooldown_seconds - elapsed)))
        if existing.expires_at > timezone.now():
            # Reuse the still-valid code instead of burning it and generating
            # a new one — the member may be about to type it.
            return existing
    OTPCode.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)
    return OTPCode.objects.create(
        user=user,
        purpose=purpose,
        code=generate_otp(),
        expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
    )


@transaction.atomic
def verify_otp(user, purpose, code) -> bool:
    """Single-use verification. Atomically consumes the code on success so two
    concurrent verify calls cannot redeem the same OTP twice."""
    from .models import OTPCode

    now = timezone.now()
    candidates = (
        OTPCode.objects.select_for_update()
        .filter(user=user, purpose=purpose, is_used=False)
        .order_by("-created_at")[:3]
    )
    for otp in candidates:
        if otp.expires_at < now:
            continue
        if hmac.compare_digest(str(otp.code), str(code)):
            otp.is_used = True
            otp.save(update_fields=["is_used"])
            return True
    return False


def send_otp_email(user, otp, purpose="verify_email") -> bool:
    """Dispatch the OTP email and record the outcome on the code row.

    ``otp`` is the OTPCode instance from ``issue_otp``. Returns True when the
    email was accepted for delivery (queued to Celery or handed to a retrying
    background thread). Never raises; failures are persisted on the row so a
    later "did the OTP actually go out?" check and the member-facing resend
    UX have real data.
    """
    is_reset = purpose == "reset_password"
    if is_reset:
        subject = "Reset your Phahendra Babu Library password"
        heading = "Reset your password"
    else:
        subject = "Verify your Phahendra Babu Library email"
        heading = "Verify your email address"

    ctx = {
        "member_name": user.name,
        "code": otp.code,
        "purpose": purpose,
        "heading": heading,
    }
    plain = (
        f"Hi {user.name},\n\n"
        f"{heading}.\n\n"
        f"Your Phahendra Babu Library verification code is: {otp.code}\n\n"
        "It expires in 10 minutes and can only be used once.\n"
        "If you didn't request this, you can safely ignore this email.\n\n"
        "Phahendra Babu Library\n"
        "Vill- Kharhat, Begusarai, Bihar 851217\n"
        "+91 8804162854 · phagendrababulibrary@gmail.com\n"
        "Managed by Akash Kumar"
    )
    html = render_to_string("emails/otp.html", ctx)
    use_celery = getattr(settings, "USE_CELERY", False)
    on_done = None if use_celery else _make_otp_recorder(otp)
    try:
        accepted = dispatch_email(subject, plain, user.email, html_body=html, on_done=on_done)
    except Exception:
        logger.exception("OTP email to %s failed to dispatch", user.email)
        _make_otp_recorder(otp)(False, "dispatch error")
        return False
    if accepted and use_celery:
        _make_otp_recorder(otp)(True, "")
    if not accepted and on_done:
        on_done(False, "dispatch rejected")
    return accepted


def _make_otp_recorder(otp):
    """Return a closure that records the final SMTP outcome on the OTP row.
    Safe to call from the background thread."""

    def record(success, error_message=""):
        try:
            otp.send_attempts += 1
            otp.last_sent_at = timezone.now()
            otp.delivery_error = "" if success else (error_message or "unknown")[:1000]
            otp.save(update_fields=["send_attempts", "last_sent_at", "delivery_error"])
        except Exception:
            logger.exception("failed to record OTP delivery state")

    return record