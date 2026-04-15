"""Unit tests for clip-speed handling in the timeline renderer."""

from __future__ import annotations

from engine.deliver.timeline_render import (
    _atempo_chain,
    _clip_speed,
    _expected_duration,
    build_command,
)


class TestClipSpeed:
    def test_default_is_one(self) -> None:
        assert _clip_speed({}) == 1.0

    def test_invalid_falls_back(self) -> None:
        assert _clip_speed({"speed": None}) == 1.0
        assert _clip_speed({"speed": "nope"}) == 1.0
        assert _clip_speed({"speed": 0}) == 1.0
        assert _clip_speed({"speed": -2}) == 1.0

    def test_clamps_to_safe_range(self) -> None:
        assert _clip_speed({"speed": 0.01}) == 0.1
        assert _clip_speed({"speed": 100}) == 10.0


class TestAtempoChain:
    def test_identity_is_empty(self) -> None:
        assert _atempo_chain(1.0) == ""

    def test_in_range_single_stage(self) -> None:
        assert _atempo_chain(1.5) == "atempo=1.500000"
        assert _atempo_chain(0.7) == "atempo=0.700000"

    def test_fast_chains_multiple_stages(self) -> None:
        # 4× → 2 × 2
        out = _atempo_chain(4.0)
        assert out.count("atempo=") == 2
        assert out.startswith("atempo=2.000000")

    def test_slow_chains_multiple_stages(self) -> None:
        # 0.25× → 0.5 × 0.5
        out = _atempo_chain(0.25)
        assert out.count("atempo=") == 2
        assert "atempo=0.500000" in out


class TestBuildCommandHonorsSpeed:
    def _timeline(self, speed: float) -> dict:
        return {
            "tracks": [{"id": "v1", "kind": "video", "index": 0}],
            "clips": [
                {
                    "track_id": "v1",
                    "asset_id": "A",
                    "start_seconds": 0.0,
                    "in_seconds": 0.0,
                    "out_seconds": 4.0,
                    "speed": speed,
                }
            ],
        }

    def test_1x_uses_plain_setpts(self) -> None:
        cmd = build_command(
            self._timeline(1.0),
            {"A": "/tmp/fake.mp4"},
            {"A": True},
            "/tmp/out.mp4",
        )
        assert cmd is not None
        filter_complex = cmd[cmd.index("-filter_complex") + 1]
        assert "setpts=PTS-STARTPTS" in filter_complex
        assert "atempo" not in filter_complex

    def test_2x_uses_divided_setpts_and_atempo(self) -> None:
        cmd = build_command(
            self._timeline(2.0),
            {"A": "/tmp/fake.mp4"},
            {"A": True},
            "/tmp/out.mp4",
        )
        assert cmd is not None
        filter_complex = cmd[cmd.index("-filter_complex") + 1]
        assert "setpts=(PTS-STARTPTS)/2.000000" in filter_complex
        assert "atempo=2.000000" in filter_complex

    def test_expected_duration_accounts_for_speed(self) -> None:
        # 4s source @ 2× → 2s timeline.
        assert _expected_duration(self._timeline(2.0)) == 2.0
        # 4s source @ 0.5× → 8s timeline.
        assert _expected_duration(self._timeline(0.5)) == 8.0
