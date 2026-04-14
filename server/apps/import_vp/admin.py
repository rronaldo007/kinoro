from django.contrib import admin

from .models import VPAccount, VPImportJob


@admin.register(VPAccount)
class VPAccountAdmin(admin.ModelAdmin):
    list_display = ("email", "base_url", "access_expires_at", "created_at")
    readonly_fields = ("access_token", "refresh_token")


@admin.register(VPImportJob)
class VPImportJobAdmin(admin.ModelAdmin):
    list_display = ("source", "status", "progress", "remote_project_id", "created_at")
    list_filter = ("source", "status")
    readonly_fields = ("created_at", "updated_at")
