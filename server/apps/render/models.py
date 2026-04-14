"""RenderJob model — built in M5.

Will hold:
    - project (FK)
    - preset (youtube_1080p | tiktok_vertical | custom)
    - status (queued | rendering | done | failed)
    - progress (0.0 - 1.0, streamed from engine.deliver.render_timeline)
    - output_path
    - error_message

See docs/ROADMAP.md M5.
"""

from django.db import models  # noqa: F401
