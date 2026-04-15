"""Tests for the ZIP-based Video Planner import path.

Three layers:
1. Unit — ``iter_zip_manifest`` on hand-crafted in-memory ZIPs, covering
   the happy path, missing-manifest, and missing-media-file cases.
2. Integration — ``start_zip_import`` against a ZIP built around the
   ``tiny_video`` fixture; asserts one MediaAsset is created, job ends
   "done", dedupe works on a second run.
3. Corrupt / unknown resource — per-asset failure records onto
   ``error_message`` without failing the whole job.
"""

from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import pytest

from apps.import_vp import importers
from apps.import_vp.models import VPImportJob
from apps.import_vp.services import (
    ZipImportError,
    iter_zip_manifest,
)
from apps.media.models import MediaAsset


# --- helpers ----------------------------------------------------------------


def _write_zip(
    zip_path: Path,
    *,
    project: dict | None,
    files: dict[str, bytes],
) -> Path:
    """Build a ZIP at ``zip_path`` with the given project.json and files."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if project is not None:
            zf.writestr("project.json", json.dumps(project))
        for name, data in files.items():
            zf.writestr(name, data)
    return zip_path


# --- 1. iter_zip_manifest unit tests ----------------------------------------


class TestIterZipManifest:
    def test_yields_project_then_resources_in_order(self, tmp_path: Path) -> None:
        zpath = tmp_path / "export.zip"
        project = {
            "id": "proj-1",
            "name": "Demo",
            "resources": [
                {"id": "r1", "name": "a", "type": "video", "file": "resources/r1.mp4"},
                {"id": "r2", "name": "b", "type": "sound", "file": "resources/r2.mp3"},
            ],
        }
        _write_zip(
            zpath,
            project=project,
            files={
                "resources/r1.mp4": b"\x00\x00\x00\x00mp4data",
                "resources/r2.mp3": b"ID3mp3data",
            },
        )

        events = list(iter_zip_manifest(zpath))
        assert events[0]["kind"] == "project"
        assert events[0]["payload"]["id"] == "proj-1"
        resources = [e for e in events if e["kind"] == "resource"]
        assert [e["payload"]["id"] for e in resources] == ["r1", "r2"]
        for r in resources:
            assert isinstance(r["payload"]["path"], Path)
            assert r["payload"]["path"].is_file()

    def test_inmemory_zip_via_bytesio_roundtrip(self, tmp_path: Path) -> None:
        """Build the ZIP in BytesIO, write to disk, confirm parser still works."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "project.json",
                json.dumps({
                    "id": "p",
                    "resources": [
                        {"id": "only-one", "name": "x", "type": "video",
                         "file": "resources/only-one.mp4"},
                    ],
                }),
            )
            zf.writestr("resources/only-one.mp4", b"fake-mp4")
        zpath = tmp_path / "inmem.zip"
        zpath.write_bytes(buf.getvalue())

        events = list(iter_zip_manifest(zpath))
        assert any(e["kind"] == "project" for e in events)
        res = [e for e in events if e["kind"] == "resource"]
        assert len(res) == 1
        assert res[0]["payload"]["id"] == "only-one"

    def test_missing_media_file_is_skipped_not_fatal(self, tmp_path: Path) -> None:
        zpath = tmp_path / "missing.zip"
        _write_zip(
            zpath,
            project={
                "id": "p",
                "resources": [
                    {"id": "present", "type": "video", "file": "resources/present.mp4"},
                    {"id": "absent", "type": "video", "file": "resources/absent.mp4"},
                ],
            },
            files={"resources/present.mp4": b"x"},
        )

        resources = [e for e in iter_zip_manifest(zpath) if e["kind"] == "resource"]
        assert [e["payload"]["id"] for e in resources] == ["present"]

    def test_missing_manifest_raises(self, tmp_path: Path) -> None:
        zpath = tmp_path / "no-manifest.zip"
        _write_zip(zpath, project=None, files={"stray.mp4": b"x"})
        with pytest.raises(ZipImportError, match="project.json"):
            list(iter_zip_manifest(zpath))

    def test_corrupt_zip_raises(self, tmp_path: Path) -> None:
        zpath = tmp_path / "bad.zip"
        zpath.write_bytes(b"this is not a zip file")
        with pytest.raises(ZipImportError):
            list(iter_zip_manifest(zpath))

    def test_nonexistent_path_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ZipImportError, match="not found"):
            list(iter_zip_manifest(tmp_path / "nope.zip"))

    def test_invalid_json_manifest_raises(self, tmp_path: Path) -> None:
        zpath = tmp_path / "bad-json.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("project.json", "{not json}")
        with pytest.raises(ZipImportError, match="valid JSON"):
            list(iter_zip_manifest(zpath))


# --- 2. start_zip_import integration ----------------------------------------


def _wait_for_job(job_id: str, timeout: float = 10.0) -> VPImportJob:
    """Poll until the background thread marks the job done/failed."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = VPImportJob.objects.get(pk=job_id)
        if job.status in ("done", "failed"):
            return job
        time.sleep(0.05)
    return VPImportJob.objects.get(pk=job_id)


@pytest.mark.django_db(transaction=True)
class TestStartZipImport:
    def test_end_to_end_with_tiny_video(
        self,
        tmp_path: Path,
        tiny_video: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A ZIP with one real video → one MediaAsset, job ends 'done'."""
        # Swap out the async ingest for a no-op so the test transaction can
        # tear down cleanly without a daemon thread racing the cursor.
        # The code path under test is the ZIP pipeline — probe/proxy are
        # covered by apps/media/tests/test_ingest_integration.py.
        monkeypatch.setattr(importers, "ingest_async", lambda _id: None)

        zpath = tmp_path / "tiny.zip"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "project.json",
                json.dumps({
                    "id": "zip-proj",
                    "name": "From ZIP",
                    "resources": [
                        {
                            "id": "r-tiny",
                            "name": "tiny clip",
                            "type": "video",
                            "file": "resources/r-tiny.mp4",
                        }
                    ],
                }),
            )
            zf.write(tiny_video, arcname="resources/r-tiny.mp4")

        before = MediaAsset.objects.count()
        job = importers.start_zip_import(zpath)
        assert job.source == "zip"
        assert job.status == "queued"

        finished = _wait_for_job(str(job.id))
        assert finished.status == "done", (
            f"job ended {finished.status}: {finished.error_message}"
        )
        assert finished.progress == pytest.approx(1.0)
        assert finished.remote_project_id == "zip-proj"
        after = MediaAsset.objects.count()
        assert after == before + 1
        asset = MediaAsset.objects.get(vp_asset_id="r-tiny")
        assert Path(asset.source_path).is_file()

    def test_rerun_same_zip_dedupes_on_vp_asset_id(
        self,
        tmp_path: Path,
        tiny_video: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Running start_zip_import twice on the same ZIP → one MediaAsset."""
        monkeypatch.setattr(importers, "ingest_async", lambda _id: None)

        zpath = tmp_path / "dedupe.zip"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "project.json",
                json.dumps({
                    "id": "p",
                    "resources": [
                        {"id": "dup", "name": "x", "type": "video",
                         "file": "resources/dup.mp4"},
                    ],
                }),
            )
            zf.write(tiny_video, arcname="resources/dup.mp4")

        job1 = importers.start_zip_import(zpath)
        _wait_for_job(str(job1.id))
        count_after_first = MediaAsset.objects.filter(vp_asset_id="dup").count()

        job2 = importers.start_zip_import(zpath)
        _wait_for_job(str(job2.id))
        count_after_second = MediaAsset.objects.filter(vp_asset_id="dup").count()

        assert count_after_first == 1
        assert count_after_second == 1  # dedupe kicked in

    def test_missing_manifest_marks_job_failed(self, tmp_path: Path) -> None:
        zpath = tmp_path / "broken.zip"
        # Valid zip, missing project.json.
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("random.txt", "hello")

        job = importers.start_zip_import(zpath)
        finished = _wait_for_job(str(job.id))
        assert finished.status == "failed"
        assert "project.json" in finished.error_message

    def test_resource_with_missing_file_records_no_failure_but_imports_zero(
        self, tmp_path: Path
    ) -> None:
        """Manifest references a resource file that's absent — job still 'done'."""
        zpath = tmp_path / "ghost.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr(
                "project.json",
                json.dumps({
                    "id": "ghost",
                    "resources": [
                        {"id": "ghost-r", "name": "missing", "type": "video",
                         "file": "resources/ghost-r.mp4"},
                    ],
                }),
            )
            # Note: no actual resource file written.

        before = MediaAsset.objects.count()
        job = importers.start_zip_import(zpath)
        finished = _wait_for_job(str(job.id))
        # iter_zip_manifest silently skips the missing file, so the job
        # sees zero resources and ends "done" with no new MediaAssets.
        assert finished.status == "done"
        assert MediaAsset.objects.count() == before

    def test_per_resource_crash_does_not_abort_job(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If one resource raises, the job records the error but still 'done'."""
        zpath = tmp_path / "partial.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr(
                "project.json",
                json.dumps({
                    "id": "p",
                    "resources": [
                        {"id": "boom", "name": "x", "type": "video",
                         "file": "resources/boom.mp4"},
                    ],
                }),
            )
            zf.writestr("resources/boom.mp4", b"x")

        def blow_up(payload: dict) -> tuple[MediaAsset | None, bool]:
            raise RuntimeError("synthetic failure")

        monkeypatch.setattr(importers, "_import_one_zip_resource", blow_up)

        job = importers.start_zip_import(zpath)
        finished = _wait_for_job(str(job.id))
        assert finished.status == "done"  # per-resource failures don't abort
        assert "synthetic failure" in finished.error_message
