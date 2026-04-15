# Kinoro backlog — unscheduled editing tasks

The committed milestones live in [`ROADMAP.md`](./ROADMAP.md). The
chronological log of shipped work lives in [`PROGRESS.md`](./PROGRESS.md).
This file is the **idea pool** — editor features that would make Kinoro
feel more like a real NLE, grouped by surface area. Nothing here is
scheduled; pick off slices as sessions allow.

Entries marked **★** are the highest value-per-hour candidates.

---

## Timeline UX

- ★ **Multi-select clips** — shift-click + marquee, batch move/delete.
- ★ **Copy / cut / paste clips** — ⌘C / ⌘X / ⌘V, paste at playhead.
- ★ **J / K / L playback** — rewind / pause / fast-forward; the NLE
  muscle-memory standard.
- ★ **Mark I / O + "play between"** — I and O keys set in/out;
  Shift+Space loops the range.
- ★ **Alt+arrow nudge** — move selected clip by one frame.
- ★ **Snap to playhead + clip edges** while dragging, toggle with N.
- **Razor tool / blade mode** — click anywhere on a clip to split.
- **Ripple edit mode vs overwrite mode** — global toggle.
- **Ripple / roll / slide / slip trim** — four standard trim flavours.
- **Drag-reorder tracks** — drag the track header to re-stack.
- **Track height resize**, **color labels**, **lock / mute / solo**.
- **Minimap of whole timeline** at the bottom.
- **Right-click context menu on clips** — split, duplicate, properties.
- **Drop files directly on the viewer** → add to timeline at playhead.

## Visual fidelity

- **Clip thumbnails on the timeline strip** — not just flat rectangles.
- **Waveforms on audio clips**.
- **Gridlines / rule of thirds overlay** in the viewer.
- **Safe-area overlays** (title-safe, action-safe).
- **Fullscreen preview** (F key).
- **Preview quality toggle** (full / half / quarter) for large projects.
- **Scrubbing audio preview** — brief "scratch" playback on drag.

## Clip operations

- **Freeze frame** at playhead (still image for N seconds).
- **Reverse clip direction**.
- **Detach / reattach audio** from video.
- **Compound clips** — nest a selection into a single clip.
- **Auto-detect scene changes** on long imports (`select='gt(scene,...)'`).
- **Clip speed ramp** — speed changes over time, not constant.

## Inspector depth

- **Transform** — position, scale, rotation, anchor (currently placeholder).
- **Opacity** (currently placeholder).
- **Blending modes** — screen, multiply, overlay, difference.
- **Crop / rotate** primitives.
- **Per-clip audio gain** in dB.
- **Generic keyframe editor** — opacity, position, scale, volume; bezier
  easing, copy/paste keyframes across clips.

## Audio

- Per-track volume + mute/solo + fade in/out (part of M6).
- LUFS normalize via ffmpeg `loudnorm` (part of M6).
- VU meters in transport bar.
- Per-clip volume automation (keyframes).
- Audio ducking — auto-lower music under voice.
- Silence detection + one-click trim.
- Noise reduction (`afftdn`).
- Voice isolation.
- Per-track EQ.
- Audio-only crossfade independent of the paired video transition.

## Text & graphics

- **Title presets** — lower third, opener, credit scroll.
- **Mixed styles in one clip** — bold / italic runs.
- **Animated text** — fade-in word-by-word, typewriter.
- **Solid color / gradient background clips**.
- **Shape overlays** — rectangle, circle, line.
- **Countdown timer generator**.

## Transitions (beyond fade + dissolve)

- Slide, push, wipe (L/R/U/D variants).
- Zoom in / out.
- Page curl, blur dissolve.

## Effects

- Blur, sharpen.
- Color correction primitives — exposure, contrast, saturation (M7 sets
  up the full color pipeline; these small primitives could land earlier).
- Vignette.
- Grain / film look.
- Pixelate (for censoring).
- Mirror / flip H+V.
- Stabilization (`vidstabdetect` + `vidstabtransform`).

## Media management

- **Bins / folders** in the media pool.
- **Search + filter** — name, duration, kind.
- **Import from URL** — paste YouTube link → yt-dlp → media pool.
- **Relink missing media** modal.
- **Proxy regeneration on demand**.
- **Reveal source file** in the OS file manager.
- **Delete unused media** — media that's not referenced by any project.

## Export / deliver polish

- **Presets** — YouTube 1080p, TikTok 9:16, Instagram 1:1, Custom.
- **Render in/out range only** (paired with the I/O mark feature).
- **Open output folder** after render.
- **Hardware acceleration** — VAAPI / NVENC / VideoToolbox.
- **Render queue** — multi-project, background render while editing.
- **Completion notifications** — OS notification + optional webhook.

## Project workflow

- **Recent projects list** on startup.
- **Duplicate project**.
- **Project templates** — save current state as template.
- **Per-project render settings memory**.
- **Auto-backup** every N minutes to a separate file.
- **Project version history**.
- **Export project as sharable ZIP** (timeline + media + thumbnails).
- **Import shared ZIP back** as a new project.
- **Comments pinned to timeline locations**.

## Keyboard & accessibility

- **Customizable shortcuts** — JSON config.
- **Shortcut cheat sheet overlay** (? key).
- **Theme toggle** — light / dark.
- **High-contrast mode**.
- **UI zoom** — Ctrl+±.

## VP integration deepening

- **Push render back to VP** as a Resource on the source project.
- **Sync timeline changes back** to VP's `EditorProject.timeline_json`.
- **VP comments** surface as Kinoro timeline markers.

---

## Suggested bundled slices

Good PR-sized groupings — each roughly one session:

1. **Timeline UX 6-pack** (all ★ items above): multi-select +
   copy/paste + J/K/L + I/O + nudge + snap. Makes Kinoro feel like
   a real NLE.
2. **Clip thumbnails + waveforms** — timeline strip visual fidelity.
3. **Transform / opacity / blending** — flesh out the Inspector
   placeholders.
4. **Media management pack** — bins, search, relink, reveal-in-folder.
5. **Render presets + range** — YouTube/TikTok/IG presets + render
   in/out range only + open folder on done.
6. **Import-from-URL** — yt-dlp integration for quick testing.
