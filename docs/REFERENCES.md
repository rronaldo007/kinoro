# References — patterns extracted for Kinoro

Concrete, file-pointer-backed patterns from six FOSS video editors + two reference
systems (DaVinci Resolve's public API, OpenColorIO). Shallow clones live at
`research/` (git-ignored). All six editors are **GPL** — patterns are fair game,
but no literal code may be copied into Kinoro unless Kinoro itself is GPL.

A broader architectural survey already lives at
`video-planner3/.claude/docs/VEDITEUR_REFERENCES.md` — this file is the
**actionable-patterns companion**: exact file paths, literal serialization shapes,
exact ffmpeg arguments.

---

## Kdenlive (C++/Qt, GPL-3, MLT-based)

- **Timeline**: MLT XML wrapped in `.kdenlive` — parsed/written by `src/doc/kdenlivedoc.cpp` and `src/doc/documentvalidator.cpp`. MLT's `<mlt><producer/><playlist/><tractor/>` schema.
- **Proxy**: User-configurable via `proxyparams` document property. Default cmdline lives in `KdenliveSettings::proxyparams()`; execution in `src/jobs/proxytask.cpp`. Does hw-accel detection with graceful fallback (`h264_nvenc → libx264`, `h264_vaapi → libx264`).
- **Render**: MLT `melt` consumer subprocess. `src/jobs/meltjob.cpp`.
- **Undo**: Qt's `QUndoCommand` + custom `DocUndoStack` (`src/doc/docundostack.cpp`) — 100s of per-operation command classes.
- **Shortcuts**: KDE XMLGUI — action definitions in `src/kdenliveui.rc` (XML), bound to `QAction` in code. Fully data-driven.

## Shotcut (C++/Qt + QML, GPL-3, MLT-based)

- **Timeline**: MLT XML via `MultitrackModel` (`src/models/multitrackmodel.cpp`). Same MLT schema as Kdenlive.
- **Proxy**: `src/transcoder.cpp` — wraps `melt` for format conversion.
- **Render**: MLT `melt` consumer subprocess.
- **Undo**: `QUndoCommand` with per-domain command classes in `src/commands/` (`filtercommands.cpp`, `markercommands.cpp`, `playlistcommands.cpp`). Cleaner separation than Kdenlive.
- **Shortcuts**: Centralized in `src/actions.cpp`/`actions.h` — single `Actions` class holds all `QAction*` with string keys. Data-driven.

## OpenShot (Python + C++ via SWIG, GPL-3, libopenshot-based)

- **Timeline**: JSON project file managed through an **UpdateManager** — every mutation is a serialized `UpdateAction(type, key, values)`. See `src/classes/updates.py`.
- **Proxy**: Handled inside `src/classes/proxy_service.py` calling `libopenshot` C++.
- **Render**: `libopenshot` C++ library via SWIG; no direct ffmpeg-subprocess layer in the Python side.
- **Undo**: **Distinctive pattern** — `UpdateManager.apply()` / `rollback()` use typed `UpdateAction` objects (`updates.py:55`). Each action has `type`, `key` (JSONPath-like), `values`, `old_values`. Fully JSON-serializable → easy persistence, collab diffs.
- **Shortcuts**: `QAction` wired scattered through main window + `src/windows/main_window.py`; not data-driven.

## Olive (C++/Qt, GPL-3, custom node graph — no MLT, no ffmpeg subprocess)

- **Timeline**: Custom serialization through `Project` class; loaded in `app/core.cpp`. JSON-ish.
- **Node graph**: Rich typed-node directory tree — `app/node/{audio,block,color,distort,effect,filter,generator,...}`. Each node subclasses `Node` with typed ports. Pull-based eval with per-time cache. **This is the pattern Kinoro's post-MVP color/VFX graph will emulate.**
- **Undo**: Custom `UndoCommand` at `app/undo/undocommand.h` (NOT `QUndoCommand` — own impl with child-command nesting).
- **Shortcuts**: Data-driven via preferences dialog (`app/dialog/preferences/tabs/preferenceskeyboardtab.cpp` + `keysequenceeditor.cpp`). User-editable.

## Flowblade (Python + GTK, GPL-3, MLT-based)

- **Timeline**: **Python `pickle`** via `src/projectdata.py` + `src/persistence.py`. Not portable across Python versions — unsafe for our use.
- **Proxy**: `src/proxyediting.py` (Python subprocess calls to `ffmpeg`).
- **Render**: MLT Python bindings.
- **Undo**: **Simplest pattern seen** — global `undo_stack = []` + `index` at `src/edit/undo.py:50`. Each entry is an "undo_edit" object with `do_edit()`/`undo_edit()` methods. Linear, max-length capped, no nesting. Clear educational value.
- **Shortcuts**: Spread across event handlers; no single config.

## LosslessCut (Electron + React + FFmpeg, GPL-2) — closest architectural twin to Kinoro

- **Timeline**: Flat segment list on a single source file — NOT a multi-track NLE. `src/renderer/src/types.ts:55`:
  ```ts
  interface StateSegment {
    start: number; end?: number; name: string;
    segId: string; segColorIndex: number;
    tags?: SegmentTags; selected: boolean;
  }
  ```
- **Proxy**: No traditional proxies. Uses `createMediaSourceProcess()` at `src/main/ffmpeg.ts:575` to stream an on-the-fly compatible preview (html5-compatible codec) into a `MediaSource`. Elegant for a cut-only tool; Kinoro needs real proxy files for multi-clip playback.
- **Render**: `runFfmpegWithProgress()` at `src/main/ffmpeg.ts:169` — uses the `concat` demuxer (via `concatTxt` file) for lossless joins, plus `filter_complex` for re-encoded paths. Progress parsed from `ffmpeg -progress` stderr.
- **Undo**: Lightweight snapshot-based state in renderer (no command pattern).
- **Shortcuts**: **Cleanest TS pattern of the six.** `src/common/types.ts:3`:
  ```ts
  export type KeyboardAction = 'addSegment' | 'play' | 'pause' | 'undo' | 'redo' | ...;   // ~130 actions
  export interface KeyBinding { keys: string; action: KeyboardAction; }
  ```
  Stored as `KeyBinding[]` in user settings; resolved via `keyBindingsByKeyCode` lookup in `src/renderer/src/hooks/useKeyboard.ts:24`. **Port this shape verbatim to Kinoro** (replace action-name list).

---

## DaVinci Resolve (proprietary — PUBLIC SDK only, no source)

From Blackmagic's public Scripting API / Workflow Integration SDK:

- **Data model hierarchy**: `Resolve → ProjectManager → Project → MediaPool → MediaPoolItem → Timeline → TimelineItem`. Kinoro should mirror this naming so Resolve power users can transfer mental models.
- **Color nodes**: `TimelineItem.SetLUT(nodeIndex, lutPath)`, `SetCDL(nodeIndex, cdlData)`. Node index is **1-based** (post v16.2). If Kinoro ever exposes scripting, match this to lower friction.
- **Interop formats**: FCP XML (File → Timelines → Export), AAF (Media Composer), EDL. Kinoro's Vediteur sibling already exports FCPXML 1.10 (per `video-planner3/.claude/docs/EDITOR_TOOL.md`) — reuse that logic for Resolve round-trip.
- **Source**: `https://forum.blackmagicdesign.com/`, community mirrors like `extremraym.com/cloud/resolve-scripting-doc/`. No access to Resolve source code — not public.

## OpenColorIO v2 (Apache-2, open-source color management)

- **Config (YAML)**: `roles:` (required: `aces_interchange`, `cie_xyz_d65_interchange` in OCIO 2.2+), `colorspaces:`, `displays:`, `views:`, `looks:`, `file_rules:`.
- **LUT loading**: `FileTransform(src=path.cube, interpolation=LINEAR|TETRAHEDRAL)` — natively loads Iridas `.cube` (3D + optional 1D shaper). No extra lib.
- **API**: `config.getProcessor(src_cs, dst_cs) → processor.applyRGB(pixels)`.
- **Default config for Kinoro**: **ACES Studio Config 1.0.3** for Resolve-parity color. ACES CG is lighter but lacks the camera/display coverage Resolve users expect.

---

## Cross-cutting takeaways — concrete decisions for Kinoro

1. **Timeline shape**: Kinoro's `timeline.json` should combine LosslessCut's flat-JSON ergonomics with a multi-track structure:
   ```ts
   interface Timeline {
     tracks: Track[];             // V1, V2, A1, A2, ...
     duration_seconds: number;
     fps: number;
   }
   interface Track { id: string; kind: 'video' | 'audio' | 'text'; clips: Clip[]; }
   interface Clip { id: string; mediaId: string; start: number; in: number; out: number; /* ...*/ }
   ```
   Reject: MLT XML (Kdenlive/Shotcut — couples to MLT runtime we don't ship), Python pickle (Flowblade — unsafe), libopenshot JSON (OpenShot — requires C++ lib).

2. **Undo model**: Use Immer + a linear history array + index (Flowblade-style, cheap structural sharing). OpenShot's serializable `UpdateAction` is tempting for future collab/sync but overkill for MVP. If we ever want server-synced edits, refactor to UpdateAction at that point.

3. **Keyboard shortcuts**: Copy **LosslessCut's** exact TypeScript shape (file pointer `src/common/types.ts:3-8` — GPL-2, so the *pattern* is ours, not the literal code). One `KeyboardAction` string-literal union + `KeyBinding[]` array persisted in settings. Bind via a `useKeyboard` hook.

4. **Proxy ffmpeg command (Kinoro M1 literal)**:
   ```bash
   ffmpeg -i <src> -c:v libx264 -preset fast -crf 23 \
          -vf "scale=1280:720:force_original_aspect_ratio=decrease" \
          -c:a aac -b:a 128k -y <proxy.mp4>
   ```
   Start hardcoded. Add Kdenlive's hw-accel fallback chain (`h264_nvenc`/`h264_vaapi` → `libx264`) post-MVP via GPU probe.

5. **Render pipeline**: Merge LosslessCut's `runFfmpegWithProgress` pattern (`src/main/ffmpeg.ts:169` — spawns ffmpeg, parses `-progress` stderr into a callback) with Vediteur's `timeline_render.py` (filter_complex assembly from timeline JSON). Stream progress over Django Channels → WebSocket → Zustand.

6. **Node graph (post-MVP)**: When we build color/VFX, model the typed-port + per-time-cache architecture from `research/olive/app/node/` — read nodes in `color/`, `effect/`, `filter/` before designing our own. Use React Flow for the UI.

7. **Interop**: Port Vediteur's FCPXML 1.10 exporter (in `video-planner3/backend/apps/exports/`) into Kinoro's `engine/deliver/` — unlocks Resolve round-trip via File → Timelines → Import FCPXML.

---

## Files to re-open when implementing each milestone

| Milestone | Primary references |
|---|---|
| M1 Media pool + proxies | `research/flowblade/flowblade-trunk/Flowblade/src/proxyediting.py` · `research/kdenlive/src/jobs/proxytask.cpp` |
| M2 Timeline | `research/lossless-cut/src/renderer/src/types.ts` · `research/olive/app/core.cpp` |
| M2 Undo | `research/flowblade/flowblade-trunk/Flowblade/src/edit/undo.py` (linear list+index pattern) |
| M2 Shortcuts | `research/lossless-cut/src/common/types.ts` + `src/renderer/src/hooks/useKeyboard.ts` |
| M5 Export | `research/lossless-cut/src/main/ffmpeg.ts` · `video-planner3/backend/vediteur_engine/deliver/timeline_render.py` |
| M7 Color | `research/olive/app/node/color/` · OCIO Studio Config · DaVinci public scripting `SetLUT`/`SetCDL` |
| Post-MVP node graph | `research/olive/app/node/` (entire tree) |

All GPL — study, don't copy verbatim.
