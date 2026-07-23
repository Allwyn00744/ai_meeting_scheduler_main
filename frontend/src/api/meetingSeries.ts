import { api } from "./client";
import type { Meeting } from "@/types";

export type SeriesCadence = "daily" | "weekly" | "monthly";

export interface MeetingSeriesCreatePayload {
  title: string;
  description?: string | null;
  start_time: string;
  end_time: string;
  location?: string | null;
  resource_id?: number | null;
  external_guest_emails?: string[];
  cadence: SeriesCadence;
  interval?: number;
  occurrence_count: number;
}

export interface MeetingSeries {
  id: number;
  owner_id: number;
  title: string;
  description: string | null;
  location: string | null;
  resource_id: number | null;
  cadence: SeriesCadence;
  interval: number;
  occurrence_count: number;
  created_at: string;
  meetings: Meeting[];
}

export interface SeriesUpdateFromPayload {
  title?: string;
  description?: string | null;
  location?: string | null;
  resource_id?: number | null;
  /** Shifts every selected occurrence's start/end by this many minutes, keeping each one's own date. */
  time_shift_minutes?: number;
}

export const meetingSeriesApi = {
  create: (payload: MeetingSeriesCreatePayload) =>
    api.post<MeetingSeries>("/meeting-series/", payload).then((r) => r.data),

  getById: (id: number) => api.get<MeetingSeries>(`/meeting-series/${id}`).then((r) => r.data),

  updateFrom: (id: number, fromSequence: number, payload: SeriesUpdateFromPayload) =>
    api
      .put<Meeting[]>(`/meeting-series/${id}/from/${fromSequence}`, payload)
      .then((r) => r.data),

  cancelFrom: (id: number, fromSequence: number) =>
    api
      .delete<{ message: string; cancelled_count: number }>(`/meeting-series/${id}/from/${fromSequence}`)
      .then((r) => r.data),
};
