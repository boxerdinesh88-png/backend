from celery import shared_task

from .services import expire_stale_holds


@shared_task
def expire_hold_bookings():
    """Periodic (beat ~1 min): release held bookings past their 10-min timer."""
    return expire_stale_holds()
