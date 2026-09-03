import { useEffect, useState, type FormEvent } from "react";
import { api, getToken, type Profile } from "../api";
import { disablePush, enablePush, pushSupported } from "../push";

const DEFAULT: Profile = {
  goal: "maintain", weekly_training_target: 3, baseline_daily_steps: 7000,
  day_start: "06:00", day_end: "22:00", coaching_tone: "warm",
};

export function SettingsScreen({ onChange }: { onChange: () => void }) {
  const [p, setP] = useState<Profile>(DEFAULT);
  const [saved, setSaved] = useState(false);
  const [pushMsg, setPushMsg] = useState<string | null>(null);
  useEffect(() => { api.profile().then(setP).catch(() => {}); }, []);

  async function save(e: FormEvent) {
    e.preventDefault();
    const { user_id: _u, push_enabled: _e, ...body } = p;
    void _u; void _e;
    setP(await api.setProfile(body as Profile));
    onChange(); setSaved(true); setTimeout(() => setSaved(false), 1800);
  }
  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => setP((s) => ({ ...s, [k]: v }));

  return (
    <>
      <div>
        <span className="eyebrow">Settings</span>
        <h1>How you want to be coached</h1>
      </div>
      <form className="card" onSubmit={save}>
        <label>Goal
          <select value={p.goal} onChange={(e) => set("goal", e.target.value as Profile["goal"])}>
            <option value="maintain">Stay consistent</option>
            <option value="fat_loss">Lean out (no restriction plans)</option>
            <option value="build">Build strength</option>
            <option value="perform">Perform (race or event)</option>
          </select>
        </label>
        <div className="row">
          <label>Sessions per week
            <input type="number" min={0} max={7} value={p.weekly_training_target}
              onChange={(e) => set("weekly_training_target", Number(e.target.value))} />
          </label>
          <label>Usual daily steps
            <input type="number" min={0} max={50000} step={500} value={p.baseline_daily_steps}
              onChange={(e) => set("baseline_daily_steps", Number(e.target.value))} />
          </label>
        </div>
        <div className="row">
          <label>Day starts<input type="time" value={p.day_start} onChange={(e) => set("day_start", e.target.value)} /></label>
          <label>Day ends<input type="time" value={p.day_end} onChange={(e) => set("day_end", e.target.value)} /></label>
        </div>
        <label>Coaching tone
          <select value={p.coaching_tone} onChange={(e) => set("coaching_tone", e.target.value)}>
            <option value="warm">Warm</option><option value="direct">Direct</option><option value="playful">Playful</option>
          </select>
        </label>
        <button className="btn primary" type="submit">{saved ? "Saved" : "Save"}</button>
      </form>
      <div className="card">
        <h2>Morning nudge</h2>
        <p className="muted">
          {p.push_enabled ? "On. The brief arrives as a notification each morning." : "Get the three lines as a notification each morning."}
          {!pushSupported() ? " Not available in this browser; on iPhone, add Corner to the home screen first." : ""}
        </p>
        <button className="btn" disabled={!pushSupported()} onClick={async () => {
          if (p.push_enabled) { await disablePush(); set("push_enabled", false); setPushMsg("Nudge off"); return; }
          const r = await enablePush();
          if (r === "enabled") { set("push_enabled", true); setPushMsg("Nudge on"); }
          else setPushMsg(r === "denied" ? "Notifications are blocked for this site." : "Push isn't configured on the server yet.");
        }}>{p.push_enabled ? "Turn off" : "Turn on"}</button>
        {pushMsg ? <p className="muted">{pushMsg}</p> : null}
      </div>
      <p className="muted">Signed in as a dev account (<code>{getToken()}</code>). Real sign-in arrives with managed auth.</p>
    </>
  );
}
