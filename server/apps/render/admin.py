from django.contrib import admin

from .models import RenderJob


@admin.register(RenderJob)
class RenderJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "project",
        "status",
        "progress",
        "preset_name",
        "output_path",
        "created_at",
    )
    list_filter = ("status", "preset_name")
    readonly_fields = ("id", "output_path", "error_message", "created_at", "updated_at")
    ordering = ("-created_at",)
