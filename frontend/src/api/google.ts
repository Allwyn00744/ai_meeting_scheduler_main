import { api, TOKEN_STORAGE_KEY } from "./client";
import type { GoogleStatus } from "@/types";

const baseURL = import.meta.env.VITE_API_URL ?? "";

export const googleApi = {
  status: () => api.get<GoogleStatus>("/google/status").then((r) => r.data),

  disconnect: () => api.delete("/google/disconnect").then((r) => r.data),

  /**
   * Full-page redirect to Google's consent screen. This must be a real
   * browser navigation (not an XHR/fetch call), so the JWT is passed as a
   * query param — see the token fallback added to GET /google/login.
   */
  connectRedirectUrl: () => {
    const token = localStorage.getItem(TOKEN_STORAGE_KEY) ?? "";
    return `${baseURL}/google/login?token=${encodeURIComponent(token)}`;
  },
};
