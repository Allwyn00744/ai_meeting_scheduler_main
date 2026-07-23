import { Input } from "@/components/ui/Input";
import { DATE_RANGE_OPTIONS, type UseDateRangeReturn } from "@/hooks/useDateRange";
import { cn } from "@/lib/utils";

/** The 7 date-range filters (Today / Last 7,30,90 Days / This Month / Last Month / Custom Range) that drive every widget on the Analytics page. */
export function DateRangeFilter({ dateRange }: { dateRange: UseDateRangeReturn }) {
  const { range, setRange, customStart, setCustomStart, customEnd, setCustomEnd } = dateRange;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex flex-wrap gap-1 rounded-xl bg-cream-100 p-1">
        {DATE_RANGE_OPTIONS.map((opt) => (
          <button
            key={opt.key}
            onClick={() => setRange(opt.key)}
            className={cn(
              "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
              range === opt.key ? "bg-white text-ink-700 shadow-card" : "text-ink-700/60 hover:text-ink-700"
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {range === "custom" && (
        <div className="flex items-center gap-2">
          <Input
            type="date"
            value={customStart}
            max={customEnd}
            onChange={(e) => setCustomStart(e.target.value)}
            className="h-9 w-[150px]"
          />
          <span className="text-xs text-ink-700/40">to</span>
          <Input
            type="date"
            value={customEnd}
            min={customStart}
            onChange={(e) => setCustomEnd(e.target.value)}
            className="h-9 w-[150px]"
          />
        </div>
      )}
    </div>
  );
}
