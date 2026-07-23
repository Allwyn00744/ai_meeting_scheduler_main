import { api } from "./client";
import type {
  MeetingNoteRecord,
  MeetingNoteCreatePayload,
  MeetingNoteUpdatePayload,
} from "@/types";

export const meetingNotesApi = {
  create: (meetingId: number, payload: MeetingNoteCreatePayload) =>
    api
      .post<MeetingNoteRecord>(`/meeting-intelligence/notes/${meetingId}`, payload)
      .then((r) => r.data),

  get: (meetingId: number) =>
    api.get<MeetingNoteRecord>(`/meeting-intelligence/notes/${meetingId}`).then((r) => r.data),

  update: (meetingId: number, payload: MeetingNoteUpdatePayload) =>
    api
      .put<MeetingNoteRecord>(`/meeting-intelligence/notes/${meetingId}`, payload)
      .then((r) => r.data),

  remove: (meetingId: number) =>
    api.delete(`/meeting-intelligence/notes/${meetingId}`).then((r) => r.data),
};
