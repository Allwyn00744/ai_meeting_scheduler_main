import axios, { AxiosError } from "axios";
import type { ApiErrorBody } from "@/types";

declare module "axios" {
  export interface InternalAxiosRequestConfig {
    /** Internal one-shot guard so the 401-retry-with-auth-header logic below never loops. */
    __authRetried?: boolean;
  }
}

export const TOKEN_STORAGE_KEY = "schedai_access_token";

// VITE_API_URL points straight at the FastAPI backend (see .env). When it's
// unset, requests fall back to relative paths, which the Vite dev proxy
// (vite.config.ts) forwards to http://localhost:8000 during `npm run dev`.
const baseURL = import.meta.env.VITE_API_URL ?? "";

export const api = axios.create({ baseURL });

function attachAuthHeader(config: import("axios").InternalAxiosRequestConfig) {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}

api.interceptors.request.use(attachAuthHeader);

// A 401 from the backend usually means "invalid or expired token" (see
// app/auth/dependencies.py) - there is no refresh-token flow in this
// backend, so the normal client behavior is to drop the token and send
// the user back to /login.
//
// One deliberate exception: if the request that got the 401 didn't
// actually carry an Authorization header even though a token exists in
// localStorage, that 401 doesn't prove the token is bad - it proves
// this one request didn't pick it up (seen in practice on a hard
// reload straight into a protected route). Retrying that request once,
// now with the header explicitly attached, resolves it without
// punishing a perfectly valid session. Only a 401 on a request that
// truly had the header (or has no token to attach) means the session
// itself is invalid.
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config;
    const status = error.response?.status;
    const hadAuthHeader = Boolean(config?.headers?.Authorization);
    const token = localStorage.getItem(TOKEN_STORAGE_KEY);

    if (status === 401 && config && token && !hadAuthHeader && !config.__authRetried) {
      config.__authRetried = true;
      return api.request(attachAuthHeader(config as import("axios").InternalAxiosRequestConfig));
    }

    if (status === 401) {
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
