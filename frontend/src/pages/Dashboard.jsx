import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, AreaChart, Area, CartesianGrid } from "recharts";
import { api, fmtUSD, fmtCompact } from "../lib/api";
import AgentStatus from "../components/AgentStatus";
import Ticker from "../components/Ticker";
import { Activity, TrendingUp, Calendar, Target, Brain, GitBranch, Zap } from "lucide-react";

const formatTime = (iso) => {
  try {
    const diff = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  } catch { return iso; }
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

const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="nx-glass px-3 py-2 text-xs">
      <div className="nx-label mb-1">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey || p.name} className="text-zinc-200" style={{ color: p.color }}>
          {p.name}: <span className="font-mono">{typeof p.value === "number" ? fmtCompact(p.value) : p.value}</span>
        </div>
      ))}
    </div>
  );
};

export default function Dashboard() {
  const [metrics, setMetrics] = useState(null);
  const [activities, setActivities] = useState([]);
  const [charts, setCharts] = useState({ waterfall: [], productivity: [] });
  const [loading, setLoading] = useState(true);

  const fetchAll = async () => {
    try {
      const [m, a, c] = await Promise.all([
        api.get("/dashboard/metrics"),
        api.get("/dashboard/activity"),
        api.get("/dashboard/charts"),
      ]);
      setMetrics(m.data);
      setActivities(a.data.activities || []);
      setCharts(c.data);
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

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        <MetricCard label="REVENUE WON" value={metrics?.revenue_won || 0} format={fmtUSD} icon={TrendingUp} testid="metric-revenue-won" />
        <MetricCard label="PIPELINE" value={metrics?.pipeline_value || 0} format={fmtUSD} icon={GitBranch} testid="metric-pipeline" />
        <MetricCard label="WEIGHTED" value={metrics?.weighted_pipeline || 0} format={fmtUSD} icon={Brain} testid="metric-weighted" />
        <MetricCard label="ACTIVE DEALS" value={metrics?.active_deals || 0} icon={Target} testid="metric-active-deals" />
        <MetricCard label="MEETINGS / WK" value={metrics?.meetings_booked_week || 0} icon={Calendar} testid="metric-meetings" />
        <MetricCard label="WIN RATE" value={(metrics?.win_rate || 0) * 100} format={(n) => `${n.toFixed(1)}%`} icon={Zap} testid="metric-win-rate" />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div className="lg:col-span-2 nx-glass p-6" data-testid="waterfall-chart">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="nx-label">REVENUE WATERFALL</div>
              <h2 className="font-serif text-xl mt-1">Pipeline → Won</h2>
            </div>
            <AgentStatus status="thinking" />
          </div>
          <div className="h-[260px] w-full min-h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={charts.waterfall} margin={{ top: 10, right: 10, left: 0, bottom: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="stage" tick={{ fill: "#a1a1aa", fontSize: 10, fontFamily: "Geist Mono" }} axisLine={{ stroke: "rgba(255,255,255,0.08)" }} tickLine={false} />
                <YAxis tick={{ fill: "#a1a1aa", fontSize: 10, fontFamily: "Geist Mono" }} axisLine={{ stroke: "rgba(255,255,255,0.08)" }} tickLine={false} tickFormatter={fmtCompact} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(0,245,212,0.05)" }} />
                <Bar dataKey="total" name="Total" fill="rgba(0,245,212,0.2)" stroke="#00f5d4" strokeWidth={1} radius={[2, 2, 0, 0]} />
                <Bar dataKey="weighted" name="Weighted" fill="rgba(255,85,0,0.18)" stroke="#ff5500" strokeWidth={1} radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="nx-glass p-6" data-testid="productivity-chart">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="nx-label">AGENT PRODUCTIVITY</div>
              <h2 className="font-serif text-xl mt-1">Actions / agent</h2>
            </div>
            <AgentStatus status="scanning" />
          </div>
          <div className="h-[260px] w-full min-h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={charts.productivity} margin={{ top: 10, right: 5, left: 0, bottom: 10 }}>
                <defs>
                  <linearGradient id="cyanGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#00f5d4" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="#00f5d4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="agent" tick={{ fill: "#a1a1aa", fontSize: 8, fontFamily: "Geist Mono" }} axisLine={{ stroke: "rgba(255,255,255,0.08)" }} tickLine={false} angle={-25} textAnchor="end" height={60} />
                <YAxis tick={{ fill: "#a1a1aa", fontSize: 10, fontFamily: "Geist Mono" }} axisLine={{ stroke: "rgba(255,255,255,0.08)" }} tickLine={false} />
                <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#00f5d4", strokeWidth: 1, strokeDasharray: "3 3" }} />
                <Area type="monotone" dataKey="actions" stroke="#00f5d4" strokeWidth={1.5} fill="url(#cyanGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Body grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
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
