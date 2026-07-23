import { api } from "./client";
import type { TeamsStatus } from "@/types";

export const teamsApi = {
  /**
   * "connected" mirrors Outlook's own connection state - there is no
   * separate Teams connect/disconnect flow (see api/teams_routes.py).
   */
  status: () => api.get<TeamsStatus>("/teams/status").then((r) => r.data),
};
