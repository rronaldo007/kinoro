"""Project — single editable timeline.

Thin metadata record. Editable state (tracks, clips, selection) lives in
``timeline_json`` per ``docs/PROJECT_FORMAT.md``. The same JSON shape is
consumed by ``engine/deliver/timeline_render.py`` (M5), so do not fork
the schema without also updating the render pipeline.
"""

from __future__ import annotations

from django.db import models

from apps.core.models import BaseModel


class Project(BaseModel):
    name = models.CharField(max_length=200)
    fps = models.PositiveIntegerField(default=30)
    width = models.PositiveIntegerField(default=1920)
    height = models.PositiveIntegerField(default=1080)
    timeline_json = models.JSONField(default=dict, blank=True)
    render_settings = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.name
