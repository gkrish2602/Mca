from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class WorkspaceUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Workspace access', {'fields': ('role', 'organization')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Workspace access', {'fields': ('role', 'organization')}),
    )
    list_display = ('username', 'email', 'role', 'organization', 'is_staff')
    list_filter = UserAdmin.list_filter + ('role', 'organization')
