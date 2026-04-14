# Kinoro — project rules for future Claude sessions

Kinoro is a **standalone desktop video editor** — Electron + React + Django
sidecar + FFmpeg. It is also an **extension of Video Planner** (the SaaS at
`/home/ronaldo/my-projects/video-planner3`) — Video Planner projects must be
trivially importable.

## What Kinoro is NOT

- Not a SaaS. No auth, no billing, no workspaces, no plan gates, no Stripe.
- Not MariaDB-backed. Uses a single local SQLite file in the OS user-data dir.
- Not a fork of Vediteur. Cleaner slate, freedom to diverge — but the render
  engine (`server/engine/`) is kept byte-identical with Vediteur so fixes port.

## Layout

```
app/      Electron main + preload + sidecar spawner (TypeScript)
ui/       Vite + React 18 + TypeScript + Tailwind renderer
server/   Django 5 + DRF sidecar (local-only, 127.0.0.1)
  apps/core       BaseModel (UUID pk + timestamps)
  apps/health     /api/health/  (sidecar readiness)
  apps/projects   Project + timeline JSON     (M2)
  apps/media      MediaAsset + proxy pipeline (M1)
  apps/render     RenderJob + export presets  (M5)
  apps/import_vp  Video Planner importer      (M1)
                   · services.VPClient  — live API client (SimpleJWT)
                   · models.VPAccount   — stored creds (token in SQLite)
                   · models.VPImportJob — job tracking (source=api|zip)
  engine/         Framework-free render lib
    ffmpeg/   probe, transcode, thumbnails
    deliver/  timeline_render (filter_complex)
    color/    LUT/curves/scopes (M7)
    audio/    mixer/LUFS (M6)
    graph/    typed-port nodes (post-MVP)
docs/     ARCHITECTURE, ROADMAP, REFERENCES, PROJECT_FORMAT
research/ 6 FOSS editor clones (git-ignored, reference-only, GPL)
```

## Conventions

### Backend
- All models extend `apps.core.models.BaseModel` (UUID pk, created_at, updated_at).
- No auth, no billing, no workspaces. DRF defaults are open.
- `server/engine/` is **framework-free** — no `from django` imports allowed.
- All ffmpeg/ffprobe subprocess calls go through `engine.ffmpeg.*`. Never
  shell out directly from views, tasks, or elsewhere.
- Paths — always `pathlib.Path`, never hardcoded separators (cross-platform).

### Frontend
- Server state: `@tanstack/react-query`
- Client state: `zustand` + `immer`
- Colors: CSS variables (`var(--color-accent)` etc.) — never hardcode hex
- Icons: `lucide-react` at size 14 or 16
- API: `ui/src/api/client.ts` axios instance (base URL resolves from
  `window.kinoro.apiPort` in Electron, env in browser dev)

### Electron
- Main process never imports the render engine — everything goes through
  HTTP to the sidecar
- Sidecar port is allocated at runtime via `net.createServer({ port: 0 })`
- Preload exposes a minimal `window.kinoro` API; no `nodeIntegration`
- Cross-platform: `python` on Windows, `python3` on Linux/macOS. Users can
  override via `KINORO_PYTHON`.

## Cross-platform invariants

- Linux, macOS, Windows — all three must work from MVP.
- `pathlib.Path` + `path.join` — never string concatenation with `/` or `\`.
- Menu roles (Cmd vs Ctrl) handled by Electron's `CmdOrCtrl` accelerator.
- Python binary name varies — see `app/src/sidecar.ts:defaultPython()`.

## What to reuse from Video Planner

When implementing a new feature, check if Vediteur already solved it:
- `/home/ronaldo/my-projects/video-planner3/backend/vediteur_engine/` —
  FFmpeg engine (copy verbatim when it makes sense; already done for M0)
- `/home/ronaldo/my-projects/video-planner3/backend/apps/exports/` —
  FCPXML 1.10 exporter (port in M5 for Resolve round-trip)
- `/home/ronaldo/my-projects/video-planner3/vediteur/electron/src/sidecar.ts` —
  pattern reference for sidecar lifecycle

## What NOT to do

- Don't add billing / workspace / multi-user code. Kinoro is single-user desktop.
- Don't bind the sidecar to anything other than 127.0.0.1.
- Don't call ffmpeg outside `engine.ffmpeg.*`.
- Don't couple `engine/` to Django. It must stay importable from bare Python.
- Don't diverge from Vediteur's engine without a clear reason — ideally patches
  land in both repos.

See `docs/ROADMAP.md` for milestone order and `docs/REFERENCES.md` for the
concrete FOSS-editor pattern catalog that shaped these decisions.
