# Kinoro roadmap — M0 through M8

Target: ~10–12 weeks part-time to MVP (M0 → M8). Each milestone produces a
runnable, useful-in-some-way Kinoro.

Cross-platform (Linux + macOS + Windows) is a requirement from M0. Code signing
and notarization are deferred (no paid certs yet).

---

## ✅ M0 — Scaffold boots

- Electron main + preload + sidecar spawner + health check
- Django sidecar with `/api/health/` reporting status, platform, ffmpeg/ffprobe availability
- Vite + React + Tailwind renderer with a splash page polling `/api/health/`
- `server/engine/ffmpeg/` + `server/engine/deliver/` copied byte-for-byte from Vediteur
- Cross-platform sidecar: `python3`/`python` auto-detect; `KINORO_PYTHON` override
- electron-builder configured for AppImage + deb + DMG + NSIS

**Verify**: `cd app && npm start` opens window showing green "Sidecar: ok" status on Linux, macOS, and Windows.

---

## M1 — Media pool + proxies + Video Planner import (API + ZIP)  (~8 days)

### Media pool
- `MediaAsset` model: source_path, probe metadata (JSON), proxy_path, thumbnail_path, kind, status
- Background thread worker (NOT Celery — single-user desktop): on create → probe → thumbnail → build_proxy (1280×720 H.264 + AAC)
- `POST /api/media/` accepts either a local path or an uploaded file
- React `MediaPool` feature: drag files in, thumbnail grid, ingesting → ready status dot

### Video Planner import — both paths live in M1

**Path A (live API)** — primary:
- `VPClient` (already scaffolded in `services.py`) exercised end-to-end
- `VPAccount` persisted across sessions; auto-refresh on 401
- React login modal → project list → pick project → background import job
- Endpoints: `/api/import/vp/login/`, `/projects/`, `/projects/<id>/`, `/jobs/<id>/`, `/logout/`

**Path B (ZIP offline)**:
- Parse `project.json` + `resources/` dir + optional `fcpxml/timeline.xml`
- File menu → "Import from Video Planner…" native file dialog
- Same downstream pipeline as API import (create Project + MediaAssets)

See `docs/VIDEO_PLANNER_INTEGRATION.md` for the full spec.

**Verify**:
- Drag 3 videos → ready in ≤ 30 s.
- Live-API import: log into a Video Planner test account, pick a project, all resources land locally with proxies built.
- ZIP import: pick a Video Planner export ZIP, same result, works offline.

---

## M2 — Multi-track timeline + undo/redo  (~9 days)

- `Project` model: name, fps, timeline_json (schema per `PROJECT_FORMAT.md`), debounced autosave every 700 ms
- `ui/src/stores/timelineStore.ts`: tracks[], clips[], selection, playhead, pxPerSec
- Command-pattern undo/redo with Immer (linear history, max 100 steps)
- Timeline UI: ruler, V1/V2/A1/A2 tracks, drag-to-add, trim handles, split (S), ripple delete, magnetic snap (N toggles)
- Shortcuts: Space play, J/K/L, ⌘Z/⌘Y, S split, Delete, +/− zoom
- Keyboard binding schema from LosslessCut (see `REFERENCES.md`)

**Verify**: build a 5-clip sequence across 2 tracks, close and reopen — exact timeline restored. Undo back to empty.

---

## M3 — Viewer + playback  (~4 days)

- `<video>` element bound to proxy of clip-under-playhead
- On playhead boundary crossing: swap `src` + seek to in-point
- Transport: play/pause, scrub, step ±1 frame
- Preroll logic for dissolves

**Verify**: Space plays the whole sequence at correct in/out points without gaps.

---

## M4 — Text overlays, transitions, speed  (~6 days)

- `TextClip` type: content, font, x/y/size, color, in/out
- Transitions on clip boundaries: fade, dissolve (duration in frames)
- Per-clip speed: FFmpeg `setpts` + `atempo` (pitch-preserved)
- Inspector panel with form controls bound to selected clip

**Verify**: title card + dissolve + 2× speed on one clip — preview approximates, export precisely.

---

## M5 — Export to MP4 + presets + FCPXML export  (~5 days)

- Port `engine/deliver/timeline_render.py` (already copied) to full multi-track
- Presets: YouTube 1080p (H.264 High CRF 18, AAC 192k), TikTok 1080×1920, Custom
- Progress via Django Channels WebSocket → Zustand
- Save-as via Electron IPC `dialog:saveAs`
- **FCPXML 1.10 export** — port from `video-planner3/backend/apps/exports/` for Resolve round-trip

**Verify**: export 10 s project → plays in VLC at expected codec/duration. Import the FCPXML into DaVinci Resolve free → timeline reconstructs.

---

## M6 — Audio mixer + LUFS  (~6 days)

- Per-track volume + mute/solo + fade in/out
- Crossfade between adjacent clips (same track)
- LUFS analyze + normalize via FFmpeg `loudnorm`
- VU meters using Web Audio API on the `<video>` element

**Verify**: two audio tracks at −6 dB vs −18 dB → audible difference. Normalize a too-loud clip to −14 LUFS.

---

## M7 — Color: LUTs, curves, scopes  (~12 days)

- `.cube` LUT loading via FFmpeg `lut3d` (OCIO `FileTransform` reserved for deeper grading)
- RGB + luma curves with 4 control points via FFmpeg `curves`
- Primary wheels: lift/gamma/gain via `colorchannelmixer` + curves combo
- Waveform + vectorscope: FFmpeg → PNG → `<canvas>` (sampled every N frames)
- Ship ACES Studio Config 1.0.3 by default (see `REFERENCES.md`)

**Verify**: apply sample `.cube` on Big Buck Bunny → visibly graded. Waveform shows expected luma distribution.

---

## M8 — Cross-platform packaging + AppImage / DMG / NSIS ship  (~8 days)

- electron-builder configurations for all three platforms (already scaffolded in M0)
- Bundle Python 3.11 via PyInstaller (one-dir) into `resources/python/`
- Bundle static FFmpeg binaries per platform (BtbN builds for Linux/Win, jellyfin-ffmpeg for macOS)
- Icons, `.desktop` entry (Linux), `Info.plist` (macOS)
- Installer smoke test on clean Ubuntu 24.04, macOS 14, Windows 11 VMs
- Release notes + keyboard-shortcut sheet

**Verify**:
- `Kinoro-0.0.1-x86_64.AppImage` runs on clean Ubuntu (no Python installed)
- `Kinoro-0.0.1-arm64.dmg` opens on macOS 14 without install
- `Kinoro-0.0.1-x64.exe` installs and runs on clean Windows 11

---

## Post-MVP (not scheduled)

- Olive-style typed-port node graph for effects/color
- Optical flow speed ramping (OpenCV via ffmpeg `minterpolate`)
- Multi-cam editing
- Nested timelines
- CLAP/LV2 plugin hosting
- HDR pipeline, ProRes/DNxHR export codecs
- Live OAuth login against Video Planner SaaS (browse/download projects without ZIP)
- Code signing + notarization (Apple Developer + Authenticode certs)
