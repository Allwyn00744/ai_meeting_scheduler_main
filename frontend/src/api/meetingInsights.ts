import { api } from "./client";
import type { MeetingInsight } from "@/types";

export const meetingInsightsApi = {
  generate: (meetingId: number) =>
    api
      .post<MeetingInsight>(`/meeting-intelligence/insights/${meetingId}`)
      .then((r) => r.data),

  get: (meetingId: number) =>
    api
      .get<MeetingInsight>(`/meeting-intelligence/insights/${meetingId}`)
      .then((r) => r.data),
};
