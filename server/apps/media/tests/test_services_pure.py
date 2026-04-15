"""Unit tests for the pure classifier in ``apps.media.services``.

Classification is where real-world probe results map to our Kind enum. It
has edge cases (single-frame images that ffprobe reports as zero-duration
video streams) so it's worth guarding.
"""

from __future__ import annotations

from apps.media.models import MediaAsset
from apps.media.services import _classify
from engine.ffmpeg import AudioStream, ProbeResult, VideoStream


def _probe(
    *,
    duration: float = 0.0,
    video: list[VideoStream] | None = None,
    audio: list[AudioStream] | None = None,
) -> ProbeResult:
    return ProbeResult(
        duration=duration,
        container="mov,mp4,m4a,3gp,3g2,mj2",
        size_bytes=0,
        video=video or [],
        audio=audio or [],
    )


def _video(duration: float = 10.0) -> VideoStream:
    return VideoStream(
        index=0,
        codec="h264",
        width=1920,
        height=1080,
        fps=30.0,
    )


def _audio() -> AudioStream:
    return AudioStream(
        index=0,
        codec="aac",
        sample_rate=48000,
        channels=2,
    )


class TestClassify:
    def test_video_with_audio_is_video(self) -> None:
        result = _probe(duration=10.0, video=[_video()], audio=[_audio()])
        assert _classify(result) == MediaAsset.Kind.VIDEO

    def test_video_without_audio_is_video_when_long_enough(self) -> None:
        result = _probe(duration=10.0, video=[_video()])
        assert _classify(result) == MediaAsset.Kind.VIDEO

    def test_single_frame_video_no_audio_is_image(self) -> None:
        # ffprobe reports still images as zero-duration video streams.
        result = _probe(duration=0.04, video=[_video()])
        assert _classify(result) == MediaAsset.Kind.IMAGE

    def test_short_video_with_audio_stays_video(self) -> None:
        # Duration < 0.5s but has audio → still a (very short) video, not an image.
        result = _probe(duration=0.2, video=[_video()], audio=[_audio()])
        assert _classify(result) == MediaAsset.Kind.VIDEO

    def test_audio_only_is_audio(self) -> None:
        result = _probe(duration=30.0, audio=[_audio()])
        assert _classify(result) == MediaAsset.Kind.AUDIO

    def test_empty_probe_is_unknown(self) -> None:
        result = _probe()
        assert _classify(result) == MediaAsset.Kind.UNKNOWN
