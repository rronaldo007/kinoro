import { useQuery } from "@tanstack/react-query";
import { Film } from "lucide-react";
import { api } from "./api/client";

interface HealthResponse {
  status: string;
  version: string;
  milestone: string;
  platform: string;
  ffmpeg_on_path: boolean;
  ffprobe_on_path: boolean;
}

export default function App() {
  const { data, isLoading, isError } = useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: async () => (await api.get("/api/health/")).data,
    refetchInterval: 2000,
  });

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center text-neutral-100 font-sans"
      style={{ backgroundColor: "#0b0c0e" }}
    >
      <div className="flex items-center gap-3 mb-6">
        <div
          className="w-12 h-12 rounded-[9px] flex items-center justify-center"
          style={{ backgroundColor: "var(--color-accent)" }}
        >
          <Film size={26} color="#0b0c0e" strokeWidth={2.5} />
        </div>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Kinoro</h1>
          <p className="text-xs text-neutral-500 tracking-wide uppercase">
            Desktop video editor · M0
          </p>
        </div>
      </div>

      <div
        className="min-w-[380px] rounded-[9px] p-5 border"
        style={{
          backgroundColor: "#141519",
          borderColor: "#24262c",
        }}
      >
        <div className="text-xs uppercase tracking-wider text-neutral-500 mb-3">
          Sidecar
        </div>
        {isLoading && (
          <div className="text-sm text-neutral-400">Connecting…</div>
        )}
        {isError && (
          <div className="text-sm text-red-400">
            Sidecar unreachable. Is Django running on port{" "}
            {window.kinoro?.apiPort ?? "(unknown)"}?
          </div>
        )}
        {data && (
          <div className="text-sm space-y-1.5">
            <Row label="Status" value={data.status} ok />
            <Row label="Version" value={data.version} />
            <Row label="Milestone" value={data.milestone} />
            <Row label="Platform" value={data.platform} />
            <Row
              label="ffmpeg"
              value={data.ffmpeg_on_path ? "on PATH" : "missing"}
              ok={data.ffmpeg_on_path}
            />
            <Row
              label="ffprobe"
              value={data.ffprobe_on_path ? "on PATH" : "missing"}
              ok={data.ffprobe_on_path}
            />
          </div>
        )}
      </div>

      <div className="mt-8 text-xs text-neutral-600 max-w-md text-center leading-relaxed">
        Kinoro is a standalone desktop editor and an extension of Video Planner.
        Import your Video Planner projects via File → Import from Video Planner
        (wired in M1).
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  ok,
}: {
  label: string;
  value: string;
  ok?: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-neutral-500">{label}</span>
      <span className={ok === false ? "text-red-400" : "text-neutral-200"}>
        {value}
      </span>
    </div>
  );
}
