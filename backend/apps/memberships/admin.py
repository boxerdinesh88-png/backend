from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html

from .models import DurationDiscount, Membership, Payment
from .services import activate_membership, _release_membership_booking


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = (
        "id", "member", "shift", "seat", "plan_type", "duration_months",
        "start_date", "end_date", "status", "payment_method",
        "cash_request_expires_at", "amount", "cash_actions",
    )
    list_filter = ("status", "payment_method", "shift")
    search_fields = ("member__email", "member__name", "seat__seat_number")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("member", "seat")
    actions = ("approve_cash_requests", "decline_cash_requests")

    # ------------------------------------------------------------- helpers
    def _decline(self, membership):
        """Cancel a pending cash request and release its held seat."""
        _release_membership_booking(membership)
        membership.status = "cancelled"
        membership.cash_request_expires_at = None
        membership.save(update_fields=["status", "cash_request_expires_at"])

    # ---------------------------------------------------- per-row buttons
    def changelist_view(self, request, extra_context=None):
        self._admin_request = request
        return super().changelist_view(request, extra_context=extra_context)

    @admin.display(description="Actions")
    def cash_actions(self, obj):
        if obj.status != "pending_cash":
            return "—"
        approve = reverse("admin:memberships_membership_approve_cash", args=[obj.id])
        decline = reverse("admin:memberships_membership_decline_cash", args=[obj.id])
        csrf = get_token(getattr(self, "_admin_request", None))
        return format_html(
            '<form method="post" action="{}" style="display:inline">'
            '<input type="hidden" name="csrfmiddlewaretoken" value="{}">'
            '<button type="submit" class="button" style="background:#059669;color:#fff;'
            'border:none;border-radius:4px;padding:4px 10px;cursor:pointer">Approve</button>'
            '</form> '
            '<form method="post" action="{}" style="display:inline">'
            '<input type="hidden" name="csrfmiddlewaretoken" value="{}">'
            '<button type="submit" class="button" style="background:#e11d48;color:#fff;'
            'border:none;border-radius:4px;padding:4px 10px;cursor:pointer">Decline</button>'
            '</form>',
            approve, csrf, decline, csrf,
        )

    # ------------------------------------------------------- custom URLs
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<uuid:pk>/approve-cash/",
                self.admin_site.admin_view(self.approve_cash_view),
                name="memberships_membership_approve_cash",
            ),
            path(
                "<uuid:pk>/decline-cash/",
                self.admin_site.admin_view(self.decline_cash_view),
                name="memberships_membership_decline_cash",
            ),
        ]
        return custom + urls

    def _redirect_back(self, request):
        return HttpResponseRedirect(
            reverse("admin:memberships_membership_changelist")
        )

    def approve_cash_view(self, request, pk):
        membership = get_object_or_404(Membership, pk=pk)
        if membership.status == "pending_cash":
            try:
                activate_membership(membership)
            except Exception as exc:
                import logging

                logging.getLogger("libseat.memberships").exception(
                    "admin approve failed for membership %s", membership.id
                )
                self.message_user(
                    request,
                    f"Approval failed: {exc}",
                    messages.ERROR,
                )
                return self._redirect_back(request)
            self.message_user(
                request,
                f"Cash request approved — seat booked for {membership.member.name}.",
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                "Only pending cash requests can be approved.",
                messages.WARNING,
            )
        return self._redirect_back(request)

    def decline_cash_view(self, request, pk):
        membership = get_object_or_404(Membership, pk=pk)
        if membership.status == "pending_cash":
            self._decline(membership)
            self.message_user(
                request,
                f"Cash request declined — seat released for {membership.member.name}.",
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                "Only pending cash requests can be declined.",
                messages.WARNING,
            )
        return self._redirect_back(request)

    # --------------------------------------------------- bulk actions
    @admin.action(description="Approve selected cash requests")
    def approve_cash_requests(self, request, queryset):
        count = 0
        for membership in queryset.filter(status="pending_cash"):
            activate_membership(membership)
            count += 1
        self.message_user(
            request,
            f"{count} cash request(s) approved and activated.",
            messages.SUCCESS,
        )

    @admin.action(description="Decline selected cash requests")
    def decline_cash_requests(self, request, queryset):
        count = 0
        for membership in queryset.filter(status="pending_cash"):
            self._decline(membership)
            count += 1
        self.message_user(
            request,
            f"{count} cash request(s) declined and seats released.",
            messages.SUCCESS,
        )

    # ------------------------------------------------------- save handling
    def save_model(self, request, obj, form, change):
        if change and obj.status == "active" and "status" in form.changed_data:
            prior_status = form.initial.get("status")
            super().save_model(request, obj, form, change)
            if prior_status and prior_status != "active":
                obj.status = prior_status
                activate_membership(obj)
            return
        super().save_model(request, obj, form, change)
        if obj.status in ("cancelled", "expired", "pending_payment"):
            _release_membership_booking(obj)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "membership", "amount", "method", "status", "razorpay_order_id",
        "razorpay_payment_id", "paid_at",
    )
    list_filter = ("status", "method")
    search_fields = ("razorpay_order_id", "razorpay_payment_id")
    readonly_fields = ("created_at", "paid_at")


@admin.register(DurationDiscount)
class DurationDiscountAdmin(admin.ModelAdmin):
    list_display = ("min_months", "discount_percent", "is_active")
    list_editable = ("discount_percent", "is_active")
    ordering = ("min_months",)
