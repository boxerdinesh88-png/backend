"""Async email delivery via Celery with a background-thread fallback.

Sending SMTP mail inline blocks the request worker for seconds. On production
(Redis configured) every email is queued to Celery so the API returns
instantly; on hosts without a broker (local dev, free tiers) the same helper
spawns a daemon thread so the HTTP response is never held up by network I/O.

Speed: a single SMTP connection (TCP + STARTTLS + Gmail AUTH ≈ 1s) is opened
once and reused for every subsequent email, so OTPs after the first arrive
almost instantly instead of paying the handshake each time. A stale connection
is detected on send error and transparently reconnected once. Concurrent sends
are serialized on a lock (Gmail throttles many parallel SMTP sessions anyway),
which also keeps bursts of signups reliable.

Both paths retry transient failures; `on_done` records the final delivery
outcome (e.g. on an OTP row).
"""
import logging
import threading
import time

from celery import shared_task
from django.conf import settings

logger = logging.getLogger("libseat.notifications")

_smtp_lock = threading.Lock()
_smtp_connection = None


def _build_message(subject, plain_body, to_emails, html_body, from_email):
    from django.core.mail import EmailMultiAlternatives

    msg = EmailMultiAlternatives(
        subject,
        plain_body,
        from_email or settings.DEFAULT_FROM_EMAIL,
        to_emails,
    )
    if html_body:
        msg.attach_alternative(html_body, "text/html")
    return msg


def _get_smtp_connection():
    global _smtp_connection
    from django.core.mail import get_connection

    if _smtp_connection is None or _smtp_connection.connection is None:
        _smtp_connection = get_connection()
        _smtp_connection.open()
    return _smtp_connection


def _send_once(subject, plain_body, to_emails, html_body, from_email):
    """Send one email, reusing the warm connection. Reconnects transparently
    once if the server dropped the idle connection. Always called under
    `_smtp_lock`."""
    global _smtp_connection
    try:
        msg = _build_message(subject, plain_body, to_emails, html_body, from_email)
        _get_smtp_connection().send_messages([msg])
    except Exception:
        # Connection may have gone stale while idle (e.g. Gmail ~5 min). Close
        # and reconnect once before surfacing the error for the retry logic.
        try:
            if _smtp_connection is not None:
                _smtp_connection.close()
        except Exception:
            pass
        _smtp_connection = None
        msg = _build_message(subject, plain_body, to_emails, html_body, from_email)
        _get_smtp_connection().send_messages([msg])


def _thread_send(subject, plain_body, to_emails, html_body, from_email, on_done=None):
    """Run inside a daemon thread so the HTTP request returns instantly.
    Retries up to 3 times with a short backoff, then reports the final outcome
    through `on_done(success, error_message)` if provided."""
    global _smtp_connection
    last_error = None
    for attempt in range(3):
        try:
            with _smtp_lock:
                _send_once(subject, plain_body, to_emails, html_body, from_email)
            if on_done:
                on_done(True, "")
            return
        except Exception as exc:
            last_error = exc
            # A dead/holding connection can stall a burst; drop it so the next
            # attempt starts clean.
            try:
                with _smtp_lock:
                    if _smtp_connection is not None:
                        _smtp_connection.close()
                        _smtp_connection = None
            except Exception:
                pass
            if attempt < 2:
                time.sleep(1 + attempt * 2)
    logger.error("background email to %s failed after retries: %s", to_emails, last_error)
    if on_done:
        on_done(False, str(last_error))


@shared_task(bind=True, max_retries=5)
def send_email_task(
    self,
    subject,
    plain_body,
    to_emails,
    html_body=None,
    from_email=None,
):
    """Deliver one email through Celery. Retries transient SMTP/network
    failures with exponential backoff + jitter (2s, 4s, 8s, 16s, 32s)."""
    try:
        with _smtp_lock:
            _send_once(subject, plain_body, to_emails, html_body, from_email)
    except Exception as exc:
        logger.warning("email to %s failed (attempt %s): %s", to_emails, self.request.retries + 1, exc)
        countdown = 2 ** (self.request.retries + 1)
        raise self.retry(exc=exc, countdown=countdown)


def dispatch_email(subject, plain_body, to_emails, html_body=None, from_email=None, on_done=None):
    """Queue an email to Celery when a broker is configured, else send in a
    daemon thread.

    `to_emails` may be a single address or a list.

    `on_done(success, error)` — optional — is called with the final delivery
    outcome (thread path runs the real send; Celery path reports optimistic
    acceptance since the worker owns retries). Returns True when the email
    was accepted/queued.
    """
    if isinstance(to_emails, str):
        to_emails = [to_emails]

    if getattr(settings, "USE_CELERY", False):
        send_email_task.delay(
            subject, plain_body, to_emails, html_body=html_body, from_email=from_email
        )
        if on_done:
            on_done(True, "")
        return True

    # No broker: send in a daemon thread so the request never blocks on SMTP.
    # On free tiers the thread is safe to run in the background because
    # `send_mail` opens its own connection and Django settings are immutable.
    t = threading.Thread(
        target=_thread_send,
        args=(subject, plain_body, to_emails, html_body, from_email, on_done),
        daemon=True,
    )
    t.start()
    return True