import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, daysAgo, isoDate, type Activity, type CalendarEvent, type Intensity } from "../api";

const TYPES = ["run", "strength", "cycle", "swim", "walk", "other"];

function CalendarBlocks({ today, onChange }: { today: string; onChange: () => void }) {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [start, setStart] = useState("09:00");
  const [end, setEnd] = useState("10:00");
  const [kind, setKind] = useState<CalendarEvent["coarse_type"]>("meeting");

  useEffect(() => { api.calendar(today).then((r) => setEvents(r.events)).catch(() => {}); }, [today]);

  async function save(next: CalendarEvent[]) {
    setEvents(next);
    await api.setCalendar(today, next);
    onChange();
  }
  function add(e: FormEvent) {
    e.preventDefault();
    if (end <= start) return;
    void save([...events, { start: `${today}T${start}:00`, end: `${today}T${end}:00`, coarse_type: kind }]
      .sort((a, b) => a.start.localeCompare(b.start)));
  }
  return (
    <div className="card">
      <h2>Today's busy blocks</h2>
      <p className="muted">Meetings, travel, anything you can't train through. Only times are stored.</p>
      <form className="row3" onSubmit={add}>
        <label>From<input type="time" value={start} onChange={(e) => setStart(e.target.value)} required /></label>
        <label>To<input type="time" value={end} onChange={(e) => setEnd(e.target.value)} required /></label>
        <label>Type
          <select value={kind} onChange={(e) => setKind(e.target.value as CalendarEvent["coarse_type"])}>
            <option value="meeting">Meeting</option><option value="travel">Travel</option>
            <option value="blocked">Blocked</option><option value="personal">Personal</option>
          </select>
        </label>
        <button className="btn" type="submit" style={{ gridColumn: "1 / -1" }}>Add block</button>
      </form>
      <div className="list">
        {events.length === 0 ? <p className="muted">Nothing yet. An empty day means a free day.</p> : null}
        {events.map((ev, i) => (
          <div className="item" key={`${ev.start}-${i}`}>
            <span className="when">{ev.start.slice(11, 16)}–{ev.end.slice(11, 16)}</span>
            <span className="chip">{ev.coarse_type}</span>
            <button className="btn small danger" onClick={() => save(events.filter((_, j) => j !== i))}>Remove</button>
          </div>
        ))}
      </div>
    </div>
  );
}

export function LogScreen({ onChange }: { onChange: () => void }) {
  const today = isoDate();
  const [sleep, setSleep] = useState<string>("");
  const sleepTouched = useRef(false);  // a slow initial load must never overwrite what the user typed
  const [acts, setActs] = useState<Activity[]>([]);
  const [on, setOn] = useState(daysAgo(1));
  const [type, setType] = useState("run");
  const [minutes, setMinutes] = useState("45");
  const [intensity, setIntensity] = useState<Intensity>("moderate");
  const [toast, setToast] = useState<string | null>(null);

  const reload = () => api.activities(daysAgo(14)).then(setActs).catch(() => {});
  useEffect(() => {
    void reload();
    api.recovery(today).then((r) => {
      if (!sleepTouched.current) setSleep(r.sleep_hours == null ? "" : String(r.sleep_hours));
    }).catch(() => {});
  }, [today]);

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(null), 1800); }

  async function saveSleep() {
    await api.setRecovery(today, sleep === "" ? null : Number(sleep));
    onChange(); flash("Sleep saved");
  }
  async function addActivity(e: FormEvent) {
    e.preventDefault();
    await api.addActivity({ on, type, duration_min: Number(minutes), intensity, source: "manual" });
    await reload(); onChange(); flash("Session logged");
  }
  async function remove(id: string) {
    await api.deleteActivity(id); await reload(); onChange();
  }

  return (
    <>
      <div>
        <span className="eyebrow">Log</span>
        <h1>What the brief needs to know</h1>
        <p className="muted">Ten seconds. Everything here re-shapes today's brief.</p>
      </div>

      <div className="card">
        <h2>Last night's sleep</h2>
        <div className="row3">
          <label style={{ gridColumn: "1 / 3" }}>Hours
            <input type="number" inputMode="decimal" min={0} max={14} step={0.5} value={sleep}
              onChange={(e) => { sleepTouched.current = true; setSleep(e.target.value); }} placeholder="e.g. 7" />
          </label>
          <button className="btn" onClick={saveSleep}>Save</button>
        </div>
      </div>

      <div className="card">
        <h2>Log a session</h2>
        <form onSubmit={addActivity} style={{ display: "grid", gap: 10 }}>
          <div className="row">
            <label>Date<input type="date" value={on} max={today} onChange={(e) => setOn(e.target.value)} required /></label>
            <label>Type
              <select value={type} onChange={(e) => setType(e.target.value)}>
                {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
          </div>
          <div className="row">
            <label>Minutes<input type="number" inputMode="numeric" min={5} max={600} value={minutes} onChange={(e) => setMinutes(e.target.value)} required /></label>
            <label>How hard
              <select value={intensity} onChange={(e) => setIntensity(e.target.value as Intensity)}>
                <option value="easy">Easy</option><option value="moderate">Moderate</option><option value="hard">Hard</option>
              </select>
            </label>
          </div>
          <button className="btn primary" type="submit">Log it</button>
        </form>
        <div className="list">
          {acts.map((a) => (
            <div className="item" key={a.id}>
              <span className="when">{a.on.slice(5)}</span>
              <span>{a.type} · {a.duration_min} min <span className="chip">{a.intensity}</span></span>
              <button className="btn small danger" onClick={() => remove(a.id)}>Remove</button>
            </div>
          ))}
        </div>
      </div>

      <CalendarBlocks today={today} onChange={onChange} />
      {toast ? <div className="toast" role="status">{toast}</div> : null}
    </>
  );
}
