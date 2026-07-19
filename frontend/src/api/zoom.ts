import { api } from "./client";
import type { ZoomStatus } from "@/types";

export const zoomApi = {
  status: () => api.get<ZoomStatus>("/zoom/status").then((r) => r.data),

  disconnect: () => api.delete("/zoom/disconnect").then((r) => r.data),

  /**
   * Like Outlook's POST /outlook/connect (and unlike Google's GET
   * /google/login redirect), this is a normal authenticated fetch call
   * - the backend returns the Zoom consent screen URL as JSON, and the
   * caller performs the page navigation itself. Avoids ever putting
   * the JWT in a URL.
   */
  connect: () =>
    api.post<{ authorization_url: string }>("/zoom/connect").then((r) => r.data),
};
