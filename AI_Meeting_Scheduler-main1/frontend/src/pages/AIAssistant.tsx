import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Sparkles, PenSquare, Video, X, Loader2, Mic, Square, RotateCcw } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/Input";
import { useToast } from "@/components/ui/Toast";
import { SuccessDialog } from "@/components/ui/SuccessDialog";
import { usersApi } from "@/api/users";
import { resourcesApi } from "@/api/resources";
import { schedulerApi } from "@/api/scheduler";
import { aiApi } from "@/api/ai";
import { getApiErrorMessage } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import type { SuggestedSlot } from "@/types";
import { cn } from "@/lib/utils";

function toDatetimeLocal(iso: string) {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Splits on commas, trims, drops empties, validates, and deduplicates
// case-insensitively - mirrors the backend's
// normalize_external_guest_emails so the payload sent is already in
// its final form.
function parseGuestEmails(raw: string): { emails: string[]; invalid: string[] } {
  const seen = new Set<string>();
  const emails: string[] = [];
  const invalid: string[] = [];

  for (const rawPart of raw.split(",")) {
    const part = rawPart.trim();
    if (!part) continue;

    if (!EMAIL_REGEX.test(part)) {
      invalid.push(part);
      continue;
    }

    const normalized = part.toLowerCase();
    if (seen.has(normalized)) continue;
    seen.add(normalized);
    emails.push(normalized);
  }

  return { emails, invalid };
}

export default function AIAssistant() {
  const navigate = useNavigate();
  const { push } = useToast();
  const { user } = useAuth();

  const { data: allUsers } = useQuery({ queryKey: ["users"], queryFn: usersApi.list });
  const { data: resources } = useQuery({ queryKey: ["resources"], queryFn: () => resourcesApi.list(false) });

  // --- AI text-to-schedule path (POST /ai/schedule-text) ---
  const [aiText, setAiText] = React.useState("");
  const [aiSubmitting, setAiSubmitting] = React.useState(false);
  const [aiSuccessOpen, setAiSuccessOpen] = React.useState(false);

  const scheduleWithAi = async () => {
    if (!aiText.trim()) {
      push("error", "Describe the meeting first");
      return;
    }
    setAiSubmitting(true);
    try {
      const result = await aiApi.scheduleFromText(aiText);
      push("success", result.message);
      setAiSuccessOpen(true);
    } catch (err) {
      push("error", "Couldn't schedule that meeting", getApiErrorMessage(err));
    } finally {
      setAiSubmitting(false);
    }
  };

  // --- AI voice-to-schedule path (POST /ai/schedule-voice) ---
  const [voiceSubmitting, setVoiceSubmitting] = React.useState(false);
  const [voiceBlob, setVoiceBlob] = React.useState<Blob | null>(null);

  // useVoiceRecorder needs its onStopped callback up front, but that
  // callback needs to call back into the `voice` object the hook
  // itself returns (e.g. voice.reset()) - a ref indirection avoids the
  // circular-definition problem without restructuring the hook.
  const handleVoiceStoppedRef = React.useRef<(blob: Blob) => void>(() => {});
  const voice = useVoiceRecorder((blob) => handleVoiceStoppedRef.current(blob));

  handleVoiceStoppedRef.current = async (blob: Blob) => {
    setVoiceBlob(blob);
    setVoiceSubmitting(true);
    try {
      const result = await aiApi.scheduleFromVoice(blob);
      push("success", result.message);
      voice.reset();
      setVoiceBlob(null);
      setAiSuccessOpen(true);
    } catch (err) {
      push("error", "Couldn't schedule that meeting", getApiErrorMessage(err));
      voice.setState("error");
    } finally {
      setVoiceSubmitting(false);
    }
  };

  const formatElapsed = (s: number) => `0:${String(s).padStart(2, "0")}`;

  // --- Manual scheduling path (POST /scheduler/schedule + /suggest-slots) ---
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [startTime, setStartTime] = React.useState("");
  const [endTime, setEndTime] = React.useState("");
  const [location, setLocation] = React.useState("");
  const [resourceId, setResourceId] = React.useState<string>("");
  const [participantIds, setParticipantIds] = React.useState<number[]>([]);
  const [guestQuery, setGuestQuery] = React.useState("");
  const [guestEmailsInput, setGuestEmailsInput] = React.useState("");
  const [slots, setSlots] = React.useState<SuggestedSlot[] | null>(null);
  const [slotsLoading, setSlotsLoading] = React.useState(false);
  const [manualSubmitting, setManualSubmitting] = React.useState(false);
  const [manualErrors, setManualErrors] = React.useState<Record<string, string>>({});

  const otherUsers = (allUsers ?? []).filter((u) => u.id !== user?.id);
  const filteredUsers = otherUsers.filter(
    (u) =>
      !participantIds.includes(u.id) &&
      (guestQuery.trim() === "" || u.name.toLowerCase().includes(guestQuery.toLowerCase()))
  );

  const buildPayload = () => ({
    title,
    description: description || undefined,
    start_time: startTime ? new Date(startTime).toISOString() : "",
    end_time: endTime ? new Date(endTime).toISOString() : "",
    location: location || undefined,
    resource_id: resourceId ? Number(resourceId) : undefined,
    participant_ids: participantIds,
    external_guest_emails: parseGuestEmails(guestEmailsInput).emails,
  });

  const validateManual = () => {
    const errs: Record<string, string> = {};
    if (!title.trim()) errs.title = "Title is required.";
    if (!startTime) errs.start_time = "Start time is required.";
    if (!endTime) errs.end_time = "End time is required.";
    if (startTime && endTime && new Date(endTime) <= new Date(startTime)) {
      errs.end_time = "End time must be after start time.";
    }
    const { invalid } = parseGuestEmails(guestEmailsInput);
    if (invalid.length > 0) {
      const message = `Invalid email address${invalid.length > 1 ? "es" : ""}: ${invalid.join(", ")}`;
      errs.guest_emails = message;
      push("error", "Fix the external guest emails", message);
    }
    setManualErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const fetchSuggestions = async () => {
    if (!validateManual()) return;
    setSlotsLoading(true);
    try {
      const result = await schedulerApi.suggestSlots(buildPayload());
      setSlots(result.slots);
      if (result.slots.length === 0) {
        push("info", "No open slots found", "Try widening the time range or removing a participant.");
      }
    } catch (err) {
      push("error", "Couldn't fetch suggestions", getApiErrorMessage(err));
    } finally {
      setSlotsLoading(false);
    }
  };

  const bookMeeting = async () => {
    if (!validateManual()) return;
    setManualSubmitting(true);
    try {
      const result = await schedulerApi.schedule(buildPayload());
      push("success", result.message);
      setGuestEmailsInput("");
      navigate(`/meetings/${result.meeting_ids[0]}`);
    } catch (err) {
      push("error", "Couldn't book this meeting", getApiErrorMessage(err));
    } finally {
      setManualSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <h1 className="text-[28px] font-bold text-ink-700">Schedule a meeting</h1>
        <p className="mt-1 text-sm text-ink-700/60">Describe it in plain language, or fill the form manually.</p>
      </div>

      <Card className="mb-6">
        <div className="flex items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
              <Sparkles className="h-4 w-4" />
            </div>
            <p className="font-semibold text-ink-700">Schedule with AI</p>
          </div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-700/40">Natural language entry</p>
        </div>
        <div className="px-6 pb-6">
          <Textarea
            className="h-28 border-0 bg-cream-100 focus:bg-white"
            placeholder="e.g., 'Schedule a 30-minute sync with the Design Team on Tuesday afternoon between 2 PM and 5 PM.'"
            value={aiText}
            onChange={(e) => setAiText(e.target.value)}
          />
          <div className="mt-4 flex justify-end">
            <Button onClick={scheduleWithAi} loading={aiSubmitting}>
              <Sparkles className="h-4 w-4" /> Parse & schedule with AI
            </Button>
          </div>
          <p className="mt-2 text-xs text-ink-700/40">
            Requires the backend's Gemini integration to be configured (GEMINI_API_KEY); returns 503 otherwise.
          </p>
        </div>
      </Card>

      <div className="mb-6 flex items-center gap-3">
        <div className="h-px flex-1 bg-slate-200" />
        <span className="text-xs font-medium text-ink-700/40">OR</span>
        <div className="h-px flex-1 bg-slate-200" />
      </div>

      <Card className="mb-6">
        <div className="flex items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
              <Mic className="h-4 w-4" />
            </div>
            <p className="font-semibold text-ink-700">Schedule by voice</p>
          </div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-700/40">Spoken request</p>
        </div>

        {!voice.isSupported ? (
          <div className="px-6 pb-6 text-center">
            <p className="text-sm text-ink-700/60">
              Voice input isn't supported in this browser. Try Chrome, Edge, or Firefox — or use the text box above instead.
            </p>
          </div>
        ) : (
          <div className="px-6 pb-8 pt-2 text-center">
            {voice.state === "idle" && (
              <>
                <button
                  onClick={voice.start}
                  className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-brand-500 text-ink-700 transition hover:bg-brand-600"
                >
                  <Mic className="h-6 w-6 text-white" />
                </button>
                <p className="text-sm text-ink-700/60">Tap to schedule a meeting by voice</p>
                <p className="mt-1 text-xs text-ink-700/40">
                  e.g. "Schedule a product meeting tomorrow at 11 AM with the engineering team"
                </p>
              </>
            )}

            {voice.state === "recording" && (
              <>
                <p className="mb-3 text-xs font-medium text-red-600">
                  Recording — {formatElapsed(voice.elapsedSeconds)} / {formatElapsed(voice.maxRecordingSeconds)}
                </p>
                <div className="mx-auto mb-4 flex items-center justify-center gap-3">
                  <button
                    onClick={voice.discard}
                    className="flex h-11 w-11 items-center justify-center rounded-full border border-slate-200 text-ink-700/60 transition hover:bg-cream-100"
                    title="Discard recording"
                  >
                    <X className="h-4 w-4" />
                  </button>
                  <button
                    onClick={voice.stop}
                    className="flex h-16 w-16 items-center justify-center rounded-full bg-red-600 transition hover:bg-red-700"
                  >
                    <Square className="h-5 w-5 fill-white text-white" />
                  </button>
                </div>
                <p className="text-sm text-ink-700/60">Tap the square to stop and schedule, or the X to discard</p>
              </>
            )}

            {(voice.state === "processing" || voiceSubmitting) && (
              <>
                <Loader2 className="mx-auto mb-4 h-8 w-8 animate-spin text-brand-700" />
                <p className="text-sm text-ink-700/60">Transcribing and scheduling...</p>
              </>
            )}

            {voice.state === "error" && (
              <div className="mx-auto max-w-sm">
                <p className="mb-4 text-sm text-red-600">{voice.error ?? "Something went wrong with that recording."}</p>
                <Button
                  variant="secondary"
                  onClick={() => {
                    voice.reset();
                    setVoiceBlob(null);
                  }}
                >
                  <RotateCcw className="h-3.5 w-3.5" /> Try again
                </Button>
              </div>
            )}

            {voiceBlob && voice.state === "idle" && (
              <p className="mt-4 text-center text-xs text-ink-700/40">Last recording sent — {Math.round(voiceBlob.size / 1024)} KB</p>
            )}
          </div>
        )}
      </Card>

      <div className="mb-6 flex items-center gap-3">
        <div className="h-px flex-1 bg-slate-200" />
        <span className="text-xs font-medium text-ink-700/40">OR</span>
        <div className="h-px flex-1 bg-slate-200" />
      </div>

      <Card>
        <div className="flex items-center gap-2.5 px-6 py-4">
          <PenSquare className="h-4 w-4 text-ink-700/60" />
          <p className="font-semibold text-ink-700">Fill Manually</p>
        </div>
        <div className="grid grid-cols-1 gap-x-8 gap-y-4 px-6 pb-6 md:grid-cols-2">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink-700">Meeting Title</label>
            <Input
              placeholder="Design Review"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              error={manualErrors.title}
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink-700">Location</label>
            <Input
              icon={<Video className="h-4 w-4" />}
              placeholder="Google Meet, Zoom, or Office Room"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink-700">Start</label>
            <Input
              type="datetime-local"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              error={manualErrors.start_time}
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink-700">End</label>
            <Input
              type="datetime-local"
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
              error={manualErrors.end_time}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink-700">Resource (optional)</label>
            <select
              className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm focus-ring"
              value={resourceId}
              onChange={(e) => setResourceId(e.target.value)}
            >
              <option value="">None</option>
              {(resources ?? []).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink-700">Description</label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Agenda / notes" />
          </div>

          <div className="md:col-span-2">
            <label className="mb-1.5 block text-sm font-medium text-ink-700">Participants</label>
            <div className="relative rounded-lg border border-slate-200 bg-white p-2">
              <div className="flex flex-wrap items-center gap-1.5">
                {participantIds.map((id) => {
                  const u = otherUsers.find((x) => x.id === id);
                  if (!u) return null;
                  return (
                    <span
                      key={id}
                      className="flex items-center gap-1 rounded-full bg-cream-100 py-1 pl-2.5 pr-1.5 text-xs font-medium text-ink-700"
                    >
                      {u.name}
                      <button
                        onClick={() => setParticipantIds((prev) => prev.filter((x) => x !== id))}
                        className="rounded-full p-0.5 hover:bg-slate-200"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  );
                })}
                <input
                  className="min-w-[140px] flex-1 border-0 text-sm outline-none placeholder:text-ink-700/40"
                  placeholder="Search teammates..."
                  value={guestQuery}
                  onChange={(e) => setGuestQuery(e.target.value)}
                />
              </div>
              {guestQuery && filteredUsers.length > 0 && (
                <div className="absolute left-0 right-0 top-full z-10 mt-1 max-h-48 overflow-auto rounded-lg border border-slate-200 bg-white shadow-lg">
                  {filteredUsers.map((u) => (
                    <button
                      key={u.id}
                      className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-cream-100"
                      onClick={() => {
                        setParticipantIds((prev) => [...prev, u.id]);
                        setGuestQuery("");
                      }}
                    >
                      <span className="font-medium text-ink-700">{u.name}</span>
                      <span className="text-xs text-ink-700/40">{u.email}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="md:col-span-2">
            <label className="mb-1.5 block text-sm font-medium text-ink-700">
              External guest emails (optional)
            </label>
            <Input
              placeholder="guest1@example.com, guest2@example.com"
              value={guestEmailsInput}
              onChange={(e) => setGuestEmailsInput(e.target.value)}
              error={manualErrors.guest_emails}
            />
            <p className="mt-1 text-xs text-ink-700/40">
              Separate multiple addresses with commas. These guests don't need an account.
            </p>
          </div>
        </div>

        {slots && (
          <div className="border-t border-slate-100 px-6 py-5">
            <p className="mb-2 text-xs font-medium text-ink-700/60">AI-suggested slots (from your + participants' availability)</p>
            {slots.length === 0 ? (
              <p className="text-sm text-ink-700/40">No open slots found in this window.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {slots.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      setStartTime(toDatetimeLocal(s.start_time));
                      setEndTime(toDatetimeLocal(s.end_time));
                    }}
                    className={cn(
                      "flex items-center justify-between rounded-lg border px-3 py-2 text-left transition-colors",
                      "border-slate-200 hover:border-brand-400 hover:bg-brand-50"
                    )}
                  >
                    <span className="text-sm text-ink-700">
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
                    <span className="text-xs font-medium text-brand-700">Use this time</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-end gap-3 border-t border-slate-100 px-6 py-4">
          <Button variant="secondary" onClick={fetchSuggestions} loading={slotsLoading}>
            {slotsLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Suggest slots
          </Button>
          <Button onClick={bookMeeting} loading={manualSubmitting}>
            Book Meeting
          </Button>
        </div>
      </Card>

      <SuccessDialog
        open={aiSuccessOpen}
        onClose={() => {
          setAiSuccessOpen(false);
          navigate("/dashboard");
        }}
        title="Meeting scheduled"
        description="The AI assistant parsed your request and booked the meeting."
        actionLabel="Back to dashboard"
      />
    </div>
  );
}
