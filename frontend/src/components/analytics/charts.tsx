import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TrendPoint } from "@/api/analytics";

// Matches the brand/ink/cream hex values Dashboard.tsx's own
// RingGauge/ArcGauge already use, plus Tailwind's own red/emerald/sky
// for the extra trend series (Dashboard already mixes both - e.g.
// text-red-500/text-emerald-600 alongside the custom tokens).
export const CHART_COLORS = {
  upcoming: "#FFB800", // brand-500
  completed: "#0EA5E9", // sky-500
  cancelled: "#EF4444", // red-500
  rescheduled: "#8B5CF6", // violet-500
  track: "#F0EADC", // cream-200
  ink: "#16233A", // ink-900-ish
};

const AXIS_STYLE = { fontSize: 11, fill: "#64748b" };

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-card">
      <p className="mb-1 font-semibold text-ink-700">{label}</p>
      {payload.map((entry: any) => (
        <p key={entry.dataKey} style={{ color: entry.color }}>
          {entry.name}: <span className="font-semibold">{entry.value}</span>
        </p>
      ))}
    </div>
  );
}

/** Meetings per day/week/month, split by status - the core Meeting Trend chart. Renders as a stacked bar so all four series stay comparable at a glance. */
export function TrendBarChart({ data, height = 260 }: { data: TrendPoint[]; height?: number }) {
  if (data.length === 0) {
    return <EmptyChartState height={height} />;
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.track} vertical={false} />
        <XAxis dataKey="date" tick={AXIS_STYLE} tickLine={false} axisLine={false} />
        <YAxis tick={AXIS_STYLE} tickLine={false} axisLine={false} allowDecimals={false} />
        <Tooltip content={<ChartTooltip />} />
        <Bar dataKey="upcoming" name="Upcoming" stackId="a" fill={CHART_COLORS.upcoming} radius={[0, 0, 0, 0]} />
        <Bar dataKey="completed" name="Completed" stackId="a" fill={CHART_COLORS.completed} />
        <Bar dataKey="cancelled" name="Cancelled" stackId="a" fill={CHART_COLORS.cancelled} />
        <Bar
          dataKey="rescheduled"
          name="Rescheduled"
          stackId="a"
          fill={CHART_COLORS.rescheduled}
          radius={[4, 4, 0, 0]}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Same trend data as an interactive line chart - useful for spotting the shape of the trend over a longer range than the bar chart. */
export function TrendLineChart({ data, height = 260 }: { data: TrendPoint[]; height?: number }) {
  if (data.length === 0) {
    return <EmptyChartState height={height} />;
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.track} vertical={false} />
        <XAxis dataKey="date" tick={AXIS_STYLE} tickLine={false} axisLine={false} />
        <YAxis tick={AXIS_STYLE} tickLine={false} axisLine={false} allowDecimals={false} />
        <Tooltip content={<ChartTooltip />} />
        <Line type="monotone" dataKey="upcoming" name="Upcoming" stroke={CHART_COLORS.upcoming} strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="completed" name="Completed" stroke={CHART_COLORS.completed} strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="cancelled" name="Cancelled" stroke={CHART_COLORS.cancelled} strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="rescheduled" name="Rescheduled" stroke={CHART_COLORS.rescheduled} strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Total meeting volume over time as a filled area - used for the "load over time" framing (e.g. cancellation trend). */
export function VolumeAreaChart({
  data,
  dataKey = "count",
  color = CHART_COLORS.upcoming,
  height = 200,
}: {
  data: { date: string; count: number }[];
  dataKey?: string;
  color?: string;
  height?: number;
}) {
  if (data.length === 0) {
    return <EmptyChartState height={height} />;
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id="volumeFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.35} />
            <stop offset="95%" stopColor={color} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.track} vertical={false} />
        <XAxis dataKey="date" tick={AXIS_STYLE} tickLine={false} axisLine={false} />
        <YAxis tick={AXIS_STYLE} tickLine={false} axisLine={false} allowDecimals={false} />
        <Tooltip content={<ChartTooltip />} />
        <Area type="monotone" dataKey={dataKey} name="Count" stroke={color} fill="url(#volumeFill)" strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

const DONUT_PALETTE = [
  CHART_COLORS.upcoming,
  CHART_COLORS.completed,
  CHART_COLORS.cancelled,
  CHART_COLORS.rescheduled,
  "#10B981",
  "#F97316",
];

/** Generic donut/pie chart for share-of-total breakdowns (virtual vs physical, internal vs external, channel share, etc). */
export function DonutChart({
  data,
  height = 220,
}: {
  data: { name: string; value: number }[];
  height?: number;
}) {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  if (total === 0) {
    return <EmptyChartState height={height} />;
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius="60%" outerRadius="85%" paddingAngle={2}>
          {data.map((entry, i) => (
            <Cell key={entry.name} fill={DONUT_PALETTE[i % DONUT_PALETTE.length]} />
          ))}
        </Pie>
        <Tooltip
          formatter={((value: number, name: string) => [
            `${value ?? 0} (${Math.round(((Number(value) || 0) / total) * 100)}%)`,
            name,
          ]) as any}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

/** Bucket counts (e.g. meetings per weekday, or per hour-of-day) as a color-intensity grid - hand-built rather than pulling in a second charting library, matching the existing hand-rolled-SVG aesthetic already used by Dashboard's gauges. */
export function IntensityHeatmap({
  cells,
  columns,
}: {
  cells: { label: string; value: number }[];
  columns: number;
}) {
  const max = Math.max(1, ...cells.map((c) => c.value));

  return (
    <div className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
      {cells.map((cell) => {
        const intensity = cell.value / max;
        return (
          <div
            key={cell.label}
            title={`${cell.label}: ${cell.value}`}
            className="flex aspect-square flex-col items-center justify-center rounded-lg text-[10px] font-medium"
            style={{
              backgroundColor: intensity === 0 ? CHART_COLORS.track : CHART_COLORS.upcoming,
              opacity: intensity === 0 ? 1 : 0.25 + intensity * 0.75,
              color: intensity > 0.5 ? "#16233A" : "#64748b",
            }}
          >
            <span>{cell.label}</span>
            <span className="font-bold">{cell.value}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Compact ring gauge for a single 0-100 percentage (calendar utilization, productivity score, etc). Renders a plain gray ring at 0 rather than a fabricated fill. */
export function GaugeRing({ value, size = 88, stroke = 9 }: { value: number; size?: number; stroke?: number }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, value));
  const offset = c - (clamped / 100) * c;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={CHART_COLORS.track} strokeWidth={stroke} />
        {clamped > 0 && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={CHART_COLORS.upcoming}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={offset}
          />
        )}
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-lg font-bold text-ink-700">{Math.round(clamped)}%</span>
      </div>
    </div>
  );
}

function EmptyChartState({ height }: { height: number }) {
  return (
    <div
      className="flex items-center justify-center rounded-lg bg-cream-50 text-xs text-ink-700/40"
      style={{ height }}
    >
      No data for this range yet.
    </div>
  );
}
