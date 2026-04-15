"""Pytest bootstrap for the Kinoro sidecar.

Two responsibilities:
1. Point Django's SQLite + data dirs at a throwaway tmp directory BEFORE
   Django settings load. Otherwise tests would read/write the real
   ``~/.config/kinoro-app/data/kinoro.sqlite3`` the running sidecar uses.
2. Provide common fixtures for the async import/ingest paths (tmp media
   roots, a tiny real video, etc.).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# MUST run before `django.setup()` (pytest-django imports the settings module
# when it sees `DJANGO_SETTINGS_MODULE`).
_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="kinoro-test-"))
os.environ["KINORO_DATA_DIR"] = str(_TEST_DATA_DIR)


@pytest.fixture
def kinoro_data_dir() -> Path:
    """The per-session tmp data dir that mirrors KINORO_DATA_DIR."""
    return _TEST_DATA_DIR


@pytest.fixture
def tiny_video(tmp_path: Path) -> Path:
    """Generate a 1-second black MP4 via ffmpeg for ingest integration tests.

    Skips the test if ffmpeg isn't on PATH so CI without ffmpeg doesn't fail.
    """
    import shutil
    import subprocess

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not on PATH — skipping integration test")

    out = tmp_path / "tiny.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=black:size=320x180:rate=24:duration=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out
