import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { api, fmtUSD } from "../lib/api";
import AgentStatus from "../components/AgentStatus";
import { ChevronRight, ChevronLeft } from "lucide-react";

const STAGES = [
  { key: "prospecting",  label: "PROSPECTING" },
  { key: "qualified",    label: "QUALIFIED" },
  { key: "proposal",     label: "PROPOSAL" },
  { key: "negotiation",  label: "NEGOTIATION" },
  { key: "closed_won",   label: "WON" },
];

export default function Pipeline() {
  const [deals, setDeals] = useState([]);

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

  const moveDeal = async (deal, dir) => {
    const idx = STAGES.findIndex((s) => s.key === deal.stage);
    const nextIdx = Math.min(Math.max(idx + dir, 0), STAGES.length - 1);
    const newStage = STAGES[nextIdx].key;
    if (newStage === deal.stage) return;
    const probabilityMap = { prospecting: 20, qualified: 45, proposal: 60, negotiation: 80, closed_won: 100 };
    await api.patch(`/pipeline/deals/${deal.id}`, {
      stage: newStage,
      probability: probabilityMap[newStage],
      last_action: dir > 0 ? `Advanced to ${newStage.replace("_", " ")}` : `Returned to ${newStage.replace("_", " ")}`,
    });
    fetchDeals();
  };

  return (
    <div className="p-6 lg:p-10" data-testid="pipeline-page">
      <div className="flex items-end justify-between mb-8 flex-wrap gap-4">
        <div>
          <div className="nx-label mb-2">[ PIPELINE AUTOMATION ]</div>
          <h1 className="font-serif text-4xl lg:text-5xl tracking-tight">Deals that move themselves.</h1>
        </div>
        <div className="flex items-center gap-3 nx-glass px-4 py-2">
          <AgentStatus status="closing" />
          <span className="text-xs text-zinc-400">{deals.length} ACTIVE · NEGOTIATOR-PRIME ENGAGED</span>
        </div>
      </div>

      {/* Stage summary strip */}
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

      {/* Kanban */}
      <div className="grid grid-cols-5 gap-3 overflow-x-auto" data-testid="kanban-board">
        {STAGES.map((s) => (
          <div key={s.key} className="min-w-[200px]" data-testid={`column-${s.key}`}>
            <div className="nx-label mb-3 px-1">{s.label}</div>
            <div className="space-y-3">
              {byStage[s.key].map((d) => (
                <motion.div
                  key={d.id}
                  layout
                  initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                  className="nx-panel nx-card-hover p-4 relative overflow-hidden"
                  style={d.agent_status === "closing" ? { borderColor: "rgba(0,245,212,0.4)", boxShadow: "0 0 0 1px rgba(0,245,212,0.18)" } : {}}
                  data-testid={`deal-card-${d.id}`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-xs text-zinc-500">{d.probability}% · {fmtUSD(d.value)}</div>
                    <AgentStatus status={d.agent_status} size="xs" />
                  </div>
                  <div className="font-mono text-sm text-zinc-100 mb-1">{d.company}</div>
                  <div className="text-[11px] text-zinc-500 mb-3">{d.contact}</div>
                  <div className="text-[11px] text-zinc-400 border-l-2 pl-2 mb-3" style={{ borderColor: "var(--nx-cyan)" }}>{d.last_action}</div>
                  <div className="flex items-center justify-between">
                    <button onClick={() => moveDeal(d, -1)} className="text-zinc-500 hover:text-zinc-200 transition" data-testid={`deal-prev-${d.id}`}>
                      <ChevronLeft size={14} />
                    </button>
                    {d.agent_status === "closing" && <div className="nx-scan-beam absolute bottom-0 left-0 right-0 h-0.5" />}
                    <button onClick={() => moveDeal(d, 1)} className="text-zinc-500 hover:text-[#00f5d4] transition" data-testid={`deal-next-${d.id}`}>
                      <ChevronRight size={14} />
                    </button>
                  </div>
                </motion.div>
              ))}
              {byStage[s.key].length === 0 && (
                <div className="text-xs text-zinc-600 text-center py-6 border border-dashed" style={{ borderColor: "var(--nx-border)" }}>
                  empty
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
