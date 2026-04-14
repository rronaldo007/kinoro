/**
 * Spawns the local Django sidecar and waits for /api/health/ before resolving.
 *
 * Cross-platform: on Linux/macOS we default to `python3`; on Windows we try
 * `python` first. Users can override with KINORO_PYTHON.
 */
import { ChildProcess, spawn } from "node:child_process";
import * as net from "node:net";
import { app } from "electron";
import * as path from "node:path";

export interface SidecarHandle {
  process: ChildProcess;
  port: number;
}

interface StartOptions {
  serverDir: string;
}

function defaultPython(): string {
  if (process.env.KINORO_PYTHON) return process.env.KINORO_PYTHON;
  return process.platform === "win32" ? "python" : "python3";
}

async function findFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const addr = srv.address();
      if (addr && typeof addr === "object") {
        const port = addr.port;
        srv.close(() => resolve(port));
      } else {
        srv.close();
        reject(new Error("Could not obtain a free port"));
      }
    });
  });
}

async function waitForHealth(port: number, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/health/`);
      if (res.status < 500) return;
    } catch {
      /* not ready yet */
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(
    `Kinoro sidecar did not become healthy on port ${port} within ${timeoutMs}ms`,
  );
}

export async function startSidecar(opts: StartOptions): Promise<SidecarHandle> {
  const port = await findFreePort();
  const python = defaultPython();
  const dataDir = path.join(app.getPath("userData"), "data");

  const args = [
    "manage.py",
    "runserver",
    `127.0.0.1:${port}`,
    "--noreload",
    "--skip-checks",
  ];

  const child = spawn(python, args, {
    cwd: opts.serverDir,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: "1",
      DJANGO_SETTINGS_MODULE: "config.settings",
      KINORO_DATA_DIR: dataDir,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  child.stdout?.on("data", (buf) => process.stdout.write(`[sidecar] ${buf}`));
  child.stderr?.on("data", (buf) => process.stderr.write(`[sidecar] ${buf}`));
  child.on("exit", (code, signal) => {
    console.warn(`[sidecar] exited code=${code} signal=${signal}`);
  });

  await waitForHealth(port, 30_000);
  console.log(`[sidecar] healthy on port ${port} (python=${python})`);
  return { process: child, port };
}

export async function stopSidecar(handle: SidecarHandle): Promise<void> {
  if (handle.process.exitCode !== null) return;
  handle.process.kill(process.platform === "win32" ? undefined : "SIGTERM");
  await new Promise<void>((resolve) => {
    const timer = setTimeout(() => {
      handle.process.kill("SIGKILL");
      resolve();
    }, 3000);
    handle.process.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}
