"""MediaAsset model — built in M1.

Will hold:
    - source_path (absolute filesystem path)
    - probe metadata (duration, streams) from engine.ffmpeg.probe
    - proxy_path (1280×720 H.264 MP4 built by engine.ffmpeg.build_proxy)
    - thumbnail_path (poster frame from engine.ffmpeg.extract_poster)
    - kind (video | audio | image)
    - status (ingesting | ready | failed)

See docs/ROADMAP.md M1.
"""

from django.db import models  # noqa: F401
