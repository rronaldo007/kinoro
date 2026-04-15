/**
 * M2.4 — Load (or create) the project backing the timeline store.
 *
 * On mount:
 *   - Fetch the full project list from the sidecar.
 *   - If the incoming handoff carries a project title and a local project with
 *     the same name exists, use it (lets re-opening the same VP project pick
 *     the same Kinoro project every time instead of creating duplicates).
 *   - Otherwise pick the most-recently-updated project, or create a new one
 *     named after the handoff (defaulting to "Untitled") if the list is empty.
 *   - Hydrate the timeline store via its existing `loadProject` action.
 *
 * When `incoming.projectId` changes (a fresh handoff arrives), the effect re-
 * runs so the editor can switch to a matching local project if one exists.
 *
 * The hook is intentionally minimal: no mutations for rename, no delete,
 * no multi-project switcher. Those arrive in later slices; this one only
 * has to keep `timelineStore.projectId` non-null so autosave can target it.
 */
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createProject,
  listProjects,
  type KinoroProject,
  type TimelineJson,
} from "../../api/projects";
import { useTimelineStore } from "../../stores/timelineStore";
import type { IncomingOpen } from "../import-vp/HandoffPanel";

interface Args {
  incoming: IncomingOpen | null;
  // The resolved VP project title, when known (HandoffPanel fetches it).
  // Passed in by EditorShell if available; falls back to "Untitled".
  projectTitle?: string | null;
}

interface LoaderState {
  loading: boolean;
  error: string | null;
  projectId: string | null;
}

function hydrate(project: KinoroProject) {
  const timeline: TimelineJson = project.timeline_json ?? {};
  useTimelineStore.getState().loadProject({
    id: project.id,
    name: project.name,
    fps: project.fps,
    tracks: Array.isArray(timeline.tracks)
      ? (timeline.tracks as never)
      : undefined,
    clips: Array.isArray(timeline.clips)
      ? (timeline.clips as never)
      : undefined,
  });
}

export function useProjectLoader({ incoming, projectTitle }: Args): LoaderState {
  const qc = useQueryClient();
  const [state, setState] = useState<LoaderState>({
    loading: true,
    error: null,
    projectId: null,
  });

  const listQ = useQuery<KinoroProject[]>({
    queryKey: ["kinoro-projects"],
    queryFn: listProjects,
    staleTime: 60_000,
  });

  // Dedupe the resolve step by (list-identity, incoming.projectId) so that
  // React StrictMode double-invocation, or a subsequent unrelated re-render,
  // does not trigger duplicate createProject calls.
  const resolvedKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!listQ.isSuccess) {
      if (listQ.isError) {
        setState({
          loading: false,
          error:
            (listQ.error as Error | undefined)?.message ??
            "Failed to load projects",
          projectId: null,
        });
      }
      return;
    }

    const key = `${listQ.dataUpdatedAt}|${incoming?.projectId ?? ""}|${projectTitle ?? ""}`;
    if (resolvedKeyRef.current === key) return;
    resolvedKeyRef.current = key;

    const list = listQ.data ?? [];
    const desiredName = projectTitle?.trim() || null;

    // 1) If the handoff gives us a title and a local project matches, use it.
    let target: KinoroProject | undefined;
    if (desiredName) {
      target = list.find((p) => p.name === desiredName);
    }

    // 2) Else pick the most-recently-updated project.
    if (!target && list.length > 0) {
      target = [...list].sort((a, b) =>
        b.updated_at.localeCompare(a.updated_at),
      )[0];
    }

    if (target) {
      hydrate(target);
      setState({ loading: false, error: null, projectId: target.id });
      return;
    }

    // 3) Nothing on disk — create a fresh project.
    let cancelled = false;
    (async () => {
      try {
        const created = await createProject({
          name: desiredName || "Untitled",
        });
        if (cancelled) return;
        hydrate(created);
        qc.setQueryData<KinoroProject[]>(
          ["kinoro-projects"],
          (prev) => (prev ? [...prev, created] : [created]),
        );
        setState({ loading: false, error: null, projectId: created.id });
      } catch (err) {
        if (cancelled) return;
        setState({
          loading: false,
          error: (err as Error)?.message ?? "Failed to create project",
          projectId: null,
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    listQ.isSuccess,
    listQ.isError,
    listQ.error,
    listQ.data,
    listQ.dataUpdatedAt,
    incoming?.projectId,
    projectTitle,
    qc,
  ]);

  return state;
}
