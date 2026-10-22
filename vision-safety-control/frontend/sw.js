/* 서비스 워커: 서버가 보낸 웹 푸시(backend/app/push.py)를 알림으로 띄우고, 누르면 그 이벤트 화면을 연다.
   화면을 모두 닫아 둬도 브라우저(휴대폰은 OS)가 이 파일을 깨워서 알림을 띄운다.
   사이트 전체(/)를 맡도록 맨 위 폴더에 둔다. 화면 파일은 따로 캐시하지 않는다 (늘 서버에서 새로 받음). */

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { body: event.data ? event.data.text() : "" };
  }
  const high = data.severity === "HIGH";
  event.waitUntil(self.registration.showNotification(data.title || "안전관제 알림", {
    body: data.body || "",
    tag: data.tag,                 // 같은 이벤트 알림은 하나로 바꿔 띄운다
    renotify: Boolean(data.tag),
    icon: "/icons/icon-192.png",
    badge: "/icons/badge-96.png",  // 안드로이드 상태 표시줄 (흰색 모양만 씀)
    image: data.image || undefined, // 스냅샷 (안드로이드 크롬은 크게 보여 줌)
    requireInteraction: high,      // 심각도 높음은 누르거나 닫을 때까지 남는다 (PC)
    vibrate: high ? [300, 100, 300, 100, 300] : [200],
    data: { url: data.url || "/monitor.html" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/monitor.html", self.location.origin).href;
  event.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const same = wins.find((w) => w.url === url);
    if (same) return same.focus();
    const any = wins.find((w) => "navigate" in w);
    if (any) {
      await any.focus();
      return any.navigate(url);
    }
    return self.clients.openWindow(url);
  })());
});
