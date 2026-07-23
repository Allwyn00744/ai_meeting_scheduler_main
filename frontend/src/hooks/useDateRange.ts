import * as React from "react";
import type { DateRangeKey, DateRangeParams } from "@/api/analytics";

export const DATE_RANGE_OPTIONS: { key: DateRangeKey; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "7d", label: "Last 7 Days" },
  { key: "30d", label: "Last 30 Days" },
  { key: "90d", label: "Last 90 Days" },
  { key: "this_month", label: "This Month" },
  { key: "last_month", label: "Last Month" },
  { key: "custom", label: "Custom Range" },
];

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/**
 * Single source of truth for the Analytics page's selected date
 * range. Every widget's React Query key includes `params` (see
 * queryKeyFor below), so switching the range - or the custom
 * start/end - refetches every widget automatically without any
 * prop-drilled "refresh" callbacks.
 */
export function useDateRange(initial: DateRangeKey = "30d") {
  const [range, setRange] = React.useState<DateRangeKey>(initial);
  const today = React.useMemo(() => new Date(), []);
  const [customStart, setCustomStart] = React.useState<string>(
    isoDate(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 6))
  );
  const [customEnd, setCustomEnd] = React.useState<string>(isoDate(today));

  const params: DateRangeParams = React.useMemo(
    () =>
      range === "custom"
        ? { range, start: customStart, end: customEnd }
        : { range },
    [range, customStart, customEnd]
  );

  /** Stable, serializable key fragment for React Query's queryKey. */
  const queryKeyFragment = React.useMemo(
    () => (range === "custom" ? `custom:${customStart}:${customEnd}` : range),
    [range, customStart, customEnd]
  );

  return {
    range,
    setRange,
    customStart,
    setCustomStart,
    customEnd,
    setCustomEnd,
    params,
    queryKeyFragment,
  };
}

export type UseDateRangeReturn = ReturnType<typeof useDateRange>;
