import { api } from "./client";
import type {
  AutoRescheduleResponse,
  ScheduleMeetingRequest,
  ScheduleMeetingResponse,
  SuggestSlotsResponse,
} from "@/types";

export const schedulerApi = {
  schedule: (payload: ScheduleMeetingRequest) =>
    api.post<ScheduleMeetingResponse>("/scheduler/schedule", payload).then((r) => r.data),

  suggestSlots: (payload: ScheduleMeetingRequest) =>
    api.post<SuggestSlotsResponse>("/scheduler/suggest-slots", payload).then((r) => r.data),

  rescheduleSuggestions: (meetingId: number, windowDays = 7) =>
    api
      .get<SuggestSlotsResponse>(`/scheduler/meetings/${meetingId}/reschedule-suggestions`, {
        params: { window_days: windowDays },
      })
      .then((r) => r.data),

  autoReschedule: (meetingId: number, windowDays = 7) =>
    api
      .post<AutoRescheduleResponse>(
        `/scheduler/meetings/${meetingId}/auto-reschedule`,
        null,
        { params: { window_days: windowDays } }
      )
      .then((r) => r.data),
};
