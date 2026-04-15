import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";

interface HealthResponse {
  status: string;
  version: string;
  milestone: string;
  platform: string;
  ffmpeg_on_path: boolean;
  ffprobe_on_path: boolean;
}

export default function SidecarStatus() {
  const { data, isLoading, isError } = useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: async () => (await api.get("/api/health/")).data,
    refetchInterval: 2000,
  });

  return (
    <div
      className="rounded-[9px] p-4 border min-w-[320px]"
      style={{ backgroundColor: "#141519", borderColor: "#24262c" }}
    >
      <div className="text-xs uppercase tracking-wider text-neutral-500 mb-3">
        Sidecar
      </div>
      {isLoading && <div className="text-sm text-neutral-400">Connecting…</div>}
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
    <div className="flex items-center justify-between gap-4">
      <span className="text-neutral-500 shrink-0">{label}</span>
      <span
        className={`text-right truncate ${
          ok === false ? "text-red-400" : "text-neutral-200"
        }`}
      >
        {value}
      </span>
    </div>
  );
}
