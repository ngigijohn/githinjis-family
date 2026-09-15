from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .groups import ensure_family_editors_group

admin.site.unregister(User)


@admin.register(User)
class FamilyUserAdmin(UserAdmin):
    list_display = ["username", "email", "first_name", "last_name", "is_active", "is_staff", "date_joined"]
    list_filter = ["is_active", "is_staff", "groups"]
    ordering = ["-date_joined"]
    actions = ["approve_as_family_editor"]

    @admin.action(description="Approve selected accounts as Family Editors")
    def approve_as_family_editor(self, request, queryset):
        group = ensure_family_editors_group()
        for user in queryset:
            user.is_active = True
            user.save(update_fields=["is_active"])
            user.groups.add(group)
        self.message_user(request, f"Approved {queryset.count()} account(s).", messages.SUCCESS)
