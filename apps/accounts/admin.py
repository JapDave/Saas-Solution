from django.contrib import admin
from .models.account import Account

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_email", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "contact_email")
    readonly_fields = ("created_at", "updated_at", "deleted_at")
