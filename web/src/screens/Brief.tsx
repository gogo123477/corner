import { useCallback, useEffect, useState } from "react";
import { api, isoDate, type Brief, type Plan } from "../api";
import { REASON_TEXT } from "../reasons";

const LABELS = ["Move", "Eat", "Why"];

export function BriefScreen({ refreshKey }: { refreshKey: number }) {
  const today = isoDate();
  const [brief, setBrief] = useState<Brief | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [showWhy, setShowWhy] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (recompute: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const p = await api.plan(today, recompute);
      setPlan(p.plan);
      setBrief(await api.briefOpened(today));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [today]);

  useEffect(() => { void load(refreshKey > 0); }, [load, refreshKey]);

  const reasons = plan
    ? [plan.training, plan.food, plan.movement]
        .flatMap((r) => [...r.rails_applied, ...r.reasons])
        .filter((c, i, a) => a.indexOf(c) === i)
    : [];
  const dateLabel = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });

  return (
    <section className="brief" aria-busy={busy}>
      <span className="eyebrow">{dateLabel}</span>
      <h1>Your day, in three lines</h1>
      {error ? <p className="error">{error}. Is the backend running?</p> : null}
      {!brief && busy ? [0, 1, 2].map((i) => <div key={i} className="line"><div className="skeleton" /></div>) : null}
      {brief?.lines.map((line, i) => (
        <div className="line" key={i}>
          <span className="k">{LABELS[i]}</span>
          <span className="v">{line}</span>
        </div>
      ))}
      {brief ? (
        <div className="actions">
          <button className="linkbtn" onClick={() => setShowWhy((s) => !s)} aria-expanded={showWhy}>
            {showWhy ? "Hide the reasoning" : "Why did you say that?"}
          </button>
          <button className="linkbtn" onClick={() => load(true)} disabled={busy}>Recompute</button>
        </div>
      ) : null}
      {showWhy && plan ? (
        <div className="reasons">
          {reasons.map((c) => (
            <span key={c} className={c.startsWith("RAIL_") ? "rail" : undefined}>{REASON_TEXT[c] ?? c}</span>
          ))}
          {plan.training_window ? (
            <span>Training window {plan.training_window.start.slice(11, 16)}–{plan.training_window.end.slice(11, 16)}</span>
          ) : null}
        </div>
      ) : null}
      {brief ? (
        <div className="foot">
          {brief.source === "llm" ? "Written by your coach" : "Written from your plan"} · updated {brief.computed_at.slice(11, 16)}
        </div>
      ) : null}
    </section>
  );
}
