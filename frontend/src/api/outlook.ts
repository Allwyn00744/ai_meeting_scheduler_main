import { api } from "./client";
import type { OutlookStatus } from "@/types";

export const outlookApi = {
  status: () => api.get<OutlookStatus>("/outlook/status").then((r) => r.data),

  disconnect: () => api.delete("/outlook/disconnect").then((r) => r.data),

  /**
   * Unlike Google's GET /google/login (a full-page browser navigation,
   * since a redirect can't carry an Authorization header), this is a
   * normal authenticated fetch call — the backend returns the Microsoft
   * consent screen URL as JSON, and the caller performs the page
   * navigation itself. Avoids ever putting the JWT in a URL.
   */
  connect: () =>
    api.post<{ authorization_url: string }>("/outlook/connect").then((r) => r.data),
};
