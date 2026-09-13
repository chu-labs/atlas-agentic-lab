import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      "/api": "http://localhost:8767",
      "/health": "http://localhost:8767",
      "/ws": { target: "ws://localhost:8767", ws: true },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
