import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api, fmtUSD } from "../lib/api";
import AgentStatus from "../components/AgentStatus";
import Ticker from "../components/Ticker";
import { Activity, TrendingUp, Calendar, Target, Brain, GitBranch, Zap } from "lucide-react";

const formatTime = (iso) => {
  try {
    const d = new Date(iso);
    const diff = Math.round((Date.now() - d.getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  } catch {
    return iso;
  }
};

const MetricCard = ({ label, value, sub, icon: Icon, testid, format }) => (
  <div className="nx-glass nx-card-hover p-5 relative overflow-hidden" data-testid={testid}>
    <div className="flex items-start justify-between">
      <div className="nx-label">{label}</div>
      <Icon size={14} className="text-zinc-500" />
    </div>
    <div className="mt-4 text-3xl font-mono" style={{ color: "var(--nx-cyan)" }}>
      <Ticker value={value} format={format} />
    </div>
    {sub && <div className="text-xs text-zinc-500 mt-1">{sub}</div>}
  </div>
);

export default function Dashboard() {
  const [metrics, setMetrics] = useState(null);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchAll = async () => {
    try {
      const [m, a] = await Promise.all([api.get("/dashboard/metrics"), api.get("/dashboard/activity")]);
      setMetrics(m.data);
      setActivities(a.data.activities || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, 8000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="p-6 lg:p-10" data-testid="dashboard-page">
      {/* Header */}
      <div className="flex items-end justify-between mb-8 flex-wrap gap-4">
        <div>
          <div className="nx-label mb-2">[ COMMAND CENTER ]</div>
          <h1 className="font-serif text-4xl lg:text-5xl tracking-tight">Live revenue operations.</h1>
        </div>
        <div className="flex items-center gap-3 nx-glass px-4 py-2">
          <AgentStatus status="scanning" />
          <span className="text-xs text-zinc-400">7 / 7 AGENTS ONLINE · SYNCING EVERY 8s</span>
        </div>
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-8">
        <MetricCard label="REVENUE WON" value={metrics?.revenue_won || 0} format={fmtUSD} icon={TrendingUp} testid="metric-revenue-won" />
        <MetricCard label="PIPELINE" value={metrics?.pipeline_value || 0} format={fmtUSD} icon={GitBranch} testid="metric-pipeline" />
        <MetricCard label="WEIGHTED" value={metrics?.weighted_pipeline || 0} format={fmtUSD} icon={Brain} testid="metric-weighted" />
        <MetricCard label="ACTIVE DEALS" value={metrics?.active_deals || 0} icon={Target} testid="metric-active-deals" />
        <MetricCard label="MEETINGS / WK" value={metrics?.meetings_booked_week || 0} icon={Calendar} testid="metric-meetings" />
        <MetricCard label="WIN RATE" value={(metrics?.win_rate || 0) * 100} format={(n) => `${n.toFixed(1)}%`} icon={Zap} testid="metric-win-rate" />
      </div>

      {/* Body grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Activity feed */}
        <div className="lg:col-span-2 nx-glass p-6 relative" data-testid="activity-feed">
          <div className="flex items-center justify-between mb-6">
            <div>
              <div className="nx-label">LIVE AGENT ACTIVITY</div>
              <h2 className="font-serif text-2xl mt-1">Real-time stream</h2>
            </div>
            <AgentStatus status="scanning" />
          </div>

          {loading && <div className="text-zinc-500 text-sm">Connecting to agent feed...</div>}

          <div className="space-y-2 max-h-[560px] overflow-y-auto pr-2">
            <AnimatePresence initial={false}>
              {activities.map((a, i) => (
                <motion.div
                  key={a.id || i}
                  initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.3 }}
                  className="border-l-2 pl-4 py-3 hover:bg-white/[0.02] transition group"
                  style={{
                    borderColor:
                      a.status === "closing" ? "#fafafa" :
                      a.status === "scanning" ? "var(--nx-cyan)" :
                      a.status === "thinking" ? "var(--nx-orange)" : "#52525b"
                  }}
                  data-testid={`activity-${i}`}
                >
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-sm text-zinc-200">{a.agent}</span>
                      <AgentStatus status={a.status} size="xs" />
                    </div>
                    <span className="text-[11px] text-zinc-500">{formatTime(a.timestamp)}</span>
                  </div>
                  <div className="mt-1 text-sm text-zinc-400">{a.action}</div>
                  <div className="mt-1 text-sm text-zinc-200">→ {a.target} {a.outcome && <span className="text-zinc-500">· {a.outcome}</span>}</div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>

        {/* Side panels */}
        <div className="flex flex-col gap-4">
          <div className="nx-glass p-6" data-testid="agent-fleet">
            <div className="nx-label mb-4">AGENT FLEET</div>
            {[
              { name: "LeadScout-7", status: "scanning", load: 87 },
              { name: "Outreach-Composer", status: "thinking", load: 64 },
              { name: "Researcher-3", status: "scanning", load: 72 },
              { name: "Meeting-Booker", status: "closing", load: 41 },
              { name: "Negotiator-Prime", status: "closing", load: 95 },
              { name: "Pipeline-Analyst", status: "thinking", load: 58 },
              { name: "Forecaster", status: "idle", load: 12 },
            ].map((a) => (
              <div key={a.name} className="py-2 border-b last:border-b-0" style={{ borderColor: "var(--nx-border)" }}>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="text-sm text-zinc-200">{a.name}</div>
                  <AgentStatus status={a.status} size="xs" />
                </div>
                <div className="h-1 w-full" style={{ background: "rgba(255,255,255,0.05)" }}>
                  <div className="h-full transition-all" style={{ width: `${a.load}%`, background: a.status === "thinking" ? "var(--nx-orange)" : "var(--nx-cyan)" }} />
                </div>
              </div>
            ))}
          </div>

          <div className="nx-glass p-6" data-testid="forecast-panel">
            <div className="nx-label mb-3">Q1 FORECAST</div>
            <div className="font-serif text-4xl mb-2" style={{ color: "var(--nx-cyan)" }}>
              <Ticker value={metrics?.pipeline_value * 0.42 || 0} format={fmtUSD} />
            </div>
            <div className="text-xs text-zinc-500">Confidence 87% · {metrics?.avg_deal_cycle_days || 23}d avg cycle</div>
            <div className="mt-4 h-px" style={{ background: "var(--nx-border)" }} />
            <div className="mt-4 flex items-center gap-2 text-xs text-zinc-400">
              <Activity size={12} color="var(--nx-cyan)" /> Recalibrated 14 minutes ago
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
