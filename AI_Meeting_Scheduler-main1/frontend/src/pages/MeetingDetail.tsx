import * as React from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Pencil, Trash2, Clock, DoorOpen, Sparkles, Mail,
  TriangleAlert, ArrowRight, X, UserPlus, Loader2, ListChecks, Copy,
  Lightbulb, Upload, Check, Video,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input, Textarea } from "@/components/ui/Input";
import { useToast } from "@/components/ui/Toast";
import { meetingsApi } from "@/api/meetings";
import { participantsApi } from "@/api/participants";
import { usersApi } from "@/api/users";
import { meetingIntelligenceApi } from "@/api/meetingIntelligence";
import { meetingNotesApi } from "@/api/meetingNotes";
import { meetingTranscriptApi } from "@/api/meetingTranscript";
import { meetingSummaryApi } from "@/api/meetingSummary";
import { meetingActionItemsApi } from "@/api/meetingActionItems";
import { meetingFollowUpEmailApi } from "@/api/meetingFollowUpEmail";
import { meetingInsightsApi } from "@/api/meetingInsights";
import { aiApi } from "@/api/ai";
import { getApiErrorMessage } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

const TABS = [
  "Details", "Participants", "Meeting Notes", "Transcript Upload", "Meeting Summary", "Notes & Summary", "Action items",
  "AI Action Items", "Follow-up Email", "Meeting Insights",
] as const;

function initialsOf(name: string) {
  const parts = name.trim().split(/\s+/);
  return parts.length === 1 ? parts[0].slice(0, 2).toUpperCase() : (parts[0][0] + parts[1][0]).toUpperCase();
}

export default function MeetingDetail() {
  const { id } = useParams();
  const meetingId = Number(id);
  const navigate = useNavigate();
  const { push } = useToast();
  const { user: me } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = React.useState<(typeof TABS)[number]>("Details");
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const [editOpen, setEditOpen] = React.useState(false);

  const { data: meeting, isLoading, isError, error } = useQuery({
    queryKey: ["meeting", meetingId],
    queryFn: () => meetingsApi.getById(meetingId),
    enabled: Number.isFinite(meetingId),
  });

  const { data: users } = useQuery({ queryKey: ["users"], queryFn: usersApi.list });
  const userMap = React.useMemo(() => new Map((users ?? []).map((u) => [u.id, u])), [users]);

  const deleteMeeting = useMutation({
    mutationFn: () => meetingsApi.remove(meetingId),
    onSuccess: () => {
      push("success", "Meeting cancelled");
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
      navigate("/dashboard");
    },
    onError: (err) => push("error", "Couldn't cancel meeting", getApiErrorMessage(err)),
  });

  if (isLoading) {
    return <div className="mx-auto h-64 max-w-3xl animate-pulse rounded-xl bg-slate-100" />;
  }

  if (isError || !meeting) {
    return (
      <div className="mx-auto max-w-3xl">
        <EmptyState
          icon={<TriangleAlert className="h-5 w-5" />}
          title="Couldn't load this meeting"
          body={getApiErrorMessage(error, "It may not exist, or you may not have access to it.")}
          actionLabel="Back to dashboard"
          onAction={() => navigate("/dashboard")}
        />
      </div>
    );
  }

  const isOwner = meeting.owner_id === me?.id;
  const owner = userMap.get(meeting.owner_id);

  return (
    <div className="mx-auto max-w-3xl">
      <button
        onClick={() => navigate("/dashboard")}
        className="mb-3 flex items-center gap-1 text-xs font-medium text-brand-600 hover:text-brand-700"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> Back to meetings
      </button>

      <div className="mb-2 flex flex-wrap items-start justify-between gap-3">
        <h1 className="text-xl font-bold text-slate-900">{meeting.title}</h1>
        {isOwner && (
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={() => setEditOpen(true)}>
              <Pencil className="h-3.5 w-3.5" /> Edit
            </Button>
            <Button variant="danger" size="sm" onClick={() => setDeleteOpen(true)}>
              <Trash2 className="h-3.5 w-3.5" /> Cancel
            </Button>
          </div>
        )}
      </div>
      <div className="flex items-center gap-2">
        <StatusBadge status={meeting.status} />
        {owner && <span className="text-xs text-slate-400">Organized by {owner.name}</span>}
      </div>

      {meeting.status !== "cancelled" && (
        <button
          onClick={() => navigate(`/meetings/${meeting.id}/reschedule`)}
          className="mt-3 flex w-full items-center justify-between gap-2 rounded-lg bg-slate-50 px-4 py-3 text-left hover:bg-slate-100"
        >
          <span className="flex items-center gap-2 text-sm font-medium text-slate-700">
            <TriangleAlert className="h-4 w-4 text-amber-500" /> Check for a better time / resolve a conflict
          </span>
          <ArrowRight className="h-4 w-4 text-slate-400" />
        </button>
      )}

      <div className="my-4 flex flex-wrap gap-x-6 gap-y-1.5 text-sm text-slate-500">
        <span className="flex items-center gap-1.5">
          <Clock className="h-4 w-4" />
          {new Date(meeting.start_time).toLocaleString(undefined, {
            weekday: "short",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          })}
          {" – "}
          {new Date(meeting.end_time).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
        </span>
        {meeting.location && (
          <span className="flex items-center gap-1.5">
            <DoorOpen className="h-4 w-4" /> {meeting.location}
          </span>
        )}
      </div>

      <div className="mb-5 flex gap-1 overflow-x-auto border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors",
              tab === t ? "border-brand-600 font-medium text-brand-700" : "border-transparent text-slate-500 hover:text-slate-800"
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Details" && (
        <div>
          <p className="mb-1 text-xs font-medium text-slate-500">Description</p>
          <p className="mb-5 text-sm text-slate-800">{meeting.description || "No description provided."}</p>
          {meeting.zoom_join_url && (
            <>
              <p className="mb-2 text-xs font-medium text-slate-500">Zoom Meeting</p>
              <div className="mb-5 flex flex-wrap gap-2">
                <a
                  href={meeting.zoom_join_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700"
                >
                  <Video className="h-3.5 w-3.5" /> Join on Zoom
                </a>
                {isOwner && meeting.zoom_start_url && (
                  <a
                    href={meeting.zoom_start_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <Video className="h-3.5 w-3.5" /> Start as host
                  </a>
                )}
              </div>
            </>
          )}
          {meeting.teams_join_url && (
            <>
              <p className="mb-2 text-xs font-medium text-slate-500">Microsoft Teams Meeting</p>
              <div className="mb-5 flex flex-wrap gap-2">
                <a
                  href={meeting.teams_join_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700"
                >
                  <Video className="h-3.5 w-3.5" /> Join on Teams
                </a>
              </div>
            </>
          )}
          {meeting.external_guests.length > 0 && (
            <>
              <p className="mb-2 text-xs font-medium text-slate-500">External guests</p>
              <div className="flex flex-wrap gap-2">
                {meeting.external_guests.map((g) => (
                  <span key={g.id} className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700">
                    {g.email}
                  </span>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {tab === "Participants" && (
        <ParticipantsTab meetingId={meeting.id} isOwner={isOwner} userMap={userMap} />
      )}

      {tab === "Meeting Notes" && <MeetingNotesTab meetingId={meeting.id} isOwner={isOwner} />}

      {tab === "Transcript Upload" && <TranscriptUploadTab meetingId={meeting.id} isOwner={isOwner} />}

      {tab === "Meeting Summary" && <MeetingSummaryTab meetingId={meeting.id} isOwner={isOwner} />}

      {tab === "Notes & Summary" && <NotesSummaryTab meetingId={meeting.id} />}

      {tab === "Action items" && <ActionItemsTab meetingId={meeting.id} />}

      {tab === "AI Action Items" && <AiActionItemsTab meetingId={meeting.id} isOwner={isOwner} />}

      {tab === "Follow-up Email" && <FollowUpEmailTab meetingId={meeting.id} isOwner={isOwner} />}

      {tab === "Meeting Insights" && <MeetingInsightsTab meetingId={meeting.id} isOwner={isOwner} />}

      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onConfirm={() => {
          setDeleteOpen(false);
          deleteMeeting.mutate();
        }}
        title="Cancel this meeting?"
        description="This permanently deletes the meeting. All participants and any Google Calendar event will be removed."
        confirmLabel="Cancel meeting"
        loading={deleteMeeting.isPending}
      />

      <EditMeetingDialog open={editOpen} onClose={() => setEditOpen(false)} meeting={meeting} />
    </div>
  );
}

// ---------------------------------------------------------------------------

function EditMeetingDialog({
  open,
  onClose,
  meeting,
}: {
  open: boolean;
  onClose: () => void;
  meeting: { id: number; title: string; description: string | null; location: string | null };
}) {
  const { push } = useToast();
  const queryClient = useQueryClient();
  const [title, setTitle] = React.useState(meeting.title);
  const [description, setDescription] = React.useState(meeting.description ?? "");
  const [location, setLocation] = React.useState(meeting.location ?? "");

  React.useEffect(() => {
    setTitle(meeting.title);
    setDescription(meeting.description ?? "");
    setLocation(meeting.location ?? "");
  }, [meeting]);

  const save = useMutation({
    mutationFn: () => meetingsApi.update(meeting.id, { title, description, location }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meeting", meeting.id] });
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
      push("success", "Meeting updated");
      onClose();
    },
    onError: (err) => push("error", "Couldn't update meeting", getApiErrorMessage(err)),
  });

  return (
    <Dialog open={open} onClose={onClose} title="Edit meeting">
      <div className="space-y-3">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Title</label>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Location</label>
          <Input value={location} onChange={(e) => setLocation(e.target.value)} />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Description</label>
          <Textarea className="h-24" value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <Button className="w-full" onClick={() => save.mutate()} loading={save.isPending} disabled={!title.trim()}>
          Save changes
        </Button>
      </div>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------

function ParticipantsTab({
  meetingId,
  isOwner,
  userMap,
}: {
  meetingId: number;
  isOwner: boolean;
  userMap: Map<number, { id: number; name: string; email: string }>;
}) {
  const { push } = useToast();
  const queryClient = useQueryClient();

  const { data: participants, isLoading } = useQuery({
    queryKey: ["participants", meetingId],
    queryFn: () => participantsApi.list(meetingId),
  });

  const removeParticipant = useMutation({
    mutationFn: (participantId: number) => participantsApi.remove(participantId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["participants", meetingId] });
      push("success", "Participant removed");
    },
    onError: (err) => push("error", "Couldn't remove participant", getApiErrorMessage(err)),
  });

  if (isLoading) return <div className="h-32 animate-pulse rounded-xl bg-slate-100" />;

  return (
    <div>
      {isOwner && (
        <div className="relative mb-4">
          <Input
            icon={<UserPlus className="h-4 w-4" />}
            placeholder="Inviting by search isn't available yet"
            disabled
          />
          <p className="mt-1.5 text-xs text-slate-400">
            A team directory isn't available yet, so participants can't be found and invited from here.
          </p>
        </div>
      )}

      {!participants || participants.length === 0 ? (
        <EmptyState icon={<UserPlus className="h-5 w-5" />} title="No participants yet" body="Invite teammates to this meeting." />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200">
          {participants.map((p, i) => {
            const u = userMap.get(p.user_id);
            return (
              <div key={p.id} className={`flex items-center gap-3 px-4 py-3 ${i !== participants.length - 1 ? "border-b border-slate-100" : ""}`}>
                <Avatar initials={u ? initialsOf(u.name) : "?"} size={32} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-900">{u?.name ?? `User #${p.user_id}`}</p>
                  <p className="truncate text-xs text-slate-500">{u?.email}</p>
                </div>
                <StatusBadge status={p.status} />
                {isOwner && (
                  <button onClick={() => removeParticipant.mutate(p.id)} className="text-slate-400 hover:text-red-500">
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------

function MeetingNotesTab({ meetingId, isOwner }: { meetingId: number; isOwner: boolean }) {
  const { push } = useToast();
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = React.useState(false);
  const [draft, setDraft] = React.useState("");
  const [deleteOpen, setDeleteOpen] = React.useState(false);

  const { data: note, isLoading, isError, error } = useQuery({
    queryKey: ["meeting-note", meetingId],
    queryFn: () => meetingNotesApi.get(meetingId),
    retry: false,
  });

  const noteMissing = isError && (error as { response?: { status?: number } })?.response?.status === 404;
  // React Query keeps the last successful `data` around through a
  // subsequent *failed* background refetch (e.g. the refetch after
  // deleting returns 404) instead of clearing it - so `note` alone
  // would still show the just-deleted note. Treat a confirmed-missing
  // note as absent regardless of what's still cached.
  const effectiveNote = noteMissing ? undefined : note;

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["meeting-note", meetingId] });

  const createNote = useMutation({
    mutationFn: () => meetingNotesApi.create(meetingId, { content: draft }),
    onSuccess: () => {
      invalidate();
      setIsEditing(false);
      push("success", "Note saved");
    },
    onError: (err) => push("error", "Couldn't save note", getApiErrorMessage(err)),
  });

  const updateNote = useMutation({
    mutationFn: () => meetingNotesApi.update(meetingId, { content: draft }),
    onSuccess: () => {
      invalidate();
      setIsEditing(false);
      push("success", "Note updated");
    },
    onError: (err) => push("error", "Couldn't update note", getApiErrorMessage(err)),
  });

  const deleteNote = useMutation({
    mutationFn: () => meetingNotesApi.remove(meetingId),
    onSuccess: () => {
      invalidate();
      setDeleteOpen(false);
      setIsEditing(false);
      push("success", "Note deleted");
    },
    onError: (err) => push("error", "Couldn't delete note", getApiErrorMessage(err)),
  });

  if (isLoading) return <div className="h-32 animate-pulse rounded-xl bg-slate-100" />;

  if (isError && !noteMissing) {
    return (
      <EmptyState
        icon={<TriangleAlert className="h-5 w-5" />}
        title="Couldn't load notes"
        body={getApiErrorMessage(error)}
      />
    );
  }

  const startEditing = () => {
    setDraft(effectiveNote?.content ?? "");
    setIsEditing(true);
  };

  if (!isOwner) {
    if (!effectiveNote) {
      return <EmptyState icon={<Pencil className="h-5 w-5" />} title="No notes yet" body="The meeting owner hasn't added notes." />;
    }
    return (
      <div className="rounded-xl border border-slate-200 p-5">
        <p className="whitespace-pre-wrap text-sm text-slate-800">{effectiveNote.content}</p>
        <p className="mt-3 text-xs text-slate-400">Last updated {new Date(effectiveNote.updated_at).toLocaleString()}</p>
      </div>
    );
  }

  if (isEditing) {
    return (
      <div>
        <Textarea
          className="h-40"
          placeholder="Write meeting notes..."
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <div className="mt-3 flex gap-2">
          <Button
            onClick={() => (effectiveNote ? updateNote.mutate() : createNote.mutate())}
            loading={createNote.isPending || updateNote.isPending}
            disabled={!draft.trim()}
          >
            Save
          </Button>
          <Button variant="secondary" onClick={() => setIsEditing(false)}>
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  if (!effectiveNote) {
    return (
      <EmptyState
        icon={<Pencil className="h-5 w-5" />}
        title="No notes yet"
        body="Add notes for this meeting."
        actionLabel="Add notes"
        onAction={startEditing}
      />
    );
  }

  return (
    <div>
      <div className="rounded-xl border border-slate-200 p-5">
        <p className="whitespace-pre-wrap text-sm text-slate-800">{effectiveNote.content}</p>
        <p className="mt-3 text-xs text-slate-400">Last updated {new Date(effectiveNote.updated_at).toLocaleString()}</p>
      </div>
      <div className="mt-3 flex gap-2">
        <Button variant="secondary" size="sm" onClick={startEditing}>
          <Pencil className="h-3.5 w-3.5" /> Edit
        </Button>
        <Button variant="danger" size="sm" onClick={() => setDeleteOpen(true)}>
          <Trash2 className="h-3.5 w-3.5" /> Delete
        </Button>
      </div>

      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onConfirm={() => deleteNote.mutate()}
        title="Delete this note?"
        description="This permanently removes the meeting note."
        confirmLabel="Delete note"
        loading={deleteNote.isPending}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------

const TRANSCRIPT_ACCEPT = ".txt,.pdf,.docx";

function TranscriptUploadTab({ meetingId, isOwner }: { meetingId: number; isOwner: boolean }) {
  const { push } = useToast();
  const queryClient = useQueryClient();
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const [progress, setProgress] = React.useState<number | null>(null);
  const [lastUploadedName, setLastUploadedName] = React.useState<string | null>(null);

  const upload = useMutation({
    mutationFn: (file: File) => meetingTranscriptApi.upload(meetingId, file, setProgress),
    onSuccess: (_data, file) => {
      queryClient.invalidateQueries({ queryKey: ["meeting-note", meetingId] });
      setProgress(null);
      setLastUploadedName(file.name);
      push("success", "Transcript uploaded", "Meeting notes have been updated from the transcript.");
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    onError: (err) => {
      setProgress(null);
      push("error", "Couldn't upload transcript", getApiErrorMessage(err));
    },
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLastUploadedName(null);
    upload.mutate(file);
  };

  if (!isOwner) {
    return (
      <EmptyState
        icon={<Upload className="h-5 w-5" />}
        title="Transcript upload"
        body="Only the meeting owner can upload transcripts. Once uploaded, the transcript replaces this meeting's notes for everyone to see."
      />
    );
  }

  return (
    <div>
      <p className="mb-1 text-xs font-medium text-slate-500">Upload a meeting transcript</p>
      <p className="mb-4 text-sm text-slate-600">
        Supported file types: .txt, .pdf, .docx (max 5 MB). Uploading replaces this meeting's notes with the
        transcript's extracted text, which then feeds the AI Summary, Action Items, Follow-up Email, and Insights tabs.
      </p>

      <input
        ref={fileInputRef}
        type="file"
        accept={TRANSCRIPT_ACCEPT}
        onChange={handleFileChange}
        disabled={upload.isPending}
        className="block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-brand-600 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-brand-700 disabled:opacity-60"
      />

      {upload.isPending && (
        <div className="mt-4">
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full bg-brand-600 transition-all"
              style={{ width: `${progress ?? 0}%` }}
            />
          </div>
          <p className="mt-1.5 text-xs text-slate-400">Uploading... {progress ?? 0}%</p>
        </div>
      )}

      {!upload.isPending && lastUploadedName && (
        <p className="mt-4 flex items-center gap-1.5 text-sm text-emerald-600">
          <Check className="h-4 w-4" /> &ldquo;{lastUploadedName}&rdquo; uploaded — meeting notes updated.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------

function MeetingSummaryTab({ meetingId, isOwner }: { meetingId: number; isOwner: boolean }) {
  const { push } = useToast();
  const queryClient = useQueryClient();

  const { data: summary, isLoading, isError, error } = useQuery({
    queryKey: ["ai-meeting-summary", meetingId],
    queryFn: () => meetingSummaryApi.get(meetingId),
    retry: false,
  });

  const summaryMissing = isError && (error as { response?: { status?: number } })?.response?.status === 404;

  const generateSummary = useMutation({
    mutationFn: () => meetingSummaryApi.generate(meetingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ai-meeting-summary", meetingId] });
      push("success", "Summary generated");
    },
    onError: (err) =>
      push(
        "error",
        "Couldn't generate summary",
        getApiErrorMessage(err, "Add a meeting note first, then try again.")
      ),
  });

  if (isLoading) return <div className="h-32 animate-pulse rounded-xl bg-slate-100" />;

  if (isError && !summaryMissing) {
    return (
      <EmptyState
        icon={<TriangleAlert className="h-5 w-5" />}
        title="Couldn't load summary"
        body={getApiErrorMessage(error)}
      />
    );
  }

  return (
    <div>
      {summary && !summaryMissing ? (
        <div className="rounded-xl bg-brand-50 p-5">
          <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-brand-700">
            <Sparkles className="h-4 w-4" /> AI-generated summary
          </p>
          <p className="whitespace-pre-wrap text-sm text-slate-800">{summary.summary}</p>
          <p className="mt-3 text-xs text-slate-400">
            Last updated {new Date(summary.updated_at).toLocaleString()}
          </p>
        </div>
      ) : (
        <EmptyState
          icon={<Sparkles className="h-5 w-5" />}
          title="No summary yet"
          body={
            isOwner
              ? "Generate an AI summary from this meeting's note."
              : "The meeting owner hasn't generated a summary yet."
          }
        />
      )}

      {isOwner && (
        <div className="mt-3">
          <Button onClick={() => generateSummary.mutate()} loading={generateSummary.isPending}>
            <Sparkles className="h-4 w-4" /> {summary && !summaryMissing ? "Regenerate" : "Generate Summary"}
          </Button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------

function NotesSummaryTab({ meetingId }: { meetingId: number }) {
  const { push } = useToast();
  const queryClient = useQueryClient();
  const [notesDraft, setNotesDraft] = React.useState("");

  const { data: notes } = useQuery({
    queryKey: ["notes", meetingId],
    queryFn: () => meetingIntelligenceApi.getNotes(meetingId),
    retry: false,
  });

  const { data: summary } = useQuery({
    queryKey: ["summary", meetingId],
    queryFn: () => meetingIntelligenceApi.getSummary(meetingId),
    retry: false,
  });

  React.useEffect(() => {
    if (notes) setNotesDraft(notes.content);
  }, [notes]);

  const generateSummary = useMutation({
    mutationFn: () => aiApi.summarizeMeeting(meetingId, notesDraft),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notes", meetingId] });
      queryClient.invalidateQueries({ queryKey: ["summary", meetingId] });
      queryClient.invalidateQueries({ queryKey: ["action-items", meetingId] });
      push("success", "Summary generated");
    },
    onError: (err) =>
      push(
        "error",
        "Couldn't generate summary",
        getApiErrorMessage(err, "The backend's Gemini integration may not be configured (GEMINI_API_KEY).")
      ),
  });

  const [followUp, setFollowUp] = React.useState<{ email_subject: string; email_body: string } | null>(null);
  const generateFollowUp = useMutation({
    mutationFn: () => aiApi.followUp(meetingId, notesDraft || notes?.content || ""),
    onSuccess: (data) => {
      setFollowUp(data);
      push("success", "Follow-up draft ready");
    },
    onError: (err) => push("error", "Couldn't draft follow-up", getApiErrorMessage(err)),
  });

  return (
    <div className="space-y-6">
      <div>
        <p className="mb-1.5 text-xs font-medium text-slate-500">Meeting notes / transcript</p>
        <Textarea
          className="h-32"
          placeholder="Paste your raw meeting notes or transcript here, then generate a summary."
          value={notesDraft}
          onChange={(e) => setNotesDraft(e.target.value)}
        />
        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            onClick={() => generateSummary.mutate()}
            loading={generateSummary.isPending}
            disabled={!notesDraft.trim()}
          >
            <Sparkles className="h-4 w-4" /> Generate summary & action items
          </Button>
          <Button
            variant="secondary"
            onClick={() => generateFollowUp.mutate()}
            loading={generateFollowUp.isPending}
            disabled={!notesDraft.trim() && !notes}
          >
            <Mail className="h-4 w-4" /> Draft follow-up email
          </Button>
        </div>
      </div>

      {summary && (
        <div className="rounded-xl bg-brand-50 p-5">
          <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-brand-700">
            <Sparkles className="h-4 w-4" /> AI-generated summary
          </p>
          <p className="text-sm text-slate-800">{summary.summary}</p>
          <p className="mt-3 text-xs text-slate-400">
            Last updated {new Date(summary.updated_at).toLocaleString()}
          </p>
        </div>
      )}

      {followUp && (
        <div className="rounded-xl border border-slate-200 p-5">
          <p className="mb-1 text-xs font-medium text-slate-500">Subject</p>
          <p className="mb-3 text-sm font-medium text-slate-900">{followUp.email_subject}</p>
          <p className="mb-1 text-xs font-medium text-slate-500">Body</p>
          <p className="whitespace-pre-wrap text-sm text-slate-800">{followUp.email_body}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------

function ActionItemsTab({ meetingId }: { meetingId: number }) {
  const { push } = useToast();
  const queryClient = useQueryClient();

  const { data: items, isLoading } = useQuery({
    queryKey: ["action-items", meetingId],
    queryFn: () => meetingIntelligenceApi.getActionItems(meetingId),
  });

  const toggleStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: "pending" | "completed" }) =>
      meetingIntelligenceApi.updateActionItemStatus(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["action-items", meetingId] }),
    onError: (err) => push("error", "Couldn't update", getApiErrorMessage(err)),
  });

  if (isLoading) return <div className="h-32 animate-pulse rounded-xl bg-slate-100" />;

  if (!items || items.length === 0) {
    return (
      <EmptyState
        icon={<Loader2 className="h-5 w-5" />}
        title="No action items yet"
        body='Generate a summary in the "Notes & Summary" tab — action items are extracted automatically.'
      />
    );
  }

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <label key={item.id} className="flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-2.5">
          <input
            type="checkbox"
            checked={item.status === "completed"}
            onChange={(e) =>
              toggleStatus.mutate({ id: item.id, status: e.target.checked ? "completed" : "pending" })
            }
            className="h-4 w-4 accent-brand-600"
          />
          <div className="flex-1">
            <p className={cn("text-sm", item.status === "completed" ? "text-slate-400 line-through" : "text-slate-800")}>
              {item.task}
            </p>
            <p className="mt-0.5 text-xs text-slate-400">
              {item.assignee ?? "Unassigned"}
              {item.due_date ? ` · Due ${item.due_date}` : ""}
            </p>
          </div>
        </label>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------

const PRIORITY_VARIANT: Record<string, "danger" | "info" | "neutral"> = {
  High: "danger",
  Medium: "info",
  Low: "neutral",
};

function AiActionItemsTab({ meetingId, isOwner }: { meetingId: number; isOwner: boolean }) {
  const { push } = useToast();
  const queryClient = useQueryClient();
  const queryKey = ["ai-action-items", meetingId];

  const { data: items, isLoading, isError, error } = useQuery({
    queryKey,
    queryFn: () => meetingActionItemsApi.list(meetingId),
    retry: false,
  });

  const itemsMissing = isError && (error as { response?: { status?: number } })?.response?.status === 404;

  const invalidate = () => queryClient.invalidateQueries({ queryKey });

  const generate = useMutation({
    mutationFn: () => meetingActionItemsApi.generate(meetingId),
    onSuccess: () => {
      invalidate();
      push("success", "Action items generated");
    },
    onError: (err) =>
      push(
        "error",
        "Couldn't generate action items",
        getApiErrorMessage(err, "Add a meeting note first, then try again.")
      ),
  });

  const toggleStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: "Pending" | "Completed" }) =>
      meetingActionItemsApi.updateStatus(id, status),
    onSuccess: invalidate,
    onError: (err) => push("error", "Couldn't update status", getApiErrorMessage(err)),
  });

  const removeItem = useMutation({
    mutationFn: (id: number) => meetingActionItemsApi.remove(id),
    onSuccess: () => {
      invalidate();
      push("success", "Action item deleted");
    },
    onError: (err) => push("error", "Couldn't delete action item", getApiErrorMessage(err)),
  });

  if (isLoading) return <div className="h-32 animate-pulse rounded-xl bg-slate-100" />;

  if (isError && !itemsMissing) {
    return (
      <EmptyState
        icon={<TriangleAlert className="h-5 w-5" />}
        title="Couldn't load action items"
        body={getApiErrorMessage(error)}
      />
    );
  }

  const effectiveItems = itemsMissing ? [] : (items ?? []);

  return (
    <div>
      {isOwner && (
        <div className="mb-4">
          <Button onClick={() => generate.mutate()} loading={generate.isPending}>
            <Sparkles className="h-4 w-4" /> {effectiveItems.length > 0 ? "Regenerate" : "Generate action items"}
          </Button>
        </div>
      )}

      {effectiveItems.length === 0 ? (
        <EmptyState
          icon={<ListChecks className="h-5 w-5" />}
          title="No action items yet"
          body={
            isOwner
              ? "Generate action items from this meeting's note."
              : "The meeting owner hasn't generated action items yet."
          }
        />
      ) : (
        <div className="space-y-2">
          {effectiveItems.map((item) => (
            <div key={item.id} className="flex items-start gap-3 rounded-lg border border-slate-200 px-3 py-2.5">
              <input
                type="checkbox"
                checked={item.status === "Completed"}
                disabled={!isOwner || toggleStatus.isPending}
                onChange={(e) =>
                  toggleStatus.mutate({
                    id: item.id,
                    status: e.target.checked ? "Completed" : "Pending",
                  })
                }
                className="mt-0.5 h-4 w-4 accent-brand-600"
              />
              <div className="min-w-0 flex-1">
                <p className={cn("text-sm", item.status === "Completed" ? "text-slate-400 line-through" : "text-slate-800")}>
                  {item.task}
                </p>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                  <span>{item.assignee ?? "Unassigned"}</span>
                  {item.due_date && <span>Due {item.due_date}</span>}
                  {item.priority && (
                    <Badge variant={PRIORITY_VARIANT[item.priority] ?? "neutral"}>{item.priority}</Badge>
                  )}
                </div>
              </div>
              {isOwner && (
                <button
                  onClick={() => removeItem.mutate(item.id)}
                  className="text-slate-400 hover:text-red-500"
                  aria-label="Delete action item"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------

function FollowUpEmailTab({ meetingId, isOwner }: { meetingId: number; isOwner: boolean }) {
  const { push } = useToast();
  const queryClient = useQueryClient();
  const queryKey = ["followup-email", meetingId];

  const { data: email, isLoading, isError, error } = useQuery({
    queryKey,
    queryFn: () => meetingFollowUpEmailApi.get(meetingId),
    retry: false,
  });

  const emailMissing = isError && (error as { response?: { status?: number } })?.response?.status === 404;

  const generate = useMutation({
    mutationFn: () => meetingFollowUpEmailApi.generate(meetingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      push("success", "Follow-up email generated");
    },
    onError: (err) =>
      push(
        "error",
        "Couldn't generate follow-up email",
        getApiErrorMessage(err, "Generate a meeting summary first, then try again.")
      ),
  });

  const copyToClipboard = async () => {
    if (!email) return;
    try {
      await navigator.clipboard.writeText(`Subject: ${email.subject}\n\n${email.body}`);
      push("success", "Copied to clipboard");
    } catch {
      push("error", "Couldn't copy to clipboard");
    }
  };

  if (isLoading) return <div className="h-32 animate-pulse rounded-xl bg-slate-100" />;

  if (isError && !emailMissing) {
    return (
      <EmptyState
        icon={<TriangleAlert className="h-5 w-5" />}
        title="Couldn't load follow-up email"
        body={getApiErrorMessage(error)}
      />
    );
  }

  return (
    <div>
      {email && !emailMissing ? (
        <div className="rounded-xl border border-slate-200 p-5">
          <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-brand-700">
            <Mail className="h-4 w-4" /> AI-generated follow-up email
          </p>
          <p className="mb-1 text-xs font-medium text-slate-500">Subject</p>
          <p className="mb-3 text-sm font-medium text-slate-900">{email.subject}</p>
          <p className="mb-1 text-xs font-medium text-slate-500">Body</p>
          <p className="whitespace-pre-wrap text-sm text-slate-800">{email.body}</p>
          <p className="mt-3 text-xs text-slate-400">
            Last updated {new Date(email.updated_at).toLocaleString()}
          </p>
        </div>
      ) : (
        <EmptyState
          icon={<Mail className="h-5 w-5" />}
          title="No follow-up email yet"
          body={
            isOwner
              ? "Generate a follow-up email from this meeting's summary."
              : "The meeting owner hasn't generated a follow-up email yet."
          }
        />
      )}

      <div className="mt-3 flex gap-2">
        {isOwner && (
          <Button onClick={() => generate.mutate()} loading={generate.isPending}>
            <Sparkles className="h-4 w-4" /> {email && !emailMissing ? "Regenerate" : "Generate follow-up email"}
          </Button>
        )}
        {email && !emailMissing && (
          <Button variant="secondary" onClick={copyToClipboard}>
            <Copy className="h-4 w-4" /> Copy
          </Button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

const INSIGHT_STATUS_VARIANT: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  "On Track": "success",
  "At Risk": "warning",
  "Blocked": "danger",
};

function InsightList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium text-slate-500">{title}</p>
      <ul className="list-disc space-y-1 pl-5">
        {items.map((item, i) => (
          <li key={i} className="text-sm text-slate-800">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function MeetingInsightsTab({ meetingId, isOwner }: { meetingId: number; isOwner: boolean }) {
  const { push } = useToast();
  const queryClient = useQueryClient();
  const queryKey = ["meeting-insights", meetingId];

  const { data: insight, isLoading, isError, error } = useQuery({
    queryKey,
    queryFn: () => meetingInsightsApi.get(meetingId),
    retry: false,
  });

  const insightMissing = isError && (error as { response?: { status?: number } })?.response?.status === 404;

  const generate = useMutation({
    mutationFn: () => meetingInsightsApi.generate(meetingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      push("success", "Insights generated");
    },
    onError: (err) =>
      push(
        "error",
        "Couldn't generate insights",
        getApiErrorMessage(err, "Generate a meeting summary first, then try again.")
      ),
  });

  if (isLoading) return <div className="h-32 animate-pulse rounded-xl bg-slate-100" />;

  if (isError && !insightMissing) {
    return (
      <EmptyState
        icon={<TriangleAlert className="h-5 w-5" />}
        title="Couldn't load insights"
        body={getApiErrorMessage(error)}
      />
    );
  }

  return (
    <div>
      {insight && !insightMissing ? (
        <div className="space-y-4 rounded-xl border border-slate-200 p-5">
          <div className="flex items-center justify-between gap-2">
            <p className="flex items-center gap-1.5 text-sm font-semibold text-brand-700">
              <Lightbulb className="h-4 w-4" /> AI-generated insights
            </p>
            <Badge variant={INSIGHT_STATUS_VARIANT[insight.overall_status] ?? "neutral"}>
              {insight.overall_status}
            </Badge>
          </div>
          <InsightList title="Key Points" items={insight.key_points} />
          <InsightList title="Decisions" items={insight.decisions} />
          <InsightList title="Risks" items={insight.risks} />
          <InsightList title="Next Steps" items={insight.next_steps} />
          <p className="text-xs text-slate-400">
            Last updated {new Date(insight.updated_at).toLocaleString()}
          </p>
        </div>
      ) : (
        <EmptyState
          icon={<Lightbulb className="h-5 w-5" />}
          title="No insights yet"
          body={
            isOwner
              ? "Generate AI insights from this meeting's summary."
              : "The meeting owner hasn't generated insights yet."
          }
        />
      )}

      {isOwner && (
        <div className="mt-3">
          <Button onClick={() => generate.mutate()} loading={generate.isPending}>
            <Sparkles className="h-4 w-4" /> {insight && !insightMissing ? "Regenerate" : "Generate insights"}
          </Button>
        </div>
      )}
    </div>
  );
}
