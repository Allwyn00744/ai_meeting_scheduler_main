import { api } from "./client";
import type { ScheduleMeetingResponse, MeetingSummary, FollowUpDraft } from "@/types";

export const aiApi = {
  scheduleFromText: (text: string) =>
    api.post<ScheduleMeetingResponse>("/ai/schedule-text", { text }).then((r) => r.data),

  /**
   * Uploads a recorded audio blob to POST /ai/schedule-voice. Backend
   * transcribes it via Gemini, then runs it through the same create
   * pipeline as scheduleFromText. Sent as multipart/form-data with
   * field name "audio" - matches the FastAPI UploadFile parameter.
   */
  scheduleFromVoice: (audioBlob: Blob, filename = "recording.webm") => {
    const formData = new FormData();
    formData.append("audio", audioBlob, filename);
    // Deliberately no explicit Content-Type header here - axios must
    // auto-generate "multipart/form-data; boundary=..." from the
    // FormData object itself. Setting one manually strips the
    // boundary parameter and breaks server-side multipart parsing.
    return api
      .post<ScheduleMeetingResponse>("/ai/schedule-voice", formData)
      .then((r) => r.data);
  },

  summarizeMeeting: (meetingId: number, notes: string) =>
    api
      .post<MeetingSummary>(`/ai/meetings/${meetingId}/summary`, { notes })
      .then((r) => r.data),

  followUp: (meetingId: number, notes: string) =>
    api
      .post<FollowUpDraft>(`/ai/meetings/${meetingId}/follow-up`, { notes })
      .then((r) => r.data),
};
