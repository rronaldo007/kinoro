import { api } from "./client";

export interface TimelineTrack {
  id: string;
  kind: "video" | "audio";
  index: number;
  name: string;
}

export interface TimelineClip {
  id: string;
  track_id: string;
  asset_id: string;
  start_seconds: number;
  in_seconds: number;
  out_seconds: number;
  speed?: number;
}

export interface TimelineJson {
  tracks?: TimelineTrack[];
  clips?: TimelineClip[];
  // Forward-compatible bag for future keys (text clips, transitions, …).
  [k: string]: unknown;
}

export interface KinoroProject {
  id: string;
  name: string;
  fps: number;
  width: number;
  height: number;
  timeline_json: TimelineJson;
  render_settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export async function listProjects(): Promise<KinoroProject[]> {
  const r = await api.get("/api/projects/");
  const d = r.data;
  return Array.isArray(d) ? d : (d.results ?? []);
}

export async function getProject(id: string): Promise<KinoroProject> {
  return (await api.get(`/api/projects/${id}/`)).data;
}

export async function createProject(body: {
  name: string;
  fps?: number;
  width?: number;
  height?: number;
}): Promise<KinoroProject> {
  return (await api.post("/api/projects/", body)).data;
}

export async function updateProject(
  id: string,
  patch: Partial<Pick<KinoroProject, "name" | "fps" | "width" | "height" | "timeline_json" | "render_settings">>,
): Promise<KinoroProject> {
  return (await api.patch(`/api/projects/${id}/`, patch)).data;
}
