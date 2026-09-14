from celery import shared_task

from .services import expire_cash_requests, expire_overdue_memberships, run_reminder_cycle


@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    retry_backoff=True,
    retry_backoff_max=600,
    acks_late=True,
)
def activate_membership_task(self, membership_id):
    """Activate one paid membership outside the request path.

    Runs after a payment is confirmed (verify or webhook). Retries with
    backoff so a transient seat/DB/email failure can never strand money.
    """
    from .models import Membership
    from .services import activate_membership

    try:
        return activate_membership(Membership.objects.get(pk=membership_id))
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task
def expire_memberships_task():
    """Periodic: release expired memberships so their seats free up."""
    return expire_overdue_memberships()


@shared_task
def run_membership_reminders():
    """Daily: expire overdue memberships and send renewal reminders."""
    return run_reminder_cycle()


@shared_task
def expire_cash_payment_requests():
    """Periodic: cancel cash requests that were not approved within 3 days."""
    return expire_cash_requests()
