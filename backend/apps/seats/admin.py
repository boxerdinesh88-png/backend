from django.contrib import admin

from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "seat", "shift", "start_date", "end_date",
        "status", "held_until", "created_at",
    )
    list_filter = ("status", "shift")
    search_fields = ("user__email", "user__name", "seat__seat_number")
    autocomplete_fields = ("user", "seat", "shift")
    readonly_fields = ("created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Releasing an active hold on save is the only admin maintenance
        # needed; explicit release lives on the member flow / Celery task.
        if obj.status in ("cancelled", "expired"):
            obj.held_until = None
            super().save_model(request, obj, form, change)
