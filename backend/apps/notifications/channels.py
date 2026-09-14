"""Pluggable notification channels.

Business logic talks to `service.notify()` only; a new channel (SMS, WhatsApp,
push) is added by subclassing `NotificationChannel` and registering it in
`get_enabled_channels()` — no membership/payment code changes required.
"""
import logging
from abc import ABC, abstractmethod

from django.conf import settings

from .tasks import dispatch_email

logger = logging.getLogger("libseat.notifications")


class NotificationChannel(ABC):
    key = ""

    @abstractmethod
    def send(self, user, subject, body):
        ...


class EmailChannel(NotificationChannel):
    key = "email"

    def send(self, user, subject, body, html=None):
        dispatch_email(subject, body, user.email, html_body=html)


class SmsChannel(NotificationChannel):
    """SMS channel (launch-ready stub). Uses Twilio when configured, else logs.

    Per the spec assumptions SMS/WhatsApp is a v2 channel; adding it later is
    a matter of flipping this on without touching membership logic.
    """

    key = "sms"

    def send(self, user, subject, body):
        phone = getattr(user, "phone", "") or ""
        if settings.SMS_PROVIDER.lower() == "twilio" and settings.TWILIO_ACCOUNT_SID:
            try:
                from twilio.rest import Client

                client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                client.messages.create(
                    to=phone, from_=settings.TWILIO_FROM_NUMBER, body=body
                )
                return
            except Exception:
                logger.exception("Twilio SMS failed for %s", phone)
        logger.info("SMS to %s: %s", phone, body)


def get_enabled_channels():
    channels = [EmailChannel()]
    if settings.SMS_PROVIDER:
        channels.append(SmsChannel())
    return channels
