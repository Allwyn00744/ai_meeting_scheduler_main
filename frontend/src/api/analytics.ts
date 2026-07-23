import { api } from "./client";

export interface KPIResponse {
  meetings_scheduled: number;
  conflicts_avoided: number;
  time_saved_minutes: number;
}

// ---- Analytics Dashboard Extension --------------------------------------

export type DateRangeKey =
  | "today"
  | "7d"
  | "30d"
  | "90d"
  | "this_month"
  | "last_month"
  | "custom";

export interface DateRangeParams {
  range: DateRangeKey;
  /** YYYY-MM-DD. Required (and only used) when range === "custom". */
  start?: string;
  end?: string;
}

export interface ResolvedRange {
  start: string;
  end: string;
}

export interface TrendPoint {
  date: string;
  upcoming: number;
  completed: number;
  cancelled: number;
  rescheduled: number;
}

export interface DurationStats {
  average_minutes: number;
  median_minutes: number;
  longest_minutes: number;
  shortest_minutes: number;
  total_hours: number;
  average_daily_minutes: number;
}

export interface UtilizationStats {
  booked_hours: number;
  available_hours: number;
  utilization_pct: number;
  free_pct: number;
}

export interface ProductivityStats {
  meeting_time_minutes: number;
  focus_time_minutes: number;
  deep_work_minutes: number;
  average_meetings_per_day: number;
  productivity_score: number;
  meeting_load_score: number;
}

export interface OverviewResponse {
  range: ResolvedRange;
  trend_daily: TrendPoint[];
  trend_weekly: TrendPoint[];
  trend_monthly: TrendPoint[];
  duration: DurationStats;
  utilization: UtilizationStats;
  productivity: ProductivityStats;
}

export interface RescheduleAnalyticsResponse {
  range: ResolvedRange;
  total_rescheduled: number;
  reschedule_rate_pct: number;
  busiest_reschedule_day: string | null;
  most_common_time_slot: string | null;
}

export interface CancellationAnalyticsResponse {
  range: ResolvedRange;
  cancellation_rate_pct: number;
  cancelled_count: number;
  cancelled_by_organizer_count: number;
  cancelled_by_participant_count: number;
  trend_daily: { date: string; count: number }[];
}

export interface ChannelNotificationStats {
  sent: number;
  failed: number;
  success_pct: number;
}

export interface NotificationAnalyticsResponse {
  range: ResolvedRange;
  by_channel: Record<"email" | "slack" | "whatsapp" | "push", ChannelNotificationStats>;
  overall_success_pct: number;
}

export interface IntegrationAnalyticsResponse {
  range: ResolvedRange;
  google_synced_count: number;
  outlook_synced_count: number;
  zoom_meetings_count: number;
  teams_meetings_count: number;
  connected_users: Record<string, number>;
  total_users: number;
}

export interface ResourceUsage {
  resource_id: number;
  name: string;
  booking_count: number;
  booked_hours: number;
  utilization_pct: number;
}

export interface ResourceAnalyticsResponse {
  range: ResolvedRange;
  most_used: ResourceUsage | null;
  least_used: ResourceUsage | null;
  average_utilization_pct: number;
  virtual_meeting_count: number;
  physical_meeting_count: number;
}

export interface GuestAnalyticsResponse {
  range: ResolvedRange;
  internal_meeting_count: number;
  external_meeting_count: number;
  guest_domains: { domain: string; count: number }[];
  top_companies: { domain: string; count: number }[];
}

export interface DepartmentCount {
  department: string;
  meeting_count: number;
  user_count: number;
}

export interface TimezoneCount {
  timezone: string;
  user_count: number;
}

export interface TeamAnalyticsResponse {
  range: ResolvedRange;
  by_department: DepartmentCount[];
  by_timezone: TimezoneCount[];
  total_users: number;
  users_with_department_set: number;
}

export interface Insight {
  id: string;
  message: string;
  tone: "info" | "positive" | "warning";
}

export interface InsightsResponse {
  range: ResolvedRange;
  insights: Insight[];
}

function rangeParams(params: DateRangeParams) {
  return {
    range: params.range,
    ...(params.range === "custom" ? { start: params.start, end: params.end } : {}),
  };
}

export const analyticsApi = {
  getKpis: () => api.get<KPIResponse>("/analytics/kpis").then((r) => r.data),

  getOverview: (params: DateRangeParams) =>
    api.get<OverviewResponse>("/analytics/overview", { params: rangeParams(params) }).then((r) => r.data),

  getReschedule: (params: DateRangeParams) =>
    api
      .get<RescheduleAnalyticsResponse>("/analytics/reschedule", { params: rangeParams(params) })
      .then((r) => r.data),

  getCancellations: (params: DateRangeParams) =>
    api
      .get<CancellationAnalyticsResponse>("/analytics/cancellations", { params: rangeParams(params) })
      .then((r) => r.data),

  getNotifications: (params: DateRangeParams) =>
    api
      .get<NotificationAnalyticsResponse>("/analytics/notifications", { params: rangeParams(params) })
      .then((r) => r.data),

  getIntegrations: (params: DateRangeParams) =>
    api
      .get<IntegrationAnalyticsResponse>("/analytics/integrations", { params: rangeParams(params) })
      .then((r) => r.data),

  getResources: (params: DateRangeParams) =>
    api
      .get<ResourceAnalyticsResponse>("/analytics/resources", { params: rangeParams(params) })
      .then((r) => r.data),

  getGuests: (params: DateRangeParams) =>
    api.get<GuestAnalyticsResponse>("/analytics/guests", { params: rangeParams(params) }).then((r) => r.data),

  getTeam: (params: DateRangeParams) =>
    api.get<TeamAnalyticsResponse>("/analytics/team", { params: rangeParams(params) }).then((r) => r.data),

  getInsights: (params: DateRangeParams) =>
    api.get<InsightsResponse>("/analytics/insights", { params: rangeParams(params) }).then((r) => r.data),

  /**
   * GET /analytics/export requires auth like every other route here,
   * so a plain <a href> (which can't carry an Authorization header)
   * won't work - this fetches the file through the authenticated
   * `api` client as a blob instead. Callers turn the result into a
   * download via triggerBlobDownload (see components/analytics/export.ts).
   */
  downloadExport: (format: "csv" | "xlsx", params: DateRangeParams) =>
    api
      .get<Blob>("/analytics/export", {
        params: { format, ...rangeParams(params) },
        responseType: "blob",
      })
      .then((r) => r.data),
};
