import { useEffect, useRef, useState } from "react";
import { Minus, Plus, Trash2, Type } from "lucide-react";
import {
  useTimelineStore,
  selectClipDuration,
  type Clip,
  type Track,
} from "../../stores/timelineStore";

const TRACK_HEADER_WIDTH = 88;
const TRACK_HEIGHT = 56;
const TRIM_HANDLE_WIDTH = 7;

type Gesture =
  | { kind: "move"; clipId: string; grabOffsetSec: number; startClientY: number }
  | { kind: "trim-in"; clipId: string }
  | { kind: "trim-out"; clipId: string };

export default function Timeline() {
  const tracks = useTimelineStore((s) => s.tracks);
  const clips = useTimelineStore((s) => s.clips);
  const pxPerSec = useTimelineStore((s) => s.pxPerSec);
  const playhead = useTimelineStore((s) => s.playhead);
  const selection = useTimelineStore((s) => s.selection);
  const addClip = useTimelineStore((s) => s.addClip);
  const addTextClip = useTimelineStore((s) => s.addTextClip);
  const removeClip = useTimelineStore((s) => s.removeClip);
  const selectClip = useTimelineStore((s) => s.selectClip);
  const setZoom = useTimelineStore((s) => s.setZoom);
  const setPlayhead = useTimelineStore((s) => s.setPlayhead);
  const beginHistoryStep = useTimelineStore((s) => s.beginHistoryStep);
  const moveClipLive = useTimelineStore((s) => s.moveClipLive);
  const trimClipInLive = useTimelineStore((s) => s.trimClipInLive);
  const trimClipOutLive = useTimelineStore((s) => s.trimClipOutLive);

  const trackPaneRef = useRef<HTMLDivElement | null>(null);
  const gestureRef = useRef<Gesture | null>(null);
  const [dragOver, setDragOver] = useState(false);

  // Ruler tick density — 1 tick / sec when zoomed in, coarser as we zoom out.
  const secondsVisible = Math.max(20, Math.ceil(600 / (pxPerSec / 40)));
  const ticks = Array.from({ length: secondsVisible }, (_, i) => i);

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const payload = e.dataTransfer.getData("application/x-kinoro-asset");
    if (!payload) return;
    try {
      const data = JSON.parse(payload) as {
        id: string;
        duration: number;
        name: string;
        kind: string;
      };
      const rect = trackPaneRef.current?.getBoundingClientRect();
      const relX = rect ? e.clientX - rect.left : 0;
      const relY = rect ? e.clientY - rect.top : 0;
      const start = Math.max(0, relX / pxPerSec);
      const trackId = trackIdAtY(tracks, relY, data.kind);
      addClip({
        assetId: data.id,
        durationSeconds: data.duration,
        startSeconds: Number.isFinite(start) ? start : undefined,
        trackId,
      });
    } catch {
      /* payload malformed — ignore */
    }
  }

  function handleTrackPaneMouseDown(e: React.MouseEvent<HTMLDivElement>) {
    // Only handle a bare click on the pane background — clip handlers
    // stop propagation for their own gestures.
    if (e.button !== 0) return;
    const rect = trackPaneRef.current?.getBoundingClientRect();
    if (!rect) return;
    const relX = e.clientX - rect.left;
    setPlayhead(Math.max(0, relX / pxPerSec));
    selectClip(null);
  }

  function handleWheel(e: React.WheelEvent<HTMLDivElement>) {
    if (!(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    const factor = e.deltaY > 0 ? 0.9 : 1.1;
    setZoom(pxPerSec * factor);
  }

  // Gesture tracking — one set of window listeners manages every drag.
  useEffect(() => {
    function onMove(e: MouseEvent) {
      const g = gestureRef.current;
      if (!g) return;
      const rect = trackPaneRef.current?.getBoundingClientRect();
      if (!rect) return;
      const relX = e.clientX - rect.left;
      const relY = e.clientY - rect.top;
      const seconds = Math.max(0, relX / pxPerSec);

      const state = useTimelineStore.getState();
      const clip = state.clips.find((c) => c.id === g.clipId);
      if (!clip) return;

      if (g.kind === "move") {
        // Allow crossing into any track of the same kind.
        const currentTrack = state.tracks.find((t) => t.id === clip.track_id);
        const desiredTrack = trackIdAtY(state.tracks, relY, currentTrack?.kind);
        moveClipLive(
          g.clipId,
          Math.max(0, seconds - g.grabOffsetSec),
          desiredTrack,
        );
      } else if (g.kind === "trim-in") {
        const timelineDelta = seconds - clip.start_seconds;
        // Moving the in-point moves the clip's start too so the visible
        // left edge tracks the cursor.
        const speed = clip.speed || 1;
        const newIn = clip.in_seconds + timelineDelta * speed;
        trimClipInLive(g.clipId, newIn);
        // Shift start to keep the right edge anchored.
        const newStart = Math.max(0, clip.start_seconds + timelineDelta);
        if (newStart !== clip.start_seconds) {
          moveClipLive(g.clipId, newStart, clip.track_id);
        }
      } else if (g.kind === "trim-out") {
        const clipEndSec = seconds;
        const speed = clip.speed || 1;
        const timelineDur = Math.max(0.05, clipEndSec - clip.start_seconds);
        const newOut = clip.in_seconds + timelineDur * speed;
        trimClipOutLive(g.clipId, newOut);
      }
    }

    function onUp() {
      gestureRef.current = null;
      document.body.style.cursor = "";
    }

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [pxPerSec, moveClipLive, trimClipInLive, trimClipOutLive]);

  function startMove(clipId: string, e: React.MouseEvent) {
    e.stopPropagation();
    e.preventDefault();
    const rect = trackPaneRef.current?.getBoundingClientRect();
    if (!rect) return;
    const clip = useTimelineStore.getState().clips.find((c) => c.id === clipId);
    if (!clip) return;
    const relX = e.clientX - rect.left;
    const grabSec = relX / pxPerSec - clip.start_seconds;
    beginHistoryStep();
    selectClip(clipId);
    gestureRef.current = {
      kind: "move",
      clipId,
      grabOffsetSec: grabSec,
      startClientY: e.clientY,
    };
    document.body.style.cursor = "grabbing";
  }

  function startTrimIn(clipId: string, e: React.MouseEvent) {
    e.stopPropagation();
    e.preventDefault();
    beginHistoryStep();
    selectClip(clipId);
    gestureRef.current = { kind: "trim-in", clipId };
    document.body.style.cursor = "col-resize";
  }

  function startTrimOut(clipId: string, e: React.MouseEvent) {
    e.stopPropagation();
    e.preventDefault();
    beginHistoryStep();
    selectClip(clipId);
    gestureRef.current = { kind: "trim-out", clipId };
    document.body.style.cursor = "col-resize";
  }

  const totalHeight = tracks.length * TRACK_HEIGHT;

  return (
    <section
      className="h-[240px] border-t flex flex-col shrink-0"
      style={{ backgroundColor: "#0f1013", borderColor: "#24262c" }}
    >
      {/* Header */}
      <div
        className="h-9 flex items-center gap-2 px-3 border-b"
        style={{ borderColor: "#24262c" }}
      >
        <span className="text-xs uppercase tracking-wider text-neutral-500">
          Timeline
        </span>
        <button
          type="button"
          onClick={() =>
            addTextClip({
              content: "Your title",
              startSeconds: useTimelineStore.getState().playhead,
              durationSeconds: 3,
            })
          }
          className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-[4px] hover:bg-white/5"
          style={{ color: "var(--color-accent)" }}
          title="Add a text overlay at the playhead"
        >
          <Type size={11} />
          Add text
        </button>
        {selection && (
          <button
            type="button"
            onClick={() => removeClip(selection)}
            className="flex items-center gap-1 text-[10px] text-red-400 hover:text-red-300 px-1.5 py-0.5 rounded-[4px]"
            title="Delete selected clip"
          >
            <Trash2 size={11} />
            Delete
          </button>
        )}
        <div className="flex-1" />
        <span className="text-[10px] font-mono text-neutral-500 tabular-nums">
          {formatTimecode(playhead)}
        </span>
        <button
          type="button"
          aria-label="Zoom out"
          onClick={() => setZoom(pxPerSec * 0.75)}
          className="p-1 rounded-[5px] hover:bg-white/5"
        >
          <Minus size={14} className="text-neutral-400" />
        </button>
        <button
          type="button"
          aria-label="Zoom in"
          onClick={() => setZoom(pxPerSec * 1.33)}
          className="p-1 rounded-[5px] hover:bg-white/5"
        >
          <Plus size={14} className="text-neutral-400" />
        </button>
      </div>

      {/* Ruler */}
      <div
        className="h-6 flex border-b select-none"
        style={{ borderColor: "#24262c" }}
      >
        <div
          className="shrink-0 border-r flex items-center justify-end pr-2 text-[10px] text-neutral-600 uppercase tracking-wider"
          style={{ width: TRACK_HEADER_WIDTH, borderColor: "#24262c" }}
        >
          00:00
        </div>
        <div
          className="flex text-[10px] text-neutral-600 font-mono overflow-hidden"
          style={{ minWidth: secondsVisible * pxPerSec }}
        >
          {ticks.map((i) => (
            <div
              key={i}
              className="border-r flex items-start pt-0.5 pl-1"
              style={{ width: pxPerSec, borderColor: "#1a1c20" }}
            >
              {i}s
            </div>
          ))}
        </div>
      </div>

      {/* Tracks */}
      <div className="flex-1 flex min-h-0 overflow-auto">
        <div
          className="shrink-0 border-r flex flex-col"
          style={{
            width: TRACK_HEADER_WIDTH,
            borderColor: "#24262c",
            backgroundColor: "#15171b",
          }}
        >
          {tracks.map((t) => (
            <div
              key={t.id}
              className="border-b flex items-center px-2 text-[10px] uppercase tracking-wider text-neutral-500"
              style={{ height: TRACK_HEIGHT, borderColor: "#1a1c20" }}
            >
              {t.name}
            </div>
          ))}
        </div>

        <div
          ref={trackPaneRef}
          className="flex-1 relative"
          onDragOver={(e) => {
            if (e.dataTransfer.types.includes("application/x-kinoro-asset")) {
              e.preventDefault();
              e.dataTransfer.dropEffect = "copy";
              setDragOver(true);
            }
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onMouseDown={handleTrackPaneMouseDown}
          onWheel={handleWheel}
          style={{
            minWidth: secondsVisible * pxPerSec,
            minHeight: totalHeight,
            backgroundColor: dragOver ? "#0f2620" : "transparent",
          }}
        >
          {tracks.map((t, idx) => (
            <div
              key={t.id}
              className="absolute left-0 right-0 border-b"
              style={{
                top: idx * TRACK_HEIGHT,
                height: TRACK_HEIGHT,
                borderColor: "#1a1c20",
              }}
            />
          ))}

          {clips.length === 0 && (
            <div
              className="absolute inset-0 flex items-center justify-center text-xs text-neutral-600 pointer-events-none"
              style={{ marginLeft: pxPerSec * 2 }}
            >
              <span className="uppercase tracking-wider">
                Drop media here
              </span>
            </div>
          )}

          {clips.map((c) => {
            const track = tracks.find((t) => t.id === c.track_id);
            if (!track) return null;
            const trackIndex = tracks.indexOf(track);
            return (
              <ClipRect
                key={c.id}
                clip={c}
                pxPerSec={pxPerSec}
                top={trackIndex * TRACK_HEIGHT}
                selected={selection === c.id}
                onStartMove={(e) => startMove(c.id, e)}
                onStartTrimIn={(e) => startTrimIn(c.id, e)}
                onStartTrimOut={(e) => startTrimOut(c.id, e)}
              />
            );
          })}

          {/* Playhead */}
          <div
            className="absolute top-0 bottom-0 w-px pointer-events-none"
            style={{
              left: playhead * pxPerSec,
              backgroundColor: "var(--color-accent)",
            }}
          />
        </div>
      </div>
    </section>
  );
}

function ClipRect({
  clip,
  pxPerSec,
  top,
  selected,
  onStartMove,
  onStartTrimIn,
  onStartTrimOut,
}: {
  clip: Clip;
  pxPerSec: number;
  top: number;
  selected: boolean;
  onStartMove: (e: React.MouseEvent) => void;
  onStartTrimIn: (e: React.MouseEvent) => void;
  onStartTrimOut: (e: React.MouseEvent) => void;
}) {
  const width = Math.max(selectClipDuration(clip) * pxPerSec, 8);
  const left = clip.start_seconds * pxPerSec;
  const isText = clip.type === "text";
  // Text clips use a yellow palette to distinguish them from media clips.
  const bg = isText
    ? selected
      ? "#3b2d0d"
      : "#2a1f08"
    : selected
      ? "#134e4a"
      : "#1f3a36";
  const border = isText
    ? selected
      ? "#f59e0b"
      : "#7a5b12"
    : selected
      ? "var(--color-accent)"
      : "#2a4a44";
  const fg = isText ? "#fde68a" : "#a7f3d0";
  const label = isText
    ? (clip.text_content || "Text").slice(0, 40)
    : clip.asset_id.slice(0, 6);
  return (
    <div
      onMouseDown={onStartMove}
      className="absolute rounded-[5px] border text-[10px] text-left px-2 py-1 overflow-hidden select-none"
      style={{
        left,
        top: top + 4,
        width,
        height: TRACK_HEIGHT - 8,
        backgroundColor: bg,
        borderColor: border,
        color: fg,
        cursor: "grab",
      }}
    >
      <span className="truncate block pointer-events-none">{label}</span>
      <span className="text-[9px] text-neutral-400 pointer-events-none">
        {selectClipDuration(clip).toFixed(2)}s{isText ? " · text" : ""}
      </span>

      {/* Transition wedges — visual cue only, no interactivity. */}
      {!isText && clip.transition_in && (
        <div
          className="absolute top-0 bottom-0 left-0 pointer-events-none"
          style={{
            width: 8,
            background:
              "linear-gradient(to right, var(--color-accent), transparent)",
            opacity: 0.55,
          }}
          title={`${clip.transition_in.kind} in (${clip.transition_in.duration_frames}f)`}
        />
      )}
      {!isText && clip.transition_out && (
        <div
          className="absolute top-0 bottom-0 right-0 pointer-events-none"
          style={{
            width: 8,
            background:
              "linear-gradient(to left, var(--color-accent), transparent)",
            opacity: 0.55,
          }}
          title={`${clip.transition_out.kind} out (${clip.transition_out.duration_frames}f)`}
        />
      )}

      {/* Trim handles */}
      <div
        onMouseDown={onStartTrimIn}
        className="absolute top-0 bottom-0 left-0"
        style={{
          width: TRIM_HANDLE_WIDTH,
          cursor: "col-resize",
          backgroundColor: selected ? "var(--color-accent)" : "transparent",
          opacity: selected ? 0.6 : 1,
        }}
        title="Trim start"
      />
      <div
        onMouseDown={onStartTrimOut}
        className="absolute top-0 bottom-0 right-0"
        style={{
          width: TRIM_HANDLE_WIDTH,
          cursor: "col-resize",
          backgroundColor: selected ? "var(--color-accent)" : "transparent",
          opacity: selected ? 0.6 : 1,
        }}
        title="Trim end"
      />
    </div>
  );
}

function trackIdAtY(
  tracks: Track[],
  relY: number,
  preferredKind?: string,
): string | undefined {
  if (!tracks.length) return undefined;
  const idx = Math.max(
    0,
    Math.min(tracks.length - 1, Math.floor(relY / TRACK_HEIGHT)),
  );
  const candidate = tracks[idx];
  if (!candidate) return undefined;
  // If a kind preference is given (from drag payload or source clip), snap
  // to the nearest track of that kind so audio doesn't land on V1.
  if (preferredKind && candidate.kind !== preferredKind) {
    const sameKind = tracks.find((t) => t.kind === preferredKind);
    return sameKind?.id ?? candidate.id;
  }
  return candidate.id;
}

function formatTimecode(seconds: number): string {
  const total = Math.max(0, seconds);
  const m = Math.floor(total / 60);
  const s = Math.floor(total % 60);
  const f = Math.floor((total % 1) * 30);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}:${String(f).padStart(2, "0")}`;
}
