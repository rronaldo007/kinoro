"""RenderJob — one export attempt of a Kinoro Project's timeline."""

from __future__ import annotations

from django.db import models

from apps.core.models import BaseModel


class RenderJob(BaseModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RENDERING = "rendering", "Rendering"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="render_jobs",
    )
    preset_name = models.CharField(
        max_length=48,
        default="youtube_1080p",
        help_text="Label only — render settings live in the engine preset.",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.QUEUED
    )
    progress = models.FloatField(default=0.0)
    output_path = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Path relative to KINORO_RENDER_DIR (e.g. '<uuid>.mp4').",
    )
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"RenderJob {self.id} · {self.status}"
