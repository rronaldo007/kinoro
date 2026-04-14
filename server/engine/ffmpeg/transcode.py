"""Proxy transcode via ffmpeg — low-bitrate H.264 for in-browser scrubbing."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_FFMPEG = "ffmpeg"


class TranscodeError(RuntimeError):
    """Raised when proxy generation fails."""


def build_proxy(
    source: str | Path,
    dest: str | Path,
    max_height: int = 720,
    crf: int = 26,
    preset: str = "veryfast",
    timeout: float = 60 * 30,
) -> Path:
    """Transcode ``source`` to an H.264 + AAC MP4 proxy at ``dest``.

    Proxies are optimized for scrub performance in a browser:
    - `-movflags +faststart` for HTTP byte-range seeking
    - capped at ``max_height`` px (letterboxed)
    - yuv420p pixel format for universal HTML5 compatibility
    """
    src = Path(source)
    out = Path(dest)
    out.parent.mkdir(parents=True, exist_ok=True)

    vf = (
        f"scale='min({max_height * 16 // 9},iw)':"
        f"'min({max_height},ih)':force_original_aspect_ratio=decrease,"
        "pad=ceil(iw/2)*2:ceil(ih/2)*2"
    )
    argv = [
        _FFMPEG,
        "-nostdin",
        "-y",
        "-i",
        str(src),
        "-map",
        "0:v:0?",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-vf",
        vf,
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(out),
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
        raise TranscodeError("ffmpeg executable not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise TranscodeError(f"ffmpeg timed out after {timeout}s") from exc

    if completed.returncode != 0 or not out.exists():
        raise TranscodeError(
            f"ffmpeg exited {completed.returncode}: {completed.stderr.strip()[:500]}"
        )
    return out
