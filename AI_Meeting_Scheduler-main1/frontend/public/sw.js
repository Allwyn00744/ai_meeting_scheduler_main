// Minimal Web Push service worker for SCHEDAI Push Notifications.
// Registered by src/api/push.ts (navigator.serviceWorker.register("/sw.js")).
// Scope is "/" (the default for a worker served from the site root), which
// is required for PushManager.subscribe() to receive events regardless of
// which page is open when a push arrives.

self.addEventListener("install", () => {
  // Activate this worker as soon as it finishes installing, without
  // waiting for existing tabs to close - there's no cached content
  // here that an in-flight page load could be relying on.
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  // Payload shape is set server-side in push_client.py:
  // json.dumps({"title": title, "body": body}).
  let data = { title: "SCHEDAI", body: "You have a notification." };
  try {
    if (event.data) {
      data = { ...data, ...event.data.json() };
    }
  } catch {
    // Non-JSON payload (shouldn't happen from this backend) - fall
    // back to the default title/body above rather than failing.
  }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      data: { url: data.url || "/" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = event.notification.data?.url || "/";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && "focus" in client) {
          return client.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })
  );
});
