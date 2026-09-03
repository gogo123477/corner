/** Typed client for the Corner backend. Dev auth for now; swap getToken() for the managed-auth session. */
// Same origin in production (Vercel rewrites /v1/* to the Python function); localhost in dev.
export const API_BASE = import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

export function getToken(): string {
  try {
    const t = localStorage.getItem("corner.token");
    if (t) return t;
    const fresh = `dev:${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem("corner.token", fresh);
    return fresh;
  } catch {
    return "dev:anonymous";
  }
}

export type Brief = {
  on: string;
  lines: [string, string, string];
  source: "llm" | "template";
  status: "planned" | "opened" | "done";
  computed_at: string;
};
export type Recommendation = {
  domain: "food" | "training" | "movement";
  value: string;
  reasons: string[];
  rails_applied: string[];
  numbers: Record<string, number>;
};
export type Plan = {
  on: string;
  food: Recommendation;
  training: Recommendation;
  movement: Recommendation;
  training_window: { start: string; end: string } | null;
  ledger: Record<string, unknown>;
};
export type Intensity = "easy" | "moderate" | "hard";
export type ActivityIn = { on: string; type: string; duration_min: number; intensity: Intensity; source?: string };
export type Activity = ActivityIn & { id: string };
export type CalendarEvent = { start: string; end: string; coarse_type: "meeting" | "travel" | "personal" | "blocked" };
export type Profile = {
  goal: "maintain" | "fat_loss" | "build" | "perform";
  weekly_training_target: number;
  baseline_daily_steps: number;
  day_start: string;
  day_end: string;
  coaching_tone: string;
  user_id?: string;
  push_enabled?: boolean;
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}`, ...(init.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail ?? ""; } catch { /* not JSON */ }
    throw new Error(`${init.method ?? "GET"} ${path} failed (${res.status})${detail ? `: ${detail}` : ""}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  brief: (on: string, recompute = false) => request<Brief>(`/v1/brief/${on}${recompute ? "?recompute=true" : ""}`),
  briefOpened: (on: string) => request<Brief>(`/v1/brief/${on}/opened`, { method: "POST" }),
  plan: (on: string, recompute = false) =>
    request<{ on: string; plan: Plan; brief: Brief | null }>(`/v1/plan/${on}${recompute ? "?recompute=true" : ""}`),
  activities: (since: string) => request<Activity[]>(`/v1/activities?since=${since}`),
  addActivity: (a: ActivityIn) =>
    request<{ inserted: number }>(`/v1/activities`, { method: "POST", body: JSON.stringify({ activities: [a] }) }),
  deleteActivity: (id: string) => request<void>(`/v1/activities/${id}`, { method: "DELETE" }),
  recovery: (on: string) => request<{ sleep_hours: number | null }>(`/v1/recovery/${on}`),
  setRecovery: (on: string, sleep_hours: number | null) =>
    request(`/v1/recovery`, { method: "POST", body: JSON.stringify({ on, sleep_hours, resting_hr_delta_bpm: null }) }),
  calendar: (on: string) => request<{ events: CalendarEvent[] }>(`/v1/calendar/${on}`),
  setCalendar: (on: string, events: CalendarEvent[]) =>
    request(`/v1/calendar/${on}`, { method: "PUT", body: JSON.stringify({ events }) }),
  profile: () => request<Profile>(`/v1/profile`),
  setProfile: (p: Profile) => request<Profile>(`/v1/profile`, { method: "PUT", body: JSON.stringify(p) }),
  vapidPublicKey: () => request<{ key: string }>(`/v1/push/vapid-public-key`),
  pushUnsubscribe: () => request<void>(`/v1/push/subscribe`, { method: "DELETE" }),
};

export const isoDate = (d: Date = new Date()) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const daysAgo = (n: number) => { const d = new Date(); d.setDate(d.getDate() - n); return isoDate(d); };
