import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      "/api/auth": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api\/auth/, ""),
      },
      "/api/alerts": {
        target: "http://localhost:8010",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api\/alerts/, ""),
      },
      "/api/cameras": {
        target: "http://localhost:8011",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api\/cameras/, ""),
      },
      "/api/uc4": {
        target: "http://localhost:8024",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api\/uc4/, ""),
      },
      "/api/incidents": {
        target: "http://localhost:8003",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api\/incidents/, ""),
      },
      "/socket.io": {
        target: "http://localhost:8010",
        ws: true,
        changeOrigin: true,
      },
    },
  },
});