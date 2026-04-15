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
 *   Ctrl/Cmd + C           → copy selected clips
 *   Ctrl/Cmd + X           → cut selected clips (copy + ripple delete)
 *   Ctrl/Cmd + V           → paste clips at playhead
 *   Alt + ← / →            → nudge selection ±1 frame on the timeline
 *   N                      → toggle snap on/off
 *   + / =                  → zoom in
 *   - / _                  → zoom out
 *
 * Pro-editor transport (JKL shuttle):
 *   J                      → play reverse; repeat to bump −1× / −2× / −4× / −8×
 *   K                      → pause (alias of Space, also drops shuttle to 0)
 *   L                      → play forward; repeat to bump 1× / 2× / 4× / 8×
 *   I                      → set mark-in at playhead
 *   O                      → set mark-out at playhead
 *   Shift + I              → clear mark-in
 *   Shift + O              → clear mark-out
 *   X                      → clear both marks (⌘X is Cut — different mod key)
 *   Shift + Space          → loop play between mark-in and mark-out;
 *                            if unset, plays from current playhead to end
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

      // Copy / Cut / Paste. Checked before generic mod bindings below so
      // they take priority on ⌘C/X/V.
      if (mod && !e.shiftKey && (key === "c" || key === "C")) {
        e.preventDefault();
        useTimelineStore.getState().copySelection();
        return;
      }
      if (mod && !e.shiftKey && (key === "x" || key === "X")) {
        e.preventDefault();
        useTimelineStore.getState().cutSelection();
        return;
      }
      if (mod && !e.shiftKey && (key === "v" || key === "V")) {
        e.preventDefault();
        useTimelineStore.getState().pasteAtPlayhead();
        return;
      }

      // Alt + Arrow → nudge selected clips by ±1 frame on the timeline.
      // Checked before the plain Arrow handler (stepFrame) so Alt steals
      // the binding from the playhead.
      if (e.altKey && !mod && key === "ArrowLeft") {
        e.preventDefault();
        useTimelineStore.getState().nudgeSelectionFrames(-1);
        return;
      }
      if (e.altKey && !mod && key === "ArrowRight") {
        e.preventDefault();
        useTimelineStore.getState().nudgeSelectionFrames(1);
        return;
      }

      // N → toggle snap on/off. Plain N only (no modifiers) so typing a
      // capital N in a non-input somewhere still toggles.
      if (!mod && !e.altKey && (key === "n" || key === "N")) {
        e.preventDefault();
        useTimelineStore.getState().toggleSnap();
        return;
      }

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

      // Shift+Space → loop-play between marks. If either mark is unset,
      // fall back to a plain toggle at the current playhead (NOT a loop of
      // the whole timeline — that's confusing).
      if (!mod && e.shiftKey && key === " ") {
        e.preventDefault();
        const s = useTimelineStore.getState();
        if (s.markIn !== null && s.markOut !== null && s.markOut > s.markIn) {
          s.startLoopPlayback();
        } else {
          // No valid range — behave like Space.
          s.stopLoopPlayback();
          s.togglePlay();
        }
        return;
      }

      // Play / pause
      if (!mod && !e.shiftKey && key === " ") {
        e.preventDefault();
        const s = useTimelineStore.getState();
        s.stopLoopPlayback();
        s.togglePlay();
        return;
      }

      // J / K / L shuttle transport. K is pause (also drops shuttle to 0).
      // L bumps forward rate (1 → 2 → 4 → 8). J bumps reverse rate.
      // Reversing direction resets to ±1. All three exit any active loop.
      if (!mod && !e.shiftKey && (key === "l" || key === "L")) {
        e.preventDefault();
        const s = useTimelineStore.getState();
        s.stopLoopPlayback();
        s.bumpPlaybackRate(1);
        return;
      }
      if (!mod && !e.shiftKey && (key === "j" || key === "J")) {
        e.preventDefault();
        const s = useTimelineStore.getState();
        s.stopLoopPlayback();
        s.bumpPlaybackRate(-1);
        return;
      }
      if (!mod && !e.shiftKey && (key === "k" || key === "K")) {
        e.preventDefault();
        const s = useTimelineStore.getState();
        s.stopLoopPlayback();
        s.setPlaying(false);
        s.setPlaybackRate(0);
        return;
      }

      // I / O → mark in / out at playhead. Shift+I / Shift+O clear them.
      if (!mod && !e.shiftKey && (key === "i" || key === "I")) {
        e.preventDefault();
        const s = useTimelineStore.getState();
        s.setMarkIn(s.playhead);
        return;
      }
      if (!mod && !e.shiftKey && (key === "o" || key === "O")) {
        e.preventDefault();
        const s = useTimelineStore.getState();
        s.setMarkOut(s.playhead);
        return;
      }
      if (!mod && e.shiftKey && (key === "I" || key === "i")) {
        e.preventDefault();
        useTimelineStore.getState().clearMarkIn();
        return;
      }
      if (!mod && e.shiftKey && (key === "O" || key === "o")) {
        e.preventDefault();
        useTimelineStore.getState().clearMarkOut();
        return;
      }

      // X (no modifier) → clear BOTH marks. ⌘X (cut) is handled above.
      if (!mod && !e.shiftKey && (key === "x" || key === "X")) {
        e.preventDefault();
        useTimelineStore.getState().clearMarks();
        return;
      }

      // Frame stepping — also exits loop + resets shuttle for predictability.
      if (!mod && key === "ArrowLeft") {
        e.preventDefault();
        const s = useTimelineStore.getState();
        s.stopLoopPlayback();
        s.stepFrame(-1);
        return;
      }
      if (!mod && key === "ArrowRight") {
        e.preventDefault();
        const s = useTimelineStore.getState();
        s.stopLoopPlayback();
        s.stepFrame(1);
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
