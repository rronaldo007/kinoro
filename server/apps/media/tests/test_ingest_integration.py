"""Integration test for the media ingest pipeline.

End-to-end: create a MediaAsset pointing at a small real video, run
``_do_ingest`` synchronously (same worker logic as the daemon thread,
just in-test for deterministic assertions), and verify the asset flips
to ready with populated probe metadata + an on-disk thumbnail.

This test requires ffmpeg/ffprobe on PATH — the ``tiny_video`` fixture
(see ``conftest.py``) will skip the test on hosts without them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings

from apps.media.models import MediaAsset
from apps.media.services import _do_ingest


@pytest.mark.django_db
def test_ingest_probes_and_generates_poster(tiny_video: Path) -> None:
    asset = MediaAsset.objects.create(
        name=tiny_video.name,
        source_path=str(tiny_video),
        status=MediaAsset.Status.INGESTING,
    )

    _do_ingest(asset.id)

    asset.refresh_from_db()
    assert asset.status == MediaAsset.Status.READY
    assert asset.kind == MediaAsset.Kind.VIDEO
    # Our fixture is exactly 1 second with audio.
    assert asset.duration is not None
    assert 0.5 < asset.duration < 3.0
    assert asset.width == 320
    assert asset.height == 180
    assert asset.fps == pytest.approx(24, abs=0.1)

    # Poster should exist under MEDIA_ROOT/thumbnails/<uuid>.jpg.
    assert asset.thumbnail_path.startswith("thumbnails/")
    thumb_abs = Path(settings.MEDIA_ROOT) / asset.thumbnail_path
    assert thumb_abs.is_file()
    assert thumb_abs.stat().st_size > 0

    # Proxy build is async on a real runserver (stage 2); the synchronous
    # pipeline kicks it off too. Assert either ready or at least attempted.
    assert asset.proxy_status in (
        MediaAsset.ProxyStatus.READY,
        MediaAsset.ProxyStatus.BUILDING,
        MediaAsset.ProxyStatus.FAILED,
        MediaAsset.ProxyStatus.SKIPPED,
    )


@pytest.mark.django_db
def test_ingest_failed_source_marks_asset_failed(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.mp4"
    asset = MediaAsset.objects.create(
        name="missing",
        source_path=str(missing),
        status=MediaAsset.Status.INGESTING,
    )

    _do_ingest(asset.id)

    asset.refresh_from_db()
    assert asset.status == MediaAsset.Status.FAILED
    assert asset.error_message  # non-empty
