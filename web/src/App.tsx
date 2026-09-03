import { useState } from "react";
import { BriefScreen } from "./screens/Brief";
import { LogScreen } from "./screens/Log";
import { SettingsScreen } from "./screens/Settings";

type Tab = "brief" | "log" | "settings";

const ICONS: Record<Tab, JSX.Element> = {
  brief: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M4 15a8 8 0 0 1 16 0" /><path d="M3 19h18" /></svg>,
  log: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>,
  settings: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" /></svg>,
};

export default function App() {
  const [tab, setTab] = useState<Tab>("brief");
  // bumps whenever inputs change so the brief recomputes on next view
  const [dirty, setDirty] = useState(0);
  const markDirty = () => setDirty((d) => d + 1);

  return (
    <div className="app">
      <main>
        {tab === "brief" ? <BriefScreen refreshKey={dirty} /> : null}
        {tab === "log" ? <LogScreen onChange={markDirty} /> : null}
        {tab === "settings" ? <SettingsScreen onChange={markDirty} /> : null}
      </main>
      <nav className="tabs" aria-label="Sections">
        <div className="inner">
          {(["brief", "log", "settings"] as Tab[]).map((t) => (
            <button key={t} className="tab" aria-current={tab === t ? "page" : undefined} onClick={() => setTab(t)}>
              {ICONS[t]}
              <span>{t === "brief" ? "Brief" : t === "log" ? "Log" : "Settings"}</span>
            </button>
          ))}
        </div>
      </nav>
    </div>
  );
}
