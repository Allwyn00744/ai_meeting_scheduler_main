import { api } from "./client";

export interface PushStatus {
  enabled: boolean;
  subscription_count: number;
}

/** Converts a base64url-encoded VAPID public key into the byte array PushManager.subscribe() expects. */
function urlBase64ToUint8Array(base64String: string): BufferSource {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray as BufferSource;
}

export const pushApi = {
  vapidPublicKey: () => api.get<{ public_key: string }>("/push/vapid-public-key").then((r) => r.data),

  status: () => api.get<PushStatus>("/push/status").then((r) => r.data),

  subscribe: (subscription: PushSubscription, isEnabled = true) => {
    const json = subscription.toJSON();
    return api
      .post<PushStatus>("/push/subscribe", {
        endpoint: json.endpoint,
        keys: json.keys,
        is_enabled: isEnabled,
      })
      .then((r) => r.data);
  },

  unsubscribe: (endpoint: string) =>
    api.delete<PushStatus>("/push/unsubscribe", { data: { endpoint } }).then((r) => r.data),

  sendTest: () => api.post("/push/test").then((r) => r.data),

  /** True only when this browser can support Web Push at all. */
  isSupported: () =>
    "serviceWorker" in navigator && "PushManager" in window && "Notification" in window,

  /**
   * Registers the service worker (idempotent - browsers reuse an
   * already-registered worker at the same scope), asks for
   * notification permission if needed, subscribes with the server's
   * VAPID public key, and persists the subscription server-side.
   * Throws if permission is denied, the browser lacks support, or the
   * server has no VAPID key configured yet.
   */
  async enable(): Promise<void> {
    if (!pushApi.isSupported()) {
      throw new Error("Push notifications aren't supported in this browser.");
    }

    const { public_key } = await pushApi.vapidPublicKey();
    if (!public_key) {
      throw new Error("Push notifications aren't configured on the server yet.");
    }

    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      throw new Error("Notification permission was not granted.");
    }

    const registration = await navigator.serviceWorker.register("/sw.js");
    await navigator.serviceWorker.ready;

    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(public_key),
      });
    }

    await pushApi.subscribe(subscription);
  },

  /** Unsubscribes this browser both locally and on the server. */
  async disable(): Promise<void> {
    if (!pushApi.isSupported()) return;

    const registration = await navigator.serviceWorker.getRegistration();
    const subscription = await registration?.pushManager.getSubscription();
    if (!subscription) return;

    const endpoint = subscription.endpoint;
    await subscription.unsubscribe();
    await pushApi.unsubscribe(endpoint);
  },
};
