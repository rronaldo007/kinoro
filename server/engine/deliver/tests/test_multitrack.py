"""Unit tests for multi-track (V1+V2, A1, A2) rendering in the timeline
renderer. These lock in the scope shift from V1-only to a full 4-track
composite (V1 + V2 overlay + A1/A2 audio mix).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from engine.deliver.timeline_render import (
    _expected_duration,
    build_command,
    render_timeline,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


_DEFAULT_TRACKS = [
    {"id": "v1", "kind": "video", "index": 0},
    {"id": "v2", "kind": "video", "index": 1},
    {"id": "a1", "kind": "audio", "index": 0},
    {"id": "a2", "kind": "audio", "index": 1},
]


def _timeline(*clips: dict, fps: int = 30) -> dict:
    return {
        "fps": fps,
        "tracks": [dict(t) for t in _DEFAULT_TRACKS],
        "clips": [
            {"type": "media", "speed": 1.0, **c} for c in clips
        ],
    }


def _filter_complex(tl: dict, *, has_audio: bool = True) -> str:
    asset_ids = {c["asset_id"] for c in tl["clips"] if c.get("asset_id")}
    cmd = build_command(
        tl,
        {a: f"/tmp/{a}.mp4" for a in asset_ids},
        {a: has_audio for a in asset_ids},
        "/tmp/out.mp4",
    )
    assert cmd is not None
    return cmd[cmd.index("-filter_complex") + 1]


# ---------------------------------------------------------------------------
# V2 overlay
# ---------------------------------------------------------------------------


class TestV2Overlay:
    def test_v2_overlap_emits_overlay_filter(self) -> None:
        tl = _timeline(
            {
                "track_id": "v1",
                "asset_id": "A",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 5,
            },
            {
                "track_id": "v2",
                "asset_id": "B",
                "start_seconds": 1,
                "in_seconds": 0,
                "out_seconds": 3,
            },
        )
        fc = _filter_complex(tl)
        # V1 stitch lands on an intermediate label when multitrack.
        assert "[v1vout]" in fc
        # V2 clip gets its own scaled stream + overlay with an enable window.
        assert "overlay=shortest=0:x=0:y=0:enable='between(t,1.000,4.000)'" in fc
        # The final composite becomes [vout] via passthrough null filter.
        assert "[vout]" in fc


# ---------------------------------------------------------------------------
# Audio mix
# ---------------------------------------------------------------------------


class TestAudioMix:
    def test_a1_only_goes_through_amix_with_v1(self) -> None:
        # V1 + A1 (A1 covers the same window).
        tl = _timeline(
            {
                "track_id": "v1",
                "asset_id": "A",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 5,
            },
            {
                "track_id": "a1",
                "asset_id": "B",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 5,
            },
        )
        fc = _filter_complex(tl)
        # 2 inputs: V1's stitched audio + the A1 track.
        assert "amix=inputs=2:duration=longest" in fc
        assert "[v1aout]" in fc  # V1 stitched audio label
        assert "[at0]" in fc     # first extra audio track label

    def test_a1_and_a2_overlap_produces_three_input_amix(self) -> None:
        tl = _timeline(
            {
                "track_id": "v1",
                "asset_id": "A",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 5,
            },
            {
                "track_id": "a1",
                "asset_id": "B",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 5,
            },
            {
                "track_id": "a2",
                "asset_id": "C",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 5,
            },
        )
        fc = _filter_complex(tl)
        assert "amix=inputs=3:duration=longest" in fc
        assert "[at0]" in fc
        assert "[at1]" in fc

    def test_a1_gap_produces_silent_anullsrc_segment(self) -> None:
        # Two A1 clips with a 2s gap → the per-track concat should have 3
        # inputs (clip1, gap-silence, clip2) and the concat filter reflects that.
        tl = _timeline(
            {
                "track_id": "v1",
                "asset_id": "V",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 10,
            },
            {
                "track_id": "a1",
                "asset_id": "A",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 2,
            },
            {
                "track_id": "a1",
                "asset_id": "B",
                "start_seconds": 4,  # 2s gap after first clip ends at 2s
                "in_seconds": 0,
                "out_seconds": 3,
            },
        )
        fc = _filter_complex(tl)
        # Silent gap label for track 0, clip index 1.
        assert "anullsrc=r=48000:cl=stereo:d=2.000[at0g1]" in fc
        # Per-track concat combines clip1 + gap + clip2.
        assert "concat=n=3:v=0:a=1[at0]" in fc


# ---------------------------------------------------------------------------
# Regression: single V1 clip keeps today's exact filter_complex shape
# ---------------------------------------------------------------------------


class TestSingleTrackRegression:
    def test_single_v1_clip_is_unchanged(self) -> None:
        # Use the 4-track default, but only place one V1 clip. No V2/A1/A2.
        tl = _timeline(
            {
                "track_id": "v1",
                "asset_id": "A",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 2,
            },
        )
        fc = _filter_complex(tl)
        # Single-segment concat lands directly on [vout][aout] — same shape
        # the renderer emitted before multitrack.
        assert "concat=n=1:v=1:a=1[vout][aout]" in fc
        assert "overlay" not in fc
        assert "amix" not in fc
        assert "v1vout" not in fc


# ---------------------------------------------------------------------------
# Expected duration honours trailing audio
# ---------------------------------------------------------------------------


class TestExpectedDurationMultitrack:
    def test_a1_tail_extends_duration(self) -> None:
        tl = _timeline(
            {
                "track_id": "v1",
                "asset_id": "A",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 2,
            },
            {
                "track_id": "a1",
                "asset_id": "B",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 5,  # A1 runs 3s past V1
            },
        )
        assert _expected_duration(tl) == 5.0


# ---------------------------------------------------------------------------
# Integration: end-to-end render of V1 + A1 with real ffmpeg
# ---------------------------------------------------------------------------


class TestMultitrackIntegration:
    def test_v1_plus_a1_renders_and_plays_back(self, tmp_path: Path, tiny_video: Path) -> None:
        if not shutil.which("ffprobe"):
            pytest.skip("ffprobe not on PATH — skipping integration test")

        out = tmp_path / "multitrack.mp4"
        tl = _timeline(
            {
                "track_id": "v1",
                "asset_id": "V",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 1,
            },
            {
                "track_id": "a1",
                "asset_id": "A",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 1,
            },
        )
        render_timeline(
            tl,
            {"V": tiny_video, "A": tiny_video},
            {"V": True, "A": True},
            out,
        )
        assert out.exists()
        # ffprobe the duration; we expect ~1s (± 0.15s for container padding).
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(out),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        duration = float(probe.stdout.strip())
        assert 0.85 <= duration <= 1.30, f"unexpected duration {duration}"
