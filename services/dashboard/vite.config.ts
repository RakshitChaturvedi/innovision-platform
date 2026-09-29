import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/auth":      "http://localhost:8000",
      "/cameras":   "http://localhost:8011",
      "/alerts":    "http://localhost:8010",
      "/incidents": "http://localhost:8003",
      "/reports":   "http://localhost:8016",
      "/audit":     "http://localhost:8002",
    },
  },
});