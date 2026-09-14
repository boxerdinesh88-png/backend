"""Notification service: deliver a message over every enabled channel and
log each delivery in NotificationLog."""
import logging

logger = logging.getLogger("libseat.notifications")


def notify_membership(membership, type_, subject, body, html=None, user=None):
    """Send `body` for `membership` via all enabled channels.

    `html` is an optional rich-text (HTML) version used by channels that
    support it (email); other channels ignore it and use `body`.

    Returns the list of channel keys that were delivered (and logged).
    """
    from .channels import get_enabled_channels
    from .models import NotificationLog

    user = user or membership.member
    sent = []
    for channel in get_enabled_channels():
        try:
            channel.send(user, subject, body, html)
        except Exception:
            logger.exception("Notification channel %s failed", channel.key)
            continue
        NotificationLog.objects.create(
            membership=membership, type=type_, channel=channel.key
        )
        sent.append(channel.key)
    return sent
