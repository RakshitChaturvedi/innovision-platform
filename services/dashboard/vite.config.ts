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
      "/auth":          "http://localhost:80",
      "/cameras":       "http://localhost:80",
      "/alerts":        "http://localhost:80",
      "/incidents":     "http://localhost:80",
      "/audit":         "http://localhost:80",
      "/notifications": "http://localhost:80",
      "/ingestion":      "http://localhost:80",
      "/uc3": "http://localhost:80",
    },
  },
});