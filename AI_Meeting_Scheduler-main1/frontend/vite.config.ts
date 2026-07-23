import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Dev server proxies /api-prefixed backend calls aren't needed here because
// the FastAPI backend uses unprefixed routes (/auth, /meetings, etc.) — see
// src/api/client.ts, which points straight at VITE_API_URL. The proxy below
// is kept only as a convenience so relative "/auth/..." calls also work
// without CORS during `vite dev` if VITE_API_URL is left unset.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/auth": "http://localhost:8000",
      "/users": "http://localhost:8000",
      "/meetings": "http://localhost:8000",
      "/participants": "http://localhost:8000",
      "/availability": "http://localhost:8000",
      "/resources": "http://localhost:8000",
      "/analytics": "http://localhost:8000",
      "/scheduler": "http://localhost:8000",
      "/email": "http://localhost:8000",
      "/google": "http://localhost:8000",
      "/outlook": "http://localhost:8000",
      "/zoom": "http://localhost:8000",
      "/ai": "http://localhost:8000",
      "/action-items": "http://localhost:8000",
      "/meeting-intelligence": "http://localhost:8000",
    },
  },
});
