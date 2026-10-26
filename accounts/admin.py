from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import User


@admin.register(User)
class AccountAdmin(UserAdmin):
    list_display = ("username", "email", "roll_number", "role", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("username", "email", "roll_number", "first_name", "last_name")
    fieldsets = UserAdmin.fieldsets + (
        ("Portal", {"fields": ("role", "roll_number")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Portal", {"fields": ("role", "email", "roll_number")}),
    )
