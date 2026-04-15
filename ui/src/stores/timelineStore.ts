/**
 * Timeline state store (zustand + immer).
 *
 * Lives entirely in-memory for M2.2. Persistence (PUT /api/projects/<id>/)
 * arrives in M2.4 via a store subscription. The shape on disk is the
 * `timeline_json` field of a Project (see docs/PROJECT_FORMAT.md); this
 * store mirrors tracks + clips one-for-one.
 *
 * M2.3: adds multi-track defaults (V1/V2/A1/A2), trim + split + ripple
 * delete, move-across-tracks, and a linear undo/redo history capped at
 * 100 snapshots. Live (non-snapshotting) setters are exposed for drag
 * gestures so a single mousedown→mouseup maps to exactly one history entry.
 */
import { create } from "zustand";
import { immer } from "zustand/middleware/immer";

export type TrackKind = "video" | "audio";

export interface Track {
  id: string;
  kind: TrackKind;
  index: number;
  name: string;
}

export type ClipType = "media" | "text";

export type TransitionKind = "fade" | "dissolve";

export interface ClipTransition {
  kind: TransitionKind;
  duration_frames: number;
}

export interface Clip {
  id: string;
  track_id: string;
  asset_id: string;
  start_seconds: number;
  in_seconds: number;
  out_seconds: number;
  speed: number;
  /** Discriminator. Default "media" for existing rows (optional for
   * backwards-compat with already-persisted timelines). */
  type?: ClipType;
  // Text-clip fields (populated only when `type === "text"`):
  text_content?: string;
  text_color?: string;
  text_font_size?: number;
  // Normalized 0..1 anchor positions (x, y) within the frame.
  text_x?: number;
  text_y?: number;
  // M4 transitions — fade (to/from black) or dissolve (cross-fade with the
  // adjacent clip on the same track when both sides ask for it).
  transition_in?: ClipTransition | null;
  transition_out?: ClipTransition | null;
}

interface Snapshot {
  tracks: Track[];
  clips: Clip[];
  selection: string | null;
}

export interface TimelineState {
  projectId: string | null;
  projectName: string;
  fps: number;
  tracks: Track[];
  clips: Clip[];
  selection: string | null;
  playhead: number;
  pxPerSec: number;
  playing: boolean;
  history: Snapshot[];
  future: Snapshot[];
}

interface TimelineActions {
  reset: () => void;
  loadProject: (payload: {
    id: string;
    name: string;
    fps: number;
    tracks?: Track[];
    clips?: Clip[];
  }) => void;
  addClip: (args: {
    assetId: string;
    durationSeconds: number;
    trackId?: string;
    startSeconds?: number;
  }) => string;
  addTextClip: (args: {
    content: string;
    durationSeconds?: number;
    startSeconds?: number;
    trackId?: string;
    color?: string;
    fontSize?: number;
    x?: number;
    y?: number;
  }) => string;
  updateTextClip: (
    clipId: string,
    patch: Partial<
      Pick<Clip, "text_content" | "text_color" | "text_font_size" | "text_x" | "text_y">
    >,
  ) => void;
  removeClip: (clipId: string) => void;
  moveClip: (clipId: string, startSeconds: number, trackId?: string) => void;
  /** Non-snapshotting live update used while dragging a clip. */
  moveClipLive: (clipId: string, startSeconds: number, trackId?: string) => void;
  trimClipIn: (clipId: string, newInSeconds: number) => void;
  trimClipOut: (clipId: string, newOutSeconds: number) => void;
  /** Non-snapshotting live trim updates used while dragging edges. */
  trimClipInLive: (clipId: string, newInSeconds: number) => void;
  trimClipOutLive: (clipId: string, newOutSeconds: number) => void;
  /** Playback rate for a clip. 1.0 is normal; values outside [0.1, 10]
   * are clamped by the render engine anyway. */
  setClipSpeed: (clipId: string, speed: number) => void;
  /** Set or clear a transition on a clip's "in" or "out" edge. Pass null
   * to remove. duration_frames is clamped to [1, 120]. */
  setClipTransition: (
    clipId: string,
    edge: "in" | "out",
    value: ClipTransition | null,
  ) => void;
  splitClipAtPlayhead: () => void;
  rippleDeleteClip: (clipId: string) => void;
  selectClip: (clipId: string | null) => void;
  setPlayhead: (seconds: number) => void;
  setZoom: (pxPerSec: number) => void;
  setPlaying: (playing: boolean) => void;
  togglePlay: () => void;
  stepFrame: (direction: 1 | -1) => void;
  /** Take a snapshot of the current state (exposed so UI gesture handlers
   * can checkpoint once at mousedown and then use the *Live* setters). */
  beginHistoryStep: () => void;
  undo: () => void;
  redo: () => void;
}

const DEFAULT_TRACKS: Track[] = [
  { id: "v1", kind: "video", index: 0, name: "V1" },
  { id: "v2", kind: "video", index: 1, name: "V2" },
  { id: "a1", kind: "audio", index: 0, name: "A1" },
  { id: "a2", kind: "audio", index: 1, name: "A2" },
];

const HISTORY_LIMIT = 100;

const uid = () =>
  (typeof crypto !== "undefined" && "randomUUID" in crypto
    ? (crypto as Crypto).randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`);

// Immer returns draft snapshots when sliced, which are not safe to keep on
// the stack. Clone to plain arrays via structured copy.
function captureSnapshot(s: TimelineState): Snapshot {
  return {
    tracks: s.tracks.map((t) => ({ ...t })),
    clips: s.clips.map((c) => ({ ...c })),
    selection: s.selection,
  };
}

function pushSnapshot(s: TimelineState): void {
  s.history.push(captureSnapshot(s));
  if (s.history.length > HISTORY_LIMIT) {
    s.history.splice(0, s.history.length - HISTORY_LIMIT);
  }
  s.future = [];
}

export const useTimelineStore = create<TimelineState & TimelineActions>()(
  immer((set, get) => ({
    projectId: null,
    projectName: "Untitled",
    fps: 30,
    tracks: DEFAULT_TRACKS,
    clips: [],
    selection: null,
    playhead: 0,
    pxPerSec: 40,
    playing: false,
    history: [],
    future: [],

    reset: () =>
      set((s) => {
        s.projectId = null;
        s.projectName = "Untitled";
        s.tracks = DEFAULT_TRACKS.map((t) => ({ ...t }));
        s.clips = [];
        s.selection = null;
        s.playhead = 0;
        s.history = [];
        s.future = [];
      }),

    loadProject: ({ id, name, fps, tracks, clips }) =>
      set((s) => {
        s.projectId = id;
        s.projectName = name;
        s.fps = fps || 30;
        s.tracks =
          tracks && tracks.length
            ? tracks.map((t) => ({ ...t }))
            : DEFAULT_TRACKS.map((t) => ({ ...t }));
        s.clips = (clips ?? []).map((c) => ({ ...c }));
        s.selection = null;
        s.playhead = 0;
        s.history = [];
        s.future = [];
      }),

    addClip: ({ assetId, durationSeconds, trackId, startSeconds }) => {
      const id = uid();
      set((s) => {
        pushSnapshot(s);
        // Default to the first video track if none specified.
        const track =
          (trackId && s.tracks.find((t) => t.id === trackId)) ||
          s.tracks.find((t) => t.kind === "video") ||
          s.tracks[0];
        if (!track) return;
        let start = startSeconds;
        if (start === undefined) {
          // Append to the end of the track so drops never overlap.
          const tail = s.clips
            .filter((c) => c.track_id === track.id)
            .reduce(
              (acc, c) =>
                Math.max(acc, c.start_seconds + (c.out_seconds - c.in_seconds)),
              0,
            );
          start = tail;
        }
        s.clips.push({
          id,
          track_id: track.id,
          asset_id: assetId,
          start_seconds: Math.max(0, start),
          in_seconds: 0,
          out_seconds: Math.max(durationSeconds || 0, 0.1),
          speed: 1,
          type: "media",
        });
        s.selection = id;
      });
      return id;
    },

    addTextClip: ({
      content,
      durationSeconds,
      startSeconds,
      trackId,
      color,
      fontSize,
      x,
      y,
    }) => {
      const id = uid();
      set((s) => {
        pushSnapshot(s);
        // Text clips land on the last-available video track by default so
        // they overlay V1 content; fall back to whatever we have.
        const videoTracks = s.tracks.filter((t) => t.kind === "video");
        const target =
          (trackId && s.tracks.find((t) => t.id === trackId)) ||
          videoTracks[videoTracks.length - 1] ||
          s.tracks[0];
        if (!target) return;
        const start = Math.max(
          0,
          startSeconds !== undefined ? startSeconds : s.playhead,
        );
        const dur = Math.max(0.1, durationSeconds ?? 3.0);
        s.clips.push({
          id,
          track_id: target.id,
          asset_id: "",
          start_seconds: start,
          in_seconds: 0,
          out_seconds: dur,
          speed: 1,
          type: "text",
          text_content: content,
          text_color: color ?? "#ffffff",
          text_font_size: fontSize ?? 64,
          text_x: x ?? 0.5,
          text_y: y ?? 0.5,
        });
        s.selection = id;
      });
      return id;
    },

    updateTextClip: (clipId, patch) =>
      set((s) => {
        const clip = s.clips.find((c) => c.id === clipId);
        if (!clip || clip.type !== "text") return;
        pushSnapshot(s);
        if (patch.text_content !== undefined) clip.text_content = patch.text_content;
        if (patch.text_color !== undefined) clip.text_color = patch.text_color;
        if (patch.text_font_size !== undefined)
          clip.text_font_size = Math.max(8, Math.min(256, patch.text_font_size));
        if (patch.text_x !== undefined)
          clip.text_x = Math.max(0, Math.min(1, patch.text_x));
        if (patch.text_y !== undefined)
          clip.text_y = Math.max(0, Math.min(1, patch.text_y));
      }),

    removeClip: (clipId) =>
      set((s) => {
        pushSnapshot(s);
        s.clips = s.clips.filter((c) => c.id !== clipId);
        if (s.selection === clipId) s.selection = null;
      }),

    moveClip: (clipId, startSeconds, trackId) =>
      set((s) => {
        pushSnapshot(s);
        const clip = s.clips.find((c) => c.id === clipId);
        if (!clip) return;
        clip.start_seconds = Math.max(0, startSeconds);
        if (trackId && s.tracks.some((t) => t.id === trackId)) {
          clip.track_id = trackId;
        }
      }),

    moveClipLive: (clipId, startSeconds, trackId) =>
      set((s) => {
        const clip = s.clips.find((c) => c.id === clipId);
        if (!clip) return;
        clip.start_seconds = Math.max(0, startSeconds);
        if (trackId && s.tracks.some((t) => t.id === trackId)) {
          clip.track_id = trackId;
        }
      }),

    trimClipIn: (clipId, newInSeconds) =>
      set((s) => {
        pushSnapshot(s);
        const clip = s.clips.find((c) => c.id === clipId);
        if (!clip) return;
        const clamped = Math.max(0, Math.min(newInSeconds, clip.out_seconds - 0.05));
        clip.in_seconds = clamped;
      }),

    trimClipOut: (clipId, newOutSeconds) =>
      set((s) => {
        pushSnapshot(s);
        const clip = s.clips.find((c) => c.id === clipId);
        if (!clip) return;
        const clamped = Math.max(clip.in_seconds + 0.05, newOutSeconds);
        clip.out_seconds = clamped;
      }),

    trimClipInLive: (clipId, newInSeconds) =>
      set((s) => {
        const clip = s.clips.find((c) => c.id === clipId);
        if (!clip) return;
        const clamped = Math.max(0, Math.min(newInSeconds, clip.out_seconds - 0.05));
        clip.in_seconds = clamped;
      }),

    trimClipOutLive: (clipId, newOutSeconds) =>
      set((s) => {
        const clip = s.clips.find((c) => c.id === clipId);
        if (!clip) return;
        const clamped = Math.max(clip.in_seconds + 0.05, newOutSeconds);
        clip.out_seconds = clamped;
      }),

    setClipSpeed: (clipId, speed) =>
      set((s) => {
        pushSnapshot(s);
        const clip = s.clips.find((c) => c.id === clipId);
        if (!clip) return;
        clip.speed = Math.max(0.1, Math.min(10, Number.isFinite(speed) ? speed : 1));
      }),

    setClipTransition: (clipId, edge, value) =>
      set((s) => {
        const clip = s.clips.find((c) => c.id === clipId);
        if (!clip) return;
        pushSnapshot(s);
        const key = edge === "in" ? "transition_in" : "transition_out";
        if (value === null) {
          clip[key] = null;
          return;
        }
        const frames = Math.max(
          1,
          Math.min(
            120,
            Number.isFinite(value.duration_frames)
              ? Math.round(value.duration_frames)
              : 12,
          ),
        );
        clip[key] = { kind: value.kind, duration_frames: frames };
      }),

    splitClipAtPlayhead: () =>
      set((s) => {
        const ph = s.playhead;
        const target = s.clips.find((c) => {
          const dur = (c.out_seconds - c.in_seconds) / (c.speed || 1);
          return ph > c.start_seconds && ph < c.start_seconds + dur;
        });
        if (!target) return;
        pushSnapshot(s);
        const speed = target.speed || 1;
        // Split point expressed in SOURCE seconds (what in/out refer to).
        const sourceSplit = target.in_seconds + (ph - target.start_seconds) * speed;
        const rightId = uid();
        const leftOut = target.out_seconds;
        // Left keeps its in_seconds, its out becomes the split point.
        target.out_seconds = sourceSplit;
        // Right abuts the left on the timeline.
        s.clips.push({
          id: rightId,
          track_id: target.track_id,
          asset_id: target.asset_id,
          start_seconds: ph,
          in_seconds: sourceSplit,
          out_seconds: leftOut,
          speed: target.speed,
        });
      }),

    rippleDeleteClip: (clipId) =>
      set((s) => {
        const victim = s.clips.find((c) => c.id === clipId);
        if (!victim) return;
        pushSnapshot(s);
        const timelineDuration =
          (victim.out_seconds - victim.in_seconds) / (victim.speed || 1);
        const victimEnd = victim.start_seconds + timelineDuration;
        const trackId = victim.track_id;
        s.clips = s.clips.filter((c) => c.id !== clipId);
        // Shift later clips on the same track leftward by the removed duration.
        for (const c of s.clips) {
          if (c.track_id === trackId && c.start_seconds >= victimEnd - 1e-6) {
            c.start_seconds = Math.max(0, c.start_seconds - timelineDuration);
          }
        }
        if (s.selection === clipId) s.selection = null;
      }),

    selectClip: (clipId) =>
      set((s) => {
        s.selection = clipId;
      }),

    setPlayhead: (seconds) =>
      set((s) => {
        s.playhead = Math.max(0, seconds);
      }),

    setZoom: (pxPerSec) =>
      set((s) => {
        s.pxPerSec = Math.max(10, Math.min(400, pxPerSec));
      }),

    setPlaying: (playing) =>
      set((s) => {
        s.playing = playing;
      }),

    togglePlay: () =>
      set((s) => {
        if (s.playing) {
          s.playing = false;
          return;
        }
        // Starting playback: if the playhead is between clips, snap to the
        // earliest video clip so the viewer has something to render.
        const videoTrackIds = new Set(
          s.tracks.filter((t) => t.kind === "video").map((t) => t.id),
        );
        const onClip = s.clips.some((c) => {
          if (!videoTrackIds.has(c.track_id)) return false;
          const dur = (c.out_seconds - c.in_seconds) / (c.speed || 1);
          return s.playhead >= c.start_seconds && s.playhead < c.start_seconds + dur;
        });
        if (!onClip) {
          const next = s.clips
            .filter((c) => videoTrackIds.has(c.track_id))
            .sort((a, b) => a.start_seconds - b.start_seconds)[0];
          if (next) s.playhead = next.start_seconds;
          else return; // no clips at all — nothing to play
        }
        s.playing = true;
      }),

    stepFrame: (direction) =>
      set((s) => {
        const frameSec = 1 / Math.max(s.fps || 30, 1);
        s.playhead = Math.max(0, s.playhead + direction * frameSec);
        s.playing = false;
      }),

    beginHistoryStep: () =>
      set((s) => {
        pushSnapshot(s);
      }),

    undo: () => {
      const { history } = get();
      if (history.length === 0) return;
      set((s) => {
        const prev = s.history.pop();
        if (!prev) return;
        s.future.push(captureSnapshot(s));
        s.tracks = prev.tracks.map((t) => ({ ...t }));
        s.clips = prev.clips.map((c) => ({ ...c }));
        s.selection = prev.selection;
      });
    },

    redo: () => {
      const { future } = get();
      if (future.length === 0) return;
      set((s) => {
        const next = s.future.pop();
        if (!next) return;
        s.history.push(captureSnapshot(s));
        s.tracks = next.tracks.map((t) => ({ ...t }));
        s.clips = next.clips.map((c) => ({ ...c }));
        s.selection = next.selection;
      });
    },
  })),
);

// Selector helpers colocated so consumers don't recompute shape.
export const selectClipDuration = (clip: Clip) =>
  (clip.out_seconds - clip.in_seconds) / (clip.speed || 1);

// Make the uid helper visible for tests + future slices (split/duplicate).
export { uid as timelineUid };
