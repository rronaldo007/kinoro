"""Timeline-to-video render.

Takes a ``TimelineDoc`` (as a dict) + a map of asset_id → source file path, and
produces a single MP4. Scope:

- V1 video track (required) plus optional V2 overlay composite
- Optional A1/A2 audio tracks, mixed with V1's own audio via ``amix``
- Silent gaps between audio clips (``anullsrc``); black fill between V1 clips
- Boundary fades to/from black, plus cross-fade dissolves between flush-adjacent
  V1 clips when both sides ask (``transition_in/out``). Transitions are V1-only
  for now — V2 clips are composited as plain enable-gated overlays.
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


def _track_id(timeline: Mapping[str, Any], kind: str, index: int) -> str | None:
    """Return the id of the track matching ``(kind, index)``, or None."""
    tracks = timeline.get("tracks") or []
    t = next(
        (
            t
            for t in tracks
            if isinstance(t, Mapping)
            and t.get("kind") == kind
            and t.get("index") == index
        ),
        None,
    )
    if not t:
        return None
    return str(t.get("id") or "")


def _sorted_clips_on_track(
    timeline: Mapping[str, Any], kind: str, index: int
) -> list[Mapping[str, Any]]:
    """All media clips on a given ``(kind, index)`` track, sorted by start."""
    track_id = _track_id(timeline, kind, index)
    if not track_id:
        return []
    clips = [
        c
        for c in (timeline.get("clips") or [])
        if isinstance(c, Mapping)
        and c.get("track_id") == track_id
        and (c.get("type") or "media") == "media"
    ]
    return sorted(clips, key=lambda c: float(c.get("start_seconds") or 0.0))


def _sorted_v1_clips(timeline: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Back-compat shim. V1 is (video, index=0)."""
    return _sorted_clips_on_track(timeline, "video", 0)


def _text_clips(timeline: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Every ``type=text`` clip, regardless of track. Applied as drawtext
    overlays on the composed video output."""
    return [
        c
        for c in (timeline.get("clips") or [])
        if isinstance(c, Mapping) and (c.get("type") or "") == "text"
    ]


def _escape_drawtext(text: str) -> str:
    """Escape the subset of characters ffmpeg's drawtext filter cares about."""
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("%", "\\%")
    )


def _drawtext_filter_parts(text_clips: Iterable[Mapping[str, Any]]) -> list[str]:
    """Build one drawtext filter per text clip. Chained with commas on the
    composed [vout] stream in ``build_command``.

    Each drawtext uses ``enable='between(t,start,end)'`` so the overlay only
    shows during the clip's timeline window.
    """
    parts: list[str] = []
    for c in text_clips:
        content = str(c.get("text_content") or "").strip()
        if not content:
            continue
        start = float(c.get("start_seconds") or 0.0)
        out_s = float(c.get("out_seconds") or 0.0)
        in_s = float(c.get("in_seconds") or 0.0)
        dur = max(0.0, out_s - in_s)
        end = start + dur
        if end <= start:
            continue
        size = max(8, min(256, int(c.get("text_font_size") or 64)))
        color = str(c.get("text_color") or "white")
        x_norm = float(c.get("text_x") or 0.5)
        y_norm = float(c.get("text_y") or 0.5)
        parts.append(
            "drawtext=text='{text}':fontsize={size}:fontcolor={color}"
            ":x=(w-text_w)*{x:.4f}:y=(h-text_h)*{y:.4f}"
            ":enable='between(t,{start:.3f},{end:.3f})'".format(
                text=_escape_drawtext(content),
                size=size,
                color=color,
                x=max(0.0, min(1.0, x_norm)),
                y=max(0.0, min(1.0, y_norm)),
                start=start,
                end=end,
            )
        )
    return parts


def _clip_speed(clip: Mapping[str, Any]) -> float:
    """Clamped playback speed with a sane default. 1.0 = normal."""
    try:
        speed = float(clip.get("speed") or 1.0)
    except (TypeError, ValueError):
        speed = 1.0
    if speed <= 0:
        speed = 1.0
    # Keep the filter math numerically safe; 10×/0.1× is plenty.
    return max(0.1, min(10.0, speed))


def _atempo_chain(speed: float) -> str:
    """ffmpeg's ``atempo`` filter only accepts [0.5, 2.0] per stage; chain
    stages to cover wider speed ratios without pitch correction breaking."""
    if abs(speed - 1.0) < 1e-4:
        return ""
    stages: list[float] = []
    remaining = speed
    while remaining > 2.0:
        stages.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        stages.append(0.5)
        remaining /= 0.5
    stages.append(remaining)
    return ",".join(f"atempo={s:.6f}" for s in stages)


# ---------------------------------------------------------------------------
# Transitions (M4)
# ---------------------------------------------------------------------------


def _fps(timeline: Mapping[str, Any]) -> int:
    """Project frame rate, falling back to 30 if missing/invalid."""
    try:
        fps = int(timeline.get("fps") or 0)
    except (TypeError, ValueError):
        fps = 0
    return fps if fps > 0 else 30


def _transition_duration_seconds(
    transition: Mapping[str, Any] | None,
    fps: int,
    clip_timeline_dur: float | None = None,
) -> float:
    """Convert a transition spec to seconds, clamped both by frame range and
    by half the clip's timeline duration (so a 3 s clip with a 2 s fade
    doesn't blow up the math)."""
    if not isinstance(transition, Mapping):
        return 0.0
    raw = transition.get("duration_frames")
    try:
        frames = int(raw)
    except (TypeError, ValueError):
        return 0.0
    frames = max(1, min(120, frames))
    f = max(1, fps)
    secs = frames / f
    if clip_timeline_dur is not None and clip_timeline_dur > 0:
        secs = min(secs, clip_timeline_dur / 2.0)
    return max(0.0, secs)


def _transition(clip: Mapping[str, Any], edge: str) -> Mapping[str, Any] | None:
    """Return the transition spec for ``edge`` ("in" or "out") if it's a
    well-formed mapping with a known kind, else None. Empty dicts and unknown
    kinds collapse to None for back-compat."""
    key = "transition_in" if edge == "in" else "transition_out"
    raw = clip.get(key)
    if not isinstance(raw, Mapping) or not raw:
        return None
    kind = raw.get("kind")
    if kind not in ("fade", "dissolve"):
        return None
    return raw


@dataclass(frozen=True)
class _Segment:
    """One slot in the V1 stitch: either a real clip or a black gap."""

    v_label: str
    a_label: str
    duration: float
    is_clip: bool
    # The clip's index in the original v1 list (only meaningful for is_clip).
    clip_index: int = -1


# ---------------------------------------------------------------------------
# build_command
# ---------------------------------------------------------------------------


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

    # V2 overlay track + optional audio tracks A1/A2. Transitions on these are
    # intentionally ignored — the V1 stitch owns transitions for now.
    v2 = _sorted_clips_on_track(timeline, "video", 1)
    a1 = _sorted_clips_on_track(timeline, "audio", 0)
    a2 = _sorted_clips_on_track(timeline, "audio", 1)
    extra_audio_tracks = [t for t in (a1, a2) if t]

    unique_assets: dict[str, int] = {}
    inputs: list[str] = []

    def _register_asset(clip: Mapping[str, Any]) -> None:
        asset_id = str(clip.get("asset_id") or "")
        if not asset_id or asset_id in unique_assets:
            return
        path = asset_paths.get(asset_id)
        if not path:
            raise RenderError(f"Asset {asset_id} has no resolved source path")
        unique_assets[asset_id] = len(unique_assets)
        inputs.extend(["-i", str(path)])

    for clip in v1:
        _register_asset(clip)
    for clip in v2:
        _register_asset(clip)
    for track in extra_audio_tracks:
        for clip in track:
            _register_asset(clip)

    fps_proj = _fps(timeline)
    filters: list[str] = []
    segments: list[_Segment] = []
    current_time = 0.0
    W, H, F = preset.width, preset.height, preset.fps
    A = preset.audio_sample_rate
    multitrack = bool(v2 or extra_audio_tracks)

    # Pass 1: per-clip stream emission. Each media clip produces [cNv]/[cNa]
    # with optional boundary fade=t=in/out and afade applied in-line.
    # Dissolves are NOT applied here — they're stitched in pass 2.
    for i, clip in enumerate(v1):
        start = float(clip.get("start_seconds") or 0.0)
        in_s = float(clip.get("in_seconds") or 0.0)
        out_s = float(clip.get("out_seconds") or 0.0)
        speed = _clip_speed(clip)
        source_dur = max(0.0, out_s - in_s)
        if source_dur <= 0:
            continue
        # On the timeline, a clip played at speed S occupies source_dur / S.
        timeline_dur = source_dur / speed

        if start > current_time + 1e-3:
            gap_dur = start - current_time
            gv, ga = f"g{i}v", f"g{i}a"
            filters.append(f"color=c=black:s={W}x{H}:d={gap_dur:.3f}:r={F}[{gv}]")
            filters.append(f"anullsrc=r={A}:cl=stereo:d={gap_dur:.3f}[{ga}]")
            segments.append(
                _Segment(v_label=gv, a_label=ga, duration=gap_dur, is_clip=False)
            )

        # Boundary fade decisions. A "fade" always paints to/from black on
        # this clip's edge. A "dissolve" is handled later by xfade IF the
        # neighbour also asked; otherwise it degrades to a fade.
        prev_clip = v1[i - 1] if i > 0 else None
        next_clip = v1[i + 1] if i + 1 < len(v1) else None
        fade_in_secs = _solo_fade_duration(
            clip, prev_clip, current_time, start, "in", fps_proj, timeline_dur
        )
        fade_out_secs = _solo_fade_duration(
            clip, next_clip, start, start + timeline_dur, "out", fps_proj, timeline_dur
        )

        asset_id = str(clip.get("asset_id") or "")
        idx = unique_assets[asset_id]
        cv, ca = f"c{i}v", f"c{i}a"

        speed_expr = (
            f"setpts=(PTS-STARTPTS)/{speed:.6f}"
            if abs(speed - 1.0) > 1e-4
            else "setpts=PTS-STARTPTS"
        )
        v_chain = (
            f"[{idx}:v]trim=start={in_s:.3f}:end={out_s:.3f},"
            f"{speed_expr},"
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"fps={F},setsar=1"
        )
        if fade_in_secs > 0:
            v_chain += f",fade=t=in:st=0:d={fade_in_secs:.3f}"
        if fade_out_secs > 0:
            fo_start = max(0.0, timeline_dur - fade_out_secs)
            v_chain += f",fade=t=out:st={fo_start:.3f}:d={fade_out_secs:.3f}"
        v_chain += f"[{cv}]"
        filters.append(v_chain)

        if asset_has_audio.get(asset_id):
            atempo = _atempo_chain(speed)
            atempo_part = f",{atempo}" if atempo else ""
            a_chain = (
                f"[{idx}:a]atrim=start={in_s:.3f}:end={out_s:.3f},"
                f"asetpts=PTS-STARTPTS{atempo_part},"
                f"aresample={A},aformat=sample_fmts=fltp:channel_layouts=stereo"
            )
            if fade_in_secs > 0:
                a_chain += f",afade=t=in:st=0:d={fade_in_secs:.3f}"
            if fade_out_secs > 0:
                fo_start = max(0.0, timeline_dur - fade_out_secs)
                a_chain += f",afade=t=out:st={fo_start:.3f}:d={fade_out_secs:.3f}"
            a_chain += f"[{ca}]"
            filters.append(a_chain)
        else:
            filters.append(
                f"anullsrc=r={A}:cl=stereo:d={timeline_dur:.3f}[{ca}]"
            )

        segments.append(
            _Segment(
                v_label=cv,
                a_label=ca,
                duration=timeline_dur,
                is_clip=True,
                clip_index=i,
            )
        )
        current_time = start + timeline_dur

    if not segments:
        return None

    # Pass 2: stitch. Walk segments left→right, accumulating into [accv]/[acca].
    # For each adjacent pair of clip-segments where BOTH sides ask for a
    # dissolve, use xfade/acrossfade. Otherwise, plain concat.
    #
    # Label plumbing depends on what post-processing we need:
    #   single-track, no text      → stitch directly to [vout][aout] (byte-same
    #                                 shape as the pre-multitrack renderer).
    #   single-track, text         → stitch to [vmix][aout], drawtext → [vout].
    #   multitrack (V2 and/or A*)  → stitch to intermediate [v1vout][v1aout],
    #                                 then overlay V2 → [vcomp] (or [v1vout]
    #                                 passthrough), amix audio → [aout], and
    #                                 finally drawtext (if any) → [vout].
    text_parts = _drawtext_filter_parts(_text_clips(timeline))

    if multitrack:
        stitch_v = "v1vout"
        stitch_a = "v1aout"
    elif text_parts:
        stitch_v = "vmix"
        stitch_a = "aout"
    else:
        stitch_v = "vout"
        stitch_a = "aout"
    _stitch_segments(filters, v1, segments, fps_proj, stitch_v, stitch_a)

    # V2 overlay composite.
    if v2:
        overlay_out = "vcomp"
        _emit_v2_overlay(filters, v2, unique_assets, asset_has_audio, preset,
                         base_label=stitch_v, out_label=overlay_out)
        video_after_composite = overlay_out
    else:
        video_after_composite = stitch_v

    # Audio mix: V1's stitched audio + each audio track's concat stream.
    if extra_audio_tracks:
        track_audio_labels: list[str] = [stitch_a]
        for ti, track in enumerate(extra_audio_tracks):
            label = f"at{ti}"
            _emit_audio_track(filters, track, ti, unique_assets, asset_has_audio,
                              preset, out_label=label)
            track_audio_labels.append(label)
        # amix combines inputs; ``duration=longest`` keeps any trailing audio.
        amix_inputs = "".join(f"[{lbl}]" for lbl in track_audio_labels)
        filters.append(
            f"{amix_inputs}amix=inputs={len(track_audio_labels)}"
            f":duration=longest:dropout_transition=0,"
            f"aresample={A},aformat=sample_fmts=fltp:channel_layouts=stereo"
            f"[aout]"
        )
        audio_final = "aout"
    else:
        audio_final = stitch_a  # already "aout" (single-track) or plumbed.

    # drawtext chains onto whatever video label is current.
    if text_parts:
        filters.append(
            f"[{video_after_composite}]" + ",".join(text_parts) + "[vout]"
        )
        v_out = "vout"
    else:
        if video_after_composite != "vout":
            # Alias the composite to [vout] via a passthrough null filter.
            filters.append(f"[{video_after_composite}]null[vout]")
            v_out = "vout"
        else:
            v_out = "vout"

    # Ensure audio lands on [aout]. For single-track paths stitch_a is
    # already "aout". For multitrack paths the amix step wrote [aout].
    a_out = audio_final
    if a_out != "aout":
        filters.append(f"[{a_out}]anull[aout]")
        a_out = "aout"

    return [
        _FFMPEG,
        "-nostdin",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        f"[{v_out}]",
        "-map",
        f"[{a_out}]",
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


def _emit_v2_overlay(
    filters: list[str],
    v2: list[Mapping[str, Any]],
    unique_assets: Mapping[str, int],
    asset_has_audio: Mapping[str, bool],  # noqa: ARG001 — audio ignored on V2
    preset: RenderPreset,
    base_label: str,
    out_label: str,
) -> None:
    """Composite V2 clips onto ``[base_label]`` as enable-gated overlays.

    Each V2 media clip is trimmed/speed-adjusted/scaled/padded the same way
    V1 clips are, then ``overlay=enable='between(t,start,end)'`` paints it on
    top during its timeline window. V2 gaps remain transparent (base shows
    through) because we never draw anything during gap ranges.

    Transitions on V2 are intentionally ignored for now; see module docstring.
    """
    W, H, F = preset.width, preset.height, preset.fps
    acc = base_label
    last = len(v2) - 1
    for i, clip in enumerate(v2):
        start = float(clip.get("start_seconds") or 0.0)
        in_s = float(clip.get("in_seconds") or 0.0)
        out_s = float(clip.get("out_seconds") or 0.0)
        speed = _clip_speed(clip)
        source_dur = max(0.0, out_s - in_s)
        if source_dur <= 0:
            continue
        timeline_dur = source_dur / speed
        end = start + timeline_dur

        asset_id = str(clip.get("asset_id") or "")
        idx = unique_assets[asset_id]
        cv = f"v2c{i}v"
        speed_expr = (
            f"setpts=(PTS-STARTPTS)/{speed:.6f}"
            if abs(speed - 1.0) > 1e-4
            else "setpts=PTS-STARTPTS"
        )
        # ``setpts=PTS+start/TB`` shifts this overlay's timeline origin so
        # that ``enable=between(t,start,end)`` lines up with the base clock.
        filters.append(
            f"[{idx}:v]trim=start={in_s:.3f}:end={out_s:.3f},"
            f"{speed_expr},"
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"fps={F},setsar=1,"
            f"setpts=PTS+{start:.3f}/TB"
            f"[{cv}]"
        )
        nxt = out_label if i == last else f"v2mix{i}"
        filters.append(
            f"[{acc}][{cv}]overlay=shortest=0:x=0:y=0"
            f":enable='between(t,{start:.3f},{end:.3f})'"
            f"[{nxt}]"
        )
        acc = nxt

    # If every V2 clip had zero source_dur and was skipped, we still need to
    # write out_label so callers don't dangle. Alias base → out.
    if acc == base_label:
        filters.append(f"[{base_label}]null[{out_label}]")


def _emit_audio_track(
    filters: list[str],
    track_clips: list[Mapping[str, Any]],
    track_index: int,
    unique_assets: Mapping[str, int],
    asset_has_audio: Mapping[str, bool],
    preset: RenderPreset,
    out_label: str,
) -> None:
    """Concat a single audio track's clips (with silent gaps) into ``[out_label]``.

    Each clip's audio is trimmed/atempo-adjusted, and ``anullsrc`` fills any
    gap between clip_start and the previous segment's end. The result is one
    contiguous audio stream starting at t=0. If a clip's source has no audio,
    we emit silence of the same timeline duration.
    """
    A = preset.audio_sample_rate
    segs: list[str] = []
    current = 0.0
    for i, clip in enumerate(track_clips):
        start = float(clip.get("start_seconds") or 0.0)
        in_s = float(clip.get("in_seconds") or 0.0)
        out_s = float(clip.get("out_seconds") or 0.0)
        speed = _clip_speed(clip)
        source_dur = max(0.0, out_s - in_s)
        if source_dur <= 0:
            continue
        timeline_dur = source_dur / speed

        if start > current + 1e-3:
            gap_dur = start - current
            g = f"at{track_index}g{i}"
            filters.append(f"anullsrc=r={A}:cl=stereo:d={gap_dur:.3f}[{g}]")
            segs.append(g)

        asset_id = str(clip.get("asset_id") or "")
        idx = unique_assets[asset_id]
        ca = f"at{track_index}c{i}"
        if asset_has_audio.get(asset_id):
            atempo = _atempo_chain(speed)
            atempo_part = f",{atempo}" if atempo else ""
            filters.append(
                f"[{idx}:a]atrim=start={in_s:.3f}:end={out_s:.3f},"
                f"asetpts=PTS-STARTPTS{atempo_part},"
                f"aresample={A},aformat=sample_fmts=fltp:channel_layouts=stereo"
                f"[{ca}]"
            )
        else:
            filters.append(
                f"anullsrc=r={A}:cl=stereo:d={timeline_dur:.3f}[{ca}]"
            )
        segs.append(ca)
        current = start + timeline_dur

    if not segs:
        # All clips had zero duration: emit a single tick of silence so the
        # label still exists for amix. Shouldn't happen in practice.
        filters.append(f"anullsrc=r={A}:cl=stereo:d=0.010[{out_label}]")
        return

    if len(segs) == 1:
        # Single segment: alias it so downstream amix sees [out_label].
        filters.append(f"[{segs[0]}]anull[{out_label}]")
        return

    concat_inputs = "".join(f"[{s}]" for s in segs)
    filters.append(
        f"{concat_inputs}concat=n={len(segs)}:v=0:a=1[{out_label}]"
    )


def _solo_fade_duration(
    clip: Mapping[str, Any],
    neighbour: Mapping[str, Any] | None,
    boundary_a: float,
    boundary_b: float,
    edge: str,  # "in" or "out"
    fps_proj: int,
    clip_timeline_dur: float,
) -> float:
    """Return the duration (seconds) of a solo fade-from-black / fade-to-black
    on this clip's edge, or 0.0 if no such fade applies.

    Rules:
      - If this clip's transition_<edge> is "fade", always apply.
      - If this clip's transition_<edge> is "dissolve" but the neighbour does
        NOT have a matching dissolve on its facing edge OR the clips are not
        flush against each other, degrade to a fade.
      - If both sides ask for a dissolve and they're flush, the cross-fade is
        handled by the stitcher — no solo fade here.
    """
    spec = _transition(clip, edge)
    if spec is None:
        return 0.0
    kind = spec.get("kind")
    if kind == "fade":
        return _transition_duration_seconds(spec, fps_proj, clip_timeline_dur)
    if kind != "dissolve":
        return 0.0
    # Dissolve: only counts as cross-fade when the neighbour mirrors it AND
    # the clips touch. Otherwise degrade to fade.
    if _dissolve_pair_active(clip, neighbour, edge, boundary_a, boundary_b):
        return 0.0
    return _transition_duration_seconds(spec, fps_proj, clip_timeline_dur)


def _dissolve_pair_active(
    clip: Mapping[str, Any],
    neighbour: Mapping[str, Any] | None,
    edge: str,
    boundary_a: float,
    boundary_b: float,
) -> bool:
    """True iff this clip and its neighbour both ask for dissolve on their
    shared boundary AND that boundary is flush (no gap in between)."""
    if neighbour is None:
        return False
    other_edge = "out" if edge == "in" else "in"
    own = _transition(clip, edge)
    other = _transition(neighbour, other_edge)
    if not own or not other:
        return False
    if own.get("kind") != "dissolve" or other.get("kind") != "dissolve":
        return False
    # "in" edge: boundary_a == current_time, boundary_b == start
    # "out" edge: boundary_a == start, boundary_b == start + timeline_dur
    # We just need clips to be flush. The caller passes a/b such that for
    # an "in" check, a == previous current_time and b == clip's start; for
    # "out" we need to recompute alignment by checking the neighbour clip.
    if edge == "in":
        # Flush iff our start ≈ the boundary_a (which is current_time before us).
        return abs(boundary_b - boundary_a) < 1e-3
    # edge == "out": neighbour must start exactly where this clip ends.
    next_start = float(neighbour.get("start_seconds") or 0.0)
    return abs(next_start - boundary_b) < 1e-3


def _stitch_segments(
    filters: list[str],
    v1: list[Mapping[str, Any]],
    segments: list[_Segment],
    fps_proj: int,
    final_v_name: str,
    final_a_name: str,
) -> float:
    """Walk segments left-to-right and produce a single composite video+audio
    stream into ``[final_v_name]``/``[final_a_name]``. Returns the accumulated
    timeline duration.

    Cross-fade dissolves replace the join between two adjacent CLIP segments
    when both sides asked for ``dissolve`` and the clips are flush against
    each other. Everything else falls through to ``concat=n=2``.
    """
    if not segments:
        raise RenderError("No segments to stitch")

    # Common case: no dissolves anywhere → emit the original single concat=N
    # shape directly into the final labels so the filter_complex matches the
    # pre-transitions output exactly (regression-safe for existing tests).
    # Single-segment timelines also flow through here as concat=n=1.
    if not _any_dissolve_pair(v1, segments):
        concat_inputs = "".join(f"[{s.v_label}][{s.a_label}]" for s in segments)
        filters.append(
            f"{concat_inputs}concat=n={len(segments)}:v=1:a=1"
            f"[{final_v_name}][{final_a_name}]"
        )
        return sum(s.duration for s in segments)

    # General path: walk pairwise, emitting xfade or concat as appropriate.
    # The very last step writes into the final labels.
    acc_v = segments[0].v_label
    acc_a = segments[0].a_label
    acc_dur = segments[0].duration
    last = len(segments) - 1

    for i in range(1, len(segments)):
        nxt = segments[i]
        prev = segments[i - 1]
        is_last = i == last
        out_v = final_v_name if is_last else f"st{i}v"
        out_a = final_a_name if is_last else f"st{i}a"

        dissolve_secs = _pair_dissolve_seconds(v1, prev, nxt, fps_proj)
        if dissolve_secs > 0:
            offset = max(0.0, acc_dur - dissolve_secs)
            filters.append(
                f"[{acc_v}][{nxt.v_label}]xfade=transition=fade:"
                f"duration={dissolve_secs:.3f}:offset={offset:.3f}[{out_v}]"
            )
            filters.append(
                f"[{acc_a}][{nxt.a_label}]acrossfade=d={dissolve_secs:.3f}"
                f":c1=tri:c2=tri[{out_a}]"
            )
            acc_dur = acc_dur + nxt.duration - dissolve_secs
        else:
            filters.append(
                f"[{acc_v}][{nxt.v_label}][{acc_a}][{nxt.a_label}]"
                f"concat=n=2:v=1:a=1[{out_v}][{out_a}]"
            )
            acc_dur = acc_dur + nxt.duration

        acc_v, acc_a = out_v, out_a

    return acc_dur


def _any_dissolve_pair(
    v1: list[Mapping[str, Any]], segments: list[_Segment]
) -> bool:
    for i in range(1, len(segments)):
        prev, nxt = segments[i - 1], segments[i]
        if not (prev.is_clip and nxt.is_clip):
            continue
        c_prev = v1[prev.clip_index]
        c_next = v1[nxt.clip_index]
        out_t = _transition(c_prev, "out")
        in_t = _transition(c_next, "in")
        if (
            out_t
            and in_t
            and out_t.get("kind") == "dissolve"
            and in_t.get("kind") == "dissolve"
        ):
            # Flush check: next clip starts exactly where prev ends.
            prev_start = float(c_prev.get("start_seconds") or 0.0)
            speed = _clip_speed(c_prev)
            prev_dur = max(0.0, float(c_prev.get("out_seconds") or 0.0)
                           - float(c_prev.get("in_seconds") or 0.0)) / speed
            next_start = float(c_next.get("start_seconds") or 0.0)
            if abs(next_start - (prev_start + prev_dur)) < 1e-3:
                return True
    return False


def _pair_dissolve_seconds(
    v1: list[Mapping[str, Any]],
    prev: _Segment,
    nxt: _Segment,
    fps_proj: int,
) -> float:
    """Return the dissolve duration (s) for this pair, or 0 if no dissolve."""
    if not (prev.is_clip and nxt.is_clip):
        return 0.0
    c_prev = v1[prev.clip_index]
    c_next = v1[nxt.clip_index]
    out_t = _transition(c_prev, "out")
    in_t = _transition(c_next, "in")
    if not (
        out_t
        and in_t
        and out_t.get("kind") == "dissolve"
        and in_t.get("kind") == "dissolve"
    ):
        return 0.0
    # Flush check.
    prev_start = float(c_prev.get("start_seconds") or 0.0)
    speed = _clip_speed(c_prev)
    prev_dur = max(0.0, float(c_prev.get("out_seconds") or 0.0)
                   - float(c_prev.get("in_seconds") or 0.0)) / speed
    next_start = float(c_next.get("start_seconds") or 0.0)
    if abs(next_start - (prev_start + prev_dur)) >= 1e-3:
        return 0.0
    # Use the shorter of the two requests, then clamp to half of the SHORTER
    # clip's duration so the math stays sane.
    next_dur = max(0.0, float(c_next.get("out_seconds") or 0.0)
                   - float(c_next.get("in_seconds") or 0.0)) / _clip_speed(c_next)
    shorter = min(prev_dur, next_dur)
    a = _transition_duration_seconds(out_t, fps_proj, shorter)
    b = _transition_duration_seconds(in_t, fps_proj, shorter)
    return min(a, b)


def _expected_duration(timeline: Mapping[str, Any]) -> float:
    clips = _sorted_v1_clips(timeline)
    end = 0.0
    for c in clips:
        start = float(c.get("start_seconds") or 0.0)
        in_s = float(c.get("in_seconds") or 0.0)
        out_s = float(c.get("out_seconds") or 0.0)
        speed = _clip_speed(c)
        source_dur = max(0.0, out_s - in_s)
        end = max(end, start + source_dur / speed)
    # V2/A1/A2 clips may extend past V1's end — account for them so the
    # progress-percent math in render_timeline doesn't cap at 99.9%.
    for kind, index in (("video", 1), ("audio", 0), ("audio", 1)):
        for c in _sorted_clips_on_track(timeline, kind, index):
            start = float(c.get("start_seconds") or 0.0)
            in_s = float(c.get("in_seconds") or 0.0)
            out_s = float(c.get("out_seconds") or 0.0)
            speed = _clip_speed(c)
            source_dur = max(0.0, out_s - in_s)
            end = max(end, start + source_dur / speed)
    # Subtract dissolve overlaps — each dissolve shortens wall-clock by its
    # own duration since the next clip starts mid-fade.
    fps_proj = _fps(timeline)
    overlap = 0.0
    for i in range(1, len(clips)):
        prev = clips[i - 1]
        nxt = clips[i]
        prev_start = float(prev.get("start_seconds") or 0.0)
        prev_speed = _clip_speed(prev)
        prev_dur = max(0.0, float(prev.get("out_seconds") or 0.0)
                       - float(prev.get("in_seconds") or 0.0)) / prev_speed
        next_start = float(nxt.get("start_seconds") or 0.0)
        if abs(next_start - (prev_start + prev_dur)) >= 1e-3:
            continue
        out_t = _transition(prev, "out")
        in_t = _transition(nxt, "in")
        if not (
            out_t
            and in_t
            and out_t.get("kind") == "dissolve"
            and in_t.get("kind") == "dissolve"
        ):
            continue
        next_dur = max(0.0, float(nxt.get("out_seconds") or 0.0)
                       - float(nxt.get("in_seconds") or 0.0)) / _clip_speed(nxt)
        shorter = min(prev_dur, next_dur)
        a = _transition_duration_seconds(out_t, fps_proj, shorter)
        b = _transition_duration_seconds(in_t, fps_proj, shorter)
        overlap += min(a, b)
    return max(0.0, end - overlap)


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
