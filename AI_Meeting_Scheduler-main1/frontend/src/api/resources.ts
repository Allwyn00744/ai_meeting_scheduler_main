import { api } from "./client";
import type { Resource, ResourceCreatePayload, ResourceUpdatePayload } from "@/types";

export const resourcesApi = {
  list: (includeInactive = false) =>
    api
      .get<Resource[]>("/resources/", { params: { include_inactive: includeInactive } })
      .then((r) => r.data),

  getById: (id: number) => api.get<Resource>(`/resources/${id}`).then((r) => r.data),

  create: (payload: ResourceCreatePayload) =>
    api.post<Resource>("/resources/", payload).then((r) => r.data),

  update: (id: number, payload: ResourceUpdatePayload) =>
    api.put<Resource>(`/resources/${id}`, payload).then((r) => r.data),
};
