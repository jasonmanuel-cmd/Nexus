import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import AgentStatus from "../components/AgentStatus";
import { Sliders, Save, Loader2, Sparkles, Info } from "lucide-react";

export default function Settings() {
  const [settings, setSettings] = useState({ auto_send_enabled: false, auto_send_threshold: 85 });
  const [stats, setStats] = useState({ pending: 0, sent: 0, received: 0, auto_sent: 0 });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    (async () => {
      const [s, st] = await Promise.all([api.get("/settings"), api.get("/replies/stats")]);
      setSettings(s.data);
      setStats(st.data);
    })();
  }, []);

  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const r = await api.put("/settings", settings);
      setSettings(r.data);
      setSaved(true);
      setTimeout(() => setSaved(false), 2400);
    } finally {
      setSaving(false);
    }
  };

  const setThreshold = (v) => setSettings((s) => ({ ...s, auto_send_threshold: Math.max(50, Math.min(100, parseInt(v) || 50)) }));

  return (
    <div className="p-6 lg:p-10" data-testid="settings-page">
      <div className="flex items-end justify-between mb-8 flex-wrap gap-4">
        <div>
          <div className="nx-label mb-2">[ SETTINGS ]</div>
          <h1 className="font-serif text-4xl lg:text-5xl tracking-tight">Tune your agents.</h1>
          <p className="text-zinc-500 mt-2 text-sm">Control how autonomous your CRO actually is.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div className="lg:col-span-2 nx-glass p-8" data-testid="autosend-panel">
          <div className="flex items-center gap-3 mb-2">
            <Sliders size={16} color="var(--nx-cyan)" />
            <div className="nx-label">AUTONOMOUS REPLY SENDING</div>
          </div>
          <h2 className="font-serif text-3xl mb-2">Auto-send when Claude is confident.</h2>
          <p className="text-zinc-400 text-sm mb-8 leading-relaxed">
            When the buyer's reply is <span className="text-zinc-200">positive</span>, the deal-probability delta is{" "}
            <span className="text-zinc-200">≥ +15%</span>, AND Claude's confidence ≥ your threshold — Nexus sends the
            follow-up <span style={{ color: "var(--nx-cyan)" }}>without waiting for you</span>. Everything else still
            lands in the Replies Queue for review.
          </p>

          {/* Toggle */}
          <div className="flex items-center justify-between py-4 border-y" style={{ borderColor: "var(--nx-border)" }} data-testid="autosend-toggle-row">
            <div>
              <div className="text-sm text-zinc-200">Enable auto-send</div>
              <div className="text-xs text-zinc-500 mt-1">When off, every draft requires manual approval.</div>
            </div>
            <button
              onClick={() => setSettings((s) => ({ ...s, auto_send_enabled: !s.auto_send_enabled }))}
              className="relative w-12 h-6 rounded-full transition"
              style={{ background: settings.auto_send_enabled ? "var(--nx-cyan)" : "rgba(255,255,255,0.1)" }}
              data-testid="autosend-toggle"
            >
              <span
                className="absolute top-0.5 w-5 h-5 rounded-full transition-all"
                style={{
                  background: settings.auto_send_enabled ? "#050505" : "#a1a1aa",
                  left: settings.auto_send_enabled ? "26px" : "2px",
                }}
              />
            </button>
          </div>

          {/* Threshold slider */}
          <div className="py-6" data-testid="threshold-row">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm text-zinc-200">Confidence threshold</div>
              <div className="font-mono text-2xl" style={{ color: "var(--nx-cyan)" }}>{settings.auto_send_threshold}%</div>
            </div>
            <input
              type="range"
              min={50}
              max={100}
              step={1}
              value={settings.auto_send_threshold}
              onChange={(e) => setThreshold(e.target.value)}
              disabled={!settings.auto_send_enabled}
              className="w-full nx-slider"
              data-testid="threshold-slider"
              style={{
                accentColor: "var(--nx-cyan)",
                opacity: settings.auto_send_enabled ? 1 : 0.4,
              }}
            />
            <div className="flex justify-between text-[10px] text-zinc-600 mt-2">
              <span>50% (aggressive)</span>
              <span>85% (recommended)</span>
              <span>100% (conservative)</span>
            </div>
          </div>

          <div className="mt-6 flex items-center gap-2 text-xs text-zinc-500 border-l-2 pl-3" style={{ borderColor: "var(--nx-orange)" }}>
            <Info size={12} />
            At threshold = <span className="text-zinc-300">85%</span> with auto-send <span className="text-zinc-300">on</span>, roughly 1-in-4 buyer replies clear the bar.
            You'll still review the rest manually.
          </div>

          <div className="mt-8 flex items-center gap-3">
            <button onClick={save} disabled={saving} className="nx-btn-primary" data-testid="save-settings-btn">
              {saving ? <><Loader2 className="animate-spin" size={14} /> Saving…</> : <><Save size={14} /> Save</>}
            </button>
            {saved && <AgentStatus status="closing" label="SAVED" testid="settings-saved" />}
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div className="nx-glass p-5" data-testid="stat-auto-sent">
            <div className="nx-label flex items-center gap-2"><Sparkles size={12} color="var(--nx-cyan)" /> AUTO-SENT</div>
            <div className="font-mono text-4xl mt-2" style={{ color: "var(--nx-cyan)" }}>{stats.auto_sent}</div>
            <div className="text-xs text-zinc-500 mt-1">No human in the loop</div>
          </div>
          <div className="nx-glass p-5">
            <div className="nx-label">MANUAL APPROVALS</div>
            <div className="font-mono text-4xl mt-2 text-zinc-200">{stats.sent - stats.auto_sent}</div>
            <div className="text-xs text-zinc-500 mt-1">You reviewed before send</div>
          </div>
          <div className="nx-glass p-5">
            <div className="nx-label">AWAITING YOU</div>
            <div className="font-mono text-4xl mt-2 text-zinc-200">{stats.pending}</div>
            <div className="text-xs text-zinc-500 mt-1">In the queue right now</div>
          </div>
        </div>
      </div>
    </div>
  );
}
