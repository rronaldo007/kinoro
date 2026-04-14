"""Thumbnail extraction via ffmpeg.

Used by ingest to generate a single poster frame + later by the timeline to
generate per-second filmstrips.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_FFMPEG = "ffmpeg"


class ThumbnailError(RuntimeError):
    """Raised when thumbnail extraction fails."""


def extract_poster(
    source: str | Path,
    dest: str | Path,
    at_seconds: float = 1.0,
    width: int = 640,
    timeout: float = 30.0,
) -> Path:
    """Extract a single JPEG poster frame at ``at_seconds`` seeking.

    We use fast input-side seek (-ss before -i) at the caller-provided position,
    which is inaccurate but 10× faster and fine for a poster. For accurate
    per-frame scrubbing, callers should use a separate filmstrip pipeline.
    """
    src = Path(source)
    out = Path(dest)
    out.parent.mkdir(parents=True, exist_ok=True)

    argv = [
        _FFMPEG,
        "-nostdin",
        "-y",
        "-ss",
        f"{max(0.0, at_seconds):.3f}",
        "-i",
        str(src),
        "-frames:v",
        "1",
        "-vf",
        f"scale={width}:-2:flags=bicubic",
        "-q:v",
        "3",
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
        raise ThumbnailError("ffmpeg executable not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ThumbnailError(f"ffmpeg timed out after {timeout}s") from exc

    if completed.returncode != 0 or not out.exists():
        raise ThumbnailError(
            f"ffmpeg exited {completed.returncode}: {completed.stderr.strip()[:500]}"
        )
    return out
