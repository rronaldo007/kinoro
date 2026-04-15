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

import json
import logging
import zipfile
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
        # VP's LoginSerializer accepts `login` (email or username).
        r = self._session.post(
            f"{self.base_url}/api/auth/login/",
            json={"login": email, "password": password},
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

    # ---- vediteur (Pro Editor) projects -------------------------------------
    # The "Ouvrir dans l'éditeur" button on VP's /vediteur page hands off
    # EditorProject UUIDs, which live at a different endpoint.

    def get_vediteur_project(self, project_id: str) -> dict[str, Any]:
        return self._get(f"/api/vediteur/projects/{project_id}/").json()

    def try_get_any_project(self, project_id: str) -> tuple[str, dict[str, Any]]:
        """Fetch by ID from either Project or EditorProject. Returns (kind, data)."""
        try:
            return "editor", self.get_vediteur_project(project_id)
        except VPClientError:
            return "project", self.get_project(project_id)

    def get_vediteur_media(self, asset_id: str) -> dict[str, Any]:
        return self._get(f"/api/vediteur/media/{asset_id}/").json()

    def download_url(
        self,
        url: str,
        dest: str | Path,
        *,
        chunk_size: int = 1 << 20,
        on_progress: "callable | None" = None,
    ) -> Path:
        """Stream an absolute URL (e.g. an asset's file_url) to disk with auth."""
        out = Path(dest)
        out.parent.mkdir(parents=True, exist_ok=True)
        r = self._session.get(
            url,
            headers=self._auth_headers(),
            timeout=self.timeout,
            stream=True,
        )
        if r.status_code >= 400:
            raise VPClientError(f"GET {url} → {r.status_code} {r.text[:200]}")
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


class ZipImportError(RuntimeError):
    """Raised when the ZIP file is missing, corrupt, or lacks a manifest."""


_MEDIA_SUFFIXES = {
    ".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi",  # video
    ".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg", ".opus",  # audio
    ".png", ".jpg", ".jpeg", ".webp", ".gif",  # images
}


def _extract_zip_to(zip_path: Path, extract_root: Path) -> Path:
    """Unzip ``zip_path`` under ``extract_root``. Returns the extract dir.

    The extract dir is a sibling of the zip, stable per zip hash, so
    re-running on the same ZIP reuses the extracted tree. Path-traversal
    entries ("..", absolute paths) are rejected — zipfile.extractall
    already does this in 3.11+ but we belt-and-braces.
    """
    if not zip_path.exists():
        raise ZipImportError(f"ZIP not found: {zip_path}")
    extract_root.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                name = info.filename
                if name.startswith("/") or ".." in Path(name).parts:
                    raise ZipImportError(f"Unsafe entry in ZIP: {name!r}")
            zf.extractall(extract_root)
    except zipfile.BadZipFile as e:
        raise ZipImportError(f"Corrupt ZIP: {e}") from e
    return extract_root


def iter_zip_manifest(zip_path: str | Path) -> Iterator[dict[str, Any]]:
    """Parse a Video Planner export ZIP into manifest events.

    Canonical format (the contract Kinoro consumes):
        project.json                   top-level project metadata
        resources/<uuid>.<ext>         media files keyed by resource UUID
        fcpxml/timeline.xml            optional editorial cut

    ``project.json`` shape::

        {
          "id": "<project uuid>",
          "name": "My film",
          "resources": [
            {"id": "<uuid>", "name": "clip.mp4", "type": "video", "file": "resources/<uuid>.mp4"},
            ...
          ]
        }

    Yields, in order:
      - ``{"kind": "project", "payload": <project.json>}`` — exactly once.
      - ``{"kind": "resource", "payload": {id, name, type, path}}`` — once
        per resource whose media file exists on disk inside the extracted
        tree. ``path`` is an absolute ``pathlib.Path`` to the extracted
        file.

    Resources that are listed but whose file is missing from the archive
    are skipped with a warning; the caller gets only events for files it
    can actually ingest.

    Extracts to a sibling temp directory so `start_zip_import` can ingest
    the files by local path. Callers are responsible for cleanup.
    """
    zip_path = Path(zip_path).resolve()
    extract_root = zip_path.parent / f".{zip_path.stem}.extracted"
    _extract_zip_to(zip_path, extract_root)

    manifest_path = extract_root / "project.json"
    if not manifest_path.exists():
        raise ZipImportError(
            f"ZIP missing project.json (looked in {extract_root})"
        )
    try:
        project = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ZipImportError(f"project.json is not valid JSON: {e}") from e
    if not isinstance(project, dict):
        raise ZipImportError("project.json must be a JSON object")

    yield {"kind": "project", "payload": project}

    resources = project.get("resources")
    if not isinstance(resources, list):
        return

    for res in resources:
        if not isinstance(res, dict):
            logger.warning("zip import: skipping non-dict resource entry")
            continue
        rid = res.get("id")
        if not isinstance(rid, str) or not rid:
            logger.warning("zip import: resource entry missing id; skipping")
            continue

        rel = res.get("file")
        candidates: list[Path] = []
        if isinstance(rel, str) and rel:
            candidates.append(extract_root / rel)
        # Fallback: match by UUID prefix in the resources/ dir. Lets a
        # slightly-broken manifest still import if the media file is present.
        res_dir = extract_root / "resources"
        if res_dir.is_dir():
            for p in res_dir.iterdir():
                if p.is_file() and p.stem == rid and p.suffix.lower() in _MEDIA_SUFFIXES:
                    candidates.append(p)

        found: Path | None = next(
            (c for c in candidates if c.is_file()), None
        )
        if found is None:
            logger.warning(
                "zip import: resource %s has no matching media file in archive",
                rid,
            )
            continue

        yield {
            "kind": "resource",
            "payload": {
                "id": rid,
                "name": res.get("name") or res.get("title") or f"resource-{rid}",
                "type": res.get("type") or "video",
                "path": found.resolve(),
                "raw": res,
            },
        }
