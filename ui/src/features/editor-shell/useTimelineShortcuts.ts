/**
 * Global keyboard shortcuts for the timeline editor.
 *
 * Bindings (all ignore when focus is inside a text input, textarea, or
 * contenteditable element so typing in modals never triggers the editor):
 *   Space                  → play / pause
 *   ← / →                  → step ±1 frame (also pauses playback)
 *   Home                   → jump to timeline start (pauses playback)
 *   End                    → jump to timeline end (pauses playback)
 *   S                      → split clip at playhead
 *   Delete / Backspace     → ripple-delete selected clip
 *   Ctrl/Cmd + Z           → undo
 *   Ctrl/Cmd + Y           → redo
 *   Ctrl/Cmd + Shift + Z   → redo
 *   + / =                  → zoom in
 *   - / _                  → zoom out
 */
import { useEffect } from "react";
import { selectClipDuration, useTimelineStore } from "../../stores/timelineStore";

function isEditable(el: Element | null): boolean {
  if (!el) return false;
  const tag = el.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if ((el as HTMLElement).isContentEditable) return true;
  return false;
}

export function useTimelineShortcuts(): void {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isEditable(document.activeElement)) return;

      const mod = e.ctrlKey || e.metaKey;
      const key = e.key;

      // Undo / Redo
      if (mod && (key === "z" || key === "Z")) {
        e.preventDefault();
        if (e.shiftKey) {
          useTimelineStore.getState().redo();
        } else {
          useTimelineStore.getState().undo();
        }
        return;
      }
      if (mod && (key === "y" || key === "Y")) {
        e.preventDefault();
        useTimelineStore.getState().redo();
        return;
      }

      // Zoom
      if (!mod && (key === "+" || key === "=")) {
        e.preventDefault();
        const s = useTimelineStore.getState();
        s.setZoom(s.pxPerSec * 1.25);
        return;
      }
      if (!mod && (key === "-" || key === "_")) {
        e.preventDefault();
        const s = useTimelineStore.getState();
        s.setZoom(s.pxPerSec * 0.8);
        return;
      }

      // Play / pause
      if (!mod && key === " ") {
        e.preventDefault();
        useTimelineStore.getState().togglePlay();
        return;
      }

      // Frame stepping
      if (!mod && key === "ArrowLeft") {
        e.preventDefault();
        useTimelineStore.getState().stepFrame(-1);
        return;
      }
      if (!mod && key === "ArrowRight") {
        e.preventDefault();
        useTimelineStore.getState().stepFrame(1);
        return;
      }

      // Jump to timeline start / end (pause playback for predictability —
      // matches the transport buttons in Viewer.tsx).
      if (!mod && key === "Home") {
        e.preventDefault();
        const { setPlaying, setPlayhead } = useTimelineStore.getState();
        setPlaying(false);
        setPlayhead(0);
        return;
      }
      if (!mod && key === "End") {
        e.preventDefault();
        const { clips, setPlaying, setPlayhead } = useTimelineStore.getState();
        const end = clips.reduce(
          (acc, c) => Math.max(acc, c.start_seconds + selectClipDuration(c)),
          0,
        );
        setPlaying(false);
        setPlayhead(end);
        return;
      }

      // Split at playhead
      if (!mod && (key === "s" || key === "S")) {
        e.preventDefault();
        useTimelineStore.getState().splitClipAtPlayhead();
        return;
      }

      // Ripple delete selected
      if (!mod && (key === "Delete" || key === "Backspace")) {
        const { selection, rippleDeleteClip } = useTimelineStore.getState();
        if (selection) {
          e.preventDefault();
          rippleDeleteClip(selection);
        }
        return;
      }
    }

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
