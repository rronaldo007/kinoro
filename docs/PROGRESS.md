# Kinoro progress log

A single source of truth for what's shipped in Kinoro and what's next.
`docs/ROADMAP.md` is the long-term milestone plan. `docs/ARCHITECTURE.md`
is the design. This file is the chronological record — what was built,
when, and what comes next.

Kinoro is a standalone desktop video editor (Electron + Vite/React +
Django sidecar + FFmpeg). It's also a first-class extension of Video
Planner: projects from VP can be handed off via `kinoro://` deep links
and imported into the local library.

---

## What's done

### M0 — Scaffold boots  ·  2026-04-14

Electron shell + Vite/React renderer + Django sidecar + framework-free
`engine/` copied from Vediteur. Status panel polls `/api/health/`,
reports platform + `ffmpeg` / `ffprobe` presence. electron-builder
configured for AppImage/deb/DMG/NSIS (M0 builds do **not** bundle Python
or ffmpeg — user-provided, per design).

Commit: `c2405af Initial Kinoro M0 scaffold`.

### M1 Slice B — VP live-API auth + handoff  ·  2026-04-14

- `kinoro://open?base_url=<vp>&project_id=<uuid>` deep-link contract
  (Electron `setAsDefaultProtocolClient` + preload bridge).
- `VPAccount` singleton + `VPClient` hitting VP's SimpleJWT endpoints
  (`login`, `refresh`, `me`, `projects`, `resources`, `vediteur/...`).
- `try_get_any_project(id)` — tries VP EditorProject first, falls back
  to regular Project. Handles both handoff sources transparently.
- React `LoginModal` + `HandoffPanel` replace the scaffold banner:
  show project name + resource count, handle 401 session-expired.
- Electron dev fixes: Vite on `:5174`, `--no-sandbox` on Linux, CORS
  allow-list, user-scoped `kinoro-dev.desktop` because Electron's
  Linux protocol registration is a no-op.

Commit: `kinoro M1 Slice B: kinoro:// handoff + Video Planner live-API auth`.

### M1 Slice A.1 — Local media pool  ·  2026-04-14

- `MediaAsset` model (uuid, name, source_path, kind, status, probe
  metadata, thumbnail_path).
- `POST /api/media/` accepts a local path → daemon-thread ingest runs
  `engine.ffmpeg.probe` + `extract_poster`, flips `status=ready`.
- `MediaPool` component: grid of cards with thumbnails / duration /
  kind, "Add media" file dialog via `window.kinoro.openFiles`, poll
  every 1s while any row is ingesting, delete-on-hover.

No proxy build yet — that lives in Audit Phase B (see below).

### M1 Slice B.2 — VP media import (both kinds)  ·  2026-04-14

- `importers.py` walks an EditorProject's `timeline_json.clips` for
  vediteur `MediaAsset` IDs, pulls each file via authenticated
  `VPClient.download_url`.
- For regular Projects: reads nested resources (`type="video"`/`"sound"`
  with http(s) URLs), downloads via bare `requests` for third-party CDNs.
- `POST /api/import/vp/projects/<id>/import/` kicks off the background
  thread. UI "Import media" button on the handoff panel.
- VP-side: new `"Kinoro"` button on the Project detail page header
  (`frontend/.../ProjectDetailPage.tsx`) using the same `buildKinoroUrl`
  helper as the Vediteur page.

Commits: kinoro changes above; VP-side
`vediteur/projects: add "Kinoro" button to project header` +
`resources: seed_video_resources management command`.

### Test data  ·  2026-04-14

- `seed_video_resources` management command — 9 video-URL `Resource`
  rows across test users using Google's `commondatastorage` public
  `.mp4` sample bucket. Runs from `scripts/start.sh` + `refresh.sh`.

### Audit + Phase A remediation  ·  2026-04-15

A full re-read of the repo (three parallel Explore audits) surfaced
~5 critical, ~8 high, ~10 medium, and ~5 low issues. See plan file at
`~/.claude/plans/delegated-dreaming-sphinx.md` for the full findings
list.

Phase A landed five critical fixes:

| Fix | Files |
|---|---|
| Import dedupe via new `vp_asset_id` column | `apps/media/models.py`, migration 0002 |
| `VPImportJob` fully wired (status transitions + progress + error_message) | `apps/import_vp/importers.py`, `views.py`, `serializers.py`, `urls.py` |
| Frontend polls `GET /api/import/vp/jobs/<id>/` every 1 s; live progress bar + error surface | `ui/src/features/import-vp/HandoffPanel.tsx`, `ui/src/api/importVp.ts` |
| Vite 5174 port-wait in `start.sh` / `refresh.sh` — no more blank Electron windows on port collision | `video-planner3/scripts/{start,refresh}.sh` |
| Canonical SQLite path `~/.config/kinoro-app/data` — repo-local fallback trap removed | `server/config/settings.py` |
| `vite-env.d.ts` added — `tsc --noEmit` now exits 0 | `ui/src/vite-env.d.ts` |

### Phase B6 — ZIP import  ·  2026-04-15

`iter_zip_manifest(zip_path)` in `apps/import_vp/services.py` now
parses the canonical VP export layout (`project.json` at the root +
`resources/<uuid>.<ext>` media files) into `{kind, payload}` events.
`importers.start_zip_import(zip_path)` feeds those events into the
same downstream pipeline the live-API import uses — copies each
resource into `$KINORO_DATA_DIR/vp-imports/`, creates a `MediaAsset`,
kicks off `ingest_async` — all behind a `VPImportJob(source="zip")`
row with live status + progress. Dedupe works the same way (by
`vp_asset_id`) so re-importing the same ZIP doesn't duplicate.

`POST /api/import/vp/zip/` accepts a `multipart/form-data` upload
(field name `file`), stages it under `$KINORO_DATA_DIR/vp-zip-imports/`,
kicks off the background thread, returns the job row for polling.

Tests: 12 new in `apps/import_vp/tests/test_zip_import.py` — unit
coverage of the manifest parser (happy path, missing manifest, corrupt
zip, invalid JSON, missing media entries, in-memory round-trip) plus
integration against the `tiny_video` fixture (end-to-end import, twice-
import dedupe, per-resource failure isolation, missing-manifest job
failure). Full sidecar suite now 80 passing.

### Phase C — Docs pass  ·  2026-04-15

- `app/package.json`: `start` no longer passes `--no-sandbox` (production
  default); `start:dev` is the Linux-dev variant that does. VP's
  `scripts/start.sh` + `scripts/refresh.sh` updated to invoke
  `npm run start:dev`.
- `docs/ROADMAP.md`: cross-platform claim rewritten — Linux-only dev
  today, macOS + Windows deferred to M8. Matches reality + CLAUDE.md's
  invariants section.
- `docs/OPERATIONS.md` (new): runbook covering the two-stack topology,
  canonical paths rooted at `~/.config/kinoro-app/data/`, the
  `--no-sandbox` split rationale, known issues (SUID sandbox, Vite
  strictPort 5174, CDN seeds retired), pkill patterns for clean
  shutdown, pytest recipe.
- `CLAUDE.md`: OPERATIONS.md linked in the docs list.
- `README.md`: bootstrap instructions call out `npm run start:dev`.

---

## Current state, in one glance

- **Works today on Linux dev**: `./scripts/start.sh` brings up VP
  (docker) + Kinoro (Vite 5174 + Electron + Django sidecar).
  `kinoro://` deep links from VP's `/vediteur` and `/projects/<id>/`
  pages open Kinoro, pull the project, fetch its media on a tracked
  background job with live progress.
- **Not tested on macOS/Windows**. ROADMAP claims "cross-platform from
  M0"; reality is Linux-first. To be corrected in Phase C2.
- **Packaged releases exist but are non-functional** (bundle doesn't
  include Python or ffmpeg — that's M8). `npm run dist:*` produces
  AppImage / deb / DMG / NSIS but they require host Python 3.11+ and
  ffmpeg on PATH.

---

## What's next

Ordered by dependency, not urgency. Everything here is tracked in the
plan file or ROADMAP.

### Phase B — M1 completeness (remaining)

| # | Item | Scope |
|---|---|---|
| B1 | `MediaAsset.proxy_path` + `proxy_status` fields | model + migration |
| B2 | Call `engine.ffmpeg.build_proxy` after poster in `_do_ingest`; write 720p H.264 + AAC MP4 to `$KINORO_DATA_DIR/proxies/<id>.mp4` | `apps/media/services.py` |
| B3 | Register `MediaAsset` in Django admin with failed-ingest filter | `apps/media/admin.py` |
| B4 | `LOGGING` dict in settings — console (INFO) + `$KINORO_DATA_DIR/kinoro.log` (DEBUG) | `config/settings.py` |
| B5 | Drop the `type` / `kind` fallback in the importer; canonicalize on VP's `type` field | `apps/import_vp/importers.py` |
| B6 | ~~ZIP import path~~ — done 2026-04-15 |

After Phase B, M1 per `ROADMAP.md` is actually shipped (not just
claimed).

### Phase C — Architectural hygiene (remaining)

| # | Item |
|---|---|
| C1 | ~~`--no-sandbox` split~~ — done 2026-04-15 |
| C2 | ~~ROADMAP cross-platform rewrite~~ — done 2026-04-15 |
| C3 | Add a section to `ARCHITECTURE.md` describing the handoff + import design that matches reality (two sources, two kinds, one job pipeline) |
| C4 | ~~`docs/OPERATIONS.md`~~ — done 2026-04-15 |
| C5 | Note in `docs/VIDEO_PLANNER_INTEGRATION.md` that seed data imports from MDN / w3schools / samplelib (was Google CDN) |

### Phase D — Tests (from zero to a thin safety net)

| # | Item |
|---|---|
| D1 | `server/pytest.ini` + `conftest.py`, first passing run |
| D2 | Unit tests for pure functions: `_collect_asset_ids`, `_video_resources_with_url`, `_classify` |
| D3 | Integration: boot sidecar, hit `/api/health/`, create a `MediaAsset` for a tiny test clip, assert probe/thumbnail populate |
| D4 | Mock `VPClient` → run `_run_import` happy path, assert job transitions |

### M2 — Multi-track timeline + undo/redo  (~9 days)

From `ROADMAP.md:54–63`:

- `Project` model (name, fps, `timeline_json` per `PROJECT_FORMAT.md`),
  autosave debounced 700 ms.
- `ui/src/stores/timelineStore.ts` — tracks, clips, selection,
  playhead, `pxPerSec`.
- Command-pattern undo/redo with Immer (linear history, max 100).
- Timeline UI: ruler + V1/V2/A1/A2 + drag-to-add + trim handles + split
  (S) + ripple delete + magnetic snap (N).
- Shortcuts: Space, J/K/L, ⌘Z/⌘Y, S, Delete, +/−.

This is also the right slice to land the **editor shell** UI (top tabs,
left media pool, centre viewer, right inspector, bottom timeline) the
user previously queued. Shell becomes functional as M2 progresses.

### M3 — Viewer + playback  (~4 days)

`<video>` bound to the proxy of the clip under the playhead; swap `src`
on boundary crossing; transport Space/J/K/L; preroll for dissolves.
Verify: Space plays the whole sequence at correct in/out points.

### M4 — Text, transitions, speed  (~6 days)

Text clips (content, font, x/y/size, color). Fade + dissolve on clip
boundaries. Per-clip speed via FFmpeg `setpts` + `atempo`. Inspector
form controls bound to selected clip.

### M5 — Export + presets + FCPXML  (~5 days)

Port `engine/deliver/timeline_render.py` to full multi-track. Presets
(YouTube 1080p, TikTok vertical, custom). Progress via Channels
WebSocket. Electron `dialog:saveAs`. FCPXML 1.10 export ported from
`video-planner3/backend/apps/exports/` for Resolve round-trip.

### M6 — Audio mixer + LUFS  (~6 days)

Per-track volume + mute/solo + fades. Crossfade between adjacent clips.
LUFS normalize via FFmpeg `loudnorm`. VU meters in the renderer via
Web Audio.

### M7 — Color: LUTs, curves, scopes  (~12 days)

`.cube` via FFmpeg `lut3d`. RGB + luma curves (4 control points).
Primary wheels (lift/gamma/gain). Waveform + vectorscope sampled every
N frames. Ship ACES Studio Config 1.0.3 by default.

### M8 — Cross-platform packaging  (~8 days)

Bundle Python 3.11 via PyInstaller (one-dir) into `resources/python/`.
Static FFmpeg per platform (BtbN builds / jellyfin-ffmpeg). Icons +
`.desktop` (Linux) + `Info.plist` (macOS). Smoke test on clean Ubuntu
24.04, macOS 14, Windows 11 VMs. This is when the "cross-platform from
M0" claim actually becomes true.

### Post-MVP

- Olive-style typed-port node graph (`engine/graph/`).
- Optical flow speed ramping (OpenCV + `minterpolate`).
- Multi-cam editing, nested timelines.
- CLAP / LV2 plugin hosting.
- HDR pipeline, ProRes / DNxHR export codecs.
- Live OAuth against VP SaaS (browse + pick remote projects without a
  pre-existing handoff).
- Code signing + notarization (Apple Developer + Authenticode).

---

## How to work on Kinoro

- **Start dev**: `./video-planner3/scripts/start.sh`. Brings up VP
  docker stack, migrates the Kinoro sidecar's SQLite, installs the
  `kinoro://` dev handler, waits for Vite on 5174, launches Electron.
- **Refresh** (pick up new code): `./scripts/refresh.sh`. Same as
  start but skips docker rebuild. Kills stale Kinoro processes first.
- **Stop everything**: `./scripts/stop.sh`.
- **Logs**: `.cache/kinoro-{ui,app}.log` under video-planner3.
- **Sidecar DB**: `~/.config/kinoro-app/data/kinoro.sqlite3`. One
  canonical path — do not create another.
- **Sidecar logs** (Phase B4): will land at
  `~/.config/kinoro-app/data/kinoro.log`.
- **Verify TS**: `cd kinoro/ui && npx tsc --noEmit` must exit 0.
- **Verify Django**: `cd kinoro/server && KINORO_DATA_DIR=... .venv/bin/python manage.py check`.

Open questions from the audit plan remain unanswered:

1. Do doc corrections (Phase C2–C5) fold into each phase as it lands,
   or get saved for a single docs pass after Phase B?
2. Is the "no Windows/macOS testing until M8" stance acceptable,
   captured via the ROADMAP rewrite in C2?

See `~/.claude/plans/delegated-dreaming-sphinx.md` for the full plan,
findings, and verification recipes.
