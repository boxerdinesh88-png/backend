"""Business logic for accounts: OTP generation/verification + email delivery."""
import hmac
import logging
from datetime import timedelta

from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.utils import generate_otp
from apps.notifications.tasks import dispatch_email

logger = logging.getLogger(__name__)

OTP_COOLDOWN_SECONDS = 60


class OTPCooldownError(Exception):
    """Raised when a fresh unused code already exists for this user/purpose."""


def issue_otp(user, purpose="verify_email", ttl_minutes=10, cooldown_seconds=OTP_COOLDOWN_SECONDS) -> str:
    from .models import OTPCode

    existing = (
        OTPCode.objects.filter(user=user, purpose=purpose, is_used=False)
        .order_by("-created_at")
        .first()
    )
    if existing and (timezone.now() - existing.created_at).total_seconds() < cooldown_seconds:
        raise OTPCooldownError
    OTPCode.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)
    otp = OTPCode.objects.create(
        user=user,
        purpose=purpose,
        code=generate_otp(),
        expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
    )
    return otp.code


def verify_otp(user, purpose, code) -> bool:
    from .models import OTPCode

    now = timezone.now()
    candidates = OTPCode.objects.filter(user=user, purpose=purpose, is_used=False).order_by("-created_at")[:3]
    for otp in candidates:
        if otp.expires_at < now:
            continue
        if hmac.compare_digest(str(otp.code), str(code)):
            otp.is_used = True
            otp.save(update_fields=["is_used"])
            return True
    return False


def send_otp_email(user, code, purpose="verify_email"):
    is_reset = purpose == "reset_password"
    if is_reset:
        subject = "Reset your Phahendra Babu Library password"
        heading = "Reset your password"
    else:
        subject = "Verify your Phahendra Babu Library email"
        heading = "Verify your email address"

    ctx = {
        "member_name": user.name,
        "code": code,
        "purpose": purpose,
        "heading": heading,
    }
    plain = (
        f"Hi {user.name},\n\n"
        f"{heading}.\n\n"
        f"Your Phahendra Babu Library verification code is: {code}\n\n"
        "It expires in 10 minutes and can only be used once.\n"
        "If you didn't request this, you can safely ignore this email.\n\n"
        "Phahendra Babu Library\n"
        "Vill- Kharhat, Begusarai, Bihar 851217\n"
        "+91 8804162854 · PhahendraBabulibrary@gmail.com\n"
        "Managed by Akash Kumar"
    )
    html = render_to_string("emails/otp.html", ctx)
    try:
        dispatch_email(subject, plain, user.email, html_body=html)
    except Exception:
        logger.exception("OTP email to %s failed (check EMAIL_HOST_USER/PASSWORD)", user.email)
