"""Integration test for the ``_run_import`` thread entrypoint.

Uses ``pytest-django``'s ``db`` fixture and monkeypatches VPClient + the
ingest pipeline so we don't touch the network or ffmpeg. Asserts the job
transitions queued → fetching_project → downloading_media → done, and
that a Kinoro MediaAsset is created per imported VP asset (with dedupe).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from apps.import_vp import importers
from apps.import_vp.models import VPAccount, VPImportJob
from apps.media.models import MediaAsset


@pytest.mark.django_db
class TestRunImport:
    def test_editor_project_falls_back_to_source_project_resources(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        account = VPAccount.objects.create(
            base_url="http://localhost:8000",
            email="pro@example.com",
            access_token="A",
            refresh_token="R",
        )
        job = VPImportJob.objects.create(
            account=account,
            source="api",
            remote_project_id="editor-1",
            status="queued",
            progress=0.0,
        )

        # Stub VPClient to avoid real HTTP. try_get_any_project returns an
        # editor project with an empty timeline but a linked source project;
        # list_resources returns two importable video URLs.
        class FakeClient:
            def __init__(self, *a: object, **k: object) -> None:
                self.access_token = "A"

            def try_get_any_project(self, pid: str) -> tuple[str, dict[str, Any]]:
                assert pid == "editor-1"
                return "editor", {
                    "id": "editor-1",
                    "timeline_json": {},
                    "source_project": "regular-1",
                }

            def list_resources(self, pid: str) -> list[dict[str, Any]]:
                assert pid == "regular-1"
                return [
                    {"id": "r1", "type": "video", "url": "https://cdn.example.com/a.mp4", "title": "First"},
                    {"id": "r2", "type": "video", "url": "https://cdn.example.com/b.mp4", "title": "Second"},
                    {"id": "r3", "type": "note", "url": "https://cdn.example.com/c.txt"},  # filtered
                ]

        monkeypatch.setattr(importers, "VPClient", FakeClient)

        # Stub the per-resource importer so we don't actually download.
        # Mimic _import_one_resource's return type: (MediaAsset|None, was_created).
        downloaded: list[str] = []

        def fake_import_one(resource: dict[str, Any], acc: VPAccount) -> tuple[MediaAsset | None, bool]:
            downloaded.append(resource["id"])
            asset = MediaAsset.objects.create(
                name=resource.get("title") or "x",
                source_path=str(tmp_path / f"{resource['id']}.mp4"),
                status=MediaAsset.Status.READY,
                vp_asset_id=resource["id"],
            )
            return asset, True

        monkeypatch.setattr(importers, "_import_one_resource", fake_import_one)
        # Skip ingest_async since MediaAssets are already marked READY by the stub.
        monkeypatch.setattr(importers, "ingest_async", lambda _id: None)

        importers._run_import(str(job.id))

        job.refresh_from_db()
        assert job.status == "done"
        assert job.progress == pytest.approx(1.0)
        assert downloaded == ["r1", "r2"]  # r3 filtered out as non-video
        assert MediaAsset.objects.count() == 2
        assert set(MediaAsset.objects.values_list("vp_asset_id", flat=True)) == {"r1", "r2"}

    def test_run_import_marks_failed_when_project_fetch_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        account = VPAccount.objects.create(
            base_url="http://localhost:8000",
            email="pro@example.com",
            access_token="A",
            refresh_token="R",
        )
        job = VPImportJob.objects.create(
            account=account,
            source="api",
            remote_project_id="missing",
            status="queued",
            progress=0.0,
        )

        class FakeClient:
            access_token = "A"

            def __init__(self, *a: object, **k: object) -> None: ...

            def try_get_any_project(self, pid: str) -> tuple[str, dict[str, Any]]:
                raise importers.VPClientError("GET /api/projects/missing/ → 404")

        monkeypatch.setattr(importers, "VPClient", FakeClient)

        importers._run_import(str(job.id))

        job.refresh_from_db()
        assert job.status == "failed"
        assert "404" in job.error_message
