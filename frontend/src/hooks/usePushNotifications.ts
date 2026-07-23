import * as React from "react";
import { pushApi } from "@/api/push";

function detectPushSupport(): boolean {
  if (typeof navigator === "undefined" || typeof window === "undefined") return false;
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

/** Converts a VAPID public key (URL-safe base64) into the Uint8Array PushManager.subscribe() expects. */
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

/**
 * Wraps the browser's Push API (service worker registration +
 * PushManager) for the Push Notifications Settings tab, mirroring
 * useVoiceRecorder's shape: isSupported reflects browser capability up
 * front so callers can show a fallback, and subscribe/unsubscribe throw
 * on failure so callers can surface errors via their own toast/mutation
 * handling instead of this hook owning that UI.
 */
export function usePushNotifications() {
  const isSupported = React.useMemo(detectPushSupport, []);
  const [permission, setPermission] = React.useState<NotificationPermission | "unsupported">(
    isSupported ? Notification.permission : "unsupported"
  );
  const [subscribed, setSubscribed] = React.useState(false);
  const [checking, setChecking] = React.useState(true);

  const refreshSubscription = React.useCallback(async () => {
    if (!isSupported) {
      setChecking(false);
      return;
    }
    try {
      const registration = await navigator.serviceWorker.register("/sw.js");
      const existing = await registration.pushManager.getSubscription();

      if (existing === null) {
        setSubscribed(false);
        return;
      }

      // A browser-side subscription existing is not proof the backend
      // can actually deliver to it - e.g. a prior POST /push/subscribe
      // call failed after the browser already created its local
      // subscription, or the row was since removed. Re-registering
      // here is idempotent (PushSubscriptionRepository.get_by_endpoint
      // updates the existing row rather than duplicating it) and
      // self-heals that mismatch instead of reporting "Subscribed"
      // for an account the backend has nothing on file for.
      const json = existing.toJSON();
      if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
        setSubscribed(false);
        return;
      }

      await pushApi.subscribe({
        endpoint: json.endpoint,
        keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
      });
      setSubscribed(true);
    } catch {
      setSubscribed(false);
    } finally {
      setChecking(false);
    }
  }, [isSupported]);

  React.useEffect(() => {
    refreshSubscription();
  }, [refreshSubscription]);

  const subscribe = async () => {
    if (!isSupported) {
      throw new Error("Push notifications aren't supported in this browser.");
    }

    const permissionResult = await Notification.requestPermission();
    setPermission(permissionResult);
    if (permissionResult !== "granted") {
      throw new Error("Notification permission was not granted.");
    }

    const { vapid_public_key } = await pushApi.vapidPublicKey();
    if (!vapid_public_key) {
      throw new Error("Push notifications are not configured on the server.");
    }

    const registration = await navigator.serviceWorker.register("/sw.js");
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapid_public_key) as BufferSource,
    });

    const json = subscription.toJSON();
    if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
      throw new Error("Couldn't read the browser push subscription.");
    }

    await pushApi.subscribe({
      endpoint: json.endpoint,
      keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
    });

    setSubscribed(true);
  };

  const unsubscribe = async () => {
    if (!isSupported) return;

    const registration = await navigator.serviceWorker.register("/sw.js");
    const subscription = await registration.pushManager.getSubscription();

    if (subscription) {
      await pushApi.unsubscribe(subscription.endpoint);
      await subscription.unsubscribe();
    }

    setSubscribed(false);
  };

  return { isSupported, permission, subscribed, checking, subscribe, unsubscribe };
}
