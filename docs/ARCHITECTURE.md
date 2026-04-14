# Kinoro architecture

## Layered design

```
┌───────────────────────────────────────────────────────────┐
│  Electron main (Node, TypeScript)                         │
│  ├─ app/src/main.ts      app lifecycle, BrowserWindow    │
│  ├─ app/src/sidecar.ts   spawn Django, wait for health   │
│  ├─ app/src/menu.ts      native menus (File/Edit/View…)  │
│  └─ app/src/preload.ts   contextBridge → window.kinoro   │
└───────────────────────────────────────────────────────────┘
                    │ loads (dev: localhost:5173
                    ▼        prod: file://resources/ui/)
┌───────────────────────────────────────────────────────────┐
│  React renderer (Vite + Tailwind)                         │
│  ├─ api/client.ts        axios → 127.0.0.1:<sidecar-port>│
│  ├─ stores/              Zustand + Immer (timeline, etc.)│
│  ├─ hooks/               React Query wrappers            │
│  └─ features/            media-pool, timeline, viewer,    │
│                          inspector, audio, color, deliver│
└───────────────────────────────────────────────────────────┘
                    │ HTTP (JSON + multipart)
                    ▼ 127.0.0.1:<dynamic port>
┌───────────────────────────────────────────────────────────┐
│  Django 5 + DRF sidecar (local-only)                      │
│  ├─ apps/health      /api/health/                        │
│  ├─ apps/projects    /api/projects/  (M2)                │
│  ├─ apps/media       /api/media/     (M1)                │
│  ├─ apps/render      /api/render/    (M5)                │
│  └─ apps/import_vp   /api/import/    (M1)                │
│  SQLite at <userData>/data/kinoro.sqlite3                 │
└───────────────────────────────────────────────────────────┘
                    │ imports (no Django back-imports)
                    ▼
┌───────────────────────────────────────────────────────────┐
│  engine/ — framework-free                                 │
│  ├─ ffmpeg/    probe · transcode · thumbnails            │
│  ├─ deliver/   timeline_render (filter_complex assembly) │
│  ├─ color/     LUT / curves / scopes        (M7)         │
│  ├─ audio/     mixer / LUFS normalize       (M6)         │
│  └─ graph/     typed-port node eval      (post-MVP)      │
└───────────────────────────────────────────────────────────┘
```

## Key design patterns (in use)

| Pattern | Where | Why |
|---|---|---|
| **Sidecar process** | `app/src/sidecar.ts` | Reuse Django skill, keep UI snappy, same shape as Vediteur |
| **contextBridge IPC** | `app/src/preload.ts` | Safe renderer ↔ main communication; no nodeIntegration |
| **Command pattern (undo/redo)** | M2 — `ui/src/stores/timelineStore.ts` | NLE convention (Kdenlive/Shotcut/Olive) |
| **Immer structural sharing** | M2 — timeline history | Flowblade-style cheap undo |
| **Typed-port node graph** | post-MVP — `engine/graph/` | Olive pattern for color/VFX pipeline |
| **Proxy media** | M1 — `engine/ffmpeg/transcode.py` | Kdenlive pattern — 720p H.264 for browser scrub |
| **Pull-based render** | M5 — `engine/deliver/timeline_render.py` | filter_complex assembly, progress streamed |

## Data flow — media ingest (M1)

```
User drops file in MediaPool
  → ui/features/media-pool/       onDrop
  → ui/api/client.ts               POST /api/media/  { source_path }
  → server/apps/media/views.py     MediaAsset created, status=ingesting
  → background thread              engine.ffmpeg.probe(...) → metadata
                                   engine.ffmpeg.extract_poster(...) → thumb
                                   engine.ffmpeg.build_proxy(...) → 720p MP4
  → MediaAsset.status=ready
  → ui polls GET /api/media/       React Query cache updates
  → clip renders with thumb + becomes drag-source
```

## Data flow — Video Planner import (M1)

Two paths, same downstream pipeline. See `VIDEO_PLANNER_INTEGRATION.md` for the full spec.

### Path A — live API (primary)

```
UI login form → POST /api/import/vp/login/ { base_url, email, password }
server/apps/import_vp/services.py:VPClient
  → POST <vp>/api/auth/login/   → { access, refresh, user }
  → VPAccount stored

UI browse → GET /api/import/vp/projects/
  → VPClient.list_projects → GET <vp>/api/projects/

UI "Import" → POST /api/import/vp/projects/<id>/
  → create VPImportJob, spawn background thread:
     · VPClient.get_project(<id>)
     · VPClient.list_resources(<id>)
     · for each resource: VPClient.download_resource(rid, local_path)
     · engine.ffmpeg.probe + extract_poster + build_proxy
     · create Kinoro Project + MediaAssets
  → UI polls GET /api/import/vp/jobs/<job_id>/ for progress
  → navigate to /project/<kinoro_project_id>
```

### Path B — ZIP offline

```
UI → File → Import from Video Planner → native file dialog → ZIP path
  → POST /api/import/vp/zip/   (multipart)
  → VPImportJob(source="zip"), background thread:
     · unzip to tmp dir
     · parse project.json + resources manifest + optional FCPXML
     · copy media files into local media/
     · engine.ffmpeg.probe + build_proxy per resource
     · create Kinoro Project + MediaAssets
```

## Cross-platform notes

- **Python**: `python3` on Linux/macOS, `python` on Windows. Overridable via `KINORO_PYTHON`.
- **Paths**: `pathlib.Path` (Python) + `path.join` (Node) everywhere.
- **FFmpeg**: must be on `PATH`. Bundling per-platform static builds is M8.
- **Packaging**: electron-builder targets AppImage/deb (Linux), DMG/zip (macOS), NSIS/portable (Windows).
- **Code signing**: deferred — Apple notarization and Windows Authenticode require paid certs.

## Why not alternative stacks

See `REFERENCES.md` for the full comparison; summary:

- **Qt/PySide** — best native feel but requires abandoning the web UI skill.
- **Tauri** — 10× smaller binary but adds Rust learning curve.
- **MLT** — used by Kdenlive/Shotcut but introduces a C++ dep we don't want.
- **libopenshot** — couples us to a specific C++ lib (OpenShot's approach).
- **Pure FFmpeg subprocess** ✅ — chosen. Matches Vediteur, LosslessCut, Flowblade.
