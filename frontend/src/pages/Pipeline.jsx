import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { api, fmtUSD } from "../lib/api";
import AgentStatus from "../components/AgentStatus";

const STAGES = [
  { key: "prospecting",  label: "PROSPECTING" },
  { key: "qualified",    label: "QUALIFIED" },
  { key: "proposal",     label: "PROPOSAL" },
  { key: "negotiation",  label: "NEGOTIATION" },
  { key: "closed_won",   label: "WON" },
];

const STAGE_PROB = { prospecting: 20, qualified: 45, proposal: 60, negotiation: 80, closed_won: 100 };

export default function Pipeline() {
  const [deals, setDeals] = useState([]);
  const [dragId, setDragId] = useState(null);
  const [dragOverStage, setDragOverStage] = useState(null);

  const fetchDeals = async () => {
    const res = await api.get("/pipeline/deals");
    setDeals(res.data.deals || []);
  };

  useEffect(() => { fetchDeals(); }, []);

  const byStage = useMemo(() => {
    const map = Object.fromEntries(STAGES.map((s) => [s.key, []]));
    for (const d of deals) {
      if (map[d.stage]) map[d.stage].push(d);
    }
    return map;
  }, [deals]);

  const onDragStart = (e, deal) => {
    setDragId(deal.id);
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", deal.id);
  };

  const onDragOver = (e, stageKey) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (dragOverStage !== stageKey) setDragOverStage(stageKey);
  };

  const onDragLeave = () => setDragOverStage(null);

  const onDrop = async (e, stageKey) => {
    e.preventDefault();
    const dealId = e.dataTransfer.getData("text/plain") || dragId;
    setDragOverStage(null);
    setDragId(null);
    if (!dealId) return;
    const deal = deals.find((d) => d.id === dealId);
    if (!deal || deal.stage === stageKey) return;

    // Optimistic
    setDeals((ds) => ds.map((d) => d.id === dealId ? { ...d, stage: stageKey, probability: STAGE_PROB[stageKey] } : d));
    try {
      await api.patch(`/pipeline/deals/${dealId}`, {
        stage: stageKey,
        probability: STAGE_PROB[stageKey],
        last_action: `Moved to ${stageKey.replace("_", " ")} via drag-drop`,
      });
      fetchDeals();
    } catch { fetchDeals(); }
  };

  return (
    <div className="p-6 lg:p-10" data-testid="pipeline-page">
      <div className="flex items-end justify-between mb-8 flex-wrap gap-4">
        <div>
          <div className="nx-label mb-2">[ PIPELINE AUTOMATION ]</div>
          <h1 className="font-serif text-4xl lg:text-5xl tracking-tight">Deals that move themselves.</h1>
          <p className="text-zinc-500 mt-2 text-sm">Drag cards between stages · agents recalibrate probability automatically</p>
        </div>
        <div className="flex items-center gap-3 nx-glass px-4 py-2">
          <AgentStatus status="closing" />
          <span className="text-xs text-zinc-400">{deals.length} ACTIVE · NEGOTIATOR-PRIME ENGAGED</span>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-3 mb-6">
        {STAGES.map((s) => {
          const items = byStage[s.key] || [];
          const total = items.reduce((acc, d) => acc + (d.value || 0), 0);
          return (
            <div key={s.key} className="nx-glass p-4" data-testid={`stage-summary-${s.key}`}>
              <div className="nx-label" style={{ fontSize: 9 }}>{s.label}</div>
              <div className="font-mono text-zinc-100 text-lg mt-1">{items.length}</div>
              <div className="text-xs text-zinc-500 mt-1">{fmtUSD(total)}</div>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-5 gap-3 overflow-x-auto" data-testid="kanban-board">
        {STAGES.map((s) => (
          <div
            key={s.key}
            onDragOver={(e) => onDragOver(e, s.key)}
            onDragLeave={onDragLeave}
            onDrop={(e) => onDrop(e, s.key)}
            className="min-w-[200px] transition-all"
            style={dragOverStage === s.key ? { background: "rgba(0,245,212,0.04)", borderRadius: 4 } : {}}
            data-testid={`column-${s.key}`}
          >
            <div className="nx-label mb-3 px-1 flex items-center gap-2">
              {s.label}
              {dragOverStage === s.key && <span className="nx-dot nx-dot-scanning" />}
            </div>
            <div className="space-y-3 min-h-[120px]">
              {byStage[s.key].map((d) => (
                <motion.div
                  key={d.id}
                  layout
                  initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                  draggable
                  onDragStart={(e) => onDragStart(e, d)}
                  onDragEnd={() => { setDragId(null); setDragOverStage(null); }}
                  className="nx-panel nx-card-hover p-4 relative overflow-hidden cursor-grab active:cursor-grabbing select-none"
                  style={{
                    ...(d.agent_status === "closing" ? { borderColor: "rgba(0,245,212,0.4)", boxShadow: "0 0 0 1px rgba(0,245,212,0.18)" } : {}),
                    ...(dragId === d.id ? { opacity: 0.35 } : {}),
                  }}
                  data-testid={`deal-card-${d.id}`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-xs text-zinc-500">{d.probability}% · {fmtUSD(d.value)}</div>
                    <AgentStatus status={d.agent_status} size="xs" />
                  </div>
                  <div className="font-mono text-sm text-zinc-100 mb-1">{d.company}</div>
                  <div className="text-[11px] text-zinc-500 mb-3">{d.contact}</div>
                  <div className="text-[11px] text-zinc-400 border-l-2 pl-2" style={{ borderColor: "var(--nx-cyan)" }}>{d.last_action}</div>
                  {d.agent_status === "closing" && <div className="nx-scan-beam absolute bottom-0 left-0 right-0 h-0.5" />}
                </motion.div>
              ))}
              {byStage[s.key].length === 0 && (
                <div className="text-xs text-zinc-600 text-center py-6 border border-dashed" style={{ borderColor: "var(--nx-border)" }}>
                  drop here
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
