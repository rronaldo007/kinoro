# Kinoro

A standalone desktop video editor — Electron + React + Django sidecar + FFmpeg.

Kinoro is also an **extension of [Video Planner](https://github.com/ronaldo/video-planner3)** — import
your Video Planner projects directly without leaving the app (File → Import
from Video Planner).

- **Target**: semi-pro editors who want a lightweight Resolve alternative
  (Kdenlive/Shotcut-class tool).
- **Platforms**: Linux, macOS, Windows.
- **License**: GPL-3.0.

## Status

**Milestone 0 — scaffold boots.** Electron shell, Django sidecar, health-check
page. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the full M0 → M8 plan.

## Requirements

- Node 20+
- Python 3.11+
- `ffmpeg` and `ffprobe` on `PATH` (bundled in M8 releases; required locally for dev)

## Quick start (dev)

```bash
# 1. Sidecar deps
cd server
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate

# 2. Renderer deps
cd ../ui
npm install

# 3. Electron deps
cd ../app
npm install

# 4. Run (two terminals)
#   Terminal A — Vite dev server:
cd ui && npm run dev

#   Terminal B — Electron (spawns Django sidecar on a free port):
#   Use start:dev on Linux — it passes --no-sandbox, which Electron needs
#   when run from some Linux dev setups. `npm start` is the production
#   default and intentionally does NOT pass it.
cd app && npm run start:dev
```

The Electron window should open showing "Kinoro · M0" + a Sidecar panel
reporting status, port, and whether `ffmpeg`/`ffprobe` are on PATH.

## Packaging

```bash
cd app
npm run dist:linux    # → release/Kinoro-0.0.1-x86_64.AppImage + .deb
npm run dist:mac      # → release/Kinoro-0.0.1-arm64.dmg
npm run dist:win      # → release/Kinoro-0.0.1-x64.exe (NSIS)
```

M0 packaging does **not** bundle Python or ffmpeg — the user must have them
installed. Bundling via PyInstaller + static ffmpeg binaries is M8.

## Layout

```
kinoro/
├── app/          Electron shell (TypeScript)
├── ui/           React renderer (Vite + Tailwind)
├── server/       Django sidecar (Python 3.11+)
│   └── engine/   Framework-free render engine (FFmpeg wrappers)
├── docs/         ARCHITECTURE, ROADMAP, REFERENCES, PROJECT_FORMAT
└── research/     Reference clones of 6 FOSS editors (git-ignored)
```

## Relationship to Video Planner

Kinoro lives in a separate repo from `video-planner3` so it can evolve without
SaaS constraints, but is designed to be a **first-class extension**:

- The `server/engine/` render library is kept byte-identical with
  `video-planner3/backend/vediteur_engine/` where possible — bug fixes port
  both ways.
- `apps/import_vp/` imports Video Planner projects via **two paths** (both M1):
  - **Live API** (primary) — JWT login → browse remote projects → pull project + resources directly over HTTPS.
  - **ZIP offline** — open a `.zip` exported from Video Planner's UI; works offline.
- See [`docs/VIDEO_PLANNER_INTEGRATION.md`](docs/VIDEO_PLANNER_INTEGRATION.md) for the full spec.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — layered design, data flow
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — M0 through M8 milestones
- [`docs/REFERENCES.md`](docs/REFERENCES.md) — patterns extracted from Kdenlive, Shotcut, OpenShot, Olive, Flowblade, LosslessCut, DaVinci Resolve SDK, OCIO
- [`docs/PROJECT_FORMAT.md`](docs/PROJECT_FORMAT.md) — `.kinoro` timeline schema
