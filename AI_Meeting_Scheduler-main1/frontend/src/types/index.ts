/**
 * TypeScript mirrors of the backend's Pydantic response schemas.
 * Field names and shapes are kept identical to app/schemas/*.py so
 * there is exactly one source of truth to keep in sync.
 */

// ---- auth / users (app/schemas/user.py) ----------------------------------

export interface User {
  id: number;
  name: string;
  email: string;
  timezone: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

// ---- meetings (app/schemas/meeting.py) ------------------------------------

export interface ExternalGuest {
  id: number;
  email: string;
}

export type MeetingStatus = "scheduled" | "cancelled" | "completed" | string;

export interface Meeting {
  id: number;
  title: string;
  description: string | null;
  start_time: string; // ISO 8601
  end_time: string;
  location: string | null;
  status: MeetingStatus;
  owner_id: number;
  resource_id: number | null;
  external_guests: ExternalGuest[];
  // Zoom Meeting Integration V1 only - Google/Outlook provider fields
  // are not exposed by MeetingResponse; see app/schemas/meeting.py.
  zoom_meeting_id: string | null;
  zoom_join_url: string | null;
  // Host-only start link. The backend clears this to null for any
  // viewer who isn't the meeting owner - see
  // MeetingService.get_meeting_by_id.
  zoom_start_url: string | null;
  // Microsoft Teams Integration V1. No teams_meeting_id - a Teams
  // meeting is the existing Outlook event with isOnlineMeeting set,
  // not a separate resource, so there's no second ID to expose.
  teams_join_url: string | null;
}

export interface MeetingCreatePayload {
  title: string;
  description?: string | null;
  start_time: string;
  end_time: string;
  location?: string | null;
  resource_id?: number | null;
  external_guest_emails?: string[];
}

export interface MeetingUpdatePayload {
  title?: string;
  description?: string | null;
  start_time?: string;
  end_time?: string;
  location?: string | null;
  status?: string;
}

// ---- participants (app/schemas/meeting_participant.py) --------------------

export type ParticipantStatus = "Pending" | "Accepted" | "Declined" | string;

export interface Participant {
  id: number;
  meeting_id: number;
  user_id: number;
  status: ParticipantStatus;
  created_at: string;
}

// ---- resources (app/schemas/resource.py) -----------------------------------

export interface Resource {
  id: number;
  name: string;
  resource_type: string;
  description: string | null;
  location: string | null;
  is_active: boolean;
  created_by_id: number;
  created_at: string;
  updated_at: string;
}

export interface ResourceCreatePayload {
  name: string;
  resource_type: string;
  description?: string | null;
  location?: string | null;
}

export interface ResourceUpdatePayload {
  name?: string;
  resource_type?: string;
  description?: string | null;
  location?: string | null;
  is_active?: boolean;
}

// ---- availability (app/schemas/availability.py) ----------------------------

export interface Availability {
  id: number;
  user_id: number;
  day_of_week: string;
  start_time: string; // "HH:MM:SS"
  end_time: string;
  is_available: boolean;
  created_at: string;
}

export interface AvailabilityCreatePayload {
  day_of_week: string;
  start_time: string;
  end_time: string;
  is_available?: boolean;
}

export interface AvailabilityUpdatePayload {
  day_of_week?: string;
  start_time?: string;
  end_time?: string;
  is_available?: boolean;
}

// ---- scheduler (app/schemas/scheduler.py) ----------------------------------

export interface ScheduleMeetingRequest {
  title: string;
  description?: string | null;
  start_time: string;
  end_time: string;
  location?: string | null;
  resource_id?: number | null;
  participant_ids: number[];
  external_guest_emails?: string[];
  repeat?: boolean;
  repeat_type?: "weekly" | null;
  occurrences?: number | null;
}

export interface ScheduleMeetingResponse {
  message: string;
  meeting_ids: number[];
}

export interface SuggestedSlot {
  start_time: string;
  end_time: string;
}

export interface SuggestSlotsResponse {
  slots: SuggestedSlot[];
}

export interface AutoRescheduleResponse {
  meeting: Meeting;
  previous_start_time: string;
  previous_end_time: string;
  new_start_time: string;
  new_end_time: string;
  message: string;
}

// ---- meeting intelligence (app/schemas/meeting_intelligence.py, ai.py) ----

export type ActionItemStatus = "pending" | "completed";

export interface ActionItem {
  id: number;
  meeting_id: number;
  task: string;
  assignee: string | null;
  due_date: string | null;
  status: ActionItemStatus;
  created_at: string;
  updated_at: string;
}

export interface MeetingNotes {
  id: number;
  meeting_id: number;
  content: string;
  created_by_id: number;
  created_at: string;
  updated_at: string;
}

// ---- meeting notes v1, manually authored (app/schemas/meeting_note.py) ----
// Distinct from MeetingNotes above, which is AI transcript/summary-pipeline
// content owned by app/services/meeting_intelligence_service.py.

export interface MeetingNoteRecord {
  id: number;
  meeting_id: number;
  content: string;
  created_by_id: number;
  created_at: string;
  updated_at: string;
}

export interface MeetingNoteCreatePayload {
  content: string;
}

export interface MeetingNoteUpdatePayload {
  content: string;
}

export interface MeetingSummary {
  id: number;
  meeting_id: number;
  summary: string;
  action_items: ActionItem[];
  created_at: string;
  updated_at: string;
}

export interface FollowUpDraft {
  email_subject: string;
  email_body: string;
}

// ---- meeting intelligence v2, AI summary (app/schemas/meeting_summary.py) --
// Sourced from MeetingNoteRecord (Meeting Notes V1), distinct from
// MeetingSummary above, which is sourced from freeform notes text.

export interface AiMeetingSummary {
  id: number;
  meeting_id: number;
  summary: string;
  generated_by_id: number;
  created_at: string;
  updated_at: string;
}

// ---- meeting intelligence v3, AI action item extraction --------------------
// (app/schemas/meeting_action_item.py). Distinct from ActionItem above, which
// is the older AI pipeline's action item (meeting_action_items, keyed off
// meeting_summaries.id). Sourced from MeetingNoteRecord (Meeting Notes V1),
// persisted to a dedicated table, meeting_owner_action_items.

export type OwnerActionItemPriority = "Low" | "Medium" | "High";
export type OwnerActionItemStatus = "Pending" | "Completed";

export interface OwnerActionItem {
  id: number;
  meeting_id: number;
  meeting_note_id: number;
  task: string;
  assignee: string | null;
  due_date: string | null;
  priority: OwnerActionItemPriority | null;
  status: OwnerActionItemStatus;
  created_at: string;
  updated_at: string;
}

// ---- meeting intelligence v4, AI follow-up email --------------------------
// (app/schemas/meeting_followup_email.py). Distinct from FollowUpDraft above,
// which is the older AI pipeline's draft-only follow-up (never persisted).
// Sourced from MeetingNoteRecord (V1) + AiMeetingSummary (V2), persisted to a
// dedicated table, meeting_owner_followup_emails.

export interface MeetingFollowUpEmail {
  id: number;
  meeting_id: number;
  subject: string;
  body: string;
  created_at: string;
  updated_at: string;
}

// ---- meeting intelligence v5, AI meeting insights --------------------------
// (app/schemas/meeting_insight.py). Sourced from MeetingNoteRecord (V1) +
// AiMeetingSummary (V2), optionally informed by V3/V4, persisted to a
// dedicated table, meeting_owner_insights.

export type MeetingInsightStatus = "On Track" | "At Risk" | "Blocked";

export interface MeetingInsight {
  id: number;
  meeting_id: number;
  key_points: string[];
  decisions: string[];
  risks: string[];
  next_steps: string[];
  overall_status: MeetingInsightStatus;
  created_at: string;
  updated_at: string;
}

// ---- google (app/api/google_routes.py) -------------------------------------

export interface GoogleStatus {
  connected: boolean;
}

// ---- outlook (app/api/outlook_routes.py) -----------------------------------

export interface OutlookStatus {
  connected: boolean;
}

// ---- zoom (app/api/zoom_routes.py) -----------------------------------------

export interface ZoomStatus {
  connected: boolean;
}

// ---- microsoft teams (app/api/teams_routes.py) -----------------------------
// "connected" mirrors Outlook's own connection state - there's no
// separate Teams connect/disconnect flow, see teams_routes.py.

export interface TeamsStatus {
  connected: boolean;
}

// ---- generic API error shape (FastAPI's default {"detail": ...}) ----------

export interface ApiErrorBody {
  detail?: string | { msg: string; loc: (string | number)[] }[];
}
