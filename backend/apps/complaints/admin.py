from django.contrib import admin
from django.utils import timezone

from .models import Complaint


@admin.action(description="Mark selected complaints as resolved")
def mark_resolved(modeladmin, request, queryset):
    queryset.update(is_resolved=True, resolved_at=timezone.now())


@admin.action(description="Mark selected complaints as open")
def mark_open(modeladmin, request, queryset):
    queryset.update(is_resolved=False, resolved_at=None)


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = (
        "reference", "display_name", "category", "subject",
        "is_resolved", "created_at",
    )
    list_filter = ("is_resolved", "category", "created_at")
    search_fields = ("reference", "name", "contact", "subject", "description")
    readonly_fields = ("id", "reference", "created_at", "resolved_at")
    list_editable = ("is_resolved",)
    actions = (mark_resolved, mark_open)
    date_hierarchy = "created_at"
    list_per_page = 30
    fieldsets = (
        (
            "Complaint",
            {"fields": ("reference", "name", "contact", "category", "subject", "description")},
        ),
        (
            "Resolution",
            {"fields": ("is_resolved", "resolved_at", "admin_note")},
        ),
        (
            "Meta",
            {"fields": ("id", "created_at")},
        ),
    )

    @admin.display(description="Name")
    def display_name(self, obj):
        return obj.display_name
