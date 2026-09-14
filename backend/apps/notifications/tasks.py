"""Async email delivery via Celery with a synchronous fallback.

Sending SMTP mail inline blocks the request worker for seconds (Gmail SMTP is
slow). On production (Redis configured) every email is queued to Celery so the
API returns instantly; on hosts without a broker (local dev, free tiers) the
same helper falls back to sending inline so nothing is silently dropped.
"""
import logging

from celery import shared_task
from django.conf import settings

logger = logging.getLogger("libseat.notifications")


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def send_email_task(
    self,
    subject,
    plain_body,
    to_emails,
    html_body=None,
    from_email=None,
):
    """Actually deliver one email. Retries transient SMTP/network failures."""
    from django.core.mail import send_mail

    try:
        send_mail(
            subject,
            plain_body,
            from_email or settings.DEFAULT_FROM_EMAIL,
            to_emails,
            html_message=html_body,
            fail_silently=False,
        )
    except Exception as exc:
        logger.exception("email to %s failed", to_emails)
        raise self.retry(exc=exc)


def dispatch_email(subject, plain_body, to_emails, html_body=None, from_email=None):
    """Queue an email to Celery when a broker is configured, else send inline.

    `to_emails` may be a single address or a list. Returns True when the email
    was accepted/queued.
    """
    if isinstance(to_emails, str):
        to_emails = [to_emails]

    if getattr(settings, "USE_CELERY", False):
        send_email_task.delay(
            subject, plain_body, to_emails, html_body=html_body, from_email=from_email
        )
        return True

    # No broker: send inline (same behaviour as before, keeps free tiers working).
    try:
        from django.core.mail import send_mail

        send_mail(
            subject,
            plain_body,
            from_email or settings.DEFAULT_FROM_EMAIL,
            to_emails,
            html_message=html_body,
            fail_silently=True,
        )
    except Exception:
        logger.exception("inline email to %s failed", to_emails)
    return True
