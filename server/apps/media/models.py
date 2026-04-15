"""MediaAsset — a single file registered in the Kinoro library.

Populated by the ingest pipeline (apps.media.services.ingest_asset), which
runs probe + poster extraction on a background thread after create.
"""

from __future__ import annotations

from django.db import models

from apps.core.models import BaseModel


class MediaAsset(BaseModel):
    class Kind(models.TextChoices):
        VIDEO = "video", "Video"
        AUDIO = "audio", "Audio"
        IMAGE = "image", "Image"
        UNKNOWN = "unknown", "Unknown"

    class Status(models.TextChoices):
        INGESTING = "ingesting", "Ingesting"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    class ProxyStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        BUILDING = "building", "Building"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    name = models.CharField(max_length=300)
    source_path = models.CharField(max_length=500)
    kind = models.CharField(
        max_length=10, choices=Kind.choices, default=Kind.UNKNOWN
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.INGESTING
    )

    duration = models.FloatField(null=True, blank=True)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    fps = models.FloatField(null=True, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)

    probe_json = models.JSONField(default=dict, blank=True)
    thumbnail_path = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Path relative to MEDIA_ROOT (e.g. 'thumbnails/<uuid>.jpg').",
    )
    proxy_path = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Path relative to KINORO_PROXY_DIR (e.g. '<uuid>.mp4').",
    )
    proxy_status = models.CharField(
        max_length=12,
        choices=ProxyStatus.choices,
        default=ProxyStatus.PENDING,
    )
    error_message = models.TextField(blank=True, default="")

    # Origin tracking for Video Planner imports — used by the VP importer to
    # dedupe (clicking "Import media" twice must not create two rows pointing
    # at the same disk file).
    vp_asset_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="VP vediteur MediaAsset id or Resource id this row was imported from.",
    )

    def __str__(self) -> str:
        return f"{self.name} ({self.kind})"
