"""Booking business logic: hold / confirm / cancel / expire seat reservations.

All conflict checks happen under a transaction with the seat row locked
(``select_for_update``) so two concurrent members can never hold the same
seat for the same slot.
"""
import logging
from datetime import date

from django.db import transaction
from django.utils import timezone

from .models import BOOKING_STATUS, Booking, HOLD_TTL

logger = logging.getLogger("libseat.seats")


class SeatHoldError(Exception):
    def __init__(self, message, code="seat_unavailable"):
        super().__init__(message)
        self.code = code


def _active_bookings_for(seat, shift, start, end, exclude_user=None, exclude_pk=None):
    now = timezone.now()
    qs = Booking.objects.select_for_update().filter(
        seat=seat,
        shift__start_time__lt=shift.end_time,
        shift__end_time__gt=shift.start_time,
        start_date__lte=end,
        end_date__gte=start,
        status__in=("held", "confirmed"),
    )
    if exclude_user:
        qs = qs.exclude(user=exclude_user)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return [b for b in qs if b.status == "confirmed" or b.held_until > now]


def booking_blocks_seat(seat, shift, start, end, user=None):
    """True when an active booking (by someone else) locks this seat/slot."""
    return bool(_active_bookings_for(seat, shift, start, end, exclude_user=user))


def held_by_other(seat, shift, start, end, user=None):
    """True when someone else is *currently holding* the seat (not confirmed)."""
    now = timezone.now()
    qs = Booking.objects.select_for_update().filter(
        seat=seat,
        shift__start_time__lt=shift.end_time,
        shift__end_time__gt=shift.start_time,
        start_date__lte=end,
        end_date__gte=start,
        status="held",
        held_until__gt=now,
    )
    if user:
        qs = qs.exclude(user=user)
    return qs.exists()


def validate_hold(user, seat, shift, start, end):
    if not seat.is_active:
        raise SeatHoldError("This seat is inactive.", code="seat_inactive")
    if not shift.is_active:
        raise SeatHoldError("This shift is no longer available.", code="shift_inactive")
    if seat.section not in user.allowed_sections:
        raise SeatHoldError(
            "This seat is outside your section. Pick a seat from your side of the hall.",
            code="section_mismatch",
        )
    if not user.is_email_verified:
        raise SeatHoldError(
            "Verify your email before holding a seat.", code="email_unverified"
        )


def hold_seat(user, seat, shift, start_date=None, end_date=None):
    """Reserve `seat` for the slot (shift, date range) and return the Booking.

    One active hold per user per slot; holding again refreshes the timer and
    silently releases any of the user's other held seats for the same slot.
    Raises ``SeatHoldError`` when the seat is taken or disallowed.
    """
    start_date = start_date or date.today()
    end_date = end_date or start_date
    if end_date < start_date:
        raise SeatHoldError("end_date must be on or after start_date.", code="invalid_date")

    with transaction.atomic():
        seat = type(seat).objects.select_for_update().get(pk=seat.pk)
        validate_hold(user, seat, shift, start_date, end_date)

        now = timezone.now()

        # A user keeps at most one active hold per slot — release the others.
        Booking.objects.filter(
            user=user,
            shift__start_time__lt=shift.end_time,
            shift__end_time__gt=shift.start_time,
            start_date__lte=end_date,
            end_date__gte=start_date,
            status="held",
        ).exclude(seat=seat).update(status="cancelled", held_until=None)

        conflict = _active_bookings_for(
            seat, shift, start_date, end_date, exclude_user=user
        )
        if conflict:
            raise SeatHoldError(
                "That seat was just taken for this slot. Pick another.",
                code="seat_taken",
            )

        booking = Booking.objects.filter(
            user=user,
            seat=seat,
            shift=shift,
            start_date=start_date,
            end_date=end_date,
        ).first()

        if booking is None:
            booking = Booking.objects.create(
                user=user,
                seat=seat,
                shift=shift,
                start_date=start_date,
                end_date=end_date,
                status="held",
                held_until=now + HOLD_TTL,
            )
        else:
            booking.status = "held"
            booking.held_until = now + HOLD_TTL
            booking.save(update_fields=["status", "held_until"])

        logger.info(
            "hold seat=%s shift=%s range=%s..%s user=%s",
            seat.seat_number, shift.name, start_date, end_date, user.email,
        )
        return booking


def cancel_booking(user, booking):
    """Release a held booking (owner only)."""
    if booking.user_id != user.id:
        raise SeatHoldError("You can only cancel your own booking.", code="not_owner")
    if booking.status != "held":
        raise SeatHoldError("Only held bookings can be cancelled.", code="bad_state")
    booking.status = "cancelled"
    booking.held_until = None
    booking.save(update_fields=["status", "held_until"])
    logger.info("cancel booking=%s user=%s", booking.id, user.email)
    return booking


def confirm_booking(user, booking):
    """Mark a booking confirmed after the seat is paid for."""
    if booking.user_id != user.id:
        raise SeatHoldError("You can only confirm your own booking.", code="not_owner")
    if booking.status not in ("held", "confirmed"):
        raise SeatHoldError("This booking can't be confirmed.", code="bad_state")
    booking.status = "confirmed"
    booking.held_until = None
    booking.save(update_fields=["status", "held_until"])
    logger.info("confirm booking=%s seat=%s user=%s",
                booking.id, booking.seat.seat_number, user.email)
    return booking


def confirm_for_membership(membership):
    """Confirm the member's held booking matching this now-active membership.

    Matches any live hold of the member for this seat/shift that overlaps the
    membership's slot, because ``activate_membership`` recomputes the date
    range (``compute_dates``) on the approval day — the original hold may
    cover slightly earlier dates. The booking's range is aligned to the
    membership's range before confirming so the two never disagree.
    """
    if not membership.seat_id:
        return None
    booking = (
        Booking.objects.filter(
            user=membership.member,
            seat=membership.seat,
            shift=membership.shift,
            status="held",
        )
        .filter(
            start_date__lte=membership.end_date,
            end_date__gte=membership.start_date,
        )
        .first()
    )
    if not booking:
        return None
    if (booking.start_date, booking.end_date) != (membership.start_date, membership.end_date):
        booking.start_date = membership.start_date
        booking.end_date = membership.end_date
        booking.save(update_fields=["start_date", "end_date"])
    return confirm_booking(membership.member, booking)


def expire_stale_holds():
    """Release every held booking past its timer (Celery beat / cron)."""
    now = timezone.now()
    expired = Booking.objects.filter(status="held", held_until__lte=now)
    count = expired.update(status="expired", held_until=None)
    if count:
        logger.info("expired %s stale holds", count)
    return count


def status_choices():
    return BOOKING_STATUS
