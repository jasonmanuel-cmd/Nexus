import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import AgentStatus from "../components/AgentStatus";
import { Mail, MessageSquare, Inbox, RefreshCw, Loader2, ArrowDownRight } from "lucide-react";

const formatTime = (iso) => {
  try {
    const diff = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  } catch { return iso; }
};

export default function Outbox() {
  const [data, setData] = useState({ emails: [], slack_messages: [] });
  const [tab, setTab] = useState("email");
  const [loading, setLoading] = useState(true);
  const [simulating, setSimulating] = useState(null);
  const [simulatedIds, setSimulatedIds] = useState(new Set());
  const navigate = useNavigate();

  const fetch = async () => {
    setLoading(true);
    try {
      const r = await api.get("/notifications/outbox");
      setData(r.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetch(); }, []);

  const simulate = async (emailId) => {
    setSimulating(emailId);
    try {
      await api.post(`/notifications/email/${emailId}/simulate-reply`);
      setSimulatedIds((s) => new Set([...s, emailId]));
      // Redirect to replies queue after a short pause so user sees the success
      setTimeout(() => navigate("/app/replies"), 700);
    } catch (e) {
      console.error(e);
    } finally {
      setSimulating(null);
    }
  };

  return (
    <div className="p-6 lg:p-10" data-testid="outbox-page">
      <div className="flex items-end justify-between mb-8 flex-wrap gap-4">
        <div>
          <div className="nx-label mb-2">[ AGENT OUTBOX ]</div>
          <h1 className="font-serif text-4xl lg:text-5xl tracking-tight">What the agents sent.</h1>
          <p className="text-zinc-500 mt-2 text-sm">All emails + Slack messages dispatched by Nexus agents on your behalf.</p>
        </div>
        <button onClick={fetch} className="nx-btn-ghost" data-testid="outbox-refresh">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
        <div className="nx-glass p-5" data-testid="outbox-stat-email">
          <div className="flex items-center justify-between mb-2"><div className="nx-label">EMAILS SENT</div><Mail size={14} className="text-zinc-500" /></div>
          <div className="font-mono text-3xl" style={{ color: "var(--nx-cyan)" }}>{data.emails.length}</div>
        </div>
        <div className="nx-glass p-5" data-testid="outbox-stat-slack">
          <div className="flex items-center justify-between mb-2"><div className="nx-label">SLACK MESSAGES</div><MessageSquare size={14} className="text-zinc-500" /></div>
          <div className="font-mono text-3xl" style={{ color: "var(--nx-cyan)" }}>{data.slack_messages.length}</div>
        </div>
        <div className="nx-glass p-5" data-testid="outbox-stat-mode">
          <div className="flex items-center justify-between mb-2"><div className="nx-label">MODE</div><Inbox size={14} className="text-zinc-500" /></div>
          <div className="font-mono text-lg" style={{ color: "var(--nx-orange)" }}>MOCKED</div>
          <div className="text-xs text-zinc-500 mt-1">Add RESEND_API_KEY + SLACK_WEBHOOK_URL to flip live</div>
        </div>
      </div>

      <div className="nx-glass p-1 inline-flex gap-1 mb-6">
        {[{k:"email",l:"EMAILS",n:data.emails.length},{k:"slack",l:"SLACK",n:data.slack_messages.length}].map((t) => (
          <button
            key={t.k}
            onClick={() => setTab(t.k)}
            className="px-4 py-2 text-xs tracking-[0.14em] uppercase transition"
            style={{
              background: tab === t.k ? "rgba(0,245,212,0.1)" : "transparent",
              color: tab === t.k ? "var(--nx-cyan)" : "var(--nx-text-dim)",
            }}
            data-testid={`outbox-tab-${t.k}`}
          >
            {t.l} ({t.n})
          </button>
        ))}
      </div>

      <div className="space-y-2">
        <AnimatePresence>
          {tab === "email" && data.emails.map((e, i) => (
            <motion.div
              key={e.id || i}
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              className="nx-glass p-5 nx-card-hover"
              data-testid={`outbox-email-${i}`}
            >
              <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
                <div className="flex items-center gap-3">
                  <Mail size={14} color="var(--nx-cyan)" />
                  <span className="font-mono text-sm text-zinc-200">{e.subject}</span>
                  <span className="nx-label" style={{ fontSize: 9, color: e.mocked ? "var(--nx-orange)" : "var(--nx-cyan)" }}>{e.mocked ? "MOCKED" : "LIVE"}</span>
                </div>
                <span className="text-[11px] text-zinc-500">{formatTime(e.created_at)}</span>
              </div>
              <div className="text-xs text-zinc-500 mb-2">to: {e.to} · kind: {e.kind}</div>
              <div className="text-sm text-zinc-400 whitespace-pre-wrap border-l-2 pl-3" style={{ borderColor: "var(--nx-border-strong)" }}>{e.body}</div>
              {(e.kind === "promote.intro" || e.kind === "reply.followup") && (
                <div className="mt-4 pt-3 border-t flex items-center justify-end gap-3" style={{ borderColor: "var(--nx-border)" }}>
                  <button
                    onClick={() => simulate(e.id)}
                    disabled={simulating === e.id || simulatedIds.has(e.id)}
                    className="nx-btn-ghost"
                    data-testid={`simulate-reply-${i}`}
                  >
                    {simulating === e.id ? (
                      <><Loader2 className="animate-spin" size={12} /> Claude thinking…</>
                    ) : simulatedIds.has(e.id) ? (
                      <>Reply drafted →</>
                    ) : (
                      <><ArrowDownRight size={12} /> Simulate buyer reply</>
                    )}
                  </button>
                </div>
              )}
            </motion.div>
          ))}
          {tab === "slack" && data.slack_messages.map((s, i) => (
            <motion.div
              key={s.id || i}
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              className="nx-glass p-5 nx-card-hover"
              data-testid={`outbox-slack-${i}`}
            >
              <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
                <div className="flex items-center gap-3">
                  <MessageSquare size={14} color="var(--nx-cyan)" />
                  <span className="nx-label" style={{ fontSize: 9, color: s.mocked ? "var(--nx-orange)" : "var(--nx-cyan)" }}>{s.mocked ? "MOCKED" : "LIVE"}</span>
                  <span className="text-xs text-zinc-500">kind: {s.kind}</span>
                </div>
                <span className="text-[11px] text-zinc-500">{formatTime(s.created_at)}</span>
              </div>
              <div className="text-sm text-zinc-200 font-mono">{s.text}</div>
            </motion.div>
          ))}
        </AnimatePresence>

        {!loading && tab === "email" && data.emails.length === 0 && (
          <div className="text-center text-zinc-500 py-12 nx-glass" data-testid="outbox-empty-email">No emails yet. Promote a target to trigger one.</div>
        )}
        {!loading && tab === "slack" && data.slack_messages.length === 0 && (
          <div className="text-center text-zinc-500 py-12 nx-glass" data-testid="outbox-empty-slack">No Slack messages yet. Advance a deal stage to trigger one.</div>
        )}
      </div>
    </div>
  );
}
