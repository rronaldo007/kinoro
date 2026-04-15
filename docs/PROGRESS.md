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

### Phase B1–B5 — M1 completeness  ·  2026-04-15

Proxy pipeline + admin + logging + type canonicalization landed
alongside the editor-shell work.

- `MediaAsset.proxy_path` + `proxy_status` (pending/building/ready/
  failed/skipped) with migration.
- `apps/media/services.py` calls `engine.ffmpeg.build_proxy` after
  poster extraction, writes `$KINORO_DATA_DIR/proxies/<id>.mp4`
  (720p H.264 + AAC). Poster seek fixed to min(1.0, duration*0.5)
  for sub-2s clips that previously crashed with empty output.
- `MediaAsset` registered in admin with failed-ingest filter.
- `LOGGING` dict added — console INFO + `$KINORO_DATA_DIR/kinoro.log`
  DEBUG with rotation.
- Importer dropped the legacy `kind` fallback; canonicalized on VP's
  `type` field.
- `/proxies/` route served by Django's `static()` for proxy playback.

### M2 — Editor shell + multi-track timeline  ·  2026-04-15

Full editor surface lands. App.tsx reduced to a thin wrapper; the
5-region shell (TopBar / MediaPool / Viewer / Inspector / Timeline /
DevDrawer) under `ui/src/features/editor-shell/` owns the UX.

- `Project` model (name, fps, width, height, `timeline_json`,
  `render_settings`) + DRF viewset + first migration.
- `ui/src/stores/timelineStore.ts` — zustand + immer. Tracks V1/V2/
  A1/A2 by default. `Clip` discriminated on `type: "media" | "text"`,
  per-clip `speed`, optional `transition_in/out`. Snapshot-based
  linear undo/redo, capped at 100 steps. Live-gesture pattern:
  `beginHistoryStep()` at mousedown + `*Live` non-snapshotting
  setters during drag.
- `Timeline.tsx` — multi-track pane, drag-to-move/trim, `Ctrl+wheel`
  zoom, "Add text" button, gradient wedges for transitions.
- Drag-from-pool to timeline; pool items carry the asset UUID.
- `useProjectLoader.ts` / `useAutosave.ts` — open-or-create match
  by handoff title, 700 ms debounced PUT on tracks/clips diff.
  TopBar shows Saving… / Saved / Unsaved.
- `useTimelineShortcuts.ts` — Space / ←→ / Home / End / S / Delete /
  ⌘Z / ⌘Y / + / −, gated on non-editable focus.

### M3 — Viewer + playback  ·  2026-04-15

- `Viewer.tsx` — `<video>` bound to the active clip's proxy. Two-way
  playhead sync; suppress-timeupdate ref breaks the feedback loop on
  external seeks.
- Active-clip selection prefers topmost video track.
- Transport bar: `[⏮ Start] [⟨ −1f] [▶/⏸] [⟩ +1f] [⏭ End]`,
  timecode, fps badge, mute toggle. Play-when-off-clip snaps to the
  first clip so the button never looks broken.
- `AudioLayer` — hidden `<audio>` per active A1/A2 clip, synced to
  playhead + `playbackRate`. Additive on top of the `<video>`'s V1
  audio (matches engine `amix` behaviour).

### M4 — Text, transitions, speed  ·  2026-04-15

- Per-clip `speed` via engine `setpts=(PTS-STARTPTS)/S` + chained
  `atempo` (pitch-preserved, clamped 0.1×–10×).
- `type="text"` clips composited via `drawtext` with
  `enable='between(t,s,e)'`; Inspector TextControls (content, colour,
  size, x/y position sliders).
- Fade + dissolve transitions. Fade = boundary `fade=t=in/out` +
  `afade`. Dissolve = `xfade=transition=fade` + `acrossfade` when
  both sides ask AND the clips are flush; degrades to fade otherwise.
  Frames clamped [1, 120] and to half-clip-duration so 3 s clips
  with 2 s fades don't blow up the math.
- Viewer text overlays use `containerType: "size"` + `cqh` so font
  sizes entered at 1080p render proportionally in the preview box.

### M5 — Export to MP4  ·  2026-04-15

- `RenderJob` model (queued/rendering/done/failed, progress,
  output_path). `start_render` spawns a daemon thread; progress
  parses `out_time_ms=` from `ffmpeg -progress pipe:1` throttled to
  every 0.5 s.
- `DeliverPanel.tsx` — swaps Viewer on the Deliver tab. Render
  button + job list with live polling + download link.
- **Multi-track render**: `timeline_render.py` generalized beyond
  V1. V2 clips composited via `overlay=enable='between(...)'` over
  V1 (gaps transparent so V1 shows through). A1/A2 mixed with V1
  audio via `amix=inputs=N:duration=longest`. Single-V1-clip path
  is byte-identical to the pre-multitrack filter_complex — existing
  tests stay green.

Engine test suite: 44 (speed 8 + text 10 + transitions 17 + multitrack
7 + existing render 2). Full sidecar suite: **80 passing**.

---

## Current state, in one glance

- **Works today on Linux dev**: `./scripts/start.sh` brings up VP
  (docker) + Kinoro (Vite 5174 + Electron + Django sidecar).
  `kinoro://` deep links from VP's `/vediteur` and `/projects/<id>/`
  pages open Kinoro, pull the project, fetch its media on a tracked
  background job with live progress.
- **Editor works end-to-end**: media pool → drag to timeline →
  trim/split/transitions/text/speed → scrub preview with proxy
  video + A1/A2 audio → render to MP4 via Deliver tab. Autosave
  every 700 ms, undo/redo 100 steps.
- **80 tests passing** under `cd server && KINORO_DATA_DIR=/tmp/x
  .venv/bin/python -m pytest -q` (~2 s).
- **Not tested on macOS/Windows** — Linux-first until M8, documented
  honestly in ROADMAP and CLAUDE.md.
- **Packaged releases exist but are non-functional** (bundle doesn't
  include Python or ffmpeg — that's M8). `npm run dist:*` produces
  AppImage / deb / DMG / NSIS but they require host Python 3.11+ and
  ffmpeg on PATH.

---

## What's next

Ordered by dependency, not urgency. Committed milestones live in
`ROADMAP.md`; loose editor-feature ideas (multi-select, J/K/L,
waveforms, presets, bins, etc.) live in
[`BACKLOG.md`](./BACKLOG.md) and can be picked off between milestones.

### Remaining polish + cleanup (small)

- **C3** — Handoff + import design section in `ARCHITECTURE.md`
  (two sources, two kinds, one job pipeline). Useful but not
  blocking.
- **C5** — Note seed swap (MDN / w3schools / samplelib replaced the
  retired Google CDN bucket) in `VIDEO_PLANNER_INTEGRATION.md`.
- **M4 / M5 polish**: preroll for dissolves in the preview (render
  already handles them), TikTok 9:16 + custom preset editor, FCPXML
  1.10 export port from VP's `apps/exports/`.

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
- **Verify tests**: `cd kinoro/server && KINORO_DATA_DIR=/tmp/kinoro-test
  .venv/bin/python -m pytest -q` — 80 passing in ~2 s.
- **Verify Django**: `cd kinoro/server && KINORO_DATA_DIR=... .venv/bin/python manage.py check`.
