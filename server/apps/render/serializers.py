from __future__ import annotations

from rest_framework import serializers

from .models import RenderJob


class RenderJobSerializer(serializers.ModelSerializer):
    output_url = serializers.SerializerMethodField()

    class Meta:
        model = RenderJob
        fields = [
            "id",
            "project",
            "preset_name",
            "status",
            "progress",
            "output_path",
            "output_url",
            "error_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "progress",
            "output_path",
            "output_url",
            "error_message",
            "created_at",
            "updated_at",
        ]

    def get_output_url(self, obj: RenderJob) -> str | None:
        if not obj.output_path:
            return None
        return f"/renders/{obj.output_path}"


class RenderJobCreateSerializer(serializers.Serializer):
    project = serializers.UUIDField()
    preset_name = serializers.CharField(
        max_length=48, required=False, default="youtube_1080p"
    )
