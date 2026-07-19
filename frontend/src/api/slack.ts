import { api } from "./client";
import type { SlackStatus } from "@/types";

export const slackApi = {
  status: () => api.get<SlackStatus>("/slack/status").then((r) => r.data),

  disconnect: () => api.delete("/slack/disconnect").then((r) => r.data),

  /**
   * Like Outlook/Zoom's POST /connect, this is a normal authenticated
   * fetch call - the backend returns the Slack consent screen URL as
   * JSON, and the caller performs the page navigation itself. Avoids
   * ever putting the JWT in a URL.
   */
  connect: () =>
    api.post<{ authorization_url: string }>("/slack/connect").then((r) => r.data),

  sendTest: () => api.post<{ message: string }>("/slack/test").then((r) => r.data),
};
