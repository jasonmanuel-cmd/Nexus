import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "../lib/api";
import AgentStatus from "../components/AgentStatus";
import { Radar, Zap, Building2, Users, Briefcase, TrendingUp } from "lucide-react";

const SIGNAL_ICON = {
  hiring: Users, funding: TrendingUp, tech_change: Zap, expansion: Building2, social: Briefcase,
};

const formatTime = (iso) => {
  try {
    const diff = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  } catch { return iso; }
};

export default function LeadEngine() {
  const [signals, setSignals] = useState([]);
  const [scanning, setScanning] = useState(false);
  const [progress, setProgress] = useState(0);

  const fetchSignals = async () => {
    const res = await api.get("/leads/signals");
    setSignals(res.data.signals || []);
  };

  useEffect(() => { fetchSignals(); }, []);

  const runScan = async () => {
    setScanning(true);
    setProgress(0);
    const interval = setInterval(() => setProgress((p) => Math.min(p + Math.random() * 12, 95)), 180);
    try {
      await api.post("/leads/scan");
      await fetchSignals();
    } finally {
      clearInterval(interval);
      setProgress(100);
      setTimeout(() => { setScanning(false); setProgress(0); }, 600);
    }
  };

  return (
    <div className="p-6 lg:p-10" data-testid="lead-engine-page">
      <div className="flex items-end justify-between mb-8 flex-wrap gap-4">
        <div>
          <div className="nx-label mb-2">[ AUTONOMOUS LEAD ENGINE ]</div>
          <h1 className="font-serif text-4xl lg:text-5xl tracking-tight">Web-scale intent surveillance.</h1>
          <p className="text-zinc-400 mt-3 max-w-2xl">Scanning <span className="text-zinc-200">12,400+</span> public &amp; proprietary sources for high-intent buying signals across your ICP.</p>
        </div>
        <button onClick={runScan} disabled={scanning} className="nx-btn-primary" data-testid="run-scan-btn">
          <Radar size={14} /> {scanning ? "Scanning…" : "Trigger live scan"}
        </button>
      </div>

      {/* Scan progress + status */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-6">
        <div className="md:col-span-3 nx-glass p-5 relative overflow-hidden" data-testid="scan-status-panel">
          <div className="flex items-center justify-between mb-3">
            <div className="nx-label">SCAN STATUS</div>
            <AgentStatus status={scanning ? "scanning" : "idle"} />
          </div>
          <div className="font-mono text-zinc-300 text-sm mb-3">
            {scanning ? "LeadScout-7 actively crawling sources…" : "Ready. Standby."}
          </div>
          <div className="relative h-2 w-full" style={{ background: "rgba(255,255,255,0.05)" }}>
            <motion.div
              className="absolute inset-y-0 left-0"
              style={{ background: "var(--nx-cyan)" }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.2 }}
            />
            {scanning && <div className="nx-scan-beam" />}
          </div>
          <div className="mt-3 grid grid-cols-3 gap-3 text-xs text-zinc-500">
            <div>SOURCES: <span className="text-zinc-200 font-mono">12,407</span></div>
            <div>SIGNALS / HR: <span className="text-zinc-200 font-mono">284</span></div>
            <div>NOISE FILTER: <span style={{ color: "var(--nx-cyan)" }} className="font-mono">94.2%</span></div>
          </div>
        </div>

        <div className="nx-glass p-5" data-testid="signal-count">
          <div className="nx-label">TOTAL SIGNALS</div>
          <div className="font-mono text-4xl mt-2" style={{ color: "var(--nx-cyan)" }}>{signals.length}</div>
          <div className="text-xs text-zinc-500 mt-1">indexed last 24h</div>
        </div>
      </div>

      {/* Signal table */}
      <div className="nx-glass overflow-hidden" data-testid="signals-table">
        <div className="grid grid-cols-12 gap-3 px-5 py-3 nx-label border-b" style={{ borderColor: "var(--nx-border)" }}>
          <div className="col-span-3">COMPANY</div>
          <div className="col-span-2">SIGNAL TYPE</div>
          <div className="col-span-4">DESCRIPTION</div>
          <div className="col-span-1 text-right">STRENGTH</div>
          <div className="col-span-2">SOURCE / TIME</div>
        </div>
        <AnimatePresence initial={false}>
          {signals.map((s, i) => {
            const Icon = SIGNAL_ICON[s.signal_type] || Zap;
            return (
              <motion.div
                key={s.id || i}
                initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}
                className="grid grid-cols-12 gap-3 px-5 py-4 border-b hover:bg-white/[0.02] items-center transition"
                style={{ borderColor: "var(--nx-border)" }}
                data-testid={`signal-row-${i}`}
              >
                <div className="col-span-3">
                  <div className="font-mono text-zinc-100">{s.company}</div>
                  <div className="text-xs text-zinc-500">{s.domain}</div>
                </div>
                <div className="col-span-2 flex items-center gap-2">
                  <Icon size={14} color="var(--nx-cyan)" />
                  <span className="text-xs text-zinc-300 uppercase tracking-wider">{s.signal_type.replace("_", " ")}</span>
                </div>
                <div className="col-span-4 text-sm text-zinc-300">{s.description}</div>
                <div className="col-span-1 text-right">
                  <div className="inline-flex items-center gap-2">
                    <div className="font-mono text-sm" style={{ color: s.strength >= 90 ? "var(--nx-cyan)" : s.strength >= 80 ? "#fafafa" : "var(--nx-orange)" }}>{s.strength}</div>
                  </div>
                  <div className="h-1 mt-1 w-full" style={{ background: "rgba(255,255,255,0.05)" }}>
                    <div className="h-full" style={{ width: `${s.strength}%`, background: s.strength >= 90 ? "var(--nx-cyan)" : "var(--nx-orange)" }} />
                  </div>
                </div>
                <div className="col-span-2 text-xs">
                  <div className="text-zinc-300">{s.source}</div>
                  <div className="text-zinc-500">{formatTime(s.detected_at)}</div>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
        {signals.length === 0 && <div className="px-5 py-10 text-center text-zinc-500">No signals yet. Run a scan.</div>}
      </div>
    </div>
  );
}
