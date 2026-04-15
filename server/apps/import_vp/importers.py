"""Live-API import pipeline for Video Planner projects.

Handles both handoff kinds:
- Editor projects (from VP `/vediteur`) — walk `timeline_json.clips` and pull
  each referenced vediteur MediaAsset via the authenticated VPClient.
- Regular projects (from VP `/projects/<id>`) — list nested resources, keep
  video/sound rows with http(s) URLs, download each one. Third-party CDNs
  are fetched without VP credentials; same-host URLs go through VPClient.

Progress is tracked in a persistent `VPImportJob` row so the UI can poll
state transitions, progress, and error_message even if the thread crashes
mid-import.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from django.db import close_old_connections

from apps.media.models import MediaAsset
from apps.media.services import ingest_async

from .models import VPAccount, VPImportJob
from .services import (
    VPAuthError,
    VPClient,
    VPClientError,
    ZipImportError,
    iter_zip_manifest,
)

logger = logging.getLogger(__name__)


# ---- timeline + resource introspection ----------------------------------


def _collect_asset_ids(timeline_json: dict[str, Any]) -> list[str]:
    """Unique asset_ids referenced by the clips in an editor timeline."""
    ids: list[str] = []
    seen: set[str] = set()
    clips = timeline_json.get("clips") if isinstance(timeline_json, dict) else None
    if not isinstance(clips, list):
        return ids
    for clip in clips:
        if not isinstance(clip, dict):
            continue
        aid = clip.get("asset_id") or clip.get("media_id")
        if isinstance(aid, str) and aid not in seen:
            seen.add(aid)
            ids.append(aid)
    return ids


def _video_resources_with_url(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Importable resources: type in video/sound with an http(s) url.

    VP's Resource model field is `type` — the serializer emits `type`. If
    that ever gets renamed, this raises (KeyError trapped upstream) rather
    than silently importing nothing.
    """
    out: list[dict[str, Any]] = []
    for r in resources:
        if not isinstance(r, dict):
            continue
        kind = r.get("type")
        url = r.get("url") or ""
        if kind in ("video", "sound") and isinstance(url, str) and url.startswith(("http://", "https://")):
            out.append(r)
    return out


def _file_extension_from_url(url: str, fallback: str = ".bin") -> str:
    path = urlparse(url).path
    ext = Path(path).suffix
    return ext if ext else fallback


# ---- per-item importers --------------------------------------------------


def _existing_by_vp_id(vp_id: str) -> MediaAsset | None:
    if not vp_id:
        return None
    return MediaAsset.objects.filter(vp_asset_id=vp_id).order_by("-created_at").first()


def _import_one_asset(
    client: VPClient, vp_asset: dict[str, Any]
) -> tuple[MediaAsset | None, bool]:
    """Download one VP vediteur MediaAsset, dedupe on vp_asset_id.

    Returns (asset, was_created). ``was_created`` is False when an existing
    MediaAsset with the same vp_asset_id was found and the download was
    skipped.
    """
    vp_id = str(vp_asset.get("id") or "")
    file_url = vp_asset.get("file_url")
    name = vp_asset.get("name") or f"vp-{vp_id}"

    existing = _existing_by_vp_id(vp_id)
    if existing is not None:
        return existing, False
    if not file_url:
        logger.warning("VP asset %s has no file_url — skipping", vp_id)
        return None, False

    ext = _file_extension_from_url(file_url)
    dest = Path(settings.KINORO_DATA_DIR) / "vp-imports" / f"{vp_id}{ext}"
    client.download_url(file_url, dest)

    asset = MediaAsset.objects.create(
        name=name,
        source_path=str(dest.resolve()),
        status=MediaAsset.Status.INGESTING,
        vp_asset_id=vp_id,
    )
    ingest_async(asset.id)
    return asset, True


def _import_one_resource(
    resource: dict[str, Any], account: VPAccount
) -> tuple[MediaAsset | None, bool]:
    """Download one regular-Project Resource URL, dedupe on vp_asset_id.

    Decides auth per-URL: same host as ``account.base_url`` → use VPClient
    (sends Bearer); anything else → bare requests (no auth leak to CDNs).
    """
    rid = str(resource.get("id") or "")
    url = resource.get("url")
    title = resource.get("title") or f"resource-{rid}"
    if not url:
        return None, False

    existing = _existing_by_vp_id(rid)
    if existing is not None:
        return existing, False

    ext = _file_extension_from_url(url)
    dest = Path(settings.KINORO_DATA_DIR) / "vp-imports" / f"{rid}{ext}"

    vp_host = urlparse(account.base_url).netloc
    dest_host = urlparse(url).netloc
    if vp_host and dest_host == vp_host:
        client = VPClient(
            base_url=account.base_url,
            access_token=account.access_token,
            refresh_token=account.refresh_token,
        )
        client.download_url(url, dest)
    else:
        import requests

        with requests.get(url, stream=True, timeout=60.0) as r:
            if r.status_code >= 400:
                logger.warning("resource %s: GET %s → %s", rid, url, r.status_code)
                return None, False
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as fh:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    if chunk:
                        fh.write(chunk)

    asset = MediaAsset.objects.create(
        name=title,
        source_path=str(dest.resolve()),
        status=MediaAsset.Status.INGESTING,
        vp_asset_id=rid,
    )
    ingest_async(asset.id)
    return asset, True


# ---- job lifecycle -------------------------------------------------------


def _set_status(job: VPImportJob, status: str, *, progress: float | None = None,
                error_message: str | None = None) -> None:
    job.status = status
    if progress is not None:
        job.progress = progress
    if error_message is not None:
        job.error_message = error_message[:2000]
    job.save(update_fields=["status", "progress", "error_message", "updated_at"])


def _run_import(job_id: str) -> None:
    """Thread entrypoint. Drives the VPImportJob through status transitions."""
    try:
        job = VPImportJob.objects.select_related("account").get(pk=job_id)
    except VPImportJob.DoesNotExist:
        logger.warning("import: job %s vanished before processing", job_id)
        return

    account = job.account
    if account is None:
        _set_status(job, "failed", error_message="No VP account attached to job.")
        return

    client = VPClient(
        base_url=account.base_url,
        access_token=account.access_token,
        refresh_token=account.refresh_token,
    )
    _set_status(job, "fetching_project", progress=0.0)

    try:
        kind, project = client.try_get_any_project(job.remote_project_id)
    except VPAuthError as e:
        _set_status(job, "failed", error_message=f"Auth: {e}")
        return
    except VPClientError as e:
        _set_status(job, "failed", error_message=str(e))
        return

    _set_status(job, "downloading_media", progress=0.05)

    try:
        asset_ids: list[str] = []
        importable_resources: list[dict[str, Any]] = []
        if kind == "editor":
            asset_ids = _collect_asset_ids(project.get("timeline_json") or {})
            if not asset_ids and project.get("source_project"):
                # Empty timeline → fall back to the linked planning project's
                # video resources. See plan_import() for the same logic.
                source_id = str(project["source_project"])
                try:
                    source_resources = client.list_resources(source_id) or []
                    importable_resources = _video_resources_with_url(source_resources)
                    logger.info(
                        "import: editor project %s empty — using %d resource(s) "
                        "from source project %s",
                        job.remote_project_id,
                        len(importable_resources),
                        source_id,
                    )
                except (VPAuthError, VPClientError) as e:
                    logger.exception(
                        "import: could not list source project %s", source_id
                    )
                    job.error_message = f"Source project: {e}"[:2000]
        else:
            resources = client.list_resources(job.remote_project_id) or []
            importable_resources = _video_resources_with_url(resources)

        if asset_ids:
            total = max(len(asset_ids), 1)
            for i, aid in enumerate(asset_ids, start=1):
                try:
                    vp_asset = client.get_vediteur_media(aid)
                    _import_one_asset(client, vp_asset)
                except (VPAuthError, VPClientError) as e:
                    logger.exception("import: failed to pull asset %s", aid)
                    job.error_message = (
                        f"{job.error_message}\nasset {aid}: {e}"[:2000]
                    )
                job.progress = 0.05 + 0.9 * (i / total)
                job.save(update_fields=["progress", "error_message", "updated_at"])
        else:
            total = max(len(importable_resources), 1)
            for i, resource in enumerate(importable_resources, start=1):
                try:
                    _import_one_resource(resource, account)
                except Exception as e:  # noqa: BLE001 — surface failures
                    logger.exception(
                        "import: failed to pull resource %s", resource.get("id")
                    )
                    job.error_message = (
                        f"{job.error_message}\nresource {resource.get('id')}: {e}"
                    )[:2000]
                job.progress = 0.05 + 0.9 * (i / total)
                job.save(update_fields=["progress", "error_message", "updated_at"])

        _set_status(job, "done", progress=1.0)
    finally:
        if client.access_token and client.access_token != account.access_token:
            account.access_token = client.access_token
            account.save(update_fields=["access_token"])
        close_old_connections()


# ---- public API used by views -------------------------------------------


def plan_import(project_id: str, account: VPAccount) -> tuple[str, int]:
    """Synchronously fetch the project once to get (kind, asset_count).

    For editor projects, if the timeline is empty but a source Project is
    linked, we fall back to the source project's video-URL resources so
    clicking 'Import media' on a freshly-created editor project actually
    imports something useful.
    """
    client = VPClient(
        base_url=account.base_url,
        access_token=account.access_token,
        refresh_token=account.refresh_token,
    )
    kind, project = client.try_get_any_project(project_id)
    if kind == "editor":
        asset_ids = _collect_asset_ids(project.get("timeline_json") or {})
        if asset_ids:
            return kind, len(asset_ids)
        source_id = project.get("source_project")
        if source_id:
            resources = client.list_resources(str(source_id)) or []
            return kind, len(_video_resources_with_url(resources))
        return kind, 0
    resources = client.list_resources(project_id) or []
    return kind, len(_video_resources_with_url(resources))


def start_import(project_id: str, account: VPAccount) -> VPImportJob:
    """Create a VPImportJob + kick off the background thread."""
    job = VPImportJob.objects.create(
        account=account,
        source="api",
        remote_project_id=project_id,
        status="queued",
        progress=0.0,
    )
    t = threading.Thread(target=_run_import, args=(str(job.id),), daemon=True)
    t.start()
    return job


# ---- ZIP import path ----------------------------------------------------


def _import_one_zip_resource(
    payload: dict[str, Any],
) -> tuple[MediaAsset | None, bool]:
    """Copy one extracted resource into the media store and kick off ingest.

    Dedupes on ``vp_asset_id`` the same way the API importer does — so
    re-importing the same ZIP twice leaves one row per resource, not two.
    """
    rid = str(payload.get("id") or "")
    src_path: Path | None = payload.get("path")
    name = payload.get("name") or f"resource-{rid}"
    if not rid or src_path is None:
        return None, False

    existing = _existing_by_vp_id(rid)
    if existing is not None:
        return existing, False

    src = Path(src_path)
    if not src.is_file():
        logger.warning("zip import: resource %s file missing: %s", rid, src)
        return None, False

    dest_dir = Path(settings.KINORO_DATA_DIR) / "vp-imports"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{rid}{src.suffix}"
    # Copy (not move) so the extracted tree stays intact for debugging /
    # re-runs. The extracted tree is under the data dir and can be pruned
    # by the caller after the job finishes.
    if not dest.exists():
        import shutil

        shutil.copy2(src, dest)

    asset = MediaAsset.objects.create(
        name=name,
        source_path=str(dest.resolve()),
        status=MediaAsset.Status.INGESTING,
        vp_asset_id=rid,
    )
    ingest_async(asset.id)
    return asset, True


def _run_zip_import(job_id: str) -> None:
    """Thread entrypoint for ZIP-sourced imports.

    Mirrors ``_run_import`` but reads resources from ``iter_zip_manifest``
    instead of the VP HTTP API. Each per-resource failure is recorded on
    ``job.error_message`` but does not abort the job — matches the
    "fetch-what-you-can" behaviour the API importer has.
    """
    try:
        job = VPImportJob.objects.get(pk=job_id)
    except VPImportJob.DoesNotExist:
        logger.warning("zip import: job %s vanished before processing", job_id)
        return

    zip_path = Path(job.zip_path)
    try:
        _set_status(job, "fetching_project", progress=0.0)
        try:
            events = list(iter_zip_manifest(zip_path))
        except ZipImportError as e:
            _set_status(job, "failed", error_message=str(e))
            return

        project_events = [e for e in events if e["kind"] == "project"]
        resource_events = [e for e in events if e["kind"] == "resource"]

        if project_events:
            project = project_events[0]["payload"]
            remote_id = str(project.get("id") or "")
            if remote_id and not job.remote_project_id:
                job.remote_project_id = remote_id[:64]
                job.save(update_fields=["remote_project_id", "updated_at"])

        _set_status(job, "downloading_media", progress=0.05)

        total = max(len(resource_events), 1)
        for i, ev in enumerate(resource_events, start=1):
            try:
                _import_one_zip_resource(ev["payload"])
            except Exception as e:  # noqa: BLE001 — surface, don't abort
                rid = ev["payload"].get("id")
                logger.exception("zip import: failed to import resource %s", rid)
                job.error_message = (
                    f"{job.error_message}\nresource {rid}: {e}"
                )[:2000]
            job.progress = 0.05 + 0.9 * (i / total)
            job.save(update_fields=["progress", "error_message", "updated_at"])

        _set_status(job, "done", progress=1.0)
    finally:
        close_old_connections()


def start_zip_import(zip_path: str | Path, user: Any = None) -> VPImportJob:
    """Create a ZIP-sourced VPImportJob and kick off the background thread.

    ``user`` is accepted for API parity with ``start_import`` but is
    currently unused — Kinoro is single-user desktop.
    """
    _ = user  # reserved for future multi-user wrapping
    job = VPImportJob.objects.create(
        account=None,
        source="zip",
        remote_project_id="",
        zip_path=str(Path(zip_path).resolve()),
        status="queued",
        progress=0.0,
    )
    t = threading.Thread(target=_run_zip_import, args=(str(job.id),), daemon=True)
    t.start()
    return job
