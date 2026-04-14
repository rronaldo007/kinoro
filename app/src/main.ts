import { app, BrowserWindow, dialog, ipcMain } from "electron";
import * as path from "node:path";
import { buildMenu } from "./menu";
import { startSidecar, stopSidecar, SidecarHandle } from "./sidecar";

const isDev = !app.isPackaged;
let mainWindow: BrowserWindow | null = null;
let sidecar: SidecarHandle | null = null;

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
    await mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools({ mode: "right" });
  } else {
    // In packaged builds the renderer lives at resources/ui/index.html.
    await mainWindow.loadFile(
      path.join(process.resourcesPath, "ui", "index.html"),
    );
  }
}

ipcMain.handle("dialog:openFiles", async (_evt, opts: Electron.OpenDialogOptions) => {
  if (!mainWindow) return { canceled: true, filePaths: [] };
  return dialog.showOpenDialog(mainWindow, opts);
});

ipcMain.handle("dialog:saveAs", async (_evt, opts: Electron.SaveDialogOptions) => {
  if (!mainWindow) return { canceled: true, filePath: undefined };
  return dialog.showSaveDialog(mainWindow, opts);
});

app.whenReady().then(async () => {
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
