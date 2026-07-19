import { api } from "./client";
import type { MeetingNotes, MeetingSummary, ActionItem, ActionItemStatus } from "@/types";

export const meetingIntelligenceApi = {
  getNotes: (meetingId: number) =>
    api.get<MeetingNotes>(`/meetings/${meetingId}/notes`).then((r) => r.data),

  getSummary: (meetingId: number) =>
    api.get<MeetingSummary>(`/meetings/${meetingId}/summary`).then((r) => r.data),

  getActionItems: (meetingId: number) =>
    api.get<ActionItem[]>(`/meetings/${meetingId}/action-items`).then((r) => r.data),

  updateActionItemStatus: (actionItemId: number, status: ActionItemStatus) =>
    api.patch<ActionItem>(`/action-items/${actionItemId}`, { status }).then((r) => r.data),
};
