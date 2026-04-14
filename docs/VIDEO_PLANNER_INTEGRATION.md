# Video Planner integration

Kinoro is a **first-class extension of Video Planner**. Users should be able
to bring their Video Planner projects across with zero friction. Two paths,
both supported from M1:

## Path A — Live API (recommended)

User logs into their Video Planner account from inside Kinoro, browses their
project list, and pulls a project directly into the local Kinoro database.
Media is streamed over HTTPS from Video Planner's resource endpoints.

```
[Kinoro UI] ──login form── POST /api/import/vp/login/
[Kinoro Django] ──login── POST  <vp>/api/auth/login/    { email, password }
                                ← { access, refresh, user }
      │
      ├── VPAccount row stored (access_token, refresh_token, expires_at)
      │
[Kinoro UI] ──browse── GET  /api/import/vp/projects/
[Kinoro Django] ──list── GET <vp>/api/projects/
                              ← [ { id, title, … }, … ]
      │
[Kinoro UI] ──click project── POST /api/import/vp/projects/<id>/
[Kinoro Django]  creates VPImportJob, kicks off background thread:
      │   1. GET <vp>/api/projects/<id>/            (metadata)
      │   2. GET <vp>/api/projects/<id>/resources/  (media list)
      │   3. for each resource:
      │         GET <vp>/api/resources/<rid>/download/   → stream to local media/
      │         engine.ffmpeg.probe(...)
      │         engine.ffmpeg.build_proxy(...)
      │   4. Create Kinoro Project + MediaAssets
      │   5. status=done, kinoro_project_id populated
      │
[Kinoro UI] polls GET /api/import/vp/jobs/<job_id>/   for progress
           navigates to /project/<kinoro_project_id>
```

Auth uses **SimpleJWT** (matches video-planner3's web frontend). Tokens expire
after ~1 hour; the VPClient auto-refreshes on 401 via the stored refresh token.

## Path B — ZIP offline import

User exports a project from Video Planner's UI → downloads a `.zip` → opens
Kinoro → File → Import from Video Planner → selects ZIP file. Useful when
Video Planner is down, when the user has changed accounts, or when working
offline.

```
[User]  Video Planner → Projects → Export → my-project.zip
[Kinoro UI] File → Import from Video Planner → pick ZIP
[Kinoro Django]  POST /api/import/vp/zip/   (multipart)
                 creates VPImportJob(source="zip"), kicks off thread:
      │   1. Unzip to temp dir
      │   2. Parse project.json + resources manifest
      │   3. Copy media files into local media/
      │   4. engine.ffmpeg.probe + build_proxy for each
      │   5. Create Kinoro Project + MediaAssets
      │   6. (optional) import FCPXML timeline if present
```

## Why both

- **API** is the low-friction default — no file juggling, always current.
- **ZIP** is the resilience path — works offline, works across accounts,
  and is a natural fit for users who already export for external editors.
- The two paths share everything downstream of the "create Project +
  MediaAssets" step, so UI/timeline code never branches on origin.

## Credential storage

`VPAccount` rows live in Kinoro's local SQLite. The access and refresh tokens
are stored as TEXT columns. That's equivalent to what a browser does with
localStorage — acceptable for a single-user desktop app.

**Future hardening (post-MVP):** encrypt tokens at rest via Electron's
`safeStorage` (OS keychain on macOS/Windows, libsecret on Linux). The tokens
would be encrypted in the Electron main process and passed to the sidecar via
an env var on startup.

## Contract Kinoro depends on (from video-planner3)

| Kinoro calls | video-planner3 endpoint | Response shape |
|---|---|---|
| Auth | `POST /api/auth/login/` | `{ access, refresh, user }` (SimpleJWT) |
| Refresh | `POST /api/auth/refresh/` | `{ access }` |
| Me | `GET /api/auth/me/` | user dict |
| Projects | `GET /api/projects/` | list or `{ results: [] }` |
| Project | `GET /api/projects/<id>/` | project dict |
| Resources | `GET /api/projects/<id>/resources/` | nested list |
| Download | `GET /api/resources/<id>/download/` | binary stream |
| Proxy | `GET /api/resources/<id>/proxy/` | binary stream (optional fast path) |

If any of these shapes change on the Video Planner side, `VPClient` in
`server/apps/import_vp/services.py` is the single point of adaptation.

## Code pointers

- Client: `server/apps/import_vp/services.py` → `VPClient`
- Models: `server/apps/import_vp/models.py` → `VPAccount`, `VPImportJob`
- Endpoints (M1): `server/apps/import_vp/views.py`
- UI (M1): `ui/src/features/import-vp/` (login modal + project list)

## Related docs

- `docs/ARCHITECTURE.md` — layered design
- `docs/ROADMAP.md` M1 — import pipeline milestone
- `docs/PROJECT_FORMAT.md` — target `.kinoro` timeline schema
