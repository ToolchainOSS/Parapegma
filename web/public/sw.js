// Service Worker for Flow Research PWA

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let payload = { title: "Flow Research", body: "You have a new message." };
  try {
    if (event.data) {
      payload = event.data.json();
    }
  } catch {
    // fallback to default payload
  }

  // Handle dismiss action (sync across devices)
  if (payload.data?.action === "dismiss" && payload.data?.notification_id) {
    event.waitUntil(
      self.registration.getNotifications().then((notifications) => {
        for (const notification of notifications) {
          // Check if this is the notification to dismiss
          if (notification.data && notification.data.notification_id === payload.data.notification_id) {
            notification.close();
          }
        }
      })
    );
    return;
  }

  // Build notification data, merging top-level url and nested data fields
  const notificationData = {
    ...(payload.data || {}),
    url: payload.url || payload.data?.url || null,
    project_id: payload.data?.project_id || null,
    notification_id: payload.data?.notification_id || null,
  };

  // Try to extract project_id from url if not explicitly provided
  if (!notificationData.project_id && notificationData.url) {
    const urlMatch = notificationData.url.match(/\/p\/([^/]+)/);
    if (urlMatch) {
      notificationData.project_id = urlMatch[1];
    }
  }

  // Show notification
  event.waitUntil(
    self.registration.showNotification(payload.title || "Flow Research", {
      body: payload.body || "",
      icon: payload.icon || "/icons/icon-192.png",
      data: notificationData,
      actions: payload.actions || [],
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const data = event.notification.data || {};
  const projectId = data.project_id;
  const notificationId = data.notification_id;

  if (event.action) {
    event.waitUntil(
      fetch("/api/chat/events/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          action_id: event.action,
          notification_id: notificationId,
          project_id: projectId,
        }),
      }).catch((err) => console.error("Feedback sync failed:", err)),
    );
    return;
  }

  // Build deep-link URL
  let urlPath;
  if (data.url) {
    urlPath = data.url;
  } else if (projectId && notificationId) {
    urlPath = `/p/${projectId}/chat?nid=${notificationId}`;
  } else if (projectId) {
    urlPath = `/p/${projectId}/chat`;
  } else {
    urlPath = "/dashboard";
  }

  // Resolve to absolute URL for proper comparison
  const target = new URL(urlPath, self.location.origin).href;

  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clients) => {
        // Try to focus existing window with matching URL
        for (const client of clients) {
          if (client.url === target && "focus" in client) {
            return client.focus();
          }
        }
        // Try to navigate an existing window to the target
        for (const client of clients) {
          if ("navigate" in client && "focus" in client) {
            return client.navigate(target).then((c) => c && c.focus());
          }
        }
        // If not found, open new
        if (self.clients.openWindow) {
          return self.clients.openWindow(target);
        }
      }),
  );
});
