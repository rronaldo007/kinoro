import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Film, Image as ImageIcon, Music, Plus, Loader2, AlertTriangle, Trash2 } from "lucide-react";
import {
  createMedia,
  deleteMedia,
  listMedia,
  type MediaAsset,
} from "../../api/media";

interface Props {
  variant?: "grid" | "list";
}

export default function MediaPool({ variant = "grid" }: Props) {
  const qc = useQueryClient();

  const assetsQ = useQuery({
    queryKey: ["media"],
    queryFn: listMedia,
    // Poll while anything is still ingesting so the UI flips to "ready".
    refetchInterval: (q) => {
      const data = q.state.data as MediaAsset[] | undefined;
      return data?.some((a) => a.status === "ingesting") ? 1000 : false;
    },
  });

  const add = useMutation({
    mutationFn: createMedia,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["media"] }),
  });

  const del = useMutation({
    mutationFn: deleteMedia,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["media"] }),
  });

  async function pickAndAdd() {
    const kinoro = window.kinoro;
    if (!kinoro) return;
    const res = (await kinoro.openFiles({
      title: "Add media",
      properties: ["openFile", "multiSelections"],
      filters: [
        {
          name: "Media",
          extensions: [
            "mp4", "mov", "mkv", "webm", "avi",
            "mp3", "wav", "flac", "aac", "m4a",
            "jpg", "jpeg", "png", "webp",
          ],
        },
      ],
    })) as { canceled: boolean; filePaths: string[] };
    if (res.canceled) return;
    for (const p of res.filePaths) {
      add.mutate(p);
    }
  }

  const assets = assetsQ.data ?? [];
  const apiPort = window.kinoro?.apiPort;
  const thumbBase = apiPort ? `http://127.0.0.1:${apiPort}` : "";

  const isList = variant === "list";

  return (
    <div
      className={
        isList
          ? "flex flex-col h-full"
          : "min-w-[380px] max-w-[920px] w-full rounded-[9px] p-5 border"
      }
      style={
        isList
          ? undefined
          : { backgroundColor: "#141519", borderColor: "#24262c" }
      }
    >
      <div
        className={
          isList
            ? "flex items-center justify-between px-3 py-2.5 border-b"
            : "flex items-center justify-between mb-4"
        }
        style={isList ? { borderColor: "#24262c" } : undefined}
      >
        <div className="text-xs uppercase tracking-wider text-neutral-500">
          Media pool
        </div>
        <button
          type="button"
          onClick={pickAndAdd}
          disabled={!window.kinoro}
          className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-[7px] active:scale-[0.98] disabled:opacity-40"
          style={{ backgroundColor: "var(--color-accent)", color: "#0b0c0e" }}
        >
          <Plus size={12} />
          Add
        </button>
      </div>

      {assets.length === 0 && !assetsQ.isLoading && (
        <p className={isList ? "text-xs text-neutral-500 p-3" : "text-xs text-neutral-500"}>
          No media yet. Click <b className="text-neutral-300">Add</b> to pick
          video, audio, or image files from disk.
        </p>
      )}

      {assets.length > 0 && isList && (
        <div className="flex-1 overflow-y-auto py-1">
          {assets.map((a) => (
            <AssetRow
              key={a.id}
              asset={a}
              thumbBase={thumbBase}
              onDelete={() => del.mutate(a.id)}
            />
          ))}
        </div>
      )}

      {assets.length > 0 && !isList && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-3">
          {assets.map((a) => (
            <AssetCard
              key={a.id}
              asset={a}
              thumbBase={thumbBase}
              onDelete={() => del.mutate(a.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function pickIcon(kind: string) {
  if (kind === "audio") return Music;
  if (kind === "image") return ImageIcon;
  return Film;
}

function AssetRow({
  asset,
  thumbBase,
  onDelete,
}: {
  asset: MediaAsset;
  thumbBase: string;
  onDelete: () => void;
}) {
  const Icon = pickIcon(asset.kind);
  const thumb = asset.thumbnail_url ? thumbBase + asset.thumbnail_url : null;

  const draggable = asset.status === "ready";

  function handleDragStart(e: React.DragEvent<HTMLDivElement>) {
    if (!draggable) return;
    const payload = JSON.stringify({
      id: asset.id,
      name: asset.name,
      kind: asset.kind,
      duration: asset.duration ?? 5,
    });
    e.dataTransfer.setData("application/x-kinoro-asset", payload);
    e.dataTransfer.effectAllowed = "copy";
  }

  return (
    <div
      draggable={draggable}
      onDragStart={handleDragStart}
      className={`group flex items-center gap-2 px-3 py-1.5 hover:bg-white/5 ${draggable ? "cursor-grab active:cursor-grabbing" : "cursor-default"}`}
    >
      <div
        className="shrink-0 w-16 h-9 rounded-[5px] overflow-hidden flex items-center justify-center"
        style={{ backgroundColor: "#0b0c0e", border: "1px solid #24262c" }}
      >
        {asset.status === "ingesting" && (
          <Loader2
            size={14}
            className="animate-spin"
            style={{ color: "var(--color-accent)" }}
          />
        )}
        {asset.status === "failed" && (
          <AlertTriangle size={14} className="text-red-400" />
        )}
        {asset.status === "ready" &&
          (thumb ? (
            <img src={thumb} alt="" className="w-full h-full object-cover" loading="lazy" />
          ) : (
            <Icon size={14} className="text-neutral-500" />
          ))}
      </div>
      <div className="min-w-0 flex-1">
        <div
          className="text-xs truncate text-neutral-200"
          title={asset.name}
        >
          {asset.name}
        </div>
        <div className="text-[10px] text-neutral-500 flex items-center gap-1.5">
          {asset.status === "ingesting" && <span>ingesting…</span>}
          {asset.status === "ready" && (
            <>
              <span>{asset.kind}</span>
              {asset.duration != null && asset.duration > 0 && (
                <>
                  <span>·</span>
                  <span>{formatDuration(asset.duration)}</span>
                </>
              )}
            </>
          )}
          {asset.status === "failed" && (
            <span className="text-red-300 truncate" title={asset.error_message}>
              failed
            </span>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={onDelete}
        className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-[5px]"
        aria-label="Delete"
        title="Delete"
      >
        <Trash2 size={12} className="text-neutral-400 hover:text-red-400" />
      </button>
    </div>
  );
}

function AssetCard({
  asset,
  thumbBase,
  onDelete,
}: {
  asset: MediaAsset;
  thumbBase: string;
  onDelete: () => void;
}) {
  const Icon = pickIcon(asset.kind);
  const thumb = asset.thumbnail_url ? thumbBase + asset.thumbnail_url : null;

  return (
    <div
      className="relative group rounded-[7px] overflow-hidden border"
      style={{ backgroundColor: "#0b0c0e", borderColor: "#24262c" }}
    >
      <div
        className="aspect-video flex items-center justify-center"
        style={{ backgroundColor: "#0b0c0e" }}
      >
        {asset.status === "ingesting" && (
          <Loader2
            size={20}
            className="animate-spin"
            style={{ color: "var(--color-accent)" }}
          />
        )}
        {asset.status === "failed" && (
          <AlertTriangle size={20} className="text-red-400" />
        )}
        {asset.status === "ready" &&
          (thumb ? (
            <img
              src={thumb}
              alt=""
              className="w-full h-full object-cover"
              loading="lazy"
            />
          ) : (
            <Icon size={22} className="text-neutral-500" />
          ))}
      </div>

      <div className="px-2 py-1.5">
        <div
          className="text-xs truncate text-neutral-200"
          title={asset.name}
        >
          {asset.name}
        </div>
        <div className="text-[10px] text-neutral-500 mt-0.5 flex items-center gap-1.5">
          {asset.status === "ingesting" && <span>ingesting…</span>}
          {asset.status === "ready" && (
            <>
              <span>{asset.kind}</span>
              {asset.duration != null && asset.duration > 0 && (
                <>
                  <span>·</span>
                  <span>{formatDuration(asset.duration)}</span>
                </>
              )}
            </>
          )}
          {asset.status === "failed" && (
            <span
              className="text-red-300 truncate"
              title={asset.error_message}
            >
              failed
            </span>
          )}
        </div>
      </div>

      <button
        type="button"
        onClick={onDelete}
        className="absolute top-1 right-1 p-1 rounded-[5px] opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ backgroundColor: "rgba(0,0,0,0.7)" }}
        aria-label="Delete"
      >
        <Trash2 size={12} className="text-neutral-300" />
      </button>
    </div>
  );
}

function formatDuration(s: number): string {
  const total = Math.round(s);
  const m = Math.floor(total / 60);
  const sec = total % 60;
  return `${m}:${String(sec).padStart(2, "0")}`;
}
