"""Sidecar health endpoint. The Electron main process polls this on boot
before loading the renderer."""

from __future__ import annotations

import platform
import shutil

from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response


@api_view(["GET"])
def health(_request: Request) -> Response:
    return Response(
        {
            "status": "ok",
            "version": "0.0.1",
            "milestone": "M0",
            "platform": platform.system().lower(),
            "ffmpeg_on_path": bool(shutil.which("ffmpeg")),
            "ffprobe_on_path": bool(shutil.which("ffprobe")),
        }
    )
