import { app, BrowserWindow, dialog, ipcMain } from "electron";
import * as path from "node:path";
import { buildMenu } from "./menu";
import { startSidecar, stopSidecar, SidecarHandle } from "./sidecar";

const isDev = !app.isPackaged;
let mainWindow: BrowserWindow | null = null;
let sidecar: SidecarHandle | null = null;

/**
 * kinoro:// deep link — handed off from Video Planner's "Open in Editor"
 * button. Shape: `kinoro://open?base_url=<encoded>&project_id=<uuid>`.
 * Parsed out of:
 *   - process.argv on initial launch (Linux/Windows)
 *   - `open-url` event (macOS)
 *   - `second-instance` event (Linux/Windows, when Kinoro is already running)
 * Always stored here; the renderer pulls it on mount + on live events.
 */
let pendingDeepLink: string | null = null;

function extractDeepLink(argv: readonly string[]): string | null {
  for (const a of argv) {
    if (a.startsWith("kinoro://")) return a;
  }
  return null;
}

function broadcastDeepLink(url: string): void {
  pendingDeepLink = url;
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("kinoro:openUrl", url);
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
}

// Register as the default handler for kinoro:// — persistent registration on
// all three OSes. In dev on Linux the registration uses the current binary
// (electron itself), so it only works while the dev process is running.
if (process.defaultApp) {
  if (process.argv.length >= 2) {
    app.setAsDefaultProtocolClient("kinoro", process.execPath, [
      path.resolve(process.argv[1]),
    ]);
  }
} else {
  app.setAsDefaultProtocolClient("kinoro");
}

// Single-instance lock — essential for protocol handoff: a second launch
// from the browser should reach the running instance, not spawn a new one.
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on("second-instance", (_evt, argv) => {
    const url = extractDeepLink(argv);
    if (url) broadcastDeepLink(url);
    else if (mainWindow && !mainWindow.isDestroyed()) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

// macOS delivers the URL via the `open-url` event (not argv).
app.on("open-url", (event, url) => {
  event.preventDefault();
  broadcastDeepLink(url);
});

async function createWindow(sidecarPort: number): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 1200,
    minHeight: 720,
    backgroundColor: "#0b0c0e",
    title: "Kinoro",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      additionalArguments: [`--sidecar-port=${sidecarPort}`],
    },
  });

  buildMenu(mainWindow);

  if (isDev) {
    await mainWindow.loadURL("http://localhost:5174");
    mainWindow.webContents.openDevTools({ mode: "right" });
  } else {
    await mainWindow.loadFile(
      path.join(process.resourcesPath, "ui", "index.html"),
    );
  }

  // Flush any deep link that arrived before the window existed.
  mainWindow.webContents.once("did-finish-load", () => {
    if (pendingDeepLink && mainWindow) {
      mainWindow.webContents.send("kinoro:openUrl", pendingDeepLink);
    }
  });
}

ipcMain.handle("dialog:openFiles", async (_evt, opts: Electron.OpenDialogOptions) => {
  if (!mainWindow) return { canceled: true, filePaths: [] };
  return dialog.showOpenDialog(mainWindow, opts);
});

ipcMain.handle("dialog:saveAs", async (_evt, opts: Electron.SaveDialogOptions) => {
  if (!mainWindow) return { canceled: true, filePath: undefined };
  return dialog.showSaveDialog(mainWindow, opts);
});

// Let the renderer synchronously pull the pending deep link on mount — useful
// when Kinoro was cold-started by clicking the browser link.
ipcMain.handle("kinoro:getPendingUrl", () => pendingDeepLink);

app.whenReady().then(async () => {
  // Initial-launch argv carries the URL on Linux/Windows.
  const initial = extractDeepLink(process.argv);
  if (initial) pendingDeepLink = initial;

  const serverDir = isDev
    ? path.join(__dirname, "..", "..", "server")
    : path.join(process.resourcesPath, "server");

  sidecar = await startSidecar({ serverDir });
  await createWindow(sidecar.port);

  app.on("activate", async () => {
    if (BrowserWindow.getAllWindows().length === 0 && sidecar) {
      await createWindow(sidecar.port);
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", async () => {
  if (sidecar) {
    await stopSidecar(sidecar);
    sidecar = null;
  }
});
