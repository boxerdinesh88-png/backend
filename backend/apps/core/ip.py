"""Client IP extraction.

``X-Forwarded-For`` is only honored when ``TRUST_X_FORWARDED_FOR`` is enabled
(you are behind a reverse proxy you control). Otherwise any client could
spoof the IP used for audit logs and rate limiting.
"""
from django.conf import settings


def client_ip(request):
    if getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
