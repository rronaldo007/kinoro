"""Ingest pipeline — probe a source file, extract a poster, build a proxy.

Runs on a daemon thread (no Celery — Kinoro is single-user desktop).
The proxy build runs as an independent stage after probe/poster so a
slow transcode doesn't hold up the card flipping to 'ready' in the UI.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.db import close_old_connections

from engine.ffmpeg import (
    ProbeResult,
    TranscodeError,
    build_proxy,
    extract_poster,
    probe,
)

from .models import MediaAsset

logger = logging.getLogger(__name__)


def _classify(result: ProbeResult) -> str:
    if result.has_video:
        vid = result.primary_video
        # A video stream with duration < 0.5s and no audio is almost always
        # a still image masquerading as a single-frame video (png, jpg).
        if vid and result.duration < 0.5 and not result.has_audio:
            return MediaAsset.Kind.IMAGE
        return MediaAsset.Kind.VIDEO
    if result.has_audio:
        return MediaAsset.Kind.AUDIO
    return MediaAsset.Kind.UNKNOWN


def _do_probe_and_poster(asset: MediaAsset) -> str:
    """Run ffprobe + extract a poster. Returns the kind ('video'/'audio'/…)."""
    src = Path(asset.source_path)
    result = probe(src)
    kind = _classify(result)
    vid = result.primary_video

    asset.duration = result.duration
    asset.size_bytes = result.size_bytes
    asset.width = vid.width if vid else None
    asset.height = vid.height if vid else None
    asset.fps = vid.fps if vid else None
    asset.kind = kind
    asset.probe_json = {
        "duration": result.duration,
        "container": result.container,
        "size_bytes": result.size_bytes,
        "video": [asdict(v) for v in result.video],
        "audio": [asdict(a) for a in result.audio],
    }

    if kind in (MediaAsset.Kind.VIDEO, MediaAsset.Kind.IMAGE):
        thumb_rel = f"thumbnails/{asset.id}.jpg"
        thumb_abs = Path(settings.MEDIA_ROOT) / thumb_rel
        # Poster at ~midpoint so short clips (< 1s) still produce a frame.
        # Images seek to 0. ffmpeg silently produces no output when seeking
        # past EOF, so never exceed duration/2.
        if kind == MediaAsset.Kind.IMAGE:
            at = 0.0
        else:
            at = min(1.0, max(0.0, (result.duration or 1.0) * 0.5))
        extract_poster(src, thumb_abs, at_seconds=at)
        asset.thumbnail_path = thumb_rel

    return kind


def _do_proxy(asset: MediaAsset) -> None:
    """Transcode the source to a 720p H.264+AAC MP4 for browser scrubbing.

    Images skip proxy entirely (they already display natively). Failures
    here don't fail the whole asset — the card stays 'ready' with
    proxy_status='failed'; a retry action (future slice) can re-run this.
    """
    if asset.kind == MediaAsset.Kind.IMAGE:
        asset.proxy_status = MediaAsset.ProxyStatus.SKIPPED
        asset.save(update_fields=["proxy_status", "updated_at"])
        return
    if asset.kind not in (MediaAsset.Kind.VIDEO, MediaAsset.Kind.AUDIO):
        asset.proxy_status = MediaAsset.ProxyStatus.SKIPPED
        asset.save(update_fields=["proxy_status", "updated_at"])
        return

    asset.proxy_status = MediaAsset.ProxyStatus.BUILDING
    asset.save(update_fields=["proxy_status", "updated_at"])

    proxy_rel = f"{asset.id}.mp4"
    proxy_abs = Path(settings.KINORO_PROXY_DIR) / proxy_rel
    try:
        build_proxy(asset.source_path, proxy_abs)
        asset.proxy_path = proxy_rel
        asset.proxy_status = MediaAsset.ProxyStatus.READY
        asset.save(update_fields=["proxy_path", "proxy_status", "updated_at"])
    except TranscodeError as exc:
        logger.exception("proxy build failed for %s", asset.id)
        asset.proxy_status = MediaAsset.ProxyStatus.FAILED
        # Append proxy error to error_message but keep status=ready — the
        # user can still drag the asset around; the UI shows the proxy
        # state separately.
        asset.error_message = (asset.error_message + f"\nproxy: {exc}").strip()[:2000]
        asset.save(update_fields=["proxy_status", "error_message", "updated_at"])


def _do_ingest(asset_id: UUID) -> None:
    try:
        asset = MediaAsset.objects.get(pk=asset_id)
    except MediaAsset.DoesNotExist:
        logger.warning("ingest: asset %s vanished before processing", asset_id)
        return

    try:
        _do_probe_and_poster(asset)
        asset.status = MediaAsset.Status.READY
        asset.save()
    except Exception as exc:  # noqa: BLE001 — surface any ingest failure to the user
        logger.exception("ingest failed for %s", asset_id)
        asset.status = MediaAsset.Status.FAILED
        asset.error_message = str(exc)[:2000]
        asset.save(update_fields=["status", "error_message", "updated_at"])
        close_old_connections()
        return

    # Proxy is a separate stage: the card flips to 'ready' with a thumb
    # immediately, then the proxy builds in the same thread afterward.
    try:
        _do_proxy(asset)
    finally:
        close_old_connections()


def ingest_async(asset_id: UUID) -> None:
    """Kick off the ingest pipeline on a background daemon thread."""
    t = threading.Thread(target=_do_ingest, args=(asset_id,), daemon=True)
    t.start()
