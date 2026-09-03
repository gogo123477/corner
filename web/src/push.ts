/** Web Push subscribe/unsubscribe via the service worker. Returns null when unsupported. */
import { api, API_BASE, getToken } from "./api";

export const pushSupported = () =>
  typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

function urlBase64ToUint8Array(b64: string): ArrayBuffer {
  const padded = (b64 + "=".repeat((4 - (b64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded);
  const buf = new ArrayBuffer(raw.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < raw.length; i++) view[i] = raw.charCodeAt(i);
  return buf;
}

export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!pushSupported()) return null;
  try { return await navigator.serviceWorker.register("/sw.js"); } catch { return null; }
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  const reg = await registerServiceWorker();
  return reg ? reg.pushManager.getSubscription() : null;
}

export async function enablePush(): Promise<"enabled" | "denied" | "unavailable"> {
  const reg = await registerServiceWorker();
  if (!reg) return "unavailable";
  const { key } = await api.vapidPublicKey();
  if (!key) return "unavailable";
  if ((await Notification.requestPermission()) !== "granted") return "denied";
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(key) });
  await fetch(`${API_BASE}/v1/push/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify(sub.toJSON()),
  });
  return "enabled";
}

export async function disablePush(): Promise<void> {
  const sub = await currentSubscription();
  await sub?.unsubscribe();
  await api.pushUnsubscribe();
}
