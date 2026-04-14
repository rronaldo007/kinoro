import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, LogOut } from "lucide-react";
import {
  getVpAccount,
  getVpProject,
  vpLogout,
  type VPAccount,
} from "../../api/importVp";
import LoginModal from "./LoginModal";

export interface IncomingOpen {
  baseUrl: string;
  projectId: string;
  rawUrl: string;
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

  const projectQ = useQuery({
    queryKey: ["vp-project", incoming.projectId],
    queryFn: () => getVpProject(incoming.projectId),
    enabled: !!accountQ.data,
    retry: false,
  });

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

      {accountQ.data && projectQ.data && (
        <p className="mt-3 text-xs text-neutral-500">
          Connected. Media download + proxy build lands in the next slice of M1.
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
