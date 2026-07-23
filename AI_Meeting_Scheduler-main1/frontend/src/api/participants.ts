import { api } from "./client";
import type { Participant } from "@/types";

export const participantsApi = {
  list: (meetingId: number) =>
    api.get<Participant[]>(`/meetings/${meetingId}/participants`).then((r) => r.data),

  add: (meetingId: number, userId: number) =>
    api
      .post<Participant>(`/meetings/${meetingId}/participants`, { user_id: userId })
      .then((r) => r.data),

  updateStatus: (participantId: number, status: string) =>
    api.put<Participant>(`/participants/${participantId}`, { status }).then((r) => r.data),

  remove: (participantId: number) =>
    api.delete(`/participants/${participantId}`).then((r) => r.data),
};
