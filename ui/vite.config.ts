import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Base './' so the built index.html works when Electron loads it via file://.
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
