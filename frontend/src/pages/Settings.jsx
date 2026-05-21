import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import AgentStatus from "../components/AgentStatus";
import { Sliders, Save, Loader2, Sparkles, Info, Mail, RefreshCw, Unplug, Plug } from "lucide-react";

export default function Settings() {
  const [settings, setSettings] = useState({ auto_send_enabled: false, auto_send_threshold: 85, auto_send_deal_value_cap: 50000 });
  const [stats, setStats] = useState({ pending: 0, sent: 0, received: 0, auto_sent: 0 });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [gmail, setGmail] = useState({ connected: false });
  const [gmailBusy, setGmailBusy] = useState(false);
  const [pollResult, setPollResult] = useState(null);

  const loadAll = async () => {
    const [s, st, gm] = await Promise.all([
      api.get("/settings"),
      api.get("/replies/stats"),
      api.get("/integrations/gmail/status"),
    ]);
    setSettings({
      auto_send_enabled: !!s.data.auto_send_enabled,
      auto_send_threshold: s.data.auto_send_threshold || 85,
      auto_send_deal_value_cap: s.data.auto_send_deal_value_cap ?? 50000,
    });
    setStats(st.data);
    setGmail(gm.data);
  };

  useEffect(() => {
    loadAll();
    // If returning from gmail oauth callback (?gmail=connected), poll once + refresh
    const params = new URLSearchParams(window.location.search);
    if (params.get("gmail") === "connected") {
      window.history.replaceState({}, "", window.location.pathname);
    }
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
  const setCap = (v) => setSettings((s) => ({ ...s, auto_send_deal_value_cap: Math.max(0, parseInt(v) || 0) }));

  const fmtCap = (n) => {
    if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1000) return `$${Math.round(n / 1000)}K`;
    return `$${n}`;
  };

  const connectGmail = async () => {
    setGmailBusy(true);
    try {
      const r = await api.post("/integrations/gmail/connect");
      window.location.href = r.data.url;
    } catch (e) {
      console.error("Gmail connect failed", e);
      setGmailBusy(false);
    }
  };

  const pollGmail = async () => {
    setGmailBusy(true);
    setPollResult(null);
    try {
      const r = await api.post("/integrations/gmail/poll");
      setPollResult(r.data);
      await loadAll();
    } catch (e) {
      console.error("Gmail poll failed", e);
      setPollResult({ error: e?.response?.data?.detail || "Poll failed" });
    } finally {
      setGmailBusy(false);
    }
  };

  const disconnectGmail = async () => {
    setGmailBusy(true);
    try {
      await api.post("/integrations/gmail/disconnect");
      await loadAll();
    } finally {
      setGmailBusy(false);
    }
  };

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

          {/* Deal-value cap */}
          <div className="py-6 mt-4 border-t" style={{ borderColor: "var(--nx-border)" }} data-testid="dealcap-row">
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="text-sm text-zinc-200">Auto-send deal-value cap</div>
                <div className="text-xs text-zinc-500 mt-1">Above this size, drafts always require human approval.</div>
              </div>
              <div className="font-mono text-2xl" style={{ color: "var(--nx-cyan)" }}>{fmtCap(settings.auto_send_deal_value_cap)}</div>
            </div>
            <input
              type="range"
              min={0}
              max={500000}
              step={5000}
              value={settings.auto_send_deal_value_cap}
              onChange={(e) => setCap(e.target.value)}
              disabled={!settings.auto_send_enabled}
              className="w-full nx-slider"
              data-testid="dealcap-slider"
              style={{ accentColor: "var(--nx-cyan)", opacity: settings.auto_send_enabled ? 1 : 0.4 }}
            />
            <div className="flex justify-between text-[10px] text-zinc-600 mt-2">
              <span>$0 (everything manual)</span>
              <span>$50K (recommended)</span>
              <span>$500K+ (very autonomous)</span>
            </div>
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

      {/* Gmail integration */}
      <div className="nx-glass p-8 mb-6" data-testid="gmail-panel">
        <div className="flex items-center gap-3 mb-2">
          <Mail size={16} color="var(--nx-cyan)" />
          <div className="nx-label">REAL INBOUND REPLIES · GMAIL</div>
        </div>
        <h2 className="font-serif text-3xl mb-2">Connect Gmail to capture real buyer replies.</h2>
        <p className="text-zinc-400 text-sm mb-6 leading-relaxed">
          When connected, Nexus polls your inbox, threads incoming replies back to the outbound email we sent, and Claude drafts your follow-up.
          {" "}
          <span className="text-zinc-200">No more simulate-reply button</span> — these are real humans replying to you.
        </p>

        {!gmail.connected ? (
          <button onClick={connectGmail} disabled={gmailBusy} className="nx-btn-primary" data-testid="connect-gmail-btn">
            {gmailBusy ? <><Loader2 className="animate-spin" size={14} /> Redirecting…</> : <><Plug size={14} /> Connect Gmail</>}
          </button>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-3 p-4 border rounded" style={{ borderColor: "rgba(0,245,212,0.35)", background: "rgba(0,245,212,0.04)" }} data-testid="gmail-connected-panel">
              <div>
                <div className="text-sm text-zinc-200 flex items-center gap-2">
                  <AgentStatus status="closing" size="xs" /> Connected as <span className="font-mono">{gmail.email || "—"}</span>
                </div>
                {gmail.last_polled_at && <div className="text-xs text-zinc-500 mt-1">Last polled: {new Date(gmail.last_polled_at).toLocaleString()}</div>}
              </div>
              <div className="flex gap-2">
                <button onClick={pollGmail} disabled={gmailBusy} className="nx-btn-ghost" data-testid="poll-gmail-btn">
                  {gmailBusy ? <><Loader2 className="animate-spin" size={14} /> Polling…</> : <><RefreshCw size={14} /> Poll inbox now</>}
                </button>
                <button onClick={disconnectGmail} disabled={gmailBusy} className="nx-btn-ghost" data-testid="disconnect-gmail-btn" style={{ color: "var(--nx-danger)", borderColor: "rgba(255,51,102,0.3)" }}>
                  <Unplug size={14} /> Disconnect
                </button>
              </div>
            </div>

            {pollResult && (
              <div className="text-xs p-3 border-l-2 text-zinc-300" data-testid="poll-result" style={{ borderColor: pollResult.error ? "var(--nx-danger)" : "var(--nx-cyan)", background: "rgba(255,255,255,0.02)" }}>
                {pollResult.error ? (
                  <span>Error: {pollResult.error}</span>
                ) : (
                  <span>
                    Pulled <span className="text-zinc-100 font-mono">{pollResult.new_replies}</span> new reply
                    {pollResult.new_replies === 1 ? "" : "ies"} · drafted{" "}
                    <span className="text-zinc-100 font-mono">{pollResult.drafts_created}</span> follow-up
                    {pollResult.drafts_created === 1 ? "" : "s"}
                  </span>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
