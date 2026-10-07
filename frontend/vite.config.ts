import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development the API is reached through the running stack (nginx on :8080),
// so cookies and paths are the same as in production.
const API_TARGET = process.env.API_TARGET ?? "http://127.0.0.1:8080";

export default defineConfig({
  plugins: [react()],
  build: {
    rolldownOptions: {
      output: {
        // Libraries in their own chunk: it changes rarely, so browsers keep it cached across releases
        codeSplitting: { groups: [{ name: (id: string) => (id.includes("node_modules") ? "vendor" : null) }] },
      },
    },
    chunkSizeWarningLimit: 600,
  },
  server: {
    port: 5173,
    proxy: { "/api": { target: API_TARGET, changeOrigin: false } },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test/setup.ts"],
  },
});
