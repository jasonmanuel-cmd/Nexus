import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import AgentStatus from "../components/AgentStatus";
import { MailOpen, Send, X, Loader2, Sparkles, RefreshCw, ArrowDownRight, MessageSquare, Inbox } from "lucide-react";

const SENT_COLOR = {
  positive: "var(--nx-cyan)",
  neutral: "#fafafa",
  negative: "var(--nx-orange)",
};

const INTENT_LABEL = {
  interested: "INTERESTED",
  wants_info: "WANTS INFO",
  deferring: "DEFERRING",
  objecting: "OBJECTING",
  not_now: "NOT NOW",
};

const formatTime = (iso) => {
  try {
    const diff = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  } catch { return iso; }
};

const DraftCard = ({ item, onSend, onDismiss }) => {
  const { draft, reply, original, deal } = item;
  const [editing, setEditing] = useState(false);
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const [sending, setSending] = useState(false);
  const [dismissing, setDismissing] = useState(false);

  const sentimentColor = SENT_COLOR[reply?.sentiment] || "#fafafa";

  const handleSend = async () => {
    setSending(true);
    try {
      await onSend(draft.id, editing ? { subject, body } : {});
    } finally {
      setSending(false);
    }
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: 30 }}
      className="nx-glass nx-card-hover overflow-hidden"
      data-testid={`draft-card-${draft.id}`}
    >
      {/* Header */}
      <div className="px-6 py-4 border-b flex items-center justify-between flex-wrap gap-3" style={{ borderColor: "var(--nx-border)" }}>
        <div className="flex items-center gap-3">
          <AgentStatus status={reply?.sentiment === "positive" ? "closing" : reply?.sentiment === "negative" ? "thinking" : "scanning"} />
          <div>
            <div className="font-mono text-sm text-zinc-200">{deal?.company || "Unknown prospect"}</div>
            <div className="text-[11px] text-zinc-500">{deal?.contact || reply?.from_address}</div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="nx-label" style={{ color: sentimentColor }}>
            {(reply?.sentiment || "neutral").toUpperCase()} · {INTENT_LABEL[reply?.intent] || "—"}
          </span>
          <span className={`font-mono text-sm ${draft.probability_delta >= 0 ? "text-[#00f5d4]" : "text-[#ff3366]"}`}>
            Δ{draft.probability_delta >= 0 ? "+" : ""}{draft.probability_delta}%
          </span>
          <span className="text-[11px] text-zinc-500">{formatTime(draft.created_at)}</span>
        </div>
      </div>

      {/* Conversation thread */}
      <div className="grid grid-cols-1 lg:grid-cols-2 divide-x" style={{ borderColor: "var(--nx-border)" }}>
        {/* Left: original + reply */}
        <div className="p-6 space-y-5 border-r" style={{ borderColor: "var(--nx-border)" }}>
          <div>
            <div className="nx-label mb-2 flex items-center gap-2"><Send size={11} /> YOUR OUTREACH</div>
            <div className="text-xs text-zinc-500 mb-1">to {original?.to}</div>
            <div className="text-sm text-zinc-300 mb-1 font-mono">{original?.subject}</div>
            <div className="text-xs text-zinc-500 whitespace-pre-wrap line-clamp-4 border-l-2 pl-3" style={{ borderColor: "var(--nx-border-strong)" }}>{original?.body}</div>
          </div>
          <div>
            <div className="nx-label mb-2 flex items-center gap-2" style={{ color: sentimentColor }}>
              <MailOpen size={11} /> BUYER REPLY
            </div>
            <div className="text-sm text-zinc-200 whitespace-pre-wrap border-l-2 pl-3" style={{ borderColor: sentimentColor }}>{reply?.body}</div>
          </div>
        </div>

        {/* Right: AI draft */}
        <div className="p-6">
          <div className="flex items-center justify-between mb-3">
            <div className="nx-label flex items-center gap-2"><Sparkles size={11} color="var(--nx-cyan)" /> AI DRAFTED FOLLOW-UP</div>
            {!editing && (
              <button onClick={() => setEditing(true)} className="text-[11px] text-zinc-500 hover:text-zinc-200 transition tracking-[0.12em] uppercase" data-testid={`draft-edit-${draft.id}`}>
                Edit
              </button>
            )}
          </div>
          {editing ? (
            <>
              <input className="nx-input mb-3 text-sm" value={subject} onChange={(e) => setSubject(e.target.value)} data-testid={`draft-subject-${draft.id}`} />
              <textarea className="nx-input min-h-[160px] text-sm" value={body} onChange={(e) => setBody(e.target.value)} data-testid={`draft-body-${draft.id}`} />
            </>
          ) : (
            <>
              <div className="text-sm text-zinc-200 font-mono mb-3">{subject}</div>
              <div className="text-sm text-zinc-400 whitespace-pre-wrap border-l-2 pl-3 mb-3" style={{ borderColor: "var(--nx-cyan)" }}>{body}</div>
            </>
          )}
          <div className="mt-4 text-xs text-zinc-500 flex items-start gap-2">
            <ArrowDownRight size={12} className="mt-0.5 flex-shrink-0" color="var(--nx-cyan)" />
            <span><span className="text-zinc-300">Suggested next:</span> {draft.suggested_action}</span>
          </div>
        </div>
      </div>

      {/* Footer actions */}
      <div className="px-6 py-4 border-t flex items-center justify-end gap-3" style={{ borderColor: "var(--nx-border)" }}>
        <button
          onClick={async () => { setDismissing(true); try { await onDismiss(draft.id); } finally { setDismissing(false); } }}
          disabled={dismissing}
          className="nx-btn-ghost"
          style={{ color: "var(--nx-text-dim)", borderColor: "var(--nx-border-strong)" }}
          data-testid={`draft-dismiss-${draft.id}`}
        >
          {dismissing ? <Loader2 className="animate-spin" size={12} /> : <X size={12} />} Dismiss
        </button>
        <button
          onClick={handleSend}
          disabled={sending}
          className="nx-btn-primary"
          data-testid={`draft-send-${draft.id}`}
        >
          {sending ? <Loader2 className="animate-spin" size={12} /> : <Send size={12} />} {editing ? "Edit & send" : "Send as-is"}
        </button>
      </div>
    </motion.div>
  );
};

export default function Replies() {
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState({ pending: 0, sent: 0, received: 0 });
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const fetch = async () => {
    setLoading(true);
    try {
      const [r, s] = await Promise.all([api.get("/replies/queue"), api.get("/replies/stats")]);
      setItems(r.data.drafts || []);
      setStats(s.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetch(); }, []);

  const handleSend = async (draftId, overrides) => {
    await api.post(`/replies/${draftId}/send`, overrides);
    await fetch();
  };
  const handleDismiss = async (draftId) => {
    await api.delete(`/replies/${draftId}`);
    await fetch();
  };

  return (
    <div className="p-6 lg:p-10" data-testid="replies-page">
      <div className="flex items-end justify-between mb-8 flex-wrap gap-4">
        <div>
          <div className="nx-label mb-2">[ REPLIES QUEUE ]</div>
          <h1 className="font-serif text-4xl lg:text-5xl tracking-tight">Agent-drafted, you-approved.</h1>
          <p className="text-zinc-500 mt-2 text-sm">Every buyer reply is read and answered by Claude. You stay in the loop — review, edit, ship.</p>
        </div>
        <button onClick={fetch} className="nx-btn-ghost" data-testid="replies-refresh">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-8">
        <div className="nx-glass p-5" data-testid="reply-stat-pending">
          <div className="flex items-center justify-between mb-2"><div className="nx-label">AWAITING REVIEW</div><Inbox size={14} className="text-zinc-500" /></div>
          <div className="font-mono text-3xl" style={{ color: "var(--nx-cyan)" }}>{stats.pending}</div>
        </div>
        <div className="nx-glass p-5" data-testid="reply-stat-received">
          <div className="flex items-center justify-between mb-2"><div className="nx-label">REPLIES RECEIVED</div><MailOpen size={14} className="text-zinc-500" /></div>
          <div className="font-mono text-3xl text-zinc-200">{stats.received}</div>
        </div>
        <div className="nx-glass p-5" data-testid="reply-stat-sent">
          <div className="flex items-center justify-between mb-2"><div className="nx-label">FOLLOW-UPS SENT</div><Send size={14} className="text-zinc-500" /></div>
          <div className="font-mono text-3xl text-zinc-200">{stats.sent}</div>
        </div>
      </div>

      {loading && <div className="text-zinc-500 text-sm">Loading drafts…</div>}

      {!loading && items.length === 0 && (
        <div className="nx-glass p-16 text-center" data-testid="replies-empty">
          <MessageSquare className="mx-auto mb-4 text-zinc-700" size={32} />
          <div className="font-serif text-2xl mb-2 text-zinc-300">No drafts yet.</div>
          <p className="text-zinc-500 max-w-md mx-auto text-sm">
            Send some outreach via Beta Onboard, then click "Simulate buyer reply" on any email in the Outbox to see Claude draft a contextual follow-up.
          </p>
          <button onClick={() => navigate("/app/outbox")} className="nx-btn-primary mt-6" data-testid="replies-go-outbox">
            <Inbox size={14} /> Open Outbox
          </button>
        </div>
      )}

      <div className="space-y-4">
        <AnimatePresence>
          {items.map((it) => (
            <DraftCard key={it.draft.id} item={it} onSend={handleSend} onDismiss={handleDismiss} />
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
