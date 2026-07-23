import { api } from "./client";
import type { MeetingFollowUpEmail } from "@/types";

export const meetingFollowUpEmailApi = {
  generate: (meetingId: number) =>
    api
      .post<MeetingFollowUpEmail>(`/meeting-intelligence/follow-up/${meetingId}`)
      .then((r) => r.data),

  get: (meetingId: number) =>
    api
      .get<MeetingFollowUpEmail>(`/meeting-intelligence/follow-up/${meetingId}`)
      .then((r) => r.data),
};
