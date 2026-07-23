import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  RefreshCw,
  Download,
  FileSpreadsheet,
  FileText,
  Sparkles,
  Clock,
  Building2,
  Users2,
  Globe2,
  Bell,
  Link2,
  TriangleAlert,
  Info,
  CheckCircle2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useDateRange } from "@/hooks/useDateRange";
import { DateRangeFilter } from "@/components/analytics/DateRangeFilter";
import { FilterBar, DEFAULT_MEETING_EXPLORER_FILTERS, type MeetingExplorerFilters } from "@/components/analytics/FilterBar";
import {
  TrendBarChart,
  TrendLineChart,
  VolumeAreaChart,
  DonutChart,
  IntensityHeatmap,
  GaugeRing,
} from "@/components/analytics/charts";
import { triggerBlobDownload, buildTrendCsv } from "@/components/analytics/export";
import { analyticsApi, type TrendPoint } from "@/api/analytics";
import { meetingsApi } from "@/api/meetings";
import { resourcesApi } from "@/api/resources";
import { getApiErrorMessage } from "@/api/client";
import { useToast } from "@/components/ui/Toast";

const AUTO_REFRESH_MS = 60_000;
const EXPLORER_PAGE_SIZE = 8;
const WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function formatMinutes(minutes: number) {
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const hours = Math.floor(minutes / 60);
  const rest = Math.round(minutes % 60);
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}m`;
}

function SectionSkeleton({ height = 220 }: { height?: number }) {
  return <Skeleton className="rounded-xl" style={{ height }} />;
}

function SectionError() {
  return (
    <p className="flex items-center gap-1.5 text-sm text-red-600">
      <TriangleAlert className="h-4 w-4" /> Couldn't load this section.
    </p>
  );
}

function isVirtualMeeting(m: { zoom_join_url: string | null; teams_join_url: string | null }) {
  return Boolean(m.zoom_join_url || m.teams_join_url);
}

export default function Analytics() {
  const navigate = useNavigate();
  const { push } = useToast();
  const queryClient = useQueryClient();
  const dateRange = useDateRange("30d");
  const { params, queryKeyFragment } = dateRange;

  const [trendGranularity, setTrendGranularity] = React.useState<"daily" | "weekly" | "monthly">("daily");
  const [trendChartType, setTrendChartType] = React.useState<"bar" | "line">("bar");
  const [explorerFilters, setExplorerFilters] = React.useState<MeetingExplorerFilters>(
    DEFAULT_MEETING_EXPLORER_FILTERS
  );
  const [explorerPage, setExplorerPage] = React.useState(0);

  const queryOpts = { refetchInterval: AUTO_REFRESH_MS, staleTime: 20_000 };

  const overview = useQuery({
    queryKey: ["analytics", "overview", queryKeyFragment],
    queryFn: () => analyticsApi.getOverview(params),
    ...queryOpts,
  });
  const reschedule = useQuery({
    queryKey: ["analytics", "reschedule", queryKeyFragment],
    queryFn: () => analyticsApi.getReschedule(params),
    ...queryOpts,
  });
  const cancellations = useQuery({
    queryKey: ["analytics", "cancellations", queryKeyFragment],
    queryFn: () => analyticsApi.getCancellations(params),
    ...queryOpts,
  });
  const notifications = useQuery({
    queryKey: ["analytics", "notifications", queryKeyFragment],
    queryFn: () => analyticsApi.getNotifications(params),
    ...queryOpts,
  });
  const integrations = useQuery({
    queryKey: ["analytics", "integrations", queryKeyFragment],
    queryFn: () => analyticsApi.getIntegrations(params),
    ...queryOpts,
  });
  const resourceAnalytics = useQuery({
    queryKey: ["analytics", "resources", queryKeyFragment],
    queryFn: () => analyticsApi.getResources(params),
    ...queryOpts,
  });
  const guests = useQuery({
    queryKey: ["analytics", "guests", queryKeyFragment],
    queryFn: () => analyticsApi.getGuests(params),
    ...queryOpts,
  });
  const team = useQuery({
    queryKey: ["analytics", "team", queryKeyFragment],
    queryFn: () => analyticsApi.getTeam(params),
    ...queryOpts,
  });
  const insights = useQuery({
    queryKey: ["analytics", "insights", queryKeyFragment],
    queryFn: () => analyticsApi.getInsights(params),
    ...queryOpts,
  });

  const resourcesList = useQuery({
    queryKey: ["resources", "active"],
    queryFn: () => resourcesApi.list(),
  });

  // Meeting Explorer: merges the normal (non-cancelled) list with an
  // explicit cancelled-status fetch, since every other listing
  // endpoint excludes cancelled meetings by design (see
  // MeetingRepository) - this is the one place on the page a person
  // can actually search/filter individual meetings rather than
  // aggregates.
  const explorerData = useQuery({
    queryKey: ["analytics", "explorer", queryKeyFragment],
    queryFn: async () => {
      const [active, cancelled] = await Promise.all([
        meetingsApi.list({ limit: 200 }),
        meetingsApi.filterByStatus("cancelled"),
      ]);
      return [...active, ...cancelled];
    },
  });

  const isRefreshing =
    overview.isFetching ||
    reschedule.isFetching ||
    cancellations.isFetching ||
    notifications.isFetching ||
    integrations.isFetching ||
    resourceAnalytics.isFetching ||
    guests.isFetching ||
    insights.isFetching;

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["analytics"] });
  };

  const handleExportCsv = () => {
    if (!overview.data) return;
    const csv = buildTrendCsv(overview.data.trend_daily, [
      ["Average meeting duration (minutes)", overview.data.duration.average_minutes],
      ["Median meeting duration (minutes)", overview.data.duration.median_minutes],
      ["Total meeting hours", overview.data.duration.total_hours],
      ["Calendar utilization (%)", overview.data.utilization.utilization_pct],
      ["Productivity score", overview.data.productivity.productivity_score],
    ]);
    triggerBlobDownload(new Blob([csv], { type: "text/csv" }), "analytics-export.csv");
  };

  const handleExportXlsx = async () => {
    try {
      const blob = await analyticsApi.downloadExport("xlsx", params);
      triggerBlobDownload(blob, "analytics-export.xlsx");
    } catch (err) {
      push("error", "Couldn't export analytics", getApiErrorMessage(err));
    }
  };

  const handleExportPdf = () => {
    window.print();
  };

  const trendData: TrendPoint[] =
    trendGranularity === "daily"
      ? overview.data?.trend_daily ?? []
      : trendGranularity === "weekly"
        ? overview.data?.trend_weekly ?? []
        : overview.data?.trend_monthly ?? [];

  const weekdayHeatmapCells = React.useMemo(() => {
    const counts = new Map<string, number>(WEEKDAY_ORDER.map((d) => [d, 0]));
    for (const point of overview.data?.trend_daily ?? []) {
      const weekday = new Date(`${point.date}T00:00:00Z`).toLocaleDateString(undefined, {
        weekday: "short",
        timeZone: "UTC",
      });
      const key = WEEKDAY_ORDER.find((d) => weekday.startsWith(d)) ?? weekday;
      counts.set(key, (counts.get(key) ?? 0) + point.upcoming + point.completed);
    }
    return WEEKDAY_ORDER.map((label) => ({ label, value: counts.get(label) ?? 0 }));
  }, [overview.data]);

  const filteredExplorerRows = React.useMemo(() => {
    const rows = explorerData.data ?? [];
    return rows.filter((m) => {
      if (explorerFilters.search && !m.title.toLowerCase().includes(explorerFilters.search.toLowerCase())) {
        return false;
      }
      if (explorerFilters.status && m.status !== explorerFilters.status) return false;
      if (explorerFilters.resourceId && String(m.resource_id ?? "") !== explorerFilters.resourceId) return false;
      if (explorerFilters.meetingType) {
        const virtual = isVirtualMeeting(m);
        if (explorerFilters.meetingType === "virtual" && !virtual) return false;
        if (explorerFilters.meetingType === "physical" && virtual) return false;
        if (explorerFilters.meetingType === "internal" && m.external_guests.length > 0) return false;
        if (explorerFilters.meetingType === "external" && m.external_guests.length === 0) return false;
      }
      return true;
    });
  }, [explorerData.data, explorerFilters]);

  React.useEffect(() => {
    setExplorerPage(0);
  }, [explorerFilters, queryKeyFragment]);

  const explorerPageCount = Math.max(1, Math.ceil(filteredExplorerRows.length / EXPLORER_PAGE_SIZE));
  const explorerPageRows = filteredExplorerRows.slice(
    explorerPage * EXPLORER_PAGE_SIZE,
    (explorerPage + 1) * EXPLORER_PAGE_SIZE
  );

  const showTeamSection = (team.data?.total_users ?? 0) > 1;

  return (
    <div className="mx-auto max-w-6xl print:max-w-none">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3 print:hidden">
        <div>
          <h1 className="text-[28px] font-bold text-ink-700">Analytics</h1>
          <p className="mt-1 text-ink-700/70">
            A deeper look at your scheduling activity. Every widget below updates with the range you pick.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" onClick={handleRefresh} disabled={isRefreshing}>
            <RefreshCw className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`} /> Refresh
          </Button>
          <Button variant="secondary" onClick={handleExportCsv} disabled={!overview.data}>
            <Download className="h-4 w-4" /> CSV
          </Button>
          <Button variant="secondary" onClick={handleExportXlsx}>
            <FileSpreadsheet className="h-4 w-4" /> Excel
          </Button>
          <Button variant="secondary" onClick={handleExportPdf}>
            <FileText className="h-4 w-4" /> PDF
          </Button>
        </div>
      </div>

      <div className="mb-6 print:hidden">
        <DateRangeFilter dateRange={dateRange} />
      </div>

      {/* Duration + Utilization + Productivity */}
      <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Meeting Duration</CardTitle>
          </CardHeader>
          <CardContent>
            {overview.isLoading ? (
              <SectionSkeleton height={160} />
            ) : overview.isError || !overview.data ? (
              <SectionError />
            ) : (
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Stat label="Average" value={formatMinutes(overview.data.duration.average_minutes)} />
                <Stat label="Median" value={formatMinutes(overview.data.duration.median_minutes)} />
                <Stat label="Longest" value={formatMinutes(overview.data.duration.longest_minutes)} />
                <Stat label="Shortest" value={formatMinutes(overview.data.duration.shortest_minutes)} />
                <Stat label="Total hours" value={`${overview.data.duration.total_hours}h`} />
                <Stat label="Avg / day" value={formatMinutes(overview.data.duration.average_daily_minutes)} />
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Calendar Utilization</CardTitle>
          </CardHeader>
          <CardContent>
            {overview.isLoading ? (
              <SectionSkeleton height={160} />
            ) : overview.isError || !overview.data ? (
              <SectionError />
            ) : (
              <div className="flex items-center gap-5">
                <GaugeRing value={overview.data.utilization.utilization_pct} />
                <div className="grid flex-1 grid-cols-2 gap-3 text-sm">
                  <Stat label="Booked" value={`${overview.data.utilization.booked_hours}h`} />
                  <Stat label="Available" value={`${overview.data.utilization.available_hours}h`} />
                  <Stat label="Free" value={`${overview.data.utilization.free_pct}%`} />
                  <Stat label="Utilized" value={`${overview.data.utilization.utilization_pct}%`} />
                </div>
              </div>
            )}
            {!overview.isLoading && overview.data && overview.data.utilization.available_hours === 0 && (
              <p className="mt-3 text-xs text-ink-700/40">
                Set your working hours on the Availability page to see utilization here.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Productivity</CardTitle>
          </CardHeader>
          <CardContent>
            {overview.isLoading ? (
              <SectionSkeleton height={160} />
            ) : overview.isError || !overview.data ? (
              <SectionError />
            ) : (
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Stat label="Focus time" value={formatMinutes(overview.data.productivity.focus_time_minutes)} />
                <Stat label="Deep work" value={formatMinutes(overview.data.productivity.deep_work_minutes)} />
                <Stat label="Meetings / day" value={overview.data.productivity.average_meetings_per_day} />
                <Stat label="Meeting load" value={`${overview.data.productivity.meeting_load_score}%`} />
                <Stat label="Productivity score" value={`${overview.data.productivity.productivity_score}%`} />
                <Stat label="Meeting time" value={formatMinutes(overview.data.productivity.meeting_time_minutes)} />
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Meeting Trend */}
      <Card className="mb-4">
        <CardHeader className="flex-wrap gap-3">
          <CardTitle>Meeting Trend</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <Segmented
              options={[
                { key: "daily", label: "Day" },
                { key: "weekly", label: "Week" },
                { key: "monthly", label: "Month" },
              ]}
              value={trendGranularity}
              onChange={(v) => setTrendGranularity(v as typeof trendGranularity)}
            />
            <Segmented
              options={[
                { key: "bar", label: "Bar" },
                { key: "line", label: "Line" },
              ]}
              value={trendChartType}
              onChange={(v) => setTrendChartType(v as typeof trendChartType)}
            />
          </div>
        </CardHeader>
        <CardContent>
          {overview.isLoading ? (
            <SectionSkeleton height={260} />
          ) : trendChartType === "bar" ? (
            <TrendBarChart data={trendData} />
          ) : (
            <TrendLineChart data={trendData} />
          )}
          <div className="mt-4 flex flex-wrap gap-4 text-xs text-ink-700/60">
            <Legend color="#FFB800" label="Upcoming" />
            <Legend color="#0EA5E9" label="Completed" />
            <Legend color="#EF4444" label="Cancelled" />
            <Legend color="#8B5CF6" label="Rescheduled" />
          </div>
        </CardContent>
      </Card>

      {/* Weekday heatmap */}
      <Card className="mb-4">
        <CardHeader>
          <CardTitle>Busiest Days (Heatmap)</CardTitle>
        </CardHeader>
        <CardContent>
          {overview.isLoading ? (
            <SectionSkeleton height={100} />
          ) : (
            <IntensityHeatmap cells={weekdayHeatmapCells} columns={7} />
          )}
        </CardContent>
      </Card>

      {/* AI Insights */}
      <Card className="mb-4">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-brand-600" /> AI Insights
          </CardTitle>
        </CardHeader>
        <CardContent>
          {insights.isLoading ? (
            <SectionSkeleton height={100} />
          ) : insights.isError || !insights.data ? (
            <SectionError />
          ) : insights.data.insights.length === 0 ? (
            <p className="text-sm text-ink-700/50">
              Not enough activity in this range yet to generate insights.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {insights.data.insights.map((insight) => (
                <div
                  key={insight.id}
                  className={`flex items-start gap-2.5 rounded-xl border p-3.5 text-sm ${
                    insight.tone === "warning"
                      ? "border-amber-200 bg-amber-50 text-amber-900"
                      : insight.tone === "positive"
                        ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                        : "border-slate-200 bg-slate-50 text-slate-800"
                  }`}
                >
                  {insight.tone === "warning" ? (
                    <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                  ) : insight.tone === "positive" ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                  ) : (
                    <Info className="mt-0.5 h-4 w-4 shrink-0" />
                  )}
                  <p>{insight.message}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Reschedule + Cancellation */}
      <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Reschedule Analytics</CardTitle>
          </CardHeader>
          <CardContent>
            {reschedule.isLoading ? (
              <SectionSkeleton height={140} />
            ) : reschedule.isError || !reschedule.data ? (
              <SectionError />
            ) : (
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Stat label="Rescheduled" value={reschedule.data.total_rescheduled} />
                <Stat label="Reschedule rate" value={`${reschedule.data.reschedule_rate_pct}%`} />
                <Stat label="Busiest day" value={reschedule.data.busiest_reschedule_day ?? "—"} />
                <Stat label="Common time slot" value={reschedule.data.most_common_time_slot ?? "—"} />
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Cancellation Analytics</CardTitle>
          </CardHeader>
          <CardContent>
            {cancellations.isLoading ? (
              <SectionSkeleton height={140} />
            ) : cancellations.isError || !cancellations.data ? (
              <SectionError />
            ) : (
              <>
                <div className="mb-4 grid grid-cols-2 gap-3 text-sm">
                  <Stat label="Cancelled" value={cancellations.data.cancelled_count} />
                  <Stat label="Cancellation rate" value={`${cancellations.data.cancellation_rate_pct}%`} />
                  <Stat label="By organizer" value={cancellations.data.cancelled_by_organizer_count} />
                  <Stat label="By participant" value={cancellations.data.cancelled_by_participant_count} />
                </div>
                <VolumeAreaChart data={cancellations.data.trend_daily} color="#EF4444" height={140} />
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Resources + Guests */}
      <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building2 className="h-4 w-4 text-brand-600" /> Resource Analytics
            </CardTitle>
          </CardHeader>
          <CardContent>
            {resourceAnalytics.isLoading ? (
              <SectionSkeleton height={180} />
            ) : resourceAnalytics.isError || !resourceAnalytics.data ? (
              <SectionError />
            ) : (
              <div className="flex flex-col gap-4 sm:flex-row">
                <DonutChart
                  data={[
                    { name: "Virtual", value: resourceAnalytics.data.virtual_meeting_count },
                    { name: "Physical", value: resourceAnalytics.data.physical_meeting_count },
                  ]}
                  height={160}
                />
                <div className="flex-1 space-y-2 text-sm">
                  <Row
                    label="Most used"
                    value={
                      resourceAnalytics.data.most_used
                        ? `${resourceAnalytics.data.most_used.name} (${resourceAnalytics.data.most_used.booking_count})`
                        : "—"
                    }
                  />
                  <Row
                    label="Least used"
                    value={
                      resourceAnalytics.data.least_used
                        ? `${resourceAnalytics.data.least_used.name} (${resourceAnalytics.data.least_used.booking_count})`
                        : "—"
                    }
                  />
                  <Row label="Avg utilization" value={`${resourceAnalytics.data.average_utilization_pct}%`} />
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Globe2 className="h-4 w-4 text-brand-600" /> External Guest Analytics
            </CardTitle>
          </CardHeader>
          <CardContent>
            {guests.isLoading ? (
              <SectionSkeleton height={180} />
            ) : guests.isError || !guests.data ? (
              <SectionError />
            ) : (
              <div className="flex flex-col gap-4 sm:flex-row">
                <DonutChart
                  data={[
                    { name: "Internal", value: guests.data.internal_meeting_count },
                    { name: "External", value: guests.data.external_meeting_count },
                  ]}
                  height={160}
                />
                <div className="flex-1 space-y-1.5 text-sm">
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-700/40">
                    Top guest domains
                  </p>
                  {guests.data.guest_domains.length === 0 ? (
                    <p className="text-ink-700/40">No external guests in this range.</p>
                  ) : (
                    guests.data.guest_domains.slice(0, 5).map((d) => (
                      <Row key={d.domain} label={d.domain} value={d.count} />
                    ))
                  )}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Notifications + Integrations */}
      <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bell className="h-4 w-4 text-brand-600" /> Notification Analytics
            </CardTitle>
          </CardHeader>
          <CardContent>
            {notifications.isLoading ? (
              <SectionSkeleton height={180} />
            ) : notifications.isError || !notifications.data ? (
              <SectionError />
            ) : (
              <div className="space-y-2">
                {(["email", "slack", "whatsapp", "push"] as const).map((channel) => {
                  const stats = notifications.data.by_channel[channel];
                  return (
                    <div key={channel} className="flex items-center justify-between rounded-lg bg-cream-50 px-3 py-2 text-sm">
                      <span className="capitalize text-ink-700">{channel}</span>
                      <span className="text-ink-700/60">
                        {stats.sent} sent · {stats.failed} failed ·{" "}
                        <span className="font-semibold text-ink-700">{stats.success_pct}%</span>
                      </span>
                    </div>
                  );
                })}
                <p className="pt-1 text-xs text-ink-700/40">
                  Overall delivery success: {notifications.data.overall_success_pct}%
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Link2 className="h-4 w-4 text-brand-600" /> Integration Analytics
            </CardTitle>
          </CardHeader>
          <CardContent>
            {integrations.isLoading ? (
              <SectionSkeleton height={180} />
            ) : integrations.isError || !integrations.data ? (
              <SectionError />
            ) : (
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Stat label="Google syncs" value={integrations.data.google_synced_count} />
                <Stat label="Outlook syncs" value={integrations.data.outlook_synced_count} />
                <Stat label="Zoom meetings" value={integrations.data.zoom_meetings_count} />
                <Stat label="Teams meetings" value={integrations.data.teams_meetings_count} />
                <Stat label="Slack users" value={integrations.data.connected_users.slack ?? 0} />
                <Stat label="Push subscribers" value={integrations.data.connected_users.push ?? 0} />
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Team Analytics - only meaningful with more than one user */}
      {showTeamSection && (
        <Card className="mb-4">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users2 className="h-4 w-4 text-brand-600" /> Team Analytics
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-700/40">
                  By department
                </p>
                {team.data!.by_department.length === 0 ? (
                  <p className="text-sm text-ink-700/40">
                    No one has set a department yet (Settings → Profile).
                  </p>
                ) : (
                  <div className="space-y-1.5">
                    {team.data!.by_department.map((d) => (
                      <Row key={d.department} label={d.department} value={`${d.meeting_count} meetings · ${d.user_count} people`} />
                    ))}
                  </div>
                )}
              </div>
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-700/40">
                  By timezone
                </p>
                <div className="space-y-1.5">
                  {team.data!.by_timezone.map((t) => (
                    <Row key={t.timezone} label={t.timezone} value={t.user_count} />
                  ))}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Meeting Explorer */}
      <Card className="mb-4 print:hidden">
        <CardHeader className="flex-col items-start gap-3 sm:flex-row sm:items-center">
          <CardTitle>Meeting Explorer</CardTitle>
          <FilterBar
            filters={explorerFilters}
            onChange={setExplorerFilters}
            resources={resourcesList.data ?? []}
          />
        </CardHeader>
        <CardContent>
          {explorerData.isLoading ? (
            <SectionSkeleton height={240} />
          ) : filteredExplorerRows.length === 0 ? (
            <EmptyState
              icon={<Clock className="h-5 w-5" />}
              title="No meetings match these filters"
              body="Try widening the date range or clearing a filter."
            />
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-xs uppercase tracking-wide text-ink-700/40">
                      <th className="pb-2 pr-4">Title</th>
                      <th className="pb-2 pr-4">Start</th>
                      <th className="pb-2 pr-4">Status</th>
                      <th className="pb-2 pr-4">Guests</th>
                    </tr>
                  </thead>
                  <tbody>
                    {explorerPageRows.map((m) => (
                      <tr
                        key={m.id}
                        className="cursor-pointer border-b border-slate-50 hover:bg-cream-50"
                        onClick={() => navigate(`/meetings/${m.id}`)}
                      >
                        <td className="py-2.5 pr-4 font-medium text-ink-700">{m.title}</td>
                        <td className="py-2.5 pr-4 text-ink-700/60">
                          {new Date(m.start_time).toLocaleString(undefined, {
                            month: "short",
                            day: "numeric",
                            hour: "numeric",
                            minute: "2-digit",
                          })}
                        </td>
                        <td className="py-2.5 pr-4">
                          <StatusBadge status={m.status} />
                        </td>
                        <td className="py-2.5 pr-4 text-ink-700/60">{m.external_guests.length}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-4 flex items-center justify-between text-xs text-ink-700/50">
                <span>
                  Page {explorerPage + 1} of {explorerPageCount} ({filteredExplorerRows.length} meetings)
                </span>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={explorerPage === 0}
                    onClick={() => setExplorerPage((p) => Math.max(0, p - 1))}
                  >
                    Previous
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={explorerPage >= explorerPageCount - 1}
                    onClick={() => setExplorerPage((p) => Math.min(explorerPageCount - 1, p + 1))}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg bg-cream-50 p-3">
      <p className="text-[11px] uppercase tracking-wide text-ink-700/50">{label}</p>
      <p className="text-lg font-bold text-ink-700">{value}</p>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="truncate text-ink-700/70">{label}</span>
      <span className="shrink-0 font-semibold text-ink-700">{value}</span>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}

function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { key: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex gap-1 rounded-lg bg-cream-100 p-1">
      {options.map((opt) => (
        <button
          key={opt.key}
          onClick={() => onChange(opt.key)}
          className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
            value === opt.key ? "bg-white text-ink-700 shadow-card" : "text-ink-700/50 hover:text-ink-700"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
