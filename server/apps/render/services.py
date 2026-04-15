"""Render pipeline — run timeline_render on a daemon thread.

Resolves every clip's asset_id to the local MediaAsset source_path before
calling the framework-free ``engine.deliver.render_timeline``.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.db import close_old_connections

from apps.media.models import MediaAsset
from apps.projects.models import Project
from engine.deliver import RenderError, render_timeline

from .models import RenderJob

logger = logging.getLogger(__name__)


def _asset_maps(project: Project) -> tuple[dict[str, str], dict[str, bool]]:
    """Build {asset_id: source_path} + {asset_id: has_audio} from the project's
    timeline_json clips."""
    timeline = project.timeline_json or {}
    clips = timeline.get("clips") or []
    asset_ids = {str(c.get("asset_id")) for c in clips if c.get("asset_id")}
    assets = MediaAsset.objects.filter(id__in=asset_ids)
    paths: dict[str, str] = {}
    has_audio: dict[str, bool] = {}
    for a in assets:
        if a.status != MediaAsset.Status.READY:
            continue
        paths[str(a.id)] = a.source_path
        audio_streams = (a.probe_json or {}).get("audio") or []
        has_audio[str(a.id)] = bool(audio_streams)
    return paths, has_audio


def _run(job_id: UUID) -> None:
    try:
        job = RenderJob.objects.select_related("project").get(pk=job_id)
    except RenderJob.DoesNotExist:
        logger.warning("render: job %s vanished", job_id)
        return

    job.status = RenderJob.Status.RENDERING
    job.progress = 0.0
    job.save(update_fields=["status", "progress", "updated_at"])

    try:
        project = job.project
        paths, has_audio = _asset_maps(project)

        out_rel = f"{job.id}.mp4"
        out_abs = Path(settings.KINORO_RENDER_DIR) / out_rel
        out_abs.parent.mkdir(parents=True, exist_ok=True)

        def on_progress(p: float) -> None:
            # Throttle DB writes — every 2% is more than enough for the UI.
            rounded = round(p, 2)
            if abs(rounded - job.progress) < 0.02:
                return
            job.progress = rounded
            job.save(update_fields=["progress", "updated_at"])

        render_timeline(
            timeline=project.timeline_json or {},
            asset_paths=paths,
            asset_has_audio=has_audio,
            output_path=out_abs,
            on_progress=on_progress,
        )

        job.output_path = out_rel
        job.progress = 1.0
        job.status = RenderJob.Status.DONE
        job.save(update_fields=["output_path", "progress", "status", "updated_at"])
    except RenderError as exc:
        logger.exception("render failed for %s", job_id)
        job.status = RenderJob.Status.FAILED
        job.error_message = str(exc)[:2000]
        job.save(update_fields=["status", "error_message", "updated_at"])
    except Exception as exc:  # noqa: BLE001 — surface any crash
        logger.exception("render crashed for %s", job_id)
        job.status = RenderJob.Status.FAILED
        job.error_message = f"{type(exc).__name__}: {exc}"[:2000]
        job.save(update_fields=["status", "error_message", "updated_at"])
    finally:
        close_old_connections()


def start_render(project: Project, preset_name: str = "youtube_1080p") -> RenderJob:
    job = RenderJob.objects.create(
        project=project,
        preset_name=preset_name,
        status=RenderJob.Status.QUEUED,
        progress=0.0,
    )
    t = threading.Thread(target=_run, args=(job.id,), daemon=True)
    t.start()
    return job
