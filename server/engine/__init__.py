"""Kinoro render engine — framework-free. No Django/FastAPI imports.

Layers:
  ffmpeg/  — probe, transcode, thumbnails
  deliver/ — timeline_render (filter_complex assembly)
  color/   — LUT / curves / scopes   (M7)
  audio/   — mixer / LUFS             (M6)
  graph/   — typed-port node eval     (post-MVP)

Shared with Vediteur in video-planner3; keep byte-identical where possible so
bug fixes port both ways.
"""
