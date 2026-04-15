"""Unit tests for the pure helpers in ``apps.import_vp.importers``.

These functions contain no Django/network state; they're cheap to cover
and guard against VP serializer-shape drift that's bitten us once already.
"""

from __future__ import annotations

from apps.import_vp.importers import (
    _collect_asset_ids,
    _file_extension_from_url,
    _video_resources_with_url,
)


class TestCollectAssetIds:
    def test_empty_timeline(self) -> None:
        assert _collect_asset_ids({}) == []
        assert _collect_asset_ids({"clips": None}) == []
        assert _collect_asset_ids({"clips": "not a list"}) == []  # type: ignore[dict-item]

    def test_unique_ids_preserved_in_clip_order(self) -> None:
        timeline = {
            "clips": [
                {"asset_id": "a"},
                {"asset_id": "b"},
                {"asset_id": "a"},  # dup
                {"asset_id": "c"},
            ]
        }
        assert _collect_asset_ids(timeline) == ["a", "b", "c"]

    def test_falls_back_to_media_id(self) -> None:
        timeline = {
            "clips": [
                {"media_id": "x"},
                {"asset_id": "y"},
            ]
        }
        assert _collect_asset_ids(timeline) == ["x", "y"]

    def test_skips_non_dict_clips(self) -> None:
        timeline = {
            "clips": [
                {"asset_id": "a"},
                "not a dict",
                {"asset_id": "b"},
            ]
        }
        assert _collect_asset_ids(timeline) == ["a", "b"]

    def test_ignores_non_string_asset_ids(self) -> None:
        timeline = {"clips": [{"asset_id": 123}, {"asset_id": None}, {"asset_id": "ok"}]}
        assert _collect_asset_ids(timeline) == ["ok"]


class TestVideoResourcesWithUrl:
    def test_passes_video_with_http_url(self) -> None:
        resources = [{"id": "1", "type": "video", "url": "http://example.com/a.mp4"}]
        assert _video_resources_with_url(resources) == resources

    def test_passes_sound_with_https_url(self) -> None:
        resources = [{"id": "1", "type": "sound", "url": "https://example.com/a.mp3"}]
        assert _video_resources_with_url(resources) == resources

    def test_rejects_non_video_kinds(self) -> None:
        resources = [
            {"id": "1", "type": "note", "url": "https://example.com/a.mp4"},
            {"id": "2", "type": "document", "url": "https://example.com/b.pdf"},
        ]
        assert _video_resources_with_url(resources) == []

    def test_rejects_missing_url(self) -> None:
        resources = [
            {"id": "1", "type": "video", "url": ""},
            {"id": "2", "type": "video"},
        ]
        assert _video_resources_with_url(resources) == []

    def test_rejects_non_http_scheme(self) -> None:
        resources = [
            {"id": "1", "type": "video", "url": "file:///local/a.mp4"},
            {"id": "2", "type": "video", "url": "ftp://example.com/a.mp4"},
        ]
        assert _video_resources_with_url(resources) == []

    def test_rejects_legacy_kind_field(self) -> None:
        # B5 cleanup — we only look at `type` now. Any serializer that
        # emits `kind` instead will silently produce zero imports (and
        # raise in plain sight rather than smuggle videos through).
        resources = [{"id": "1", "kind": "video", "url": "https://example.com/a.mp4"}]
        assert _video_resources_with_url(resources) == []

    def test_skips_non_dict_rows(self) -> None:
        resources = [
            "not a dict",
            {"id": "1", "type": "video", "url": "https://example.com/a.mp4"},
            None,
        ]
        got = _video_resources_with_url(resources)  # type: ignore[arg-type]
        assert len(got) == 1
        assert got[0]["id"] == "1"


class TestFileExtensionFromUrl:
    def test_extracts_common_extensions(self) -> None:
        assert _file_extension_from_url("https://x/y.mp4") == ".mp4"
        assert _file_extension_from_url("https://x/y.tar.gz") == ".gz"
        assert _file_extension_from_url("http://x/y.webm?query=1") == ".webm"

    def test_falls_back_when_no_extension(self) -> None:
        assert _file_extension_from_url("https://x/no-ext") == ".bin"
        assert _file_extension_from_url("https://x/no-ext", fallback=".dat") == ".dat"
