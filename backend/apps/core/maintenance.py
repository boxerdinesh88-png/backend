"""Periodic-maintenance helpers for hosts without cron / Celery beat.

Free tiers (e.g. PythonAnywhere) cannot run scheduled tasks. Instead of relying
on beat to expire stale holds and overdue memberships, we run the same
maintenance lazily on read-heavy endpoints, throttled to once per minute via
the cache. This keeps the P0 invariant intact: seats are never locked forever
after a hold timer or a membership ends.
"""
import logging

from django.core.cache import cache

logger = logging.getLogger("libseat.maintenance")

MAINTENANCE_INTERVAL_SECONDS = 120  # Increased from 60s to reduce DB load on free tier
_CACHE_KEY = "maintenance:last_run"


def run_light_maintenance(force=False) -> bool:
    """Run cheap expiry jobs at most once per minute. Returns True when run."""
    from apps.memberships.services import expire_cash_requests, expire_overdue_memberships
    from apps.seats.services import expire_stale_holds

    if not force and cache.get(_CACHE_KEY):
        return False
    cache.set(_CACHE_KEY, 1, MAINTENANCE_INTERVAL_SECONDS)

    expired_holds = expire_stale_holds()
    expired_cash = expire_cash_requests()
    expired_memberships = expire_overdue_memberships()
    if expired_holds or expired_cash or expired_memberships:
        logger.info(
            "lazy maintenance: expired holds=%s cash=%s memberships=%s",
            expired_holds, expired_cash, expired_memberships,
        )
    return True
