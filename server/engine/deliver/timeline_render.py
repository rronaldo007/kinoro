"""Timeline-to-video render.

Takes a ``TimelineDoc`` (as a dict) + a map of asset_id → source file path, and
produces a single MP4. Current scope intentionally narrow:

- V1 video track only (V2, audio tracks come later)
- Audio pulled from each V1 clip's source (or silent fill if missing)
- Black + silence for gaps between clips
- Fixed output: 1920×1080 @ 30fps H.264 AAC

This module is pure Python — no Django, no Celery. Consumers (Celery tasks,
tests, desktop wrapper) import ``render_timeline`` and handle orchestration.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

logger = logging.getLogger(__name__)

_FFMPEG = "ffmpeg"

ProgressCallback = Callable[[float], None]


class RenderError(RuntimeError):
    """Raised when ffmpeg fails or the timeline is unrenderable."""


@dataclass(frozen=True)
class RenderPreset:
    width: int = 1920
    height: int = 1080
    fps: int = 30
    crf: int = 20
    preset: str = "medium"
    audio_sample_rate: int = 48000
    audio_bitrate: str = "192k"


DEFAULT_PRESET = RenderPreset()


def _v1_track_id(timeline: Mapping[str, Any]) -> str | None:
    tracks = timeline.get("tracks") or []
    v1 = next(
        (
            t
            for t in tracks
            if isinstance(t, Mapping) and t.get("kind") == "video" and t.get("index") == 0
        ),
        None,
    )
    if not v1:
        return None
    return str(v1.get("id") or "")


def _sorted_v1_clips(timeline: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    track_id = _v1_track_id(timeline)
    if not track_id:
        return []
    clips = [
        c
        for c in (timeline.get("clips") or [])
        if isinstance(c, Mapping) and c.get("track_id") == track_id
    ]
    return sorted(clips, key=lambda c: float(c.get("start_seconds") or 0.0))


def build_command(
    timeline: Mapping[str, Any],
    asset_paths: Mapping[str, str | Path],
    asset_has_audio: Mapping[str, bool],
    output_path: str | Path,
    preset: RenderPreset = DEFAULT_PRESET,
) -> list[str] | None:
    """Return an ffmpeg argv list, or None if the timeline has nothing to render."""
    v1 = _sorted_v1_clips(timeline)
    if not v1:
        return None

    unique_assets: dict[str, int] = {}
    inputs: list[str] = []
    for clip in v1:
        asset_id = str(clip.get("asset_id") or "")
        if not asset_id or asset_id in unique_assets:
            continue
        path = asset_paths.get(asset_id)
        if not path:
            raise RenderError(f"Asset {asset_id} has no resolved source path")
        unique_assets[asset_id] = len(unique_assets)
        inputs.extend(["-i", str(path)])

    filters: list[str] = []
    segments: list[tuple[str, str]] = []
    current_time = 0.0
    W, H, F = preset.width, preset.height, preset.fps
    A = preset.audio_sample_rate

    for i, clip in enumerate(v1):
        start = float(clip.get("start_seconds") or 0.0)
        in_s = float(clip.get("in_seconds") or 0.0)
        out_s = float(clip.get("out_seconds") or 0.0)
        duration = max(0.0, out_s - in_s)
        if duration <= 0:
            continue

        if start > current_time + 1e-3:
            gap_dur = start - current_time
            gv, ga = f"g{i}v", f"g{i}a"
            filters.append(f"color=c=black:s={W}x{H}:d={gap_dur:.3f}:r={F}[{gv}]")
            filters.append(f"anullsrc=r={A}:cl=stereo:d={gap_dur:.3f}[{ga}]")
            segments.append((gv, ga))

        asset_id = str(clip.get("asset_id") or "")
        idx = unique_assets[asset_id]
        cv, ca = f"c{i}v", f"c{i}a"

        filters.append(
            f"[{idx}:v]trim=start={in_s:.3f}:end={out_s:.3f},"
            "setpts=PTS-STARTPTS,"
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"fps={F},setsar=1[{cv}]"
        )

        if asset_has_audio.get(asset_id):
            filters.append(
                f"[{idx}:a]atrim=start={in_s:.3f}:end={out_s:.3f},"
                f"asetpts=PTS-STARTPTS,aresample={A},aformat=sample_fmts=fltp:channel_layouts=stereo[{ca}]"
            )
        else:
            filters.append(
                f"anullsrc=r={A}:cl=stereo:d={duration:.3f}[{ca}]"
            )

        segments.append((cv, ca))
        current_time = start + duration

    if not segments:
        return None

    concat_inputs = "".join(f"[{v}][{a}]" for v, a in segments)
    filters.append(f"{concat_inputs}concat=n={len(segments)}:v=1:a=1[vout][aout]")

    return [
        _FFMPEG,
        "-nostdin",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-c:v",
        "libx264",
        "-preset",
        preset.preset,
        "-crf",
        str(preset.crf),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        preset.audio_bitrate,
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        "-nostats",
        str(output_path),
    ]


def _expected_duration(timeline: Mapping[str, Any]) -> float:
    clips = _sorted_v1_clips(timeline)
    end = 0.0
    for c in clips:
        start = float(c.get("start_seconds") or 0.0)
        in_s = float(c.get("in_seconds") or 0.0)
        out_s = float(c.get("out_seconds") or 0.0)
        end = max(end, start + max(0.0, out_s - in_s))
    return end


def render_timeline(
    timeline: Mapping[str, Any],
    asset_paths: Mapping[str, str | Path],
    asset_has_audio: Mapping[str, bool],
    output_path: str | Path,
    preset: RenderPreset = DEFAULT_PRESET,
    on_progress: ProgressCallback | None = None,
    timeout: float = 60 * 60,
) -> Path:
    """Render ``timeline`` into ``output_path`` via ffmpeg; return the path."""
    argv = build_command(timeline, asset_paths, asset_has_audio, output_path, preset)
    if not argv:
        raise RenderError("Timeline is empty — nothing to render")

    total = _expected_duration(timeline) or 1.0
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        raise RenderError("ffmpeg executable not found on PATH") from exc

    last_emit = 0.0
    stderr_tail: list[str] = []
    start_time = time.monotonic()

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            if line.startswith("out_time_ms="):
                try:
                    out_time_ms = int(line.split("=", 1)[1])
                except ValueError:
                    continue
                pct = min(0.999, (out_time_ms / 1_000_000.0) / total)
                now = time.monotonic()
                if on_progress and now - last_emit >= 0.5:
                    on_progress(pct)
                    last_emit = now
            elif line == "progress=end":
                if on_progress:
                    on_progress(1.0)
            if time.monotonic() - start_time > timeout:
                proc.kill()
                raise RenderError(f"ffmpeg timed out after {timeout}s")
    finally:
        if proc.stderr:
            stderr_tail = _read_tail(proc.stderr)
        rc = proc.wait()

    if rc != 0 or not out.exists():
        raise RenderError(
            f"ffmpeg exited {rc}: {' | '.join(stderr_tail[-5:])[:800]}"
        )

    return out


def _read_tail(stream: Iterable[str], max_lines: int = 200) -> list[str]:
    lines: list[str] = []
    for line in stream:
        lines.append(line.rstrip("\n"))
        if len(lines) > max_lines:
            lines.pop(0)
    return lines
