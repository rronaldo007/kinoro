"""ffmpeg — all ffmpeg/ffprobe subprocess calls live under this package.

Architectural rule: no other module in ``engine`` or ``apps`` may call
``subprocess.run("ffmpeg …")`` directly. Import the typed wrappers from here.
"""

from .probe import AudioStream, ProbeError, ProbeResult, VideoStream, probe
from .thumbnails import ThumbnailError, extract_poster
from .transcode import TranscodeError, build_proxy

__all__ = [
    "AudioStream",
    "ProbeError",
    "ProbeResult",
    "VideoStream",
    "probe",
    "ThumbnailError",
    "extract_poster",
    "TranscodeError",
    "build_proxy",
]
