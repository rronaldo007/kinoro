"""Video Planner account + import job tracking.

Single-account model: Kinoro is a single-user desktop app, so we store at most
one VPAccount at a time. The access_token expires every ~1 hour and is
refreshed via refresh_token.
"""

from __future__ import annotations

from django.db import models

from apps.core.models import BaseModel


class VPAccount(BaseModel):
    """A logged-in Video Planner account. At most one row exists at a time."""

    base_url = models.URLField(
        help_text="Video Planner base URL, e.g. https://api.videoplanner.io",
        default="https://api.videoplanner.io",
    )
    email = models.EmailField()
    access_token = models.TextField(blank=True, default="")
    refresh_token = models.TextField(blank=True, default="")
    access_expires_at = models.DateTimeField(null=True, blank=True)
    user_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="The `user` object returned by /api/auth/login/ — name, avatar, plan.",
    )

    class Meta:
        verbose_name = "Video Planner account"


class VPImportJob(BaseModel):
    """Tracks progress of a single 'pull a VP project into Kinoro' job."""

    STATUS_CHOICES = (
        ("queued", "Queued"),
        ("fetching_project", "Fetching project"),
        ("downloading_media", "Downloading media"),
        ("building_proxies", "Building proxies"),
        ("done", "Done"),
        ("failed", "Failed"),
    )

    SOURCE_CHOICES = (
        ("api", "Live API"),
        ("zip", "ZIP file"),
    )

    account = models.ForeignKey(
        VPAccount,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="import_jobs",
        help_text="Null for zip-based imports (no account required).",
    )
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES)
    remote_project_id = models.CharField(max_length=64, blank=True, default="")
    zip_path = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="queued")
    progress = models.FloatField(default=0.0)
    error_message = models.TextField(blank=True, default="")
    kinoro_project_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Populated once the Kinoro-side Project row is created.",
    )
