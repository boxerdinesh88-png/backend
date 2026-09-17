from django.contrib import admin

from .models import Seat, Section, Shift


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "sort_order")
    ordering = ("sort_order", "code")


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ("name", "start_time", "end_time", "price", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ("seat_number", "zone", "section", "grid_col", "grid_row", "is_girls_only", "is_premium", "premium_percent", "is_active")
    list_filter = ("zone", "section", "is_girls_only", "is_premium", "is_active")
    list_editable = ("is_girls_only", "is_premium", "premium_percent", "is_active")
    search_fields = ("seat_number",)
