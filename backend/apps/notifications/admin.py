from django.contrib import admin

from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("membership", "type", "channel", "sent_at")
    list_filter = ("type", "channel")
    readonly_fields = [f.name for f in NotificationLog._meta.fields]
