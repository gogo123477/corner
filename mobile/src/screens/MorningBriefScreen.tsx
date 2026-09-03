import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { api, Brief, isoDate, Plan } from "../lib/api";
import { syncTodayCalendar } from "../sync/calendar";
import { syncHealth } from "../sync/health";

const REASON_TEXT: Record<string, string> = {
  HARD_SESSION_YESTERDAY: "Yesterday was a hard session",
  CONSECUTIVE_HARD_DAYS: "Two or more hard days in a row",
  NO_REST_DAY_RECENTLY: "No rest day in about a week",
  SHORT_SLEEP: "Sleep was under six hours",
  ELEVATED_RESTING_HR: "Resting heart rate is above your baseline",
  WELL_RESTED: "Recovery looks good",
  BEHIND_WEEKLY_TARGET: "Behind on this week's sessions",
  ON_TRACK_WEEKLY_TARGET: "On track this week",
  WEEKLY_TARGET_MET: "This week's sessions are done",
  NO_TRAINING_WINDOW: "No free slot long enough today",
  TIGHT_TRAINING_WINDOW: "Only a short free slot today",
  TRAINING_WINDOW_FOUND: "There is a good slot today",
  HEAVY_MEETING_DAY: "Six or more hours of meetings",
  TRAVEL_DAY: "Travelling today",
  FUEL_FOR_TRAINING: "Today's session needs fuel",
  REFUEL_AFTER_HARD_SESSION: "Yesterday's effort needs refuelling",
  STRENGTH_DAY_PROTEIN: "Strength day: protein first",
  LOW_MOVEMENT_DAY: "A desk-bound day",
  DEFAULT_STEADY: "An ordinary day",
  FIRST_DAY_BACK: "First day back after a break",
  RAIL_MAX_CONSECUTIVE_HARD: "Limit: two hard days is the cap",
  RAIL_MIN_REST_PER_WEEK: "Limit: a rest day every week",
  RAIL_NO_HARD_AFTER_SHORT_SLEEP: "Limit: no hard sessions on short sleep",
  RAIL_NO_LIGHTER_FOOD_AFTER_HARD: "Limit: never lighter food after a hard day",
  RAIL_NO_LIGHTER_FOOD_ON_TRAINING_DAY: "Limit: never lighter food on a training day",
};

export function MorningBriefScreen() {
  const today = isoDate();
  const [brief, setBrief] = useState<Brief | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [showWhy, setShowWhy] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (sync: boolean) => {
    setBusy(true);
    setError(null);
    try {
      if (sync) {
        // Best-effort: the brief still works on partial data (design §7).
        await Promise.allSettled([syncHealth(), syncTodayCalendar()]);
      }
      const b = await api.briefOpened(today);
      setBrief(b);
      const p = await api.plan(today);
      setPlan(p.plan);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [today]);

  useEffect(() => {
    void load(true);
  }, [load]);

  const reasons = plan
    ? [plan.training, plan.food, plan.movement]
        .flatMap((r) => [...r.rails_applied, ...r.reasons])
        .filter((c, i, arr) => arr.indexOf(c) === i)
    : [];

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      refreshControl={<RefreshControl refreshing={busy} onRefresh={() => load(true)} />}
    >
      <Text style={styles.eyebrow}>{new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}</Text>
      <Text style={styles.title}>Your day, in three lines</Text>

      {busy && !brief ? <ActivityIndicator style={{ marginTop: 32 }} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}

      {brief?.lines.map((line, i) => (
        <View key={i} style={styles.line}>
          <Text style={styles.lineLabel}>{["Move", "Eat", "Why"][i]}</Text>
          <Text style={styles.lineText}>{line}</Text>
        </View>
      ))}

      {plan ? (
        <Pressable onPress={() => setShowWhy((s) => !s)} style={styles.whyButton} accessibilityRole="button">
          <Text style={styles.whyButtonText}>{showWhy ? "Hide the reasoning" : "Why did you say that?"}</Text>
        </Pressable>
      ) : null}

      {showWhy && plan ? (
        <View style={styles.why}>
          {reasons.map((code) => (
            <Text key={code} style={[styles.reason, code.startsWith("RAIL_") && styles.rail]}>
              {REASON_TEXT[code] ?? code}
            </Text>
          ))}
          {plan.training_window ? (
            <Text style={styles.reason}>
              Training window {plan.training_window.start.slice(11, 16)}–{plan.training_window.end.slice(11, 16)}
            </Text>
          ) : null}
        </View>
      ) : null}

      {brief ? (
        <Text style={styles.footer}>
          {brief.source === "llm" ? "Written by your coach" : "Written from your plan"} · updated{" "}
          {brief.computed_at.slice(11, 16)}
        </Text>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 24, paddingTop: 72, gap: 16 },
  eyebrow: { fontSize: 13, letterSpacing: 1, textTransform: "uppercase", opacity: 0.6 },
  title: { fontSize: 28, fontWeight: "700", marginBottom: 8 },
  line: { gap: 4 },
  lineLabel: { fontSize: 12, letterSpacing: 1, textTransform: "uppercase", opacity: 0.55 },
  lineText: { fontSize: 18, lineHeight: 26 },
  whyButton: { marginTop: 8, alignSelf: "flex-start" },
  whyButtonText: { fontSize: 15, textDecorationLine: "underline" },
  why: { gap: 6, paddingLeft: 12, borderLeftWidth: 2, borderLeftColor: "#8884" },
  reason: { fontSize: 15, opacity: 0.85 },
  rail: { fontWeight: "600" },
  error: { color: "#b00020" },
  footer: { marginTop: 24, fontSize: 12, opacity: 0.5 },
});
