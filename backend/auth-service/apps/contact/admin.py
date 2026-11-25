from django.contrib import admin

from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ["email", "name", "company", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["email", "name", "company", "phone"]
    readonly_fields = ["name", "email", "company", "phone", "message", "accept_terms", "ip_address", "user_agent", "created_at"]
