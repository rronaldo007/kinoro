import { api } from "./client";

export type MediaKind = "video" | "audio" | "image" | "unknown";
export type MediaStatus = "ingesting" | "ready" | "failed";
export type ProxyStatus = "pending" | "building" | "ready" | "failed" | "skipped";

export interface MediaAsset {
  id: string;
  name: string;
  source_path: string;
  kind: MediaKind;
  status: MediaStatus;
  duration: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  size_bytes: number | null;
  thumbnail_path: string;
  thumbnail_url: string | null;
  proxy_path: string;
  proxy_status: ProxyStatus;
  proxy_url: string | null;
  error_message: string;
  created_at: string;
  updated_at: string;
}

export async function listMedia(): Promise<MediaAsset[]> {
  const r = await api.get("/api/media/");
  const d = r.data;
  return Array.isArray(d) ? d : d.results ?? [];
}

export async function createMedia(sourcePath: string): Promise<MediaAsset> {
  return (await api.post("/api/media/", { source_path: sourcePath })).data;
}

export async function deleteMedia(id: string): Promise<void> {
  await api.delete(`/api/media/${id}/`);
}
