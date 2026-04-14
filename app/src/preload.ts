import { contextBridge, ipcRenderer, IpcRendererEvent } from "electron";

function parseSidecarPort(): number {
  const arg = process.argv.find((a) => a.startsWith("--sidecar-port="));
  if (!arg) return 0;
  const v = Number(arg.split("=")[1]);
  return Number.isFinite(v) && v > 0 ? v : 0;
}

type OpenUrlHandler = (url: string) => void;

contextBridge.exposeInMainWorld("kinoro", {
  apiPort: parseSidecarPort(),
  platform: process.platform, // 'linux' | 'darwin' | 'win32'

  openFiles: (opts: Electron.OpenDialogOptions) =>
    ipcRenderer.invoke("dialog:openFiles", opts),

  saveAs: (opts: Electron.SaveDialogOptions) =>
    ipcRenderer.invoke("dialog:saveAs", opts),

  /**
   * Kinoro was cold-started with a kinoro:// URL — returns it, else null.
   * Call once on mount to pick up the handoff from a fresh launch.
   */
  getPendingOpenUrl: (): Promise<string | null> =>
    ipcRenderer.invoke("kinoro:getPendingUrl"),

  /**
   * Subscribe to kinoro:// URLs that arrive after the window exists (macOS
   * `open-url` or a second-instance launch). Returns an unsubscribe fn.
   */
  onOpenUrl: (handler: OpenUrlHandler): (() => void) => {
    const listener = (_e: IpcRendererEvent, url: string) => handler(url);
    ipcRenderer.on("kinoro:openUrl", listener);
    return () => ipcRenderer.removeListener("kinoro:openUrl", listener);
  },
});

export {};
