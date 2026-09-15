"""Throttle that keys OTP/auth limits by email, not just client IP.

A pure per-IP `ScopedRateThrottle` breaks legitimate bursts: 15-20 students
registering at once from the same library Wi-Fi all share one NAT IP, so the
3rd+ request gets 429'd and the OTP "never arrives". By keying on the email in
the request body, every member gets their own budget while abuse is still
capped per address. Requests without an email (e.g. phone OTP) fall back to
per-IP, preserving the old behaviour.
"""
from rest_framework.throttling import ScopedRateThrottle


class EmailScopedThrottle(ScopedRateThrottle):
    def get_cache_key(self, request, view):
        scope = getattr(self, "scope", None)
        if not scope:
            return None

        email = ""
        try:
            raw = getattr(request, "data", None) or {}
            email = (raw.get("email") or "").strip().lower()
        except Exception:
            email = ""

        ident = email or self.get_ident(request)
        return self.cache_format % {"scope": scope, "ident": ident}