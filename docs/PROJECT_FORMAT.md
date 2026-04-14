# Kinoro project format

## `.kinoro` bundle

A Kinoro project is a directory (packaged as a ZIP on export) containing:

```
my-project.kinoro/
├── project.json         # Top-level metadata + timeline
├── media/               # Imported/copied media files
├── proxies/             # 1280×720 H.264 proxies (regenerable)
├── thumbnails/          # Poster frames
└── renders/             # Exported MP4s (regenerable)
```

The live working state during dev lives in the OS user-data dir
(`app.getPath("userData")/data/`) as a SQLite DB + media folders. Export packs
it into the bundle above.

## `project.json`

Inspired by LosslessCut's flat JSON (see `docs/REFERENCES.md`) but multi-track.

```jsonc
{
  "version": 1,
  "id": "uuid",
  "name": "My Project",
  "fps": 30,
  "width": 1920,
  "height": 1080,
  "duration_seconds": 0,
  "created_at": "2026-04-14T18:00:00Z",
  "updated_at": "2026-04-14T18:00:00Z",

  "media_assets": [
    {
      "id": "uuid",
      "source_path": "media/bunny.mp4",
      "kind": "video",               // video | audio | image
      "duration": 10.0,
      "width": 1920,
      "height": 1080,
      "fps": 24,
      "has_audio": true,
      "proxy_path": "proxies/bunny.mp4",
      "thumbnail_path": "thumbnails/bunny.jpg"
    }
  ],

  "tracks": [
    { "id": "v1", "kind": "video", "index": 0, "name": "V1" },
    { "id": "v2", "kind": "video", "index": 1, "name": "V2" },
    { "id": "a1", "kind": "audio", "index": 0, "name": "A1" },
    { "id": "a2", "kind": "audio", "index": 1, "name": "A2" }
  ],

  "clips": [
    {
      "id": "uuid",
      "track_id": "v1",
      "asset_id": "uuid",
      "start_seconds": 0.0,          // position on the timeline
      "in_seconds": 0.0,             // in-point within the source
      "out_seconds": 3.0,            // out-point within the source
      "speed": 1.0,                  // 1.0 = normal; 2.0 = 2× fast
      "transition_in": null,         // { kind: "fade" | "dissolve", duration_frames: 12 }
      "transition_out": null
    },
    {
      "id": "uuid",
      "track_id": "v2",
      "kind": "text",                // text clips are a special sub-shape
      "content": "Hello",
      "font": "Inter",
      "size": 64,
      "color": "#ffffff",
      "x": 0.5, "y": 0.5,            // normalized 0..1 anchor
      "start_seconds": 1.0,
      "duration_seconds": 2.0
    }
  ],

  "render_settings": {
    "preset": "youtube_1080p",        // or "tiktok_vertical" or "custom"
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "video_codec": "libx264",
    "video_crf": 18,
    "audio_codec": "aac",
    "audio_bitrate": "192k"
  }
}
```

## Compatibility

- Versioned (`version: 1`). Breaking schema changes bump the version and ship a migration.
- The same `tracks`/`clips` shape is consumed by `engine/deliver/timeline_render.py`.
- Video Planner's FCPXML exports are translated into this shape by `apps/import_vp/` in M1.

## Why not reuse Vediteur's timeline JSON verbatim

Vediteur's timeline schema couples to video-planner3's `Resource` + `Cut` models
(workspace IDs, plan-gated features). Kinoro strips those out. The render engine
expects the same `tracks` + `clips` shape, which is the only surface that
matters for compatibility.
