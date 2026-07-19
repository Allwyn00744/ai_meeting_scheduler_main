import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Clock, Trash2, Globe, Zap, Timer } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import { availabilityApi } from "@/api/availability";
import { getApiErrorMessage } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import type { Availability as AvailabilityRow } from "@/types";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export default function Availability() {
  const { push } = useToast();
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const { data: rows, isLoading } = useQuery({
    queryKey: ["availability"],
    queryFn: availabilityApi.list,
  });

  const createRow = useMutation({
    mutationFn: (day: string) =>
      availabilityApi.create({ day_of_week: day, start_time: "09:00:00", end_time: "17:00:00", is_available: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["availability"] });
      push("success", "Day added");
    },
    onError: (err) => push("error", "Couldn't add day", getApiErrorMessage(err)),
  });

  const updateRow = useMutation({
    mutationFn: ({ id, ...payload }: Partial<AvailabilityRow> & { id: number }) =>
      availabilityApi.update(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["availability"] }),
    onError: (err) => push("error", "Couldn't update", getApiErrorMessage(err)),
  });

  const deleteRow = useMutation({
    mutationFn: (id: number) => availabilityApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["availability"] });
      push("success", "Day removed");
    },
    onError: (err) => push("error", "Couldn't remove day", getApiErrorMessage(err)),
  });

  const daysConfigured = new Set((rows ?? []).map((r) => r.day_of_week));
  const missingDays = DAYS.filter((d) => !daysConfigured.has(d));
  const activeDays = (rows ?? []).filter((r) => r.is_available).map((r) => r.day_of_week.slice(0, 3));

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6">
        <h1 className="text-[28px] font-bold text-ink-700">Availability</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-700/60">
          Set the hours you're open to being scheduled by the AI and external stakeholders. These rules govern
          your primary calendar rhythm.
        </p>
      </div>

      <div className="mb-4 flex items-center justify-between rounded-2xl bg-white p-5 shadow-card">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-100 text-brand-700">
            <Globe className="h-4.5 w-4.5" />
          </div>
          <div>
            <p className="font-semibold text-ink-700">Timezone</p>
            <p className="text-sm text-ink-700/60">
              Your current timezone is <span className="font-medium text-brand-700">{user?.timezone ?? "UTC"}</span>
            </p>
          </div>
        </div>
        <Button variant="secondary" size="sm" disabled title="Change timezone from Settings">
          Change
        </Button>
      </div>

      <div className="mb-4 overflow-hidden rounded-2xl bg-white shadow-card">
        <div className="flex items-center justify-between px-6 py-4">
          <p className="font-semibold text-ink-700">Weekly Schedule</p>
          <div className="flex items-center gap-2">
            {activeDays.length > 0 && (
              <span className="rounded-full bg-brand-100 px-3 py-1 text-xs font-medium text-brand-800">
                Active: {activeDays.join("-")}
              </span>
            )}
            {missingDays.length > 0 && (
              <select
                className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs text-ink-700"
                value=""
                onChange={(e) => {
                  if (e.target.value) createRow.mutate(e.target.value);
                }}
              >
                <option value="">+ Add a day...</option>
                {missingDays.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        {isLoading ? (
          <div className="p-6">
            <div className="h-32 animate-pulse rounded-lg bg-cream-100" />
          </div>
        ) : !rows || rows.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={<Clock className="h-5 w-5" />}
              title="No availability set"
              body="Add days you're open to being scheduled."
              actionLabel="Add Monday"
              onAction={() => createRow.mutate("Monday")}
            />
          </div>
        ) : (
          rows.map((row, i) => (
            <div
              key={row.id}
              className={`flex flex-wrap items-center gap-3 px-6 py-4 ${
                i !== rows.length - 1 ? "border-b border-slate-100" : ""
              } ${!row.is_available ? "bg-cream-50/60" : ""}`}
            >
              <span className={`w-24 text-sm font-medium ${row.is_available ? "text-ink-700" : "text-ink-700/30"}`}>
                {row.day_of_week}
              </span>
              {row.is_available ? (
                <>
                  <Input
                    type="time"
                    defaultValue={row.start_time.slice(0, 5)}
                    className="h-9 w-32"
                    onBlur={(e) =>
                      e.target.value &&
                      updateRow.mutate({ id: row.id, start_time: `${e.target.value}:00` })
                    }
                  />
                  <span className="text-sm text-ink-700/40">to</span>
                  <Input
                    type="time"
                    defaultValue={row.end_time.slice(0, 5)}
                    className="h-9 w-32"
                    onBlur={(e) =>
                      e.target.value && updateRow.mutate({ id: row.id, end_time: `${e.target.value}:00` })
                    }
                  />
                </>
              ) : (
                <span className="text-sm text-ink-700/40">Unavailable for scheduling</span>
              )}
              <button onClick={() => deleteRow.mutate(row.id)} className="text-ink-700/30 hover:text-red-500">
                <Trash2 className="h-4 w-4" />
              </button>
              <div className="ml-auto flex items-center gap-2">
                <span className="text-sm text-ink-700/60">{row.is_available ? "Available" : "Unavailable"}</span>
                <Switch
                  checked={row.is_available}
                  onCheckedChange={(v) => updateRow.mutate({ id: row.id, is_available: v })}
                />
              </div>
            </div>
          ))
        )}

        {rows && rows.length > 0 && (
          <div className="flex items-center justify-between border-t border-slate-100 bg-cream-50 px-6 py-4">
            <button
              className="text-sm text-ink-700/50 hover:text-ink-700"
              onClick={() => push("info", "Nothing to reset", "Remove days individually with the trash icon.")}
            >
              Reset Defaults
            </button>
            <Button onClick={() => push("success", "Schedule saved", "Your availability is up to date.")}>
              Save Schedule
            </Button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-2xl bg-white p-5 shadow-card">
          <div className="mb-1 flex items-center gap-2">
            <Zap className="h-4 w-4 text-brand-600" />
            <p className="font-semibold text-ink-700">Buffer Times</p>
          </div>
          <p className="text-sm text-ink-700/60">
            Automatically add breaks before or after your meetings to avoid fatigue.
          </p>
        </div>
        <div className="rounded-2xl bg-white p-5 shadow-card">
          <div className="mb-1 flex items-center gap-2">
            <Timer className="h-4 w-4 text-brand-600" />
            <p className="font-semibold text-ink-700">Meeting Limits</p>
          </div>
          <p className="text-sm text-ink-700/60">
            Set a daily cap to prevent back-to-back burnout and preserve deep work.
          </p>
        </div>
      </div>
    </div>
  );
}
