"""Unit tests for text-clip handling in the timeline renderer."""

from __future__ import annotations

from engine.deliver.timeline_render import (
    _drawtext_filter_parts,
    _escape_drawtext,
    _text_clips,
    build_command,
)


def _base_timeline() -> dict:
    return {
        "tracks": [{"id": "v1", "kind": "video", "index": 0}],
        "clips": [
            {
                "track_id": "v1",
                "asset_id": "A",
                "start_seconds": 0.0,
                "in_seconds": 0.0,
                "out_seconds": 2.0,
                "speed": 1.0,
                "type": "media",
            }
        ],
    }


class TestEscapeDrawtext:
    def test_preserves_simple_text(self) -> None:
        assert _escape_drawtext("Hello") == "Hello"

    def test_escapes_ffmpeg_specials(self) -> None:
        assert _escape_drawtext("a:b,c%d\\e'f") == "a\\:b\\,c\\%d\\\\e\\'f"


class TestTextClips:
    def test_filters_media_clips(self) -> None:
        timeline = _base_timeline()
        assert _text_clips(timeline) == []

    def test_returns_text_clips_any_track(self) -> None:
        timeline = _base_timeline()
        timeline["clips"].append(
            {
                "track_id": "v2",
                "type": "text",
                "text_content": "Hi",
                "start_seconds": 0.5,
                "in_seconds": 0,
                "out_seconds": 2.0,
            }
        )
        got = _text_clips(timeline)
        assert len(got) == 1
        assert got[0]["text_content"] == "Hi"


class TestDrawtextFilterParts:
    def test_skips_empty_content(self) -> None:
        parts = _drawtext_filter_parts([{"text_content": "  ", "start_seconds": 0, "out_seconds": 1}])
        assert parts == []

    def test_skips_zero_duration(self) -> None:
        parts = _drawtext_filter_parts([
            {"text_content": "x", "start_seconds": 1.0, "in_seconds": 0.0, "out_seconds": 0.0}
        ])
        assert parts == []

    def test_renders_full_filter(self) -> None:
        parts = _drawtext_filter_parts([
            {
                "text_content": "Title",
                "start_seconds": 1.0,
                "in_seconds": 0.0,
                "out_seconds": 3.0,
                "text_font_size": 48,
                "text_color": "yellow",
                "text_x": 0.25,
                "text_y": 0.75,
            }
        ])
        assert len(parts) == 1
        f = parts[0]
        assert "text='Title'" in f
        assert "fontsize=48" in f
        assert "fontcolor=yellow" in f
        assert "x=(w-text_w)*0.2500" in f
        assert "y=(h-text_h)*0.7500" in f
        assert "enable='between(t,1.000,4.000)'" in f

    def test_clamps_font_and_position(self) -> None:
        parts = _drawtext_filter_parts([
            {
                "text_content": "x",
                "start_seconds": 0.0,
                "in_seconds": 0.0,
                "out_seconds": 1.0,
                "text_font_size": 9999,  # clamped to 256
                "text_x": 5.0,  # clamped to 1
                "text_y": -1.0,  # clamped to 0
            }
        ])
        assert "fontsize=256" in parts[0]
        assert "x=(w-text_w)*1.0000" in parts[0]
        assert "y=(h-text_h)*0.0000" in parts[0]


class TestBuildCommandWithText:
    def test_no_text_uses_plain_concat(self) -> None:
        cmd = build_command(
            _base_timeline(),
            {"A": "/tmp/fake.mp4"},
            {"A": True},
            "/tmp/out.mp4",
        )
        assert cmd is not None
        fc = cmd[cmd.index("-filter_complex") + 1]
        assert "[vout][aout]" in fc
        assert "drawtext" not in fc

    def test_text_clip_adds_drawtext_overlay(self) -> None:
        tl = _base_timeline()
        tl["clips"].append(
            {
                "track_id": "v1",
                "type": "text",
                "text_content": "Hello",
                "start_seconds": 0.5,
                "in_seconds": 0.0,
                "out_seconds": 2.0,
            }
        )
        cmd = build_command(
            tl,
            {"A": "/tmp/fake.mp4"},
            {"A": True},
            "/tmp/out.mp4",
        )
        assert cmd is not None
        fc = cmd[cmd.index("-filter_complex") + 1]
        # Concat now produces [vmix], then drawtext writes [vout].
        assert "[vmix][aout]" in fc
        assert "[vmix]drawtext=text='Hello'" in fc
        assert "[vout]" in fc
