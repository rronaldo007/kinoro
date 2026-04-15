import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Pause,
  Play,
  SkipBack,
  SkipForward,
  Volume2,
  VolumeX,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { listMedia, type MediaAsset } from "../../api/media";
import {
  selectClipDuration,
  useTimelineStore,
  type Clip,
  type Track,
} from "../../stores/timelineStore";

// Engine renders text at 1080p. Preview is rendered in whatever the
// viewer container happens to be — scale fontSize proportionally so
// what you see approximates what you export.
const RENDER_HEIGHT = 1080;

export default function Viewer() {
  const tracks = useTimelineStore((s) => s.tracks);
  const clips = useTimelineStore((s) => s.clips);
  const playhead = useTimelineStore((s) => s.playhead);
  const playing = useTimelineStore((s) => s.playing);
  const fps = useTimelineStore((s) => s.fps);
  const setPlayhead = useTimelineStore((s) => s.setPlayhead);
  const setPlaying = useTimelineStore((s) => s.setPlaying);
  const stepFrame = useTimelineStore((s) => s.stepFrame);

  // If the playhead isn't over any clip, "play" should snap to the first
  // video clip's start before starting playback — otherwise the disabled
  // button looks broken.
  function handlePlayPause() {
    if (playing) {
      setPlaying(false);
      return;
    }
    const active = findActiveVideoClip(tracks, clips, playhead);
    if (!active) {
      const first = firstVideoClip(tracks, clips);
      if (first) {
        setPlayhead(first.start_seconds);
        setPlaying(true);
      }
      return;
    }
    setPlaying(true);
  }

  const mediaQ = useQuery({ queryKey: ["media"], queryFn: listMedia });
  const assets = mediaQ.data ?? [];

  // Topmost media-track clip under the playhead. Text clips are overlays,
  // not the source video, so we skip them here.
  const activeClip = useMemo(
    () => findActiveVideoClip(tracks, clips, playhead),
    [tracks, clips, playhead],
  );

  // All text clips active at this instant — drawn as absolutely-positioned
  // overlays on top of the video.
  const activeTextClips = useMemo(
    () =>
      clips.filter((c) => {
        if ((c.type ?? "media") !== "text") return false;
        const dur = selectClipDuration(c);
        return playhead >= c.start_seconds && playhead < c.start_seconds + dur;
      }),
    [clips, playhead],
  );
  const activeAsset = useMemo(
    () =>
      activeClip ? assets.find((a) => a.id === activeClip.asset_id) ?? null : null,
    [activeClip, assets],
  );

  const proxyUrl = useMemo(() => resolveProxyUrl(activeAsset), [activeAsset]);

  // All audio-track clips active at this instant. A1/A2 may overlap, so we
  // allow multiple. Each one is rendered as a hidden <audio> element by
  // AudioLayer and played additively on top of the V1 <video>'s own audio.
  const activeAudioClips = useMemo(
    () =>
      findActiveAudioClips(tracks, clips, playhead, assets),
    [tracks, clips, playhead, assets],
  );

  // Local mute toggle for the transport bar — mirrored to the <video> element
  // and every <audio> element inside AudioLayer. Default: unmuted.
  const [muted, setMuted] = useState(false);

  // Furthest right edge across all clips on every track. Used by the
  // jump-to-end transport button (and matched by the End keybinding in
  // useTimelineShortcuts.ts).
  const timelineEnd = useMemo(
    () =>
      clips.reduce(
        (acc, c) => Math.max(acc, c.start_seconds + selectClipDuration(c)),
        0,
      ),
    [clips],
  );

  function jumpToStart() {
    setPlaying(false);
    setPlayhead(0);
  }

  function jumpToEnd() {
    setPlaying(false);
    setPlayhead(timelineEnd);
  }

  const videoRef = useRef<HTMLVideoElement>(null);
  // Suppress the timeupdate → setPlayhead handler when WE just set the
  // currentTime from an external playhead change (avoids feedback loops).
  const suppressTimeupdateRef = useRef(false);

  // Swap src when active clip (or its proxy URL) changes.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (!proxyUrl) {
      video.removeAttribute("src");
      video.load();
      return;
    }
    if (video.src !== proxyUrl) {
      video.src = proxyUrl;
    }
  }, [proxyUrl]);

  // Keep the video element's currentTime in sync with the external playhead
  // when we're NOT the ones driving it (i.e. not playing, or user scrubbed).
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !activeClip || !proxyUrl) return;
    const speed = activeClip.speed || 1;
    const sourceSeconds =
      activeClip.in_seconds + (playhead - activeClip.start_seconds) * speed;
    if (!Number.isFinite(sourceSeconds)) return;
    if (Math.abs(video.currentTime - sourceSeconds) > 0.08) {
      suppressTimeupdateRef.current = true;
      video.currentTime = Math.max(0, sourceSeconds);
    }
  }, [playhead, activeClip, proxyUrl]);

  // Play/pause controller.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (playing && activeClip && proxyUrl) {
      video.playbackRate = activeClip.speed || 1;
      void video.play().catch(() => {
        /* autoplay may be blocked until a click; swallow */
      });
    } else {
      video.pause();
    }
  }, [playing, activeClip, proxyUrl]);

  function onTimeUpdate() {
    if (suppressTimeupdateRef.current) {
      suppressTimeupdateRef.current = false;
      return;
    }
    if (!playing || !activeClip) return;
    const video = videoRef.current;
    if (!video) return;
    const speed = activeClip.speed || 1;
    const clipDur = selectClipDuration(activeClip);
    const offsetInClip = (video.currentTime - activeClip.in_seconds) / speed;
    const newPlayhead = activeClip.start_seconds + offsetInClip;
    // Step past the boundary to hand off to the next clip (or stop).
    if (newPlayhead >= activeClip.start_seconds + clipDur - 1e-3) {
      setPlayhead(activeClip.start_seconds + clipDur + 1e-3);
    } else {
      setPlayhead(newPlayhead);
    }
  }

  function onEnded() {
    if (!activeClip) return;
    setPlayhead(
      activeClip.start_seconds + selectClipDuration(activeClip) + 1e-3,
    );
    // If there's another clip ahead, the playhead update swaps src above.
    // If not, explicitly stop.
    const next = findActiveVideoClip(
      tracks,
      clips,
      activeClip.start_seconds + selectClipDuration(activeClip) + 1e-3,
    );
    if (!next) setPlaying(false);
  }

  return (
    <div
      className="flex-1 flex flex-col min-w-0"
      style={{ backgroundColor: "#0b0c0e" }}
    >
      <div
        className="flex items-center gap-3 px-4 py-2 border-b"
        style={{ borderColor: "#24262c" }}
      >
        <button
          type="button"
          aria-label="Jump to start"
          onClick={jumpToStart}
          disabled={clips.length === 0}
          className="p-1 rounded-[5px] hover:bg-white/5 text-neutral-400 disabled:opacity-40"
        >
          <SkipBack size={14} />
        </button>
        <button
          type="button"
          aria-label="Step back one frame"
          onClick={() => stepFrame(-1)}
          className="p-1 rounded-[5px] hover:bg-white/5 text-neutral-400"
        >
          <ChevronLeft size={14} />
        </button>
        <button
          type="button"
          aria-label={playing ? "Pause" : "Play"}
          onClick={handlePlayPause}
          className="p-1.5 rounded-[5px] hover:bg-white/5 disabled:opacity-40"
          style={{
            color: playing ? "var(--color-accent)" : "#a3a3a3",
          }}
          disabled={clips.length === 0}
        >
          {playing ? <Pause size={16} /> : <Play size={16} />}
        </button>
        <button
          type="button"
          aria-label="Step forward one frame"
          onClick={() => stepFrame(1)}
          className="p-1 rounded-[5px] hover:bg-white/5 text-neutral-400"
        >
          <ChevronRight size={14} />
        </button>
        <button
          type="button"
          aria-label="Jump to end"
          onClick={jumpToEnd}
          disabled={clips.length === 0}
          className="p-1 rounded-[5px] hover:bg-white/5 text-neutral-400 disabled:opacity-40"
        >
          <SkipForward size={14} />
        </button>
        <div className="flex-1 flex justify-center items-center gap-3">
          <span className="font-mono text-sm text-neutral-400 tabular-nums">
            {formatTimecode(playhead, fps)}
          </span>
          <button
            type="button"
            aria-label={muted ? "Unmute" : "Mute"}
            onClick={() => setMuted((m) => !m)}
            className="p-1 rounded-[5px] hover:bg-white/5"
            style={{
              color: muted ? "var(--color-text-tertiary, #6b7280)" : "var(--color-accent)",
            }}
          >
            {muted ? <VolumeX size={14} /> : <Volume2 size={14} />}
          </button>
        </div>
        <span className="text-[10px] uppercase tracking-wider text-neutral-600">
          {fps} fps
        </span>
      </div>
      <div className="flex-1 flex items-center justify-center p-4 min-h-0">
        <div
          className="relative aspect-video max-w-full max-h-full w-full flex items-center justify-center rounded-[5px] overflow-hidden"
          style={{
            backgroundColor: "#000",
            // Enable container queries so text overlays scale by this box's
            // height (see TextOverlays at the bottom of this file).
            containerType: "size",
          }}
        >
          <video
            ref={videoRef}
            onTimeUpdate={onTimeUpdate}
            onEnded={onEnded}
            className="w-full h-full object-contain"
            playsInline
            muted={muted}
            style={{ display: proxyUrl ? "block" : "none" }}
          />
          <AudioLayer
            clips={activeAudioClips}
            assets={assets}
            playhead={playhead}
            playing={playing}
            muted={muted}
          />
          <TextOverlays clips={activeTextClips} />
          {!activeClip && (
            <span className="absolute text-xs text-neutral-600 uppercase tracking-wider">
              No video on playhead
            </span>
          )}
          {activeClip && !proxyUrl && (
            <span className="absolute text-xs text-neutral-600 uppercase tracking-wider">
              Proxy building…
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// Audio-track clips overlapping the current playhead, limited to clips whose
// asset has a ready proxy (the browser can only play ready AAC proxies).
// We don't dedupe across tracks — A1 + A2 both play if they overlap, which
// matches the engine's amix behaviour.
function findActiveAudioClips(
  tracks: Track[],
  clips: Clip[],
  playhead: number,
  assets: MediaAsset[],
): Clip[] {
  const audioTrackIds = new Set(
    tracks.filter((t) => t.kind === "audio").map((t) => t.id),
  );
  if (audioTrackIds.size === 0) return [];
  return clips.filter((c) => {
    if (!audioTrackIds.has(c.track_id)) return false;
    if ((c.type ?? "media") !== "media") return false;
    const dur = selectClipDuration(c);
    if (!(playhead >= c.start_seconds && playhead < c.start_seconds + dur)) {
      return false;
    }
    const asset = assets.find((a) => a.id === c.asset_id);
    return !!asset && asset.proxy_status === "ready" && !!asset.proxy_url;
  });
}

// Hidden <audio> elements, one per active audio clip. Elements stay mounted
// across playhead ticks as long as their clip is still active (keyed by
// clip id) so we don't thrash DOM on every frame. Each element's currentTime,
// playbackRate, and playing state are driven by effects that mirror the
// main <video>'s pattern.
function AudioLayer({
  clips,
  assets,
  playhead,
  playing,
  muted,
}: {
  clips: Clip[];
  assets: MediaAsset[];
  playhead: number;
  playing: boolean;
  muted: boolean;
}) {
  const refs = useRef<Map<string, HTMLAudioElement>>(new Map());
  // Suppress feedback on programmatic currentTime writes, per-clip.
  const suppressRef = useRef<Map<string, boolean>>(new Map());

  // Prune refs for clips no longer active.
  useEffect(() => {
    const alive = new Set(clips.map((c) => c.id));
    for (const key of Array.from(refs.current.keys())) {
      if (!alive.has(key)) {
        refs.current.delete(key);
        suppressRef.current.delete(key);
      }
    }
  }, [clips]);

  // Sync currentTime + playbackRate + play/pause for every active audio clip.
  useEffect(() => {
    for (const clip of clips) {
      const el = refs.current.get(clip.id);
      if (!el) continue;
      const speed = clip.speed || 1;
      const sourceSeconds =
        clip.in_seconds + (playhead - clip.start_seconds) * speed;
      if (Number.isFinite(sourceSeconds)) {
        if (Math.abs(el.currentTime - sourceSeconds) > 0.08) {
          suppressRef.current.set(clip.id, true);
          el.currentTime = Math.max(0, sourceSeconds);
        }
      }
      el.playbackRate = speed;
      el.muted = muted;
      if (playing) {
        void el.play().catch(() => {
          /* autoplay may be blocked until a click; swallow */
        });
      } else {
        el.pause();
      }
    }
  }, [clips, playhead, playing, muted]);

  return (
    <>
      {clips.map((clip) => {
        const asset = assets.find((a) => a.id === clip.asset_id) ?? null;
        const src = resolveProxyUrl(asset);
        if (!src) return null;
        return (
          <audio
            key={clip.id}
            ref={(el) => {
              if (el) {
                refs.current.set(clip.id, el);
              } else {
                // Element unmounting — pause + rewind so next mount starts clean.
                const prev = refs.current.get(clip.id);
                if (prev) {
                  prev.pause();
                  try {
                    prev.currentTime = 0;
                  } catch {
                    /* ignore */
                  }
                }
                refs.current.delete(clip.id);
              }
            }}
            src={src}
            preload="auto"
            style={{ display: "none" }}
          />
        );
      })}
    </>
  );
}

function findActiveVideoClip(
  tracks: Track[],
  clips: Clip[],
  playhead: number,
): Clip | null {
  // Preference: topmost video track (lowest `index` since V1 is on top).
  const videoTracks = tracks
    .filter((t) => t.kind === "video")
    .sort((a, b) => a.index - b.index);
  for (const track of videoTracks) {
    const candidate = clips.find((c) => {
      if (c.track_id !== track.id) return false;
      if ((c.type ?? "media") !== "media") return false;
      const dur = selectClipDuration(c);
      return playhead >= c.start_seconds && playhead < c.start_seconds + dur;
    });
    if (candidate) return candidate;
  }
  return null;
}

function TextOverlays({ clips }: { clips: Clip[] }) {
  if (clips.length === 0) return null;
  return (
    <div
      className="absolute inset-0 pointer-events-none"
      // Use a CSS container-query style trick: font-size scales with the
      // box height so fontSize values (set at 1080p reference) render
      // proportionally in whatever viewer size we have.
    >
      {clips.map((c) => (
        <div
          key={c.id}
          className="absolute whitespace-pre-wrap text-center"
          style={{
            left: `${(c.text_x ?? 0.5) * 100}%`,
            top: `${(c.text_y ?? 0.5) * 100}%`,
            transform: "translate(-50%, -50%)",
            color: c.text_color ?? "#ffffff",
            // Scale via viewport-height-ish trick: use cqh via container
            // queries so text tracks the viewer box. Fallback: approximate
            // the render height (1080) with a fixed ratio.
            fontSize: `calc(${((c.text_font_size ?? 64) / RENDER_HEIGHT) * 100}cqh)`,
            textShadow: "0 2px 10px rgba(0,0,0,0.55)",
            fontWeight: 600,
            lineHeight: 1.1,
            letterSpacing: "-0.01em",
            maxWidth: "90%",
          }}
        >
          {c.text_content}
        </div>
      ))}
    </div>
  );
}

function firstVideoClip(tracks: Track[], clips: Clip[]): Clip | null {
  const videoTrackIds = new Set(
    tracks.filter((t) => t.kind === "video").map((t) => t.id),
  );
  return (
    clips
      .filter((c) => videoTrackIds.has(c.track_id))
      .sort((a, b) => a.start_seconds - b.start_seconds)[0] ?? null
  );
}

function resolveProxyUrl(asset: MediaAsset | null): string | null {
  if (!asset || !asset.proxy_url || asset.proxy_status !== "ready") return null;
  const port = typeof window !== "undefined" ? window.kinoro?.apiPort : undefined;
  if (!port) return null;
  // proxy_url is already the absolute path "/proxies/<uuid>.mp4" served by
  // the sidecar's static() mapping.
  return `http://127.0.0.1:${port}${asset.proxy_url}`;
}

function formatTimecode(seconds: number, fps: number): string {
  const f = Math.max(fps || 30, 1);
  const total = Math.max(0, seconds);
  const hh = Math.floor(total / 3600);
  const mm = Math.floor((total % 3600) / 60);
  const ss = Math.floor(total % 60);
  const ff = Math.floor((total - Math.floor(total)) * f);
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}:${String(ff).padStart(2, "0")}`;
}
