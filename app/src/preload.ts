import { contextBridge, ipcRenderer } from "electron";

function parseSidecarPort(): number {
  const arg = process.argv.find((a) => a.startsWith("--sidecar-port="));
  if (!arg) return 0;
  const v = Number(arg.split("=")[1]);
  return Number.isFinite(v) && v > 0 ? v : 0;
}

contextBridge.exposeInMainWorld("kinoro", {
  apiPort: parseSidecarPort(),
  platform: process.platform, // 'linux' | 'darwin' | 'win32'

  openFiles: (opts: Electron.OpenDialogOptions) =>
    ipcRenderer.invoke("dialog:openFiles", opts),

  saveAs: (opts: Electron.SaveDialogOptions) =>
    ipcRenderer.invoke("dialog:saveAs", opts),
});

export {};
