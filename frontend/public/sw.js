// Minimal service worker for Push Notifications V1. Only handles the
// "push" and "notificationclick" events - it deliberately does not
// implement offline caching/precaching, which is out of scope here.

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
  let payload = { title: "AI Meeting Scheduler", body: "" };

  if (event.data) {
    try {
      payload = event.data.json();
    } catch {
      payload.body = event.data.text();
    }
  }

  event.waitUntil(
    self.registration.showNotification(payload.title || "AI Meeting Scheduler", {
      body: payload.body || "",
      data: { url: payload.url || "/" },
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
