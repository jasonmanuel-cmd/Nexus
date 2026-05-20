import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, fmtUSD } from "../lib/api";
import { ArrowUpRight, Check, Loader2, Sparkles, ShieldCheck, X, Calendar } from "lucide-react";
import AgentStatus from "../components/AgentStatus";

export default function Subscribe() {
  const [packages, setPackages] = useState([]);
  const [subscription, setSubscription] = useState(null);
  const [busy, setBusy] = useState(null);
  const [canceling, setCanceling] = useState(false);
  const navigate = useNavigate();

  const fetchAll = async () => {
    const [pkgs, sub] = await Promise.all([api.get("/payments/packages"), api.get("/payments/subscription")]);
    setPackages(pkgs.data.packages || []);
    setSubscription(sub.data);
  };

  useEffect(() => { fetchAll(); }, []);

  const subscribe = async (pkgId) => {
    setBusy(pkgId);
    try {
      const r = await api.post("/payments/checkout/session", {
        package_id: pkgId,
        origin_url: window.location.origin,
      });
      window.location.href = r.data.url;
    } catch (e) {
      console.error(e);
      setBusy(null);
    }
  };

  const cancel = async () => {
    setCanceling(true);
    try {
      await api.post("/payments/subscription/cancel");
      await fetchAll();
    } finally {
      setCanceling(false);
    }
  };

  const featureMap = {
    operator: ["3 AI agents", "500 prospects / mo", "Standard intent signals", "Email + calendar automation"],
    scale:    ["7 AI agents", "Unlimited prospects", "Premium intent + dark social", "Full pipeline orchestration", "Slack + CRM bidirectional"],
  };

  return (
    <div className="p-6 lg:p-10" data-testid="subscribe-page">
      <div className="mb-10 max-w-3xl">
        <div className="nx-label mb-2">[ BILLING · POWERED BY SQUARE ]</div>
        <h1 className="font-serif text-4xl lg:text-5xl tracking-tight leading-[1.02]">
          Activate your <span className="italic" style={{ color: "var(--nx-cyan)" }}>autonomous CRO.</span>
        </h1>
        <p className="text-zinc-400 mt-3">Sandbox-mode Square Checkout · Cancel anytime · SOC 2 secured.</p>
      </div>

      {subscription?.active && (
        <div className="nx-glass p-6 mb-6 flex items-center justify-between flex-wrap gap-4" data-testid="active-subscription-panel" style={{ borderColor: "rgba(0,245,212,0.4)" }}>
          <div className="flex items-center gap-4">
            <AgentStatus status="closing" label="ACTIVE" />
            <div>
              <div className="font-serif text-2xl">{subscription.package?.name} plan</div>
              <div className="text-xs text-zinc-500 flex items-center gap-2 mt-1">
                <Calendar size={12} /> Renews {subscription.renews_at ? new Date(subscription.renews_at).toLocaleDateString() : "—"} · {fmtUSD(subscription.package?.amount || 0)}/mo
              </div>
            </div>
          </div>
          <button onClick={cancel} disabled={canceling} className="nx-btn-ghost" data-testid="cancel-subscription-btn" style={{ color: "var(--nx-danger)", borderColor: "rgba(255,51,102,0.4)" }}>
            {canceling ? <><Loader2 className="animate-spin" size={14} /> Canceling…</> : <><X size={14} /> Cancel subscription</>}
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {packages.map((p) => {
          const featured = p.id === "scale";
          const isCurrent = subscription?.active && subscription?.package_id === p.id;
          return (
            <div
              key={p.id}
              className="nx-glass p-8 relative"
              style={featured ? { borderColor: "var(--nx-cyan)", boxShadow: "0 0 50px -16px rgba(0,245,212,0.35)" } : {}}
              data-testid={`subscribe-${p.id}`}
            >
              {featured && (
                <div className="absolute -top-3 left-8 px-3 py-1 text-[10px] tracking-[0.18em]" style={{ background: "var(--nx-cyan)", color: "#050505" }}>
                  MOST DEPLOYED
                </div>
              )}
              <div className="nx-label mb-3">{p.name.toUpperCase()}</div>
              <div className="flex items-baseline gap-1 mb-2">
                <span className="font-serif text-5xl">{fmtUSD(p.amount)}</span>
                <span className="text-zinc-500">/mo</span>
              </div>
              <div className="text-sm text-zinc-400 mb-6">{p.description}</div>
              <ul className="space-y-3 mb-8">
                {(featureMap[p.id] || []).map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm text-zinc-300">
                    <Check size={14} color="var(--nx-cyan)" className="mt-0.5 flex-shrink-0" /> {f}
                  </li>
                ))}
              </ul>
              <button
                onClick={() => subscribe(p.id)}
                disabled={busy !== null || isCurrent}
                className={featured ? "nx-btn-primary w-full justify-center" : "nx-btn-ghost w-full justify-center"}
                style={isCurrent ? { opacity: 0.5, cursor: "not-allowed" } : {}}
                data-testid={`subscribe-btn-${p.id}`}
              >
                {isCurrent ? <><Check size={14} /> Current plan</> : busy === p.id ? <><Loader2 className="animate-spin" size={14} /> Redirecting…</> : <><Sparkles size={14} /> Subscribe</>}
              </button>
            </div>
          );
        })}

        <div className="nx-glass p-8 md:col-span-3" data-testid="subscribe-enterprise">
          <div className="flex items-start justify-between flex-wrap gap-6">
            <div>
              <div className="nx-label mb-2">ENTERPRISE</div>
              <div className="flex items-baseline gap-3 mb-2">
                <span className="font-serif text-4xl">Custom</span>
                <AgentStatus status="closing" label="WHITE-GLOVE DEPLOYMENT" />
              </div>
              <p className="text-zinc-400 text-sm max-w-2xl">Custom agent fleet, dedicated revenue model, on-prem signal sources, SSO + audit, dedicated CSM.</p>
            </div>
            <a href="mailto:sales@nexus.ai" className="nx-btn-ghost" data-testid="enterprise-cta">
              Talk to sales <ArrowUpRight size={14} />
            </a>
          </div>
        </div>
      </div>

      <div className="mt-10 flex items-center justify-between flex-wrap gap-4">
        <div className="nx-label flex items-center gap-3">
          <ShieldCheck size={14} color="var(--nx-cyan)" /> SOC 2 · GDPR · ISO 27001 · Square-secured · Cancel anytime
        </div>
        <button onClick={() => navigate("/app/dashboard")} className="nx-btn-ghost" data-testid="back-to-dashboard">
          Back to dashboard
        </button>
      </div>
    </div>
  );
}
