"""Build and send professional branded transactional emails for memberships."""
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

LIBRARY_PHONE = "+91 8804162854"
LIBRARY_EMAIL = "Phagendrababulibrary@gmail.com"
LIBRARY_ADDRESS = "Vill- Kharhat, Begusarai, Bihar 851217"


def _membership_context(membership):
    seat = membership.seat
    try:
        payment = membership.payment
    except Exception:
        payment = None
    payment_ref = ""
    payment_method = (membership.payment_method or "upi").upper()
    if payment is not None and payment.method:
        payment_method = (payment.method or "upi").upper()
        payment_ref = (
            payment.razorpay_payment_id
            or payment.transaction_id
        )

    return {
        "member_name": membership.member.name,
        "booking_id": str(membership.id),
        "shift_name": membership.shift.name,
        "hours": f"{membership.shift.start_time:%H:%M} – {membership.shift.end_time:%H:%M}",
        "seat": seat.seat_number if seat else "Will be assigned",
        "section": seat.get_section_display() if seat else "",
        "premium": membership.is_premium or bool(seat and seat.is_premium),
        "premium_percent": seat.premium_percent if (seat and (membership.is_premium or seat.is_premium)) else None,
        "months": membership.duration_months,
        "plan_label": membership.get_plan_type_display(),
        "start_date": membership.start_date,
        "end_date": membership.end_date,
        "amount": membership.amount,
        "payment_method": payment_method,
        "payment_ref": payment_ref,
        "dashboard_url": f"{settings.FRONTEND_URL}/dashboard",
        "renew_url": f"{settings.FRONTEND_URL}/membership",
        "features_url": f"{settings.FRONTEND_URL}/#features",
        "terms_url": f"{settings.FRONTEND_URL}/terms",
        "help_url": f"{settings.FRONTEND_URL}/help",
        "library_phone": LIBRARY_PHONE,
        "library_email": LIBRARY_EMAIL,
        "library_address": LIBRARY_ADDRESS,
    }


def build_membership_confirmation(membership):
    """Return (subject, plain_text, html) for the seat-confirmation email."""
    ctx = _membership_context(membership)
    subject = f"Your seat is confirmed · {ctx['shift_name']} · Phagendra Babu Library"
    plain = (
        f"Hi {ctx['member_name']},\n\n"
        "Your seat at Phagendra Babu Library is confirmed!\n\n"
        f"Booking ID : {ctx['booking_id']}\n"
        f"Time block : {ctx['shift_name']} ({ctx['hours']})\n"
        f"Seat       : {ctx['seat']}"
        f"{' (' + ctx['section'] + ')' if ctx['section'] else ''}\n"
        + (f"Seat type  : PREMIUM (+{ctx['premium_percent']}% of base price)\n" if ctx["premium"] and ctx["premium_percent"] else "")
        + f"Duration   : {ctx['plan_label']}\n"
        f"Valid      : {ctx['start_date']} → {ctx['end_date']}\n"
        f"Amount paid: ₹{ctx['amount']}\n"
        f"Payment    : {ctx['payment_method']}"
        f"{' (' + ctx['payment_ref'] + ')' if ctx['payment_ref'] else ''}\n\n"
        "Show this booking ID at the front desk to claim your seat, or view it "
        f"anytime at {ctx['dashboard_url']}.\n\n"
        f"Features         : {ctx['features_url']}\n"
        f"Terms of Service : {ctx['terms_url']}\n"
        f"Help & support   : {ctx['help_url']}\n\n"
        f"Phagendra Babu Library\n{ctx['library_address']}\n"
        f"{ctx['library_phone']} · {ctx['library_email']}\n"
        "Managed by Akash Kumar"
    )
    html = render_to_string("emails/membership_confirmation.html", ctx)
    return subject, plain, html


def build_membership_renewal(membership):
    """Return (subject, plain_text, html) for a renewed membership."""
    ctx = _membership_context(membership)
    subject = f"Your membership is renewed · {ctx['shift_name']} · Phagendra Babu Library"
    plain = (
        f"Hi {ctx['member_name']},\n\n"
        "Your Phagendra Babu Library membership has been renewed successfully.\n"
        "Your seat stays reserved for your time block — no action is needed.\n\n"
        f"Booking ID : {ctx['booking_id']}\n"
        f"Time block : {ctx['shift_name']} ({ctx['hours']})\n"
        f"Seat       : {ctx['seat']}"
        f"{' (' + ctx['section'] + ')' if ctx['section'] else ''}\n"
        + (f"Seat type  : PREMIUM (+{ctx['premium_percent']}% of base price)\n" if ctx["premium"] and ctx["premium_percent"] else "")
        + f"Plan       : {ctx['plan_label']}\n"
        f"New term   : {ctx['start_date']} → {ctx['end_date']}\n"
        f"Amount paid: ₹{ctx['amount']}\n"
        f"Payment    : {ctx['payment_method']}"
        f"{' (' + ctx['payment_ref'] + ')' if ctx['payment_ref'] else ''}\n\n"
        "Thank you for continuing with Phagendra Babu Library — we're glad to "
        "keep your seat ready for you.\n\n"
        f"View membership  : {ctx['dashboard_url']}\n"
        f"Features         : {ctx['features_url']}\n"
        f"Terms of Service : {ctx['terms_url']}\n"
        f"Help & support   : {ctx['help_url']}\n\n"
        f"Phagendra Babu Library\n{ctx['library_address']}\n"
        f"{ctx['library_phone']} · {ctx['library_email']}\n"
        "Managed by Akash Kumar"
    )
    html = render_to_string("emails/membership_renewal.html", ctx)
    return subject, plain, html


def build_cash_request_acknowledgement(membership):
    """Return (subject, plain_text, html) for the cash-request acknowledgement."""
    ctx = _membership_context(membership)
    expires_at = membership.cash_request_expires_at
    ctx["cash_expires"] = (
        timezone.localtime(expires_at).strftime("%d %b %Y, %I:%M %p")
        if expires_at
        else ""
    )
    ctx["heading"] = "Cash booking request received"
    ctx["body_note"] = (
        f"Your seat is reserved for the next 3 days, until {ctx['cash_expires']}. "
        "Please visit the library desk and pay the amount in cash within this "
        "window. Once the library confirms your payment, your seat pass is "
        "activated automatically."
    )
    subject = "Cash booking request received · seat held for 3 days"
    plain = (
        f"Hi {ctx['member_name']},\n\n"
        "We received your cash booking request.\n\n"
        f"Request ID : {ctx['booking_id']}\n"
        f"Time block : {ctx['shift_name']} ({ctx['hours']})\n"
        f"Seat       : {ctx['seat']}"
        f"{' (' + ctx['section'] + ')' if ctx['section'] else ''}\n"
        + (f"Seat type  : PREMIUM (+{ctx['premium_percent']}% of base price)\n" if ctx["premium"] and ctx["premium_percent"] else "")
        + f"Duration   : {ctx['plan_label']}\n"
        f"Amount     : ₹{ctx['amount']} (to be paid in cash)\n\n"
        f"{ctx['body_note']}\n\n"
        f"Request status can be viewed anytime at {ctx['dashboard_url']}.\n\n"
        f"Phagendra Babu Library\n{ctx['library_address']}\n"
        f"{ctx['library_phone']} · {ctx['library_email']}\n"
        "Managed by Akash Kumar"
    )
    html = render_to_string("emails/cash_request.html", ctx)
    return subject, plain, html


def build_manual_payment_acknowledgement(membership):
    """Return (subject, plain_text, html) for the QR/manual payment ack."""
    ctx = _membership_context(membership)
    expires_at = membership.cash_request_expires_at
    try:
        payment = membership.payment
    except Exception:
        payment = None
    ctx["transaction_id"] = payment.transaction_id if payment else ""
    ctx["cash_expires"] = (
        timezone.localtime(expires_at).strftime("%d %b %Y, %I:%M %p")
        if expires_at
        else ""
    )
    ctx["heading"] = "UPI payment received — awaiting confirmation"
    ctx["body_note"] = (
        f"We received your UPI payment for ₹{ctx['amount']} "
        f"(transaction {ctx['transaction_id']}). Your seat is reserved for the "
        f"next 3 days, until {ctx['cash_expires']}. The library verifies each "
        "transfer manually — once confirmed, your seat pass is activated "
        "automatically and you will receive a confirmation email."
    )
    subject = "UPI payment received · seat held while we confirm"
    plain = (
        f"Hi {ctx['member_name']},\n\n"
        "We received your UPI payment details.\n\n"
        f"Booking ID    : {ctx['booking_id']}\n"
        f"Transaction ID: {ctx['transaction_id']}\n"
        f"Amount        : ₹{ctx['amount']}\n"
        f"Time block    : {ctx['shift_name']} ({ctx['hours']})\n"
        f"Seat          : {ctx['seat']}"
f"{' (' + ctx['section'] + ')' if ctx['section'] else ''}\n"
        + (f"Seat type     : PREMIUM (+{ctx['premium_percent']}% of base price)\n" if ctx["premium"] and ctx["premium_percent"] else "")
        + f"Duration      : {ctx['plan_label']}\n\n"
        f"{ctx['body_note']}\n\n"
        f"Request status can be viewed anytime at {ctx['dashboard_url']}.\n\n"
        f"Phagendra Babu Library\n{ctx['library_address']}\n"
        f"{ctx['library_phone']} · {ctx['library_email']}\n"
        "Managed by Akash Kumar"
    )
    html = render_to_string("emails/manual_payment.html", ctx)
    return subject, plain, html


def build_library_subscription_notice(membership):
    """Return (subject, plain_text, html) for an internal notice to the library.

    Sent when a member initiates a cash/QR-manual payment booking so the
    library can verify the member and check them in within the hold window.
    """
    ctx = _membership_context(membership)
    member = membership.member
    ctx["member_email"] = member.email
    ctx["member_phone"] = member.phone or ""
    ctx["member_class"] = member.class_name
    ctx["member_gender"] = member.get_gender_display()
    expires_at = membership.cash_request_expires_at
    ctx["cash_expires"] = (
        timezone.localtime(expires_at).strftime("%d %b %Y, %I:%M %p")
        if expires_at
        else ""
    )
    subject = (
        f"New subscription taken · {ctx['member_name']} · {ctx['shift_name']} · Phagendra Babu Library"
    )
    plain = (
        "The following member has taken a subscription at Phagendra Babu Library.\n"
        "Please check the booking below and take the response within the given time.\n\n"
        f"Booking ID : {ctx['booking_id']}\n"
        f"Member     : {ctx['member_name']} <{ctx['member_email']}>\n"
        f"Phone      : {ctx['member_phone'] or '—'}"
        f"{' · ' + ctx['member_class'] if ctx['member_class'] else ''}"
        f" · {ctx['member_gender']}\n"
        f"Time block : {ctx['shift_name']} ({ctx['hours']})\n"
        f"Seat       : {ctx['seat']}"
        f"{' (' + ctx['section'] + ')' if ctx['section'] else ''}\n"
        + (f"Seat type  : PREMIUM (+{ctx['premium_percent']}% of base price)\n" if ctx["premium"] and ctx["premium_percent"] else "")
        + f"Plan       : {ctx['plan_label']}\n"
        f"Valid      : {ctx['start_date']} → {ctx['end_date']}\n"
        f"Amount     : ₹{ctx['amount']}\n"
        f"Payment    : {ctx['payment_method']}"
        f"{' (' + ctx['payment_ref'] + ')' if ctx['payment_ref'] else ''}\n"
        + (f"Respond by : {ctx['cash_expires']}\n" if ctx["cash_expires"] else "")
        + "\n"
        "If no response is received before the deadline, the booking is "
        "automatically cancelled and the seat is released.\n\n"
        f"Phagendra Babu Library\n{ctx['library_address']}\n"
        f"{ctx['library_phone']} · {ctx['library_email']}\n"
        "Managed by Akash Kumar"
    )
    html = render_to_string("emails/library_subscription_notice.html", ctx)
    return subject, plain, html


def build_payment_rejection(membership, reason):
    """Return (subject, plain_text, html) for a rejected payment review."""
    ctx = _membership_context(membership)
    ctx["reason"] = reason
    ctx["heading"] = "Payment could not be verified"
    ctx["body_note"] = (
        "Our team could not verify the payment for this booking. "
        "The held seat has been released, so you can book again with a "
        "different payment method or contact us for help."
    )
    subject = "Payment couldn't be verified · please book again"
    plain = (
        f"Hi {ctx['member_name']},\n\n"
        f"We could not verify your payment for booking {ctx['booking_id']}.\n\n"
        + (f"Reason noted: {reason}\n\n" if reason else "")
        + f"{ctx['body_note']}\n\n"
        f"Book again: {ctx['renew_url']}\n"
        f"Questions? Call us at {ctx['library_phone']}.\n\n"
        f"Phagendra Babu Library\n{ctx['library_address']}\n"
        f"{ctx['library_phone']} · {ctx['library_email']}\n"
        "Managed by Akash Kumar"
    )
    html = render_to_string("emails/payment_rejected.html", ctx)
    return subject, plain, html


def build_membership_reminder(membership, type_):
    """Return (subject, plain_text, html) for an expiry warning / renewal reminder."""
    ctx = _membership_context(membership)
    today = timezone.localdate()
    days_left = (membership.end_date - today).days if membership.end_date else 0

    if type_ == "expiry_warning":
        ctx["days_left"] = 7
        heading = "Your membership expires in 7 days"
        subject = "Your Phagendra Babu Library membership expires in 7 days"
        body_note = (
            f"This is a heads-up that your membership runs out in 7 days "
            f"({ctx['end_date']}). Renew now to keep your seat."
        )
    elif type_ == "reminder_3day":
        ctx["days_left"] = 3
        heading = "Your membership expires in 3 days"
        subject = "Your Phagendra Babu Library membership expires in 3 days"
        body_note = (
            f"Reminder: your membership runs out in 3 days "
            f"({ctx['end_date']}). Renew today so your seat stays reserved."
        )
    else:
        ctx["days_left"] = max(days_left, 1)
        heading = "Your membership expires tomorrow"
        subject = "Your Phagendra Babu Library membership expires tomorrow"
        body_note = (
            f"This is your final reminder — your membership ends tomorrow "
            f"({ctx['end_date']}). Renew today so your seat stays reserved."
        )

    ctx["heading"] = heading
    ctx["body_note"] = body_note

    plain = (
        f"Hi {ctx['member_name']},\n\n"
        f"{heading}!\n\n"
        f"{body_note}\n\n"
        f"Time block : {ctx['shift_name']} ({ctx['hours']})\n"
        f"Seat       : {ctx['seat']}\n"
        f"Valid until: {ctx['end_date']}\n\n"
        "Dear Member, please note the following points regarding your library seat renewal:\n\n"
        "1. Kindly complete the renewal process within the stipulated time to ensure the "
        "continuation of your seat.\n"
        "2. If the subscription is not renewed within the given time, the management reserves "
        "the right to allocate your seat to another member.\n"
        "3. Once the seat is allotted to another member, its availability cannot be guaranteed.\n"
        "4. For any queries regarding renewal, please contact the library management.\n\n"
        "Thank you for your cooperation.\n"
        "Phagendra Babu Library Management\n\n"
        f"Renew online anytime: {ctx['renew_url']}\n"
        f"Questions? Call us at {ctx['library_phone']}.\n\n"
        f"Phagendra Babu Library\n{ctx['library_address']}\n"
        f"{ctx['library_phone']} · {ctx['library_email']}\n"
        "Managed by Akash Kumar"
    )
    html = render_to_string("emails/membership_expiry.html", ctx)
    return subject, plain, html
