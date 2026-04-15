import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Film, Play } from "lucide-react";
import {
  listRenderJobs,
  startRender,
  type RenderJob,
} from "../../api/render";
import { useTimelineStore } from "../../stores/timelineStore";

export default function DeliverPanel() {
  const projectId = useTimelineStore((s) => s.projectId);
  const projectName = useTimelineStore((s) => s.projectName);
  const clips = useTimelineStore((s) => s.clips);
  const fps = useTimelineStore((s) => s.fps);

  const qc = useQueryClient();

  const jobsQ = useQuery({
    queryKey: ["render-jobs"],
    queryFn: listRenderJobs,
    // Poll while anything is running.
    refetchInterval: (q) => {
      const data = q.state.data as RenderJob[] | undefined;
      return data?.some((j) => j.status === "queued" || j.status === "rendering")
        ? 1000
        : false;
    },
  });

  const startMut = useMutation({
    mutationFn: (id: string) => startRender({ project: id }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["render-jobs"] }),
  });

  const canRender = !!projectId && clips.length > 0;
  const jobs = jobsQ.data ?? [];
  const apiPort =
    typeof window !== "undefined" ? window.kinoro?.apiPort : undefined;
  const origin = apiPort ? `http://127.0.0.1:${apiPort}` : "";

  return (
    <div
      className="flex-1 flex flex-col min-w-0 overflow-y-auto"
      style={{ backgroundColor: "#0b0c0e" }}
    >
      <div
        className="px-6 py-5 border-b"
        style={{ borderColor: "#24262c" }}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2
              className="text-lg font-semibold truncate"
              style={{ color: "var(--color-text-heading, #e5e5e5)" }}
            >
              {projectName}
            </h2>
            <p className="text-xs text-neutral-500 mt-1">
              {clips.length} clip{clips.length === 1 ? "" : "s"} · {fps} fps ·
              YouTube 1080p preset
            </p>
          </div>
          <button
            type="button"
            onClick={() => projectId && startMut.mutate(projectId)}
            disabled={!canRender || startMut.isPending}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-[7px] active:scale-[0.98] disabled:opacity-40"
            style={{
              backgroundColor: "var(--color-accent)",
              color: "#0b0c0e",
            }}
          >
            <Play size={14} />
            {startMut.isPending ? "Queuing…" : "Render"}
          </button>
        </div>
        {!canRender && (
          <p className="text-xs text-neutral-600 mt-2">
            Add at least one clip to the timeline before rendering.
          </p>
        )}
        {startMut.isError && (
          <p className="text-xs text-red-300 mt-2">
            {startMut.error instanceof Error
              ? startMut.error.message
              : "Could not queue render."}
          </p>
        )}
      </div>

      <div className="px-6 py-5">
        <div className="text-xs uppercase tracking-wider text-neutral-500 mb-3">
          Recent renders
        </div>
        {jobs.length === 0 && (
          <p className="text-xs text-neutral-600">
            No renders yet. Hit <b className="text-neutral-300">Render</b> to
            export the current timeline to a 1080p MP4.
          </p>
        )}
        <ul className="space-y-2">
          {jobs.map((j) => (
            <li
              key={j.id}
              className="rounded-[7px] border p-3"
              style={{ backgroundColor: "#141519", borderColor: "#24262c" }}
            >
              <div className="flex items-center gap-3">
                <Film size={14} className="text-neutral-500 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-neutral-200 truncate">
                    {j.preset_name}
                  </div>
                  <div className="text-[10px] text-neutral-500 truncate">
                    {new Date(j.created_at).toLocaleString()}
                  </div>
                </div>
                <JobStatusBadge job={j} />
                {j.status === "done" && j.output_url && (
                  <a
                    href={origin + j.output_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    download
                    className="flex items-center gap-1 px-2 py-1 text-[10px] uppercase tracking-wider rounded-[5px]"
                    style={{
                      backgroundColor: "var(--color-accent)",
                      color: "#0b0c0e",
                    }}
                  >
                    <Download size={11} />
                    MP4
                  </a>
                )}
              </div>
              {(j.status === "queued" || j.status === "rendering") && (
                <div
                  className="mt-2 h-1 w-full rounded-full overflow-hidden"
                  style={{ backgroundColor: "#24262c" }}
                >
                  <div
                    className="h-full transition-all"
                    style={{
                      width: `${Math.round((j.progress ?? 0) * 100)}%`,
                      backgroundColor: "var(--color-accent)",
                    }}
                  />
                </div>
              )}
              {j.status === "failed" && j.error_message && (
                <p className="mt-2 text-[10px] text-red-300 whitespace-pre-wrap break-words">
                  {j.error_message}
                </p>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function JobStatusBadge({ job }: { job: RenderJob }) {
  const label: Record<RenderJob["status"], string> = {
    queued: "queued",
    rendering: `${Math.round((job.progress ?? 0) * 100)}%`,
    done: "ready",
    failed: "failed",
  };
  const color: Record<RenderJob["status"], string> = {
    queued: "#a3a3a3",
    rendering: "var(--color-accent)",
    done: "var(--color-accent)",
    failed: "#ef4444",
  };
  return (
    <span
      className="text-[10px] uppercase tracking-wider tabular-nums"
      style={{ color: color[job.status] }}
    >
      {label[job.status]}
    </span>
  );
}
