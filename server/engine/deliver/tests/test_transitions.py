"""Unit tests for M4 transitions (fade + dissolve) in the timeline renderer."""

from __future__ import annotations

from engine.deliver.timeline_render import (
    _expected_duration,
    _transition_duration_seconds,
    build_command,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _timeline(*clips: dict, fps: int = 30) -> dict:
    return {
        "fps": fps,
        "tracks": [{"id": "v1", "kind": "video", "index": 0}],
        "clips": [{"track_id": "v1", "type": "media", "speed": 1.0, **c} for c in clips],
    }


def _filter_complex(tl: dict) -> str:
    cmd = build_command(
        tl,
        {a: f"/tmp/{a}.mp4" for a in {c["asset_id"] for c in tl["clips"]}},
        {a: True for a in {c["asset_id"] for c in tl["clips"]}},
        "/tmp/out.mp4",
    )
    assert cmd is not None
    return cmd[cmd.index("-filter_complex") + 1]


# ---------------------------------------------------------------------------
# _transition_duration_seconds
# ---------------------------------------------------------------------------


class TestTransitionDurationSeconds:
    def test_none_is_zero(self) -> None:
        assert _transition_duration_seconds(None, 30) == 0.0

    def test_empty_dict_is_zero(self) -> None:
        assert _transition_duration_seconds({}, 30) == 0.0

    def test_unparseable_frames_is_zero(self) -> None:
        assert _transition_duration_seconds({"duration_frames": "x"}, 30) == 0.0

    def test_clamps_below_one_frame(self) -> None:
        # 0 frames → clamp to 1 frame.
        assert _transition_duration_seconds({"duration_frames": 0}, 30) == 1 / 30

    def test_clamps_above_120_frames(self) -> None:
        # 9999 frames → clamp to 120 frames = 4 s @ 30fps.
        assert _transition_duration_seconds({"duration_frames": 9999}, 30) == 4.0

    def test_clamps_to_half_clip_duration(self) -> None:
        # 60 frames @ 30fps = 2 s, but clip is only 3 s long → cap at 1.5 s.
        secs = _transition_duration_seconds(
            {"duration_frames": 60}, 30, clip_timeline_dur=3.0
        )
        assert secs == 1.5

    def test_uses_project_fps(self) -> None:
        # 12 frames @ 24fps = 0.5 s.
        assert _transition_duration_seconds({"duration_frames": 12}, 24) == 0.5


# ---------------------------------------------------------------------------
# Regression guard: no transitions → byte-identical filter_complex
# ---------------------------------------------------------------------------


class TestNoTransitionsRegression:
    def test_two_clip_concat_unchanged(self) -> None:
        tl = _timeline(
            {"asset_id": "A", "start_seconds": 0, "in_seconds": 0, "out_seconds": 2},
            {"asset_id": "B", "start_seconds": 2, "in_seconds": 0, "out_seconds": 3},
        )
        fc = _filter_complex(tl)
        # Plain concat into the final [vout][aout] labels — same as before M4.
        assert "concat=n=2:v=1:a=1[vout][aout]" in fc
        assert "xfade" not in fc
        assert "fade=t=" not in fc
        assert "afade" not in fc


# ---------------------------------------------------------------------------
# Solo fades (to/from black)
# ---------------------------------------------------------------------------


class TestSoloFades:
    def test_fade_in_on_first_clip(self) -> None:
        tl = _timeline(
            {
                "asset_id": "A",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 2,
                "transition_in": {"kind": "fade", "duration_frames": 12},
            },
        )
        fc = _filter_complex(tl)
        # 12 frames @ 30fps = 0.4 s.
        assert "fade=t=in:st=0:d=0.400" in fc
        assert "afade=t=in:st=0:d=0.400" in fc

    def test_fade_out_on_last_clip(self) -> None:
        tl = _timeline(
            {
                "asset_id": "A",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 2,
                "transition_out": {"kind": "fade", "duration_frames": 9},
            },
        )
        fc = _filter_complex(tl)
        # 9 frames @ 30fps = 0.3s, clip is 2s long → fade-out starts at 1.7s.
        assert "fade=t=out:st=1.700:d=0.300" in fc
        assert "afade=t=out:st=1.700:d=0.300" in fc

    def test_solo_dissolve_degrades_to_fade(self) -> None:
        # Single clip asks for dissolve-out, but no neighbour → render as fade.
        tl = _timeline(
            {
                "asset_id": "A",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 2,
                "transition_out": {"kind": "dissolve", "duration_frames": 6},
            },
        )
        fc = _filter_complex(tl)
        assert "fade=t=out" in fc
        assert "xfade" not in fc

    def test_huge_duration_clamps_to_half_clip(self) -> None:
        # 1s clip with a 9999-frame fade-in → 9999 clamps to 120 frames = 4s,
        # then half-clip cap drops it to 0.5s.
        tl = _timeline(
            {
                "asset_id": "A",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 1,
                "transition_in": {"kind": "fade", "duration_frames": 9999},
            },
        )
        fc = _filter_complex(tl)
        assert "fade=t=in:st=0:d=0.500" in fc


# ---------------------------------------------------------------------------
# Cross-fade dissolves between adjacent clips
# ---------------------------------------------------------------------------


class TestDissolveBetweenAdjacent:
    def test_xfade_and_acrossfade_emitted(self) -> None:
        tl = _timeline(
            {
                "asset_id": "A",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 2,
                "transition_out": {"kind": "dissolve", "duration_frames": 12},
            },
            {
                "asset_id": "B",
                "start_seconds": 2,
                "in_seconds": 0,
                "out_seconds": 2,
                "transition_in": {"kind": "dissolve", "duration_frames": 12},
            },
        )
        fc = _filter_complex(tl)
        # 12 frames @ 30fps = 0.4 s; A is 2s long → xfade offset = 1.6s.
        assert "xfade=transition=fade:duration=0.400:offset=1.600" in fc
        assert "acrossfade=d=0.400" in fc
        # Neither side should also receive a solo fade on the shared boundary.
        assert "fade=t=out" not in fc
        assert "fade=t=in" not in fc

    def test_one_sided_dissolve_falls_back_to_fade(self) -> None:
        # A asks for dissolve-out, B asks for nothing → A renders a fade-out
        # to black, B renders no transition.
        tl = _timeline(
            {
                "asset_id": "A",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 2,
                "transition_out": {"kind": "dissolve", "duration_frames": 12},
            },
            {
                "asset_id": "B",
                "start_seconds": 2,
                "in_seconds": 0,
                "out_seconds": 2,
            },
        )
        fc = _filter_complex(tl)
        assert "fade=t=out:st=1.600:d=0.400" in fc
        assert "xfade" not in fc

    def test_dissolve_across_a_gap_falls_back_to_fade(self) -> None:
        # A and B both ask for dissolve, but B starts after a gap → no xfade.
        tl = _timeline(
            {
                "asset_id": "A",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 2,
                "transition_out": {"kind": "dissolve", "duration_frames": 6},
            },
            {
                "asset_id": "B",
                "start_seconds": 4,  # 2s gap
                "in_seconds": 0,
                "out_seconds": 2,
                "transition_in": {"kind": "dissolve", "duration_frames": 6},
            },
        )
        fc = _filter_complex(tl)
        assert "xfade" not in fc
        # Each side gets a solo fade on its facing edge.
        assert "fade=t=out:st=" in fc
        assert "fade=t=in:st=0" in fc


# ---------------------------------------------------------------------------
# Expected duration accounting
# ---------------------------------------------------------------------------


class TestExpectedDuration:
    def test_dissolve_shortens_total(self) -> None:
        tl = _timeline(
            {
                "asset_id": "A",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 2,
                "transition_out": {"kind": "dissolve", "duration_frames": 15},
            },
            {
                "asset_id": "B",
                "start_seconds": 2,
                "in_seconds": 0,
                "out_seconds": 2,
                "transition_in": {"kind": "dissolve", "duration_frames": 15},
            },
        )
        # Naive end = 4s; dissolve overlap @ 30fps = 0.5s → wall-clock 3.5s.
        assert _expected_duration(tl) == 3.5

    def test_one_sided_does_not_shorten(self) -> None:
        tl = _timeline(
            {
                "asset_id": "A",
                "start_seconds": 0,
                "in_seconds": 0,
                "out_seconds": 2,
                "transition_out": {"kind": "dissolve", "duration_frames": 15},
            },
            {
                "asset_id": "B",
                "start_seconds": 2,
                "in_seconds": 0,
                "out_seconds": 2,
            },
        )
        assert _expected_duration(tl) == 4.0
