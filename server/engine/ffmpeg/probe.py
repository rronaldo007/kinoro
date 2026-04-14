"""ffprobe wrapper — extracts durations, streams, and codec metadata from a media file.

All ffmpeg/ffprobe subprocess calls MUST go through this module. Never shell out
to ffprobe directly from views, tasks, or engine code.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_FFPROBE = "ffprobe"


class ProbeError(RuntimeError):
    """Raised when ffprobe fails or returns unparseable output."""


@dataclass(frozen=True)
class VideoStream:
    index: int
    codec: str
    width: int
    height: int
    fps: float
    pix_fmt: str = ""
    bit_rate: int | None = None


@dataclass(frozen=True)
class AudioStream:
    index: int
    codec: str
    sample_rate: int
    channels: int
    bit_rate: int | None = None


@dataclass(frozen=True)
class ProbeResult:
    duration: float
    container: str
    size_bytes: int
    video: list[VideoStream] = field(default_factory=list)
    audio: list[AudioStream] = field(default_factory=list)

    @property
    def has_video(self) -> bool:
        return bool(self.video)

    @property
    def has_audio(self) -> bool:
        return bool(self.audio)

    @property
    def primary_video(self) -> VideoStream | None:
        return self.video[0] if self.video else None

    @property
    def primary_audio(self) -> AudioStream | None:
        return self.audio[0] if self.audio else None


def _parse_fps(rate: str) -> float:
    """ffprobe reports rates as 'num/den'. Handle zero denominators gracefully."""
    if not rate:
        return 0.0
    try:
        num, _, den = rate.partition("/")
        num_f = float(num)
        den_f = float(den) if den else 1.0
        if den_f == 0:
            return 0.0
        return num_f / den_f
    except (TypeError, ValueError):
        return 0.0


def probe(path: str | Path, timeout: float = 20.0) -> ProbeResult:
    """Probe a media file and return structured metadata.

    Raises:
        ProbeError: ffprobe missing, timed out, or produced no parseable JSON.
    """
    file_path = Path(path)
    argv = [
        _FFPROBE,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ProbeError("ffprobe executable not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ProbeError(f"ffprobe timed out after {timeout}s") from exc

    if completed.returncode != 0:
        raise ProbeError(
            f"ffprobe exited {completed.returncode}: {completed.stderr.strip()[:500]}"
        )

    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError("ffprobe produced invalid JSON") from exc

    fmt = data.get("format") or {}
    streams = data.get("streams") or []

    video: list[VideoStream] = []
    audio: list[AudioStream] = []
    for s in streams:
        codec_type = s.get("codec_type")
        if codec_type == "video":
            video.append(
                VideoStream(
                    index=int(s.get("index", 0)),
                    codec=s.get("codec_name", ""),
                    width=int(s.get("width") or 0),
                    height=int(s.get("height") or 0),
                    fps=_parse_fps(s.get("avg_frame_rate") or s.get("r_frame_rate") or ""),
                    pix_fmt=s.get("pix_fmt", ""),
                    bit_rate=int(s["bit_rate"]) if s.get("bit_rate") else None,
                )
            )
        elif codec_type == "audio":
            audio.append(
                AudioStream(
                    index=int(s.get("index", 0)),
                    codec=s.get("codec_name", ""),
                    sample_rate=int(s.get("sample_rate") or 0),
                    channels=int(s.get("channels") or 0),
                    bit_rate=int(s["bit_rate"]) if s.get("bit_rate") else None,
                )
            )

    try:
        duration = float(fmt.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0

    try:
        size_bytes = int(fmt.get("size") or file_path.stat().st_size)
    except (OSError, TypeError, ValueError):
        size_bytes = 0

    return ProbeResult(
        duration=duration,
        container=fmt.get("format_name", ""),
        size_bytes=size_bytes,
        video=video,
        audio=audio,
    )
