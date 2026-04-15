import { api } from "./client";

export type RenderStatus = "queued" | "rendering" | "done" | "failed";

export interface RenderJob {
  id: string;
  project: string;
  preset_name: string;
  status: RenderStatus;
  progress: number;
  output_path: string;
  output_url: string | null;
  error_message: string;
  created_at: string;
  updated_at: string;
}

export async function listRenderJobs(): Promise<RenderJob[]> {
  const r = await api.get("/api/render/");
  const d = r.data;
  return Array.isArray(d) ? d : (d.results ?? []);
}

export async function getRenderJob(id: string): Promise<RenderJob> {
  return (await api.get(`/api/render/${id}/`)).data;
}

export async function startRender(body: {
  project: string;
  preset_name?: string;
}): Promise<RenderJob> {
  return (await api.post("/api/render/", body)).data;
}
