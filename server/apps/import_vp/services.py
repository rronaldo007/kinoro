"""HTTP client for the Video Planner REST API.

Kinoro hits these endpoints (from video-planner3):

    POST /api/auth/login/             email+password → { access, refresh, user }
    POST /api/auth/refresh/           refresh → { access }
    GET  /api/auth/me/                current user
    GET  /api/projects/               list user's projects
    GET  /api/projects/<pk>/          project detail
    GET  /api/projects/<pk>/resources/  nested list (videos, sounds, …)
    GET  /api/resources/<pk>/download/  media file
    GET  /api/resources/<pk>/proxy/     proxy file (already built by VP)

Auth uses SimpleJWT: `Authorization: Bearer <access>`. Tokens last ~1 hour;
refresh on 401.

Keep this module thin and synchronous — the Django sidecar is single-user,
so we don't need async HTTP. Bigger imports run in a background thread (M1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import requests

logger = logging.getLogger(__name__)


class VPClientError(RuntimeError):
    """Raised for any failure talking to the Video Planner API."""


class VPAuthError(VPClientError):
    """401 from the API — token invalid or expired and refresh failed."""


@dataclass
class VPLoginResult:
    access: str
    refresh: str
    user: dict[str, Any]


class VPClient:
    """Stateless synchronous client. Hold instances per request — don't share."""

    def __init__(
        self,
        base_url: str,
        access_token: str | None = None,
        refresh_token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.timeout = timeout
        self._session = requests.Session()

    # ---- auth ---------------------------------------------------------------

    def login(self, email: str, password: str) -> VPLoginResult:
        r = self._session.post(
            f"{self.base_url}/api/auth/login/",
            json={"email": email, "password": password},
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise VPAuthError(
                f"login failed: {r.status_code} {r.text[:200]}"
            )
        data = r.json()
        self.access_token = data["access"]
        self.refresh_token = data["refresh"]
        return VPLoginResult(
            access=data["access"],
            refresh=data["refresh"],
            user=data.get("user", {}),
        )

    def refresh_access(self) -> str:
        if not self.refresh_token:
            raise VPAuthError("no refresh token stored")
        r = self._session.post(
            f"{self.base_url}/api/auth/refresh/",
            json={"refresh": self.refresh_token},
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise VPAuthError(
                f"refresh failed: {r.status_code} {r.text[:200]}"
            )
        self.access_token = r.json()["access"]
        return self.access_token

    def _auth_headers(self) -> dict[str, str]:
        if not self.access_token:
            raise VPAuthError("not authenticated — call login() first")
        return {"Authorization": f"Bearer {self.access_token}"}

    def _get(self, path: str, *, params: dict | None = None, stream: bool = False):
        """GET with automatic refresh-on-401 (one retry)."""
        url = f"{self.base_url}{path}"
        r = self._session.get(
            url,
            headers=self._auth_headers(),
            params=params,
            timeout=self.timeout,
            stream=stream,
        )
        if r.status_code == 401 and self.refresh_token:
            self.refresh_access()
            r = self._session.get(
                url,
                headers=self._auth_headers(),
                params=params,
                timeout=self.timeout,
                stream=stream,
            )
        if r.status_code >= 400:
            raise VPClientError(f"GET {path} → {r.status_code} {r.text[:200]}")
        return r

    # ---- project browse -----------------------------------------------------

    def me(self) -> dict[str, Any]:
        return self._get("/api/auth/me/").json()

    def list_projects(self) -> list[dict[str, Any]]:
        data = self._get("/api/projects/").json()
        return data.get("results") if isinstance(data, dict) else data

    def get_project(self, project_id: str) -> dict[str, Any]:
        return self._get(f"/api/projects/{project_id}/").json()

    def list_resources(self, project_id: str) -> list[dict[str, Any]]:
        data = self._get(f"/api/projects/{project_id}/resources/").json()
        return data.get("results") if isinstance(data, dict) else data

    # ---- media download -----------------------------------------------------

    def download_resource(
        self,
        resource_id: str,
        dest: str | Path,
        *,
        chunk_size: int = 1 << 20,
        on_progress: "callable | None" = None,
    ) -> Path:
        """Stream a resource file to disk. Returns the final path."""
        out = Path(dest)
        out.parent.mkdir(parents=True, exist_ok=True)
        r = self._get(f"/api/resources/{resource_id}/download/", stream=True)
        total = int(r.headers.get("content-length") or 0)
        downloaded = 0
        with out.open("wb") as fh:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                fh.write(chunk)
                downloaded += len(chunk)
                if on_progress and total:
                    on_progress(downloaded / total)
        return out


# ---- ZIP import path --------------------------------------------------------


def iter_zip_manifest(zip_path: str | Path) -> Iterator[dict[str, Any]]:
    """Placeholder for the ZIP-import parser (wired in M1).

    video-planner3's `exports/` app produces a ZIP bundle containing:
      - project.json        top-level project metadata
      - resources/           media files referenced by resource UUIDs
      - fcpxml/timeline.xml  optional editorial cut
    M1 parses this into a stream of ``{kind, payload}`` events consumed by
    the same import pipeline used for live-API imports.
    """
    raise NotImplementedError("ZIP import parsing lands in M1")
