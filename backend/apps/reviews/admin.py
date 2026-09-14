from django.contrib import admin

from .models import Review


@admin.action(description="Approve selected reviews (show publicly)")
def approve(modeladmin, request, queryset):
    queryset.update(is_approved=True)


@admin.action(description="Hide selected reviews (remove from site)")
def hide(modeladmin, request, queryset):
    queryset.update(is_approved=False)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("display_name", "rating", "atmosphere", "facilities", "is_approved", "created_at")
    list_filter = ("is_approved", "rating")
    search_fields = ("name", "liked_most", "suggestion")
    actions = (approve, hide)
    list_per_page = 30
