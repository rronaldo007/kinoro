"""Project model — built in M2. Each project owns a timeline JSON.

Skeleton only for M0. The M2 schema will look like:

    class Project(BaseModel):
        name = models.CharField(max_length=200)
        fps = models.PositiveIntegerField(default=30)
        timeline_json = models.JSONField(default=dict)  # Timeline shape per docs/PROJECT_FORMAT.md

See docs/ROADMAP.md M2 for the full definition.
"""

from django.db import models  # noqa: F401
