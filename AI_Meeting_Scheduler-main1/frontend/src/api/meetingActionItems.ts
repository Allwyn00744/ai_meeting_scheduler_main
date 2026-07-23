import { api } from "./client";
import type { OwnerActionItem, OwnerActionItemStatus } from "@/types";

export const meetingActionItemsApi = {
  generate: (meetingId: number) =>
    api
      .post<OwnerActionItem[]>(`/meeting-intelligence/action-items/${meetingId}`)
      .then((r) => r.data),

  list: (meetingId: number) =>
    api
      .get<OwnerActionItem[]>(`/meeting-intelligence/action-items/${meetingId}`)
      .then((r) => r.data),

  updateStatus: (actionItemId: number, status: OwnerActionItemStatus) =>
    api
      .put<OwnerActionItem>(`/meeting-intelligence/action-items/${actionItemId}`, { status })
      .then((r) => r.data),

  remove: (actionItemId: number) =>
    api.delete(`/meeting-intelligence/action-items/${actionItemId}`).then((r) => r.data),
};
