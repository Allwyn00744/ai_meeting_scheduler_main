import { Search } from "lucide-react";
import { Input, Select } from "@/components/ui/Input";
import type { Resource } from "@/types";

export interface MeetingExplorerFilters {
  search: string;
  status: string;
  resourceId: string;
  meetingType: string;
}

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "scheduled", label: "Scheduled" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
];

const MEETING_TYPE_OPTIONS = [
  { value: "", label: "All types" },
  { value: "virtual", label: "Virtual" },
  { value: "physical", label: "Physical" },
  { value: "internal", label: "Internal only" },
  { value: "external", label: "Has external guests" },
];

/**
 * Filters for the Meeting Explorer table below the charts. Scoped to
 * what's actually meaningful for a single-owner view - every meeting
 * here already belongs to the current user, so there's no
 * organizer/participant/timezone filter (those would only mean
 * something in a cross-user drill-down, which Team Analytics
 * deliberately doesn't expose - see AnalyticsService.get_team_overview).
 */
export function FilterBar({
  filters,
  onChange,
  resources,
}: {
  filters: MeetingExplorerFilters;
  onChange: (filters: MeetingExplorerFilters) => void;
  resources: Resource[];
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="min-w-[200px] flex-1">
        <Input
          icon={<Search className="h-4 w-4" />}
          placeholder="Search by title..."
          value={filters.search}
          onChange={(e) => onChange({ ...filters, search: e.target.value })}
        />
      </div>
      <Select
        className="w-auto"
        value={filters.status}
        onChange={(e) => onChange({ ...filters, status: e.target.value })}
      >
        {STATUS_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </Select>
      <Select
        className="w-auto"
        value={filters.resourceId}
        onChange={(e) => onChange({ ...filters, resourceId: e.target.value })}
      >
        <option value="">All resources</option>
        {resources.map((r) => (
          <option key={r.id} value={String(r.id)}>
            {r.name}
          </option>
        ))}
      </Select>
      <Select
        className="w-auto"
        value={filters.meetingType}
        onChange={(e) => onChange({ ...filters, meetingType: e.target.value })}
      >
        {MEETING_TYPE_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </Select>
    </div>
  );
}

export const DEFAULT_MEETING_EXPLORER_FILTERS: MeetingExplorerFilters = {
  search: "",
  status: "",
  resourceId: "",
  meetingType: "",
};
