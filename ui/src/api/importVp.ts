import { api } from "./client";

export interface VPUserPayload {
  id?: string;
  email?: string;
  first_name?: string;
  last_name?: string;
  name?: string;
  [k: string]: unknown;
}

export interface VPAccount {
  id: string;
  base_url: string;
  email: string;
  user_payload: VPUserPayload;
  created_at: string;
}

export interface VPProjectSummary {
  id: string;
  name?: string;
  title?: string;
  description?: string;
  updated_at?: string;
  [k: string]: unknown;
}

export interface VPProjectDetail {
  project: VPProjectSummary;
  resources: Array<Record<string, unknown>>;
}

export async function vpLogin(body: {
  base_url: string;
  email: string;
  password: string;
}): Promise<VPAccount> {
  return (await api.post("/api/import/vp/login/", body)).data;
}

export async function vpLogout(): Promise<void> {
  await api.post("/api/import/vp/logout/");
}

export async function getVpAccount(): Promise<VPAccount | null> {
  try {
    const r = await api.get("/api/import/vp/account/");
    return r.data;
  } catch (e: unknown) {
    const status =
      typeof e === "object" && e !== null && "response" in e
        ? (e as { response?: { status?: number } }).response?.status
        : undefined;
    if (status === 404) return null;
    throw e;
  }
}

export async function listVpProjects(): Promise<VPProjectSummary[]> {
  return (await api.get("/api/import/vp/projects/")).data;
}

export async function getVpProject(id: string): Promise<VPProjectDetail> {
  return (await api.get(`/api/import/vp/projects/${id}/`)).data;
}
