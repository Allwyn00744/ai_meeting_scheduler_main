import * as React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Sparkles, Zap } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import { meetingsApi } from "@/api/meetings";
import { schedulerApi } from "@/api/scheduler";
import { getApiErrorMessage } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";
import type { AutoRescheduleResponse, SuggestedSlot } from "@/types";

function formatDateTime(value: string) {
  return new Date(value).toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Reached from Meeting Detail — uses the real GET /scheduler/meetings/{id}/reschedule-suggestions endpoint. */
export default function RescheduleMeeting() {
  const { id } = useParams();
  const meetingId = Number(id);
  const navigate = useNavigate();
  const { push } = useToast();
  const { user: me } = useAuth();
  const queryClient = useQueryClient();
  const [chosen, setChosen] = React.useState<SuggestedSlot | null>(null);
  const [done, setDone] = React.useState(false);
  const [autoResult, setAutoResult] = React.useState<AutoRescheduleResponse | null>(null);

  const { data: meeting } = useQuery({
    queryKey: ["meeting", meetingId],
    queryFn: () => meetingsApi.getById(meetingId),
    enabled: Number.isFinite(meetingId),
  });

  const {
    data: suggestions,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["reschedule-suggestions", meetingId],
    queryFn: () => schedulerApi.rescheduleSuggestions(meetingId, 7),
    enabled: Number.isFinite(meetingId),
  });

  const isOwner = Boolean(me && meeting && me.id === meeting.owner_id);

  const applyReschedule = useMutation({
    mutationFn: () =>
      meetingsApi.update(meetingId, {
        start_time: chosen!.start_time,
        end_time: chosen!.end_time,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meeting", meetingId] });
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
      setDone(true);
    },
    onError: (err) => push("error", "Couldn't reschedule", getApiErrorMessage(err)),
  });

  const autoResolve = useMutation({
    mutationFn: () => schedulerApi.autoReschedule(meetingId, 7),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["meeting", meetingId] });
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
      queryClient.invalidateQueries({ queryKey: ["kpis"] });
      setAutoResult(result);
      setDone(true);
      push("success", "Meeting rescheduled", result.message);
    },
    onError: (err) => push("error", "Couldn't auto-reschedule", getApiErrorMessage(err)),
  });

  return (
    <div className="mx-auto max-w-lg">
      <button
        onClick={() => navigate(`/meetings/${meetingId}`)}
        className="mb-4 flex items-center gap-1 text-xs font-medium text-brand-600 hover:text-brand-700"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> Back to meeting
      </button>

      {done ? (
        <EmptyState
          icon={<CheckCircle2 className="h-5 w-5" />}
          title="Meeting rescheduled"
          body={
            autoResult
              ? `"${meeting?.title}" moved from ${formatDateTime(autoResult.previous_start_time)} to ${formatDateTime(autoResult.new_start_time)}.`
              : `"${meeting?.title}" has been moved to the new time.`
          }
          actionLabel="Back to meeting"
          onAction={() => navigate(`/meetings/${meetingId}`)}
        />
      ) : isLoading ? (
        <div className="h-48 animate-pulse rounded-xl bg-slate-100" />
      ) : isError ? (
        <EmptyState
          icon={<Sparkles className="h-5 w-5" />}
          title="Couldn't fetch suggestions"
          body={getApiErrorMessage(error)}
        />
      ) : (
        <>
          {isOwner && (
            <Button
              className="mb-4 w-full"
              variant="secondary"
              loading={autoResolve.isPending}
              onClick={() => autoResolve.mutate()}
            >
              <Zap className="mr-1.5 h-4 w-4" />
              {autoResolve.isPending ? "Finding a new time…" : "Auto-resolve for me"}
            </Button>
          )}
          <p className="mb-2 text-xs font-medium text-slate-500">
            AI-suggested times over the next 7 days, checked against your existing meetings
          </p>
          {!suggestions || suggestions.slots.length === 0 ? (
            <EmptyState icon={<Sparkles className="h-5 w-5" />} title="No open slots found" body="Try again later or pick a time manually via Edit on the meeting." />
          ) : (
            <div className="mb-5 space-y-2">
              {suggestions.slots.map((s, i) => (
                <button
                  key={i}
                  onClick={() => setChosen(s)}
                  className={cn(
                    "flex w-full items-center justify-between rounded-lg border px-4 py-3 text-left transition-colors",
                    chosen === s ? "border-brand-500 bg-brand-50" : "border-slate-200 hover:border-slate-300"
                  )}
                >
                  <span className="text-sm text-slate-800">
                    {new Date(s.start_time).toLocaleString(undefined, {
                      weekday: "short",
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                    {" – "}
                    {new Date(s.end_time).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                  </span>
                  {i === 0 && (
                    <span className="rounded-md bg-brand-100 px-2 py-0.5 text-[11px] font-medium text-brand-700">
                      Best match
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
          <Button
            className="w-full"
            disabled={!chosen}
            loading={applyReschedule.isPending}
            onClick={() => applyReschedule.mutate()}
          >
            Reschedule
          </Button>
        </>
      )}
    </div>
  );
}
