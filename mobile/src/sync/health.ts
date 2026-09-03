/**
 * Health platform bridge (design §4.4). iOS/HealthKit first; Health Connect is Phase 3.
 *
 * Raw samples never leave the device: we normalize workouts into {date, type, minutes, intensity}
 * and sleep/resting-HR into one number per day before uploading.
 */
import { Platform } from "react-native";
import { api, ActivityIn, isoDate } from "../lib/api";

type Workout = {
  uuid: string;
  startDate: Date;
  endDate: Date;
  workoutActivityType: string;
  totalEnergyBurned?: { quantity: number } | null;
};

function normalizeType(hkType: string): string {
  const t = hkType.toLowerCase();
  if (t.includes("running")) return "run";
  if (t.includes("cycling")) return "cycle";
  if (t.includes("swimming")) return "swim";
  if (t.includes("walking") || t.includes("hiking")) return "walk";
  if (t.includes("strength") || t.includes("functional") || t.includes("crosstraining")) return "strength";
  return "other";
}

/** Intensity from energy per minute — a coarse, stable cut. Real HR-based load is Phase 1. */
function intensity(w: Workout, minutes: number): ActivityIn["intensity"] {
  const kcal = w.totalEnergyBurned?.quantity ?? 0;
  const perMin = minutes > 0 ? kcal / minutes : 0;
  if (perMin >= 10) return "hard";
  if (perMin >= 5) return "moderate";
  return "easy";
}

export async function syncHealth(days = 14): Promise<number> {
  if (Platform.OS !== "ios") return 0;
  // Dynamic import so the JS bundle still loads in Expo Go / simulators without the native module.
  const hk = await import("@kingstinct/react-native-healthkit");
  const ok = await hk.requestAuthorization([
    "HKWorkoutTypeIdentifier",
    "HKCategoryTypeIdentifierSleepAnalysis",
    "HKQuantityTypeIdentifierRestingHeartRate",
  ] as never[]);
  if (!ok) return 0;

  const from = new Date();
  from.setDate(from.getDate() - days);
  const workouts = (await hk.queryWorkoutSamples({ from, limit: 500 } as never)) as unknown as Workout[];

  const activities: ActivityIn[] = workouts.map((w) => {
    const minutes = Math.round((w.endDate.getTime() - w.startDate.getTime()) / 60000);
    return {
      on: isoDate(w.startDate),
      type: normalizeType(w.workoutActivityType),
      duration_min: minutes,
      intensity: intensity(w, minutes),
      source: "healthkit",
      source_ref: w.uuid,
      ts: w.startDate.toISOString(),
    };
  });
  if (activities.length) await api.pushActivities(activities);
  return activities.length;
}
