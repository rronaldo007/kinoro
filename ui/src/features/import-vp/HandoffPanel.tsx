import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, ExternalLink, LogOut } from "lucide-react";
import {
  getVpAccount,
  getVpImportJob,
  getVpProject,
  startVpProjectImport,
  vpAdoptTokens,
  vpLogout,
  type VPAccount,
  type VpImportJob,
  type VpImportJobStarted,
} from "../../api/importVp";
import LoginModal from "./LoginModal";

export interface IncomingOpen {
  baseUrl: string;
  projectId: string;
  rawUrl: string;
  access?: string;
  refresh?: string;
}

interface Props {
  incoming: IncomingOpen;
}

export default function HandoffPanel({ incoming }: Props) {
  const qc = useQueryClient();
  const [showLogin, setShowLogin] = useState(false);

  const accountQ = useQuery<VPAccount | null>({
    queryKey: ["vp-account"],
    queryFn: getVpAccount,
  });

  const logout = useMutation({
    mutationFn: vpLogout,
    onSuccess: () => qc.setQueryData(["vp-account"], null),
  });

  const adopt = useMutation({
    mutationFn: vpAdoptTokens,
    onSuccess: (acc) => {
      qc.setQueryData(["vp-account"], acc);
      qc.invalidateQueries({ queryKey: ["vp-account"] });
    },
  });

  // Auto-adopt handoff tokens whenever the URL carries a fresh access JWT.
  // Key the dedupe ref on the access-token value itself so a NEW handoff
  // (browser→Kinoro with a different token) overwrites any stale local
  // VPAccount from a previous session. The backend adopt endpoint is
  // idempotent (delete-then-create), so re-invoking is safe.
  const lastAdoptedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!incoming.access) return;
    if (!accountQ.isSuccess) return;
    if (lastAdoptedRef.current === incoming.access) return;
    lastAdoptedRef.current = incoming.access;
    adopt.mutate({
      base_url: incoming.baseUrl,
      access: incoming.access,
      refresh: incoming.refresh,
    });
  }, [incoming.access, incoming.baseUrl, incoming.refresh, accountQ.isSuccess, adopt]);

  const [jobId, setJobId] = useState<string | null>(null);

  const importMedia = useMutation<VpImportJobStarted>({
    mutationFn: () => startVpProjectImport(incoming.projectId),
    onSuccess: (job) => {
      setJobId(job.id);
      qc.invalidateQueries({ queryKey: ["media"] });
    },
  });

  const jobQ = useQuery<VpImportJob>({
    queryKey: ["vp-import-job", jobId],
    queryFn: () => getVpImportJob(jobId!),
    enabled: !!jobId,
    // Poll fast while the job is running; stop once it's terminal.
    refetchInterval: (q) => {
      const s = (q.state.data as VpImportJob | undefined)?.status;
      return s === "done" || s === "failed" ? false : 1000;
    },
  });

  // Keep the media pool query fresh while the job is running so new
  // MediaAssets appear in the left pane as each download completes. The
  // useEffect also fires once on terminal transition so the last row that
  // got created between polls doesn't miss its final render.
  if (jobId && jobQ.data && jobQ.data.status !== "done" && jobQ.data.status !== "failed") {
    void qc.invalidateQueries({ queryKey: ["media"] });
  }
  const jobStatus = jobQ.data?.status;
  useEffect(() => {
    if (jobStatus === "done" || jobStatus === "failed") {
      void qc.invalidateQueries({ queryKey: ["media"] });
    }
  }, [jobStatus, qc]);

  const projectQ = useQuery({
    queryKey: ["vp-project", incoming.projectId],
    queryFn: () => getVpProject(incoming.projectId),
    enabled: !!accountQ.data,
    retry: false,
  });

  // Auto-start the import once the handoff is fully resolved. Dedupe per
  // projectId so re-renders don't re-kick; if the user wants to re-import
  // after a failure, they can still click the visible button.
  const autoImportedRef = useRef<string | null>(null);
  useEffect(() => {
    if (autoImportedRef.current === incoming.projectId) return;
    if (jobId) return;
    if (!accountQ.data) return;
    const count = projectQ.data?.resources.length ?? 0;
    if (count === 0) return;
    autoImportedRef.current = incoming.projectId;
    importMedia.mutate();
  }, [incoming.projectId, accountQ.data, projectQ.data, jobId, importMedia]);

  // If the server says 401, the account is stale — clear it so the user re-logs.
  const projectErrStatus =
    projectQ.error && typeof projectQ.error === "object" && "response" in projectQ.error
      ? (projectQ.error as { response?: { status?: number } }).response?.status
      : undefined;
  const projectErrDetail =
    projectQ.error && typeof projectQ.error === "object" && "response" in projectQ.error
      ? (projectQ.error as { response?: { data?: { detail?: string } } }).response?.data?.detail
      : undefined;

  const title =
    projectQ.data?.project.name ??
    projectQ.data?.project.title ??
    incoming.projectId;
  const resourceCount = projectQ.data?.resources.length ?? 0;

  // Default the login base_url to the origin Video Planner's frontend sits on
  // but swap 5173 → 8000 since we need the backend API URL, not the UI URL.
  const suggestedBase = (() => {
    try {
      const u = new URL(incoming.baseUrl);
      if (u.port === "5173") u.port = "8000";
      return u.origin;
    } catch {
      return "http://localhost:8000";
    }
  })();

  return (
    <div
      className="min-w-[380px] max-w-[560px] rounded-[9px] p-5 mb-4 border"
      style={{ backgroundColor: "#0f2620", borderColor: "var(--color-accent)" }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <ExternalLink size={14} style={{ color: "var(--color-accent)" }} />
          <span
            className="text-xs uppercase tracking-wider"
            style={{ color: "var(--color-accent)" }}
          >
            Incoming handoff
          </span>
        </div>
        {accountQ.data && (
          <button
            type="button"
            onClick={() => logout.mutate()}
            className="flex items-center gap-1 text-xs text-neutral-400 hover:text-neutral-200 rounded-[5px] px-1 py-0.5"
            title="Log out of Video Planner"
          >
            <LogOut size={12} />
            {accountQ.data.email}
          </button>
        )}
      </div>

      <div className="text-sm space-y-1.5">
        <Row label="From" value={incoming.baseUrl} />
        <Row label="Project" value={title} />
        {accountQ.data && projectQ.data && (
          <Row label="Resources" value={String(resourceCount)} />
        )}
      </div>

      {!accountQ.isLoading && !accountQ.data && (
        <div className="mt-4 flex items-center justify-between gap-3">
          <p className="text-xs text-neutral-400">
            Log in to Video Planner to pull this project in.
          </p>
          <button
            type="button"
            onClick={() => setShowLogin(true)}
            className="px-3 py-1.5 text-xs font-medium rounded-[7px] active:scale-[0.98]"
            style={{ backgroundColor: "var(--color-accent)", color: "#0b0c0e" }}
          >
            Log in
          </button>
        </div>
      )}

      {accountQ.data && projectQ.isPending && (
        <p className="mt-3 text-xs text-neutral-400">Fetching project…</p>
      )}

      {accountQ.data && projectErrStatus === 401 && (
        <div className="mt-3 flex items-center justify-between gap-3">
          <p className="text-xs text-red-300">
            Session expired. Please log in again.
          </p>
          <button
            type="button"
            onClick={() => {
              logout.mutate();
              setShowLogin(true);
            }}
            className="px-3 py-1.5 text-xs rounded-[7px]"
            style={{ backgroundColor: "var(--color-accent)", color: "#0b0c0e" }}
          >
            Log in
          </button>
        </div>
      )}

      {accountQ.data && projectQ.isError && projectErrStatus !== 401 && (
        <p className="mt-3 text-xs text-red-300">
          {projectErrDetail ?? "Could not fetch project from Video Planner."}
        </p>
      )}

      {accountQ.data && projectQ.data && !jobId && (
        <div className="mt-4 flex items-center justify-between gap-3">
          <p className="text-xs text-neutral-500">
            {resourceCount === 0
              ? "No media referenced in this project's timeline yet."
              : "Pull this project's timeline media into your local pool."}
          </p>
          <button
            type="button"
            onClick={() => importMedia.mutate()}
            disabled={importMedia.isPending || resourceCount === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[7px] active:scale-[0.98] disabled:opacity-40"
            style={{ backgroundColor: "var(--color-accent)", color: "#0b0c0e" }}
          >
            <Download size={12} />
            {importMedia.isPending ? "Starting…" : "Import media"}
          </button>
        </div>
      )}

      {jobId && jobQ.data && (
        <JobProgress
          job={jobQ.data}
          assetCount={importMedia.data?.asset_count ?? 0}
          onDismiss={() => setJobId(null)}
        />
      )}

      {importMedia.isError && (
        <p className="mt-2 text-xs text-red-300">
          Import failed — check the sidecar log.
        </p>
      )}

      {showLogin && (
        <LoginModal
          defaultBaseUrl={suggestedBase}
          onClose={() => setShowLogin(false)}
          onSuccess={() => projectQ.refetch()}
        />
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-neutral-500 shrink-0">{label}</span>
      <span className="text-right truncate text-neutral-200">{value}</span>
    </div>
  );
}

function JobProgress({
  job,
  assetCount,
  onDismiss,
}: {
  job: VpImportJob;
  assetCount: number;
  onDismiss: () => void;
}) {
  const pct = Math.round((job.progress ?? 0) * 100);
  const terminal = job.status === "done" || job.status === "failed";
  const label: Record<VpImportJob["status"], string> = {
    queued: "Queued…",
    fetching_project: "Fetching project…",
    downloading_media: `Downloading media (${assetCount} asset${assetCount === 1 ? "" : "s"})`,
    building_proxies: "Building proxies…",
    done: `Done — ${assetCount} asset${assetCount === 1 ? "" : "s"} imported`,
    failed: "Import failed",
  };

  return (
    <div className="mt-4 space-y-2">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span
          className={
            job.status === "failed" ? "text-red-300" : "text-neutral-300"
          }
        >
          {label[job.status]}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-neutral-500 tabular-nums">{pct}%</span>
          {terminal && (
            <button
              type="button"
              onClick={onDismiss}
              className="text-[10px] uppercase tracking-wider text-neutral-500 hover:text-neutral-300"
            >
              Dismiss
            </button>
          )}
        </div>
      </div>
      <div
        className="h-1 w-full rounded-full overflow-hidden"
        style={{ backgroundColor: "#24262c" }}
      >
        <div
          className="h-full transition-all"
          style={{
            width: `${pct}%`,
            backgroundColor:
              job.status === "failed"
                ? "#ef4444"
                : "var(--color-accent)",
          }}
        />
      </div>
      {job.error_message && (
        <p className="text-[10px] text-red-300 whitespace-pre-wrap break-words">
          {job.error_message}
        </p>
      )}
    </div>
  );
}
