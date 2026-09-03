/** Typed client for the Corner backend. One file; keep it boring. */
import * as SecureStore from "expo-secure-store";

export const API_BASE = process.env.EXPO_PUBLIC_API_BASE ?? "http://localhost:8000";

// Phase 0 auth: a dev token. Replace `getToken` with the managed-auth session token (Supabase/Clerk).
export async function getToken(): Promise<string> {
  const existing = await SecureStore.getItemAsync("corner.token");
  if (existing) return existing;
  const fresh = `dev:${Math.random().toString(36).slice(2, 10)}`;
  await SecureStore.setItemAsync("corner.token", fresh);
  return fresh;
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

export type ActivityIn = {
  on: string;
  type: string;
  duration_min: number;
  intensity: "easy" | "moderate" | "hard";
  source: "healthkit" | "health_connect" | "manual";
  source_ref?: string;
  ts?: string;
};

export type CalendarEventIn = {
  start: string;
  end: string;
  coarse_type: "meeting" | "travel" | "personal" | "blocked";
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${init.method ?? "GET"} ${path} → ${res.status}: ${body}`);
  }
  return (await res.json()) as T;
}

export const api = {
  brief: (on: string, recompute = false) =>
    request<Brief>(`/v1/brief/${on}${recompute ? "?recompute=true" : ""}`),
  briefOpened: (on: string) => request<Brief>(`/v1/brief/${on}/opened`, { method: "POST" }),
  plan: (on: string) => request<{ on: string; plan: Plan; brief: Brief | null }>(`/v1/plan/${on}`),
  pushActivities: (activities: ActivityIn[]) =>
    request<{ inserted: number; updated: number }>(`/v1/activities`, {
      method: "POST",
      body: JSON.stringify({ activities }),
    }),
  pushRecovery: (on: string, sleep_hours: number | null, resting_hr_delta_bpm: number | null) =>
    request(`/v1/recovery`, {
      method: "POST",
      body: JSON.stringify({ on, sleep_hours, resting_hr_delta_bpm }),
    }),
  putCalendar: (on: string, events: CalendarEventIn[]) =>
    request<{ events: number }>(`/v1/calendar/${on}`, {
      method: "PUT",
      body: JSON.stringify({ events }),
    }),
  putProfile: (profile: Record<string, unknown>) =>
    request(`/v1/profile`, { method: "PUT", body: JSON.stringify(profile) }),
};

export const isoDate = (d: Date = new Date()) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
