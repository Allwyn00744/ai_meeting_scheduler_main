import { api } from "./client";
import type { User } from "@/types";

export interface UserUpdatePayload {
  name?: string;
  email?: string;
  timezone?: string;
}

export const usersApi = {
  list: () => api.get<User[]>("/users/").then((r) => r.data),

  getById: (id: number) => api.get<User>(`/users/${id}`).then((r) => r.data),

  update: (id: number, payload: UserUpdatePayload) =>
    api.put<User>(`/users/${id}`, payload).then((r) => r.data),

  updatePassword: (id: number, password: string) =>
    api.put(`/users/${id}/password`, { password }).then((r) => r.data),

  remove: (id: number) => api.delete(`/users/${id}`).then((r) => r.data),
};
