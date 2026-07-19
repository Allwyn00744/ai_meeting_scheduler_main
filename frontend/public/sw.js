// Minimal service worker for Push Notifications V1. Only handles the
// "push" and "notificationclick" events - it deliberately does not
// implement offline caching/precaching, which is out of scope here.

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
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(self.clients.openWindow("/"));
});
