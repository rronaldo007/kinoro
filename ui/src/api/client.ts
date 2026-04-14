import axios from "axios";

declare global {
  interface Window {
    kinoro?: {
      apiPort: number;
      platform: string;
      openFiles: (opts: unknown) => Promise<unknown>;
      saveAs: (opts: unknown) => Promise<unknown>;
    };
  }
}

/**
 * When running under Electron, the preload script exposes the sidecar port
 * via `window.kinoro.apiPort`. When running under `vite dev` in a plain
 * browser (no Electron), fall back to an explicit port passed via env, or
 * the default Django dev port.
 */
function resolveBaseURL(): string {
  const port = window.kinoro?.apiPort;
  if (port && port > 0) return `http://127.0.0.1:${port}`;
  const envPort = import.meta.env.VITE_KINORO_PORT;
  if (envPort) return `http://127.0.0.1:${envPort}`;
  return "http://127.0.0.1:8000";
}

export const api = axios.create({
  baseURL: resolveBaseURL(),
  timeout: 10_000,
});
