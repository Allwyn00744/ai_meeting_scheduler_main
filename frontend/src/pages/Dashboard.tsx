import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  Plus,
  CalendarCheck,
  ClipboardCheck,
  TriangleAlert,
  Sparkles,
  Video,
  BarChart3,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { DashboardSkeleton } from "@/components/ui/Skeleton";
import { meetingsApi } from "@/api/meetings";
import { analyticsApi } from "@/api/analytics";
import { getApiErrorMessage } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";

const WEEKDAY_LABELS = ["S", "M", "T", "W", "T", "F", "S"];

function firstName(name: string) {
  return name.trim().split(/\s+/)[0];
}

function minutesUntil(iso: string) {
  return Math.round((new Date(iso).getTime() - Date.now()) / 60000);
}

function formatDuration(minutes: number) {
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"}`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}m`;
}

/** Full ring gauge (0-100), rendered with real SVG so the stroke is pixel-accurate rather than a border/conic-gradient hack. A value of 0 (no data yet) renders as a plain gray ring with "0" in the center - never a fabricated number. */
function RingGauge({ value, size = 96, stroke = 8 }: { value: number; size?: number; stroke?: number }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (value / 100) * c;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#F0EADC" strokeWidth={stroke} />
        {value > 0 && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="#FFB800"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={offset}
          />
        )}
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-xl font-bold text-ink-700">{value}</span>
      </div>
    </div>
  );
}

/** Half-circle "speedometer" arc gauge matching the Figma Scheduling Efficiency card. A value of 0 (no data yet) renders as a plain gray arc with "0%" - never a fabricated number. */
function ArcGauge({ value, size = 200 }: { value: number; size?: number }) {
  const stroke = 14;
  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2 + r * 0.15;
  const startAngle = 180;
  const endAngle = 0;

  const pointAt = (angleDeg: number) => {
    const a = (angleDeg * Math.PI) / 180;
    return { x: cx + r * Math.cos(a), y: cy - r * Math.sin(a) };
  };
  const start = pointAt(startAngle);
  const end = pointAt(endAngle);
  const sweepAngle = startAngle - (value / 100) * (startAngle - endAngle);
  const fillEnd = pointAt(sweepAngle);

  const trackPath = `M ${start.x} ${start.y} A ${r} ${r} 0 0 1 ${end.x} ${end.y}`;
  const fillPath = `M ${start.x} ${start.y} A ${r} ${r} 0 0 1 ${fillEnd.x} ${fillEnd.y}`;

  return (
    <div className="relative" style={{ width: size, height: size / 2 + 40 }}>
      <svg width={size} height={size / 2 + 40}>
        <path d={trackPath} fill="none" stroke="#F0EADC" strokeWidth={stroke} strokeLinecap="round" />
        {value > 0 && (
          <path d={fillPath} fill="none" stroke="#FFB800" strokeWidth={stroke} strokeLinecap="round" />
        )}
      </svg>
      <div className="absolute inset-x-0 bottom-1 flex flex-col items-center">
        <span className="text-3xl font-bold text-ink-700">{value}%</span>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const {
    data: meetings,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["meetings"],
    queryFn: () => meetingsApi.list({ limit: 200 }),
  });

  const { data: kpis } = useQuery({
    queryKey: ["kpis"],
    queryFn: analyticsApi.getKpis,
  });

  const now = new Date();
  const startOfToday = new Date(now);
  startOfToday.setHours(0, 0, 0, 0);
  const endOfToday = new Date(startOfToday);
  endOfToday.setDate(endOfToday.getDate() + 1);

  const active = (meetings ?? []).filter((m) => m.status !== "cancelled");
  const upcoming = active.filter((m) => new Date(m.start_time).getTime() >= now.getTime());
  const todaysMeetings = active
    .filter((m) => {
      const t = new Date(m.start_time);
      return t >= startOfToday && t < endOfToday;
    })
    .sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime());
  const nextToday = todaysMeetings.find((m) => new Date(m.start_time).getTime() >= now.getTime());
  const pendingRsvp = upcoming.filter((m) => m.external_guests.length > 0).length;
  const completed = active.filter((m) => m.status === "completed").length;
  const cancelledCount = (meetings ?? []).filter((m) => m.status === "cancelled").length;

  // Meeting Analytics: how many meetings fall on each weekday of the
  // current week (Sun-Sat), from real meeting data. Also tracks last
  // week's total so the "trend" caption below is a real comparison,
  // not a fabricated "+12%".
  const { weekCounts, thisWeekTotal, lastWeekTotal } = React.useMemo(() => {
    const counts = [0, 0, 0, 0, 0, 0, 0];
    const weekStart = new Date(startOfToday);
    weekStart.setDate(weekStart.getDate() - weekStart.getDay());
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 7);
    const lastWeekStart = new Date(weekStart);
    lastWeekStart.setDate(lastWeekStart.getDate() - 7);

    let lastWeek = 0;
    for (const m of active) {
      const t = new Date(m.start_time);
      if (t >= weekStart && t < weekEnd) counts[t.getDay()] += 1;
      else if (t >= lastWeekStart && t < weekStart) lastWeek += 1;
    }
    return {
      weekCounts: counts,
      thisWeekTotal: counts.reduce((a, b) => a + b, 0),
      lastWeekTotal: lastWeek,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meetings]);
  const maxWeekCount = Math.max(0, ...weekCounts);
  const peakDayIndex = maxWeekCount > 0 ? weekCounts.indexOf(maxWeekCount) : -1;
  const weekTrendPct = lastWeekTotal > 0 ? Math.round(((thisWeekTotal - lastWeekTotal) / lastWeekTotal) * 100) : 0;

  // Shortest meeting on record, and a completed/total "resolved"
  // ratio - both computed from real meeting durations/status rather
  // than invented.
  const shortestMinutes =
    active.length > 0
      ? Math.min(
          ...active.map((m) => Math.round((new Date(m.end_time).getTime() - new Date(m.start_time).getTime()) / 60000))
        )
      : 0;

  // "Scheduling efficiency": share of scheduled meetings that didn't
  // hit a conflict, from the real KPI endpoint - not fabricated.
  // Defaults to 0 (not hidden) when there's no KPI data yet, so the
  // card always renders with the same layout, just zeroed out.
  const conflictFreeRate =
    kpis && kpis.meetings_scheduled > 0
      ? Math.max(0, Math.min(100, Math.round((1 - kpis.conflicts_avoided / kpis.meetings_scheduled) * 100)))
      : 0;
  const completionRate = active.length > 0 ? Math.round((completed / active.length) * 100) : 0;
  const hoursSaved = kpis ? Math.round((kpis.time_saved_minutes / 60) * 10) / 10 : 0;
  // "Productivity score": share of scheduled meetings that weren't
  // cancelled - a real, if approximate, stand-in for the design's
  // "Productivity Score".
  const totalScheduledEver = (meetings ?? []).length;
  const productivityScore = totalScheduledEver > 0 ? Math.round((1 - cancelledCount / totalScheduledEver) * 100) : 0;

  return (
    <div className="mx-auto max-w-6xl">
      {/* Greeting */}
      <div className="mb-6">
        <h1 className="text-[28px] font-bold text-ink-700">
          Good {now.getHours() < 12 ? "morning" : now.getHours() < 18 ? "afternoon" : "evening"}
          {user ? `, ${firstName(user.name)}` : ""}.
        </h1>
        <p className="mt-1 text-ink-700/70">
          {todaysMeetings.length === 0
            ? "You have no meetings scheduled today."
            : nextToday
              ? `You have ${todaysMeetings.length} meeting${todaysMeetings.length === 1 ? "" : "s"} today. Your next one starts in ${formatDuration(Math.max(0, minutesUntil(nextToday.start_time)))}.`
              : `You have ${todaysMeetings.length} meeting${todaysMeetings.length === 1 ? "" : "s"} today, all done for now.`}
        </p>
      </div>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-ink-700">Dashboard</h2>
          <p className="mt-1 flex items-center gap-1.5 text-sm text-ink-700/60">
            <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
            {upcoming.length} meeting{upcoming.length === 1 ? "" : "s"} upcoming
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => navigate("/ai-assistant")}>
            <Plus className="h-4 w-4" /> New meeting
          </Button>
        </div>
      </div>

      {isLoading ? (
        <DashboardSkeleton />
      ) : isError ? (
        <EmptyState
          icon={<TriangleAlert className="h-5 w-5" />}
          title="Couldn't load your meetings"
          body={getApiErrorMessage(error, "Check that the backend is running and reachable.")}
        />
      ) : (meetings ?? []).length === 0 ? (
        <EmptyState
          icon={<CalendarCheck className="h-5 w-5" />}
          title="No meetings scheduled"
          body="You don't have any meetings yet. Schedule one manually or describe it to the AI assistant."
          actionLabel="New meeting"
          onAction={() => navigate("/ai-assistant")}
        />
      ) : (
        <>
          {/* Stat cards */}
          <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-2xl bg-white p-5 shadow-card">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wide text-ink-700/50">Upcoming</p>
                <CalendarCheck className="h-4 w-4 text-brand-600" />
              </div>
              <p className="mt-2 text-3xl font-bold text-ink-700">{upcoming.length}</p>
            </div>
            <div className="rounded-2xl bg-white p-5 shadow-card">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wide text-ink-700/50">Pending RSVP</p>
                <ClipboardCheck className="h-4 w-4 text-brand-600" />
              </div>
              <p className="mt-2 text-3xl font-bold text-ink-700">{pendingRsvp}</p>
            </div>
            <div className="rounded-2xl bg-white p-5 shadow-card">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wide text-red-500">Conflicts</p>
                <TriangleAlert className="h-4 w-4 text-red-500" />
              </div>
              <p className="mt-2 text-3xl font-bold text-red-600">{kpis?.conflicts_avoided ?? 0}</p>
            </div>
          </div>

          {/* Time saved + efficiency */}
          <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="rounded-2xl bg-white p-6 shadow-card">
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-700/50">Weekly time saved</p>
              <p className="mt-2 flex items-baseline gap-1.5">
                <span className="text-4xl font-bold text-brand-600">{hoursSaved}</span>
                <span className="text-sm font-medium text-ink-700/60">Hours</span>
              </p>
              <div className="mt-4 flex items-center justify-between text-xs text-ink-700/60">
                <span>Productivity Score</span>
                <span className="font-semibold text-ink-700">{productivityScore}%</span>
              </div>
              <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-cream-200">
                <div
                  className="h-full rounded-full bg-brand-500"
                  style={{ width: `${productivityScore ?? 0}%` }}
                />
              </div>
              <p className="mt-2 text-xs font-medium text-emerald-600">
                {weekTrendPct >= 0 ? "↗" : "↘"} {Math.abs(weekTrendPct)}% from last week
              </p>
            </div>

            <div className="rounded-2xl bg-white p-6 shadow-card">
              <div className="mb-1 flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wide text-ink-700/50">Meeting Efficiency</p>
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-100 text-brand-700">
                  <BarChart3 className="h-3.5 w-3.5" />
                </div>
              </div>
              <div className="mt-3 flex items-center gap-5">
                <div className="flex flex-col items-center">
                  <RingGauge value={completionRate} />
                  <span className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-ink-700/40">
                    Avg index
                  </span>
                </div>
                <div className="grid flex-1 grid-cols-2 gap-3">
                  <div className="rounded-lg bg-cream-100 p-3">
                    <p className="text-[11px] uppercase tracking-wide text-ink-700/50">Shortest</p>
                    <p className="text-lg font-bold text-brand-700">
                      {formatDuration(shortestMinutes)}
                    </p>
                  </div>
                  <div className="rounded-lg bg-cream-100 p-3">
                    <p className="text-[11px] uppercase tracking-wide text-ink-700/50">Resolved</p>
                    <p className="text-lg font-bold text-ink-700">
                      {`${completed}/${active.length}`}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Analytics + scheduling efficiency */}
          <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="rounded-2xl bg-white p-6 shadow-card">
              <p className="mb-5 text-base font-semibold text-ink-700">Meeting Analytics</p>
              <div className="flex h-32 items-end justify-between gap-2">
                {weekCounts.map((count, i) => (
                  <div key={i} className="flex flex-1 flex-col items-center gap-2">
                    <div className="relative flex w-full flex-1 items-end justify-center">
                      {i === peakDayIndex && count > 0 && (
                        <span className="absolute -top-6 rounded-full bg-cream-200 px-2 py-0.5 text-[10px] font-semibold text-ink-700 whitespace-nowrap">
                          {count} Meeting{count === 1 ? "" : "s"}
                        </span>
                      )}
                      {count > 0 ? (
                        <div
                          className={`w-full rounded-lg ${i === peakDayIndex ? "bg-brand-500" : "bg-brand-300"}`}
                          style={{ height: `${Math.max(8, (count / Math.max(1, maxWeekCount)) * 100)}%` }}
                          title={`${count} meeting${count === 1 ? "" : "s"}`}
                        />
                      ) : (
                        <div className="h-2 w-full rounded-lg bg-slate-100" />
                      )}
                    </div>
                    <span className="text-xs text-ink-700/50">{WEEKDAY_LABELS[i]}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex flex-col items-center rounded-2xl bg-white p-6 shadow-card">
              <p className="mb-2 self-start text-base font-semibold text-ink-700">Scheduling Efficiency</p>
              <ArcGauge value={conflictFreeRate} />
              <p className="-mt-2 text-xs text-ink-700/50">Time Optimized</p>
            </div>
          </div>

          {/* Today's schedule */}
          <div className="mb-4 rounded-2xl bg-white p-6 shadow-card">
            <div className="mb-4 flex items-center justify-between">
              <p className="text-base font-semibold text-ink-700">Today's Schedule</p>
            </div>
            {todaysMeetings.length === 0 ? (
              <p className="py-6 text-center text-sm text-ink-700/50">No meetings scheduled for today.</p>
            ) : (
              <div className="space-y-3">
                {todaysMeetings.map((m) => {
                  const joinUrl = m.zoom_join_url || m.teams_join_url;
                  const isPast = new Date(m.end_time).getTime() < now.getTime();
                  return (
                    <div
                      key={m.id}
                      className="flex flex-wrap items-center gap-4 rounded-xl border border-slate-100 px-4 py-3.5"
                    >
                      <div className="w-16 shrink-0 text-sm font-semibold text-brand-700">
                        {new Date(m.start_time).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
                      </div>
                      <button
                        onClick={() => navigate(`/meetings/${m.id}`)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <p className="truncate font-semibold text-ink-700">{m.title}</p>
                        {m.location && <p className="truncate text-xs text-ink-700/50">{m.location}</p>}
                      </button>
                      {m.external_guests.length > 0 && (
                        <span className="rounded-full bg-cream-100 px-2.5 py-1 text-xs font-medium text-ink-700/70">
                          {m.external_guests.length} guest{m.external_guests.length === 1 ? "" : "s"}
                        </span>
                      )}
                      {joinUrl ? (
                        <a
                          href={joinUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="flex items-center gap-1.5 rounded-full bg-ink-700 px-4 py-2 text-xs font-semibold text-white hover:bg-ink-800"
                        >
                          <Video className="h-3.5 w-3.5" /> Join
                        </a>
                      ) : (
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={isPast}
                          onClick={() => navigate(`/meetings/${m.id}`)}
                        >
                          {isPast ? "Ended" : "Details"}
                        </Button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* CTA */}
          <div className="rounded-2xl bg-gradient-to-br from-ink-900 to-ink-700 p-6 text-white">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="mb-3 flex items-center gap-2 text-brand-400">
                  <Sparkles className="h-4 w-4" />
                  <span className="text-xs font-semibold uppercase tracking-wide">Smart Scheduler</span>
                </div>
                <p className="text-lg font-semibold">Ready to schedule your next meeting?</p>
                <p className="mt-1 max-w-md text-sm text-white/70">
                  Describe it in plain language and let the AI assistant find a time and book it for you.
                </p>
              </div>
              <Button className="shrink-0" onClick={() => navigate("/ai-assistant")}>
                <Sparkles className="h-4 w-4" /> Open AI Assistant
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
