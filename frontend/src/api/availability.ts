import { api } from "./client";
import type { Availability, AvailabilityCreatePayload, AvailabilityUpdatePayload } from "@/types";

export const availabilityApi = {
  list: () => api.get<Availability[]>("/availability/").then((r) => r.data),

  create: (payload: AvailabilityCreatePayload) =>
    api.post<Availability>("/availability/", payload).then((r) => r.data),

  update: (id: number, payload: AvailabilityUpdatePayload) =>
    api.put<Availability>(`/availability/${id}`, payload).then((r) => r.data),

  remove: (id: number) => api.delete(`/availability/${id}`).then((r) => r.data),
};
