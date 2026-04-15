from django.contrib import admin

from .models import MediaAsset


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "kind",
        "status",
        "proxy_status",
        "duration",
        "size_bytes",
        "vp_asset_id",
        "created_at",
    )
    list_filter = ("kind", "status", "proxy_status")
    search_fields = ("name", "source_path", "vp_asset_id")
    readonly_fields = (
        "id",
        "probe_json",
        "thumbnail_path",
        "proxy_path",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)
