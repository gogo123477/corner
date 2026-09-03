/* Corner service worker: shows the morning-brief push and opens the app on tap. */
self.addEventListener("push", (event) => {
  let data = { title: "Corner", body: "Your day, in three lines.", url: "/" };
  try { data = { ...data, ...event.data.json() }; } catch { /* plain-text payload */ }
  event.waitUntil(
    self.registration.showNotification(data.title, { body: data.body, icon: "/icon.svg", data: { url: data.url } }),
  );
});
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      const open = list.find((c) => "focus" in c);
      return open ? open.focus() : self.clients.openWindow(event.notification.data?.url ?? "/");
    }),
  );
});
