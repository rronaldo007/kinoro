from __future__ import annotations

from rest_framework import serializers

from .models import VPAccount, VPImportJob


class VPAccountSerializer(serializers.ModelSerializer):
    """Safe read-only view of VPAccount — never expose tokens."""

    class Meta:
        model = VPAccount
        fields = ["id", "base_url", "email", "user_payload", "created_at"]
        read_only_fields = fields


class VPLoginSerializer(serializers.Serializer):
    base_url = serializers.URLField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class VPImportJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = VPImportJob
        fields = [
            "id",
            "source",
            "remote_project_id",
            "status",
            "progress",
            "error_message",
            "kinoro_project_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
