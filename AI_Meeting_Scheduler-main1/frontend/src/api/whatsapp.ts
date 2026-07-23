import { api } from "./client";

export interface WhatsAppStatus {
  enabled: boolean;
  phone_number: string | null;
}

export const whatsappApi = {
  status: () => api.get<WhatsAppStatus>("/whatsapp/status").then((r) => r.data),

  /**
   * Saves (or updates) the current user's WhatsApp number and opt-in
   * flag. There is no OAuth flow for WhatsApp (unlike Google/Outlook) -
   * the phone number comes straight from the Settings form. Fields
   * are patched independently server-side: omit one to leave it
   * unchanged.
   */
  saveSettings: (payload: { phone_number?: string; is_enabled?: boolean }) =>
    api.put<WhatsAppStatus>("/whatsapp/settings", payload).then((r) => r.data),

  sendTest: () => api.post("/whatsapp/test").then((r) => r.data),
};
