import axios, { AxiosError } from "axios";
import type { ApiErrorBody } from "@/types";

export const TOKEN_STORAGE_KEY = "schedai_access_token";

// VITE_API_URL points straight at the FastAPI backend (see .env). When it's
// unset, requests fall back to relative paths, which the Vite dev proxy
// (vite.config.ts) forwards to http://localhost:8000 during `npm run dev`.
const baseURL = import.meta.env.VITE_API_URL ?? "";

export const api = axios.create({ baseURL });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// A 401 from the backend always means "invalid or expired token" (see
// app/auth/dependencies.py) — there is no refresh-token flow in this
// backend, so the correct client behavior is to drop the token and send
// the user back to /login.
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

/** Extracts a human-readable message from FastAPI's {"detail": ...} error shape. */
export function getApiErrorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as ApiErrorBody | undefined;
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail) && body.detail.length > 0) {
      return body.detail.map((d) => d.msg).join(" ");
    }
    if (error.message) return error.message;
  }
  return fallback;
}
