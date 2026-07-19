import { api } from "./client";
import type { WhatsAppStatus } from "@/types";

export interface WhatsAppSettingsUpdatePayload {
  phone_number?: string | null;
  is_enabled?: boolean;
}

export const whatsappApi = {
  status: () => api.get<WhatsAppStatus>("/whatsapp/status").then((r) => r.data),

  updateSettings: (payload: WhatsAppSettingsUpdatePayload) =>
    api.put<WhatsAppStatus>("/whatsapp/settings", payload).then((r) => r.data),

  sendTest: () => api.post<{ message: string }>("/whatsapp/test").then((r) => r.data),
};
