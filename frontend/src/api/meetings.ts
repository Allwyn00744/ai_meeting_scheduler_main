import { api } from "./client";
import type { Meeting, MeetingCreatePayload, MeetingUpdatePayload } from "@/types";

export const meetingsApi = {
  list: (params?: { limit?: number; offset?: number }) =>
    api.get<Meeting[]>("/meetings/", { params }).then((r) => r.data),

  getById: (id: number) => api.get<Meeting>(`/meetings/${id}`).then((r) => r.data),

  create: (payload: MeetingCreatePayload) =>
    api.post<Meeting>("/meetings/", payload).then((r) => r.data),

  update: (id: number, payload: MeetingUpdatePayload) =>
    api.put<Meeting>(`/meetings/${id}`, payload).then((r) => r.data),

  remove: (id: number) => api.delete(`/meetings/${id}`).then((r) => r.data),

  search: (keyword: string) =>
    api.get<Meeting[]>("/meetings/search", { params: { keyword } }).then((r) => r.data),

  filterByStatus: (status: string) =>
    api.get<Meeting[]>("/meetings/filter/status", { params: { status } }).then((r) => r.data),

  filterByDate: (meeting_date: string) =>
    api.get<Meeting[]>("/meetings/filter/date", { params: { meeting_date } }).then((r) => r.data),

  filterByRange: (start_date: string, end_date: string) =>
    api
      .get<Meeting[]>("/meetings/filter/range", { params: { start_date, end_date } })
      .then((r) => r.data),
};
