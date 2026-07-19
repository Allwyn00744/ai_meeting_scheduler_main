import { api } from "./client";
import type { AiMeetingSummary } from "@/types";

export const meetingSummaryApi = {
  generate: (meetingId: number) =>
    api
      .post<AiMeetingSummary>(`/meeting-intelligence/summary/${meetingId}`)
      .then((r) => r.data),

  get: (meetingId: number) =>
    api
      .get<AiMeetingSummary>(`/meeting-intelligence/summary/${meetingId}`)
      .then((r) => r.data),
};
