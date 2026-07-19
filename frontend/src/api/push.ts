import { api } from "./client";
import type { PushStatus, PushSubscribePayload } from "@/types";

export const pushApi = {
  status: () => api.get<PushStatus>("/push/status").then((r) => r.data),

  vapidPublicKey: () =>
    api
      .get<{ vapid_public_key: string | null }>("/push/vapid-public-key")
      .then((r) => r.data),

  subscribe: (payload: PushSubscribePayload) =>
    api.post<PushStatus>("/push/subscribe", payload).then((r) => r.data),

  unsubscribe: (endpoint: string) =>
    api.delete<PushStatus>("/push/unsubscribe", { data: { endpoint } }).then((r) => r.data),

  sendTest: () => api.post<{ message: string }>("/push/test").then((r) => r.data),
};
