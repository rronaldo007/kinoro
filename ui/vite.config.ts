import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Base './' so the built index.html works when Electron loads it via file://.
//
// strictPort is required because Electron main (app/src/main.ts:loadURL)
// hard-codes http://localhost:5174. If Vite silently fell back to 5175,
// Electron would load nothing. `./scripts/start.sh` waits for 5174 to bind
// before launching Electron so the failure is surfaced loudly.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    port: 5174,
    strictPort: true,
    host: "127.0.0.1",
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
