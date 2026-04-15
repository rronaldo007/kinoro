/**
 * M2.4 — Debounced autosave of the timeline to `/api/projects/<id>/`.
 *
 * Strategy:
 *   - Subscribe unconditionally to the timeline store (zustand+immer does not
 *     expose `subscribeWithSelector` here) and diff only the fields we persist
 *     — `tracks` and `clips` — so playhead scrubs and zoom changes don't
 *     trigger network traffic.
 *   - Debounce 700ms. If another change lands during the debounce, the timer
 *     resets. If another change lands while a save is in-flight, we schedule
 *     another save for after the current one resolves.
 *   - The in-flight guard keeps at most one PUT open at a time — simpler than
 *     cancelling the axios request, and good enough for single-user local.
 *
 * Intentionally NOT persisted yet: fps, name, render_settings. A rename UI
 * and project-settings panel will plug into this later.
 */
import { useEffect, useRef, useState } from "react";
import { updateProject } from "../../api/projects";
import {
  useTimelineStore,
  type Clip,
  type Track,
} from "../../stores/timelineStore";

export type SaveStatus = "idle" | "saving" | "saved" | "error";

export interface AutosaveState {
  status: SaveStatus;
  lastSavedAt: Date | null;
  error: string | null;
}

interface Args {
  projectId: string | null;
  enabled: boolean;
  debounceMs?: number;
}

interface Snapshot {
  tracks: Track[];
  clips: Clip[];
}

function snap(): Snapshot {
  const s = useTimelineStore.getState();
  return { tracks: s.tracks, clips: s.clips };
}

function sameSnapshot(a: Snapshot, b: Snapshot): boolean {
  if (a.tracks === b.tracks && a.clips === b.clips) return true;
  // Immer produces new array identities on every mutation, so the reference
  // check above is the fast path. The deep compare below is a safety net for
  // hypothetical cases where the store mutates in place.
  return (
    JSON.stringify(a.tracks) === JSON.stringify(b.tracks) &&
    JSON.stringify(a.clips) === JSON.stringify(b.clips)
  );
}

export function useAutosave({
  projectId,
  enabled,
  debounceMs = 700,
}: Args): AutosaveState {
  const [state, setState] = useState<AutosaveState>({
    status: "idle",
    lastSavedAt: null,
    error: null,
  });

  // Mutable refs keep the subscription handler stable across renders.
  const projectIdRef = useRef(projectId);
  const enabledRef = useRef(enabled);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlightRef = useRef(false);
  const pendingRef = useRef(false);
  const baselineRef = useRef<Snapshot>(snap());

  useEffect(() => {
    projectIdRef.current = projectId;
  }, [projectId]);
  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  // When the loader hydrates a fresh project, the store's tracks/clips refs
  // are brand new — treat that as the new baseline so the first hydrate
  // doesn't immediately trigger an autosave loop.
  useEffect(() => {
    if (projectId) baselineRef.current = snap();
  }, [projectId]);

  useEffect(() => {
    const save = async () => {
      const pid = projectIdRef.current;
      if (!pid || !enabledRef.current) return;
      if (inFlightRef.current) {
        pendingRef.current = true;
        return;
      }
      const { tracks, clips } = snap();
      inFlightRef.current = true;
      setState((s) => ({ ...s, status: "saving", error: null }));
      try {
        await updateProject(pid, {
          timeline_json: { version: 1, tracks, clips },
        });
        baselineRef.current = { tracks, clips };
        setState({
          status: "saved",
          lastSavedAt: new Date(),
          error: null,
        });
      } catch (err) {
        setState({
          status: "error",
          lastSavedAt: null,
          error: (err as Error)?.message ?? "Save failed",
        });
      } finally {
        inFlightRef.current = false;
        if (pendingRef.current) {
          pendingRef.current = false;
          // A change landed while we were saving — schedule another pass.
          schedule();
        }
      }
    };

    const schedule = () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        void save();
      }, debounceMs);
    };

    const unsubscribe = useTimelineStore.subscribe(() => {
      if (!projectIdRef.current || !enabledRef.current) return;
      const current = snap();
      if (sameSnapshot(current, baselineRef.current)) return;
      schedule();
    });

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      unsubscribe();
    };
  }, [debounceMs]);

  return state;
}
