"""Kinoro Django settings — single-user desktop mode.

No auth, no workspaces, no billing. The sidecar only accepts connections from
the local Electron renderer via CORS, and from the Electron main process. It is
NEVER exposed to a network — bind to 127.0.0.1 only.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "KINORO_SECRET_KEY",
    # Desktop-local only — regenerated on first run in prod.
    "dev-secret-do-not-ship-to-anyone",
)

DEBUG = os.environ.get("KINORO_DEBUG", "1") == "1"

# Local-only. If this list ever grows beyond localhost, something is wrong.
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

# Electron renderer in dev lives at http://localhost:5174 (Vite); 5173 kept
# as a fallback for standalone Kinoro dev when Video Planner isn't running.
# In packaged builds the renderer loads via file:// and CORS is still required
# because it uses fetch/XHR to hit 127.0.0.1:<sidecar-port>.
CORS_ALLOWED_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:5174",
    "http://localhost:5174",
]
CORS_ALLOWED_ORIGIN_REGEXES = [
    # Electron file:// wraps the UI in a null origin; allow via regex.
    r"^file://",
]
CORS_ALLOW_CREDENTIALS = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    # Kinoro apps
    "apps.core",
    "apps.health",
    "apps.projects",
    "apps.media",
    "apps.render",
    "apps.import_vp",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Single local SQLite file in the user data directory. The Electron main
# process passes KINORO_DATA_DIR to the sidecar; in dev it falls back to
# <repo>/user-data/.
_DATA_DIR = Path(
    os.environ.get("KINORO_DATA_DIR")
    or (BASE_DIR.parent / "user-data")
).resolve()
_DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(_DATA_DIR / "kinoro.sqlite3"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Media / proxies / renders live inside the data directory.
MEDIA_ROOT = _DATA_DIR / "media"
MEDIA_URL = "/media/"

STATIC_URL = "/static/"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

REST_FRAMEWORK = {
    # Desktop-local: no auth. Anyone who can reach 127.0.0.1 IS the user.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
}

# Kinoro-specific paths exposed to apps.
KINORO_DATA_DIR = _DATA_DIR
KINORO_PROXY_DIR = _DATA_DIR / "proxies"
KINORO_RENDER_DIR = _DATA_DIR / "renders"
for _p in (KINORO_PROXY_DIR, KINORO_RENDER_DIR):
    _p.mkdir(parents=True, exist_ok=True)
