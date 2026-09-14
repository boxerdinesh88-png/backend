"""Security middleware: audit logging + basic per-IP rate limiting."""
import time

from django.utils import timezone

from apps.core.ip import client_ip

from .models import AuditLog


class AuditLogMiddleware:
    """Record every request for staff/admin users as an audit trail."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if user and user.is_authenticated and (user.is_staff or user.is_admin):
            try:
                AuditLog.objects.create(
                    user=user,
                    actor_email=user.email,
                    action=f"{request.method} {request.path}",
                    ip=client_ip(request),
                    path=request.path,
                    method=request.method,
                    status_code=response.status_code,
                )
            except Exception:
                # Audit trail must never break the request (e.g. DB hiccup).
                pass
        return response


class RateLimitMiddleware:
    """Simple in-memory sliding-window limiter for anonymous abuse.

    Production should rely on DRF throttles / a CDN / Redis-based limits.
    Adjusted for FREE plan to reduce memory footprint.
    """

    WINDOW = 60
    MAX_HITS = 100  # Reduced from 300 for FREE plan
    MAX_TRACKED_IPS = 1000  # Reduced from 5000 for FREE plan
    _hits = {}
    _last_prune = 0.0

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        key = client_ip(request)
        now = time.time()
        if now - self._last_prune > self.WINDOW:
            self._prune(now)
        bucket = self._hits.setdefault(key, [])
        bucket[:] = [t for t in bucket if now - t < self.WINDOW]
        if len(bucket) >= self.MAX_HITS and not request.path.startswith("/static/"):
            from django.http import HttpResponse

            return HttpResponse("Rate limit exceeded", status=429)
        bucket.append(now)
        return self.get_response(request)

    def _prune(self, now):
        """Drop stale windows and evict idle IPs so the table never grows unbounded."""
        cutoff = now - self.WINDOW
        stale = [k for k, v in self._hits.items() if not v or v[-1] < cutoff]
        for k in stale:
            del self._hits[k]
        if len(self._hits) > self.MAX_TRACKED_IPS:
            for k in list(self._hits)[: len(self._hits) - self.MAX_TRACKED_IPS]:
                del self._hits[k]
        type(self)._last_prune = now
