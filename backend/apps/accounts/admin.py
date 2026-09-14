from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import AuditLog, OTPCode, User


def _thumb(file_field, max_h="48px"):
    """Render a clickable thumbnail for a photo or Aadhaar file."""
    if not file_field:
        return "—"
    if str(file_field.name).lower().endswith(".pdf"):
        return format_html('<a href="{}" target="_blank">Open PDF ↗</a>', file_field.url)
    return format_html(
        '<a href="{}" target="_blank"><img src="{}" style="max-height:{}; max-width:120px; '
        'border-radius:8px; object-fit:cover;" /></a>',
        file_field.url,
        file_field.url,
        max_h,
    )


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)
    list_display = (
        "email", "name", "gender", "class_name", "role", "photo_preview",
        "aadhar_preview", "ip_address", "is_active", "date_joined",
    )
    search_fields = ("email", "name", "phone")
    list_filter = ("role", "gender", "is_active")
    readonly_fields = ("date_joined", "updated_at", "photo_preview", "aadhar_preview", "aadhar_back_preview")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("name", "phone", "gender", "role")}),
        ("Documents", {"fields": ("photo", "photo_preview", "aadhar_document", "aadhar_document_back", "aadhar_preview", "aadhar_back_preview")}),
        ("Study", {"fields": ("class_name", "purpose")}),
        ("Device", {"fields": ("wifi_device_name", "ip_address")}),
        ("Verification", {"fields": ("is_email_verified",)}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "name", "gender", "password1", "password2")}),
    )

    @admin.display(description="Photo")
    def photo_preview(self, obj):
        return _thumb(obj.photo)

    @admin.display(description="Aadhaar")
    def aadhar_preview(self, obj):
        return _thumb(obj.aadhar_document, max_h="72px")

    @admin.display(description="Aadhaar Back")
    def aadhar_back_preview(self, obj):
        return _thumb(obj.aadhar_document_back, max_h="72px")


@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "is_used", "expires_at", "created_at")
    list_filter = ("purpose", "is_used")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("actor_email", "action", "method", "status_code", "created_at")
    list_filter = ("method", "status_code")
    search_fields = ("actor_email", "action")
    readonly_fields = [f.name for f in AuditLog._meta.fields]
