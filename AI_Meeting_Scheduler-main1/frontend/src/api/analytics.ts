import { api } from "./client";

export interface KPIResponse {
  meetings_scheduled: number;
  conflicts_avoided: number;
  time_saved_minutes: number;
}

export const analyticsApi = {
  getKpis: () => api.get<KPIResponse>("/analytics/kpis").then((r) => r.data),
};
