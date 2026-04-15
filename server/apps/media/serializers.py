from __future__ import annotations

from django.conf import settings
from rest_framework import serializers

from .models import MediaAsset


class MediaAssetSerializer(serializers.ModelSerializer):
    thumbnail_url = serializers.SerializerMethodField()
    proxy_url = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = [
            "id",
            "name",
            "source_path",
            "kind",
            "status",
            "duration",
            "width",
            "height",
            "fps",
            "size_bytes",
            "thumbnail_path",
            "thumbnail_url",
            "proxy_path",
            "proxy_status",
            "proxy_url",
            "error_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "kind",
            "status",
            "duration",
            "width",
            "height",
            "fps",
            "size_bytes",
            "thumbnail_path",
            "thumbnail_url",
            "proxy_path",
            "proxy_status",
            "proxy_url",
            "error_message",
            "created_at",
            "updated_at",
        ]

    def get_thumbnail_url(self, obj: MediaAsset) -> str | None:
        if not obj.thumbnail_path:
            return None
        return f"{settings.MEDIA_URL}{obj.thumbnail_path}"

    def get_proxy_url(self, obj: MediaAsset) -> str | None:
        if not obj.proxy_path:
            return None
        return f"/proxies/{obj.proxy_path}"


class MediaAssetCreateSerializer(serializers.Serializer):
    source_path = serializers.CharField(max_length=500)
    name = serializers.CharField(max_length=300, required=False, allow_blank=True)
