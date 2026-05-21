import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { api, fmtUSD } from "../lib/api";
import { useAuth } from "../lib/AuthContext";
import AgentStatus from "../components/AgentStatus";
import { Rocket, Building2, ChevronRight, CheckCircle2, Loader2, Sparkles, ArrowUpRight, GitBranch } from "lucide-react";

const INDUSTRIES = ["B2B SaaS", "Fintech", "Healthcare", "Cybersecurity", "AI / ML", "DevTools", "Logistics", "Manufacturing", "Energy", "Other"];
const SIZES = ["1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"];
const REVENUE_BANDS = ["Pre-revenue", "$0-1M", "$1-5M", "$5-25M", "$25-100M", "$100M+"];

const STEPS = [
  { key: "company", label: "Company" },
  { key: "icp",     label: "ICP" },
  { key: "value",   label: "Value Prop" },
  { key: "review",  label: "Review" },
];

const TERMINAL_LINES = [
  ">> Initializing Nexus AI…",
  ">> Loading 7-agent fleet [LeadScout-7, Researcher-3, Outreach-Composer, Meeting-Booker, Negotiator-Prime, Pipeline-Analyst, Forecaster]",
  ">> Authenticating company profile…",
  ">> LeadScout-7: indexing 12,407 sources…",
  ">> Researcher-3: building ICP embedding model…",
  ">> Cross-referencing funding rounds in target geographies…",
  ">> Filtering against negative-fit signals (-204 noise rejected)…",
  ">> Computing intent scores via 184-feature model…",
  ">> Negotiator-Prime: estimating ACV bands per prospect…",
  ">> Forecaster: calibrating fit-score distribution…",
  ">> Compiling top 10 targets…",
  ">> READY.",
];

export default function Onboarding() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [step, setStep] = useState(0);
  const [profileId, setProfileId] = useState(null);
  const [promoting, setPromoting] = useState(null);
  const [promoted, setPromoted] = useState({});
  const [form, setForm] = useState({
    company_name: "",
    industry: "",
    company_size: "",
    annual_revenue: "",
    icp_description: "",
    value_proposition: "",
    target_geographies: [],
  });
  const [phase, setPhase] = useState("form"); // form | thinking | results
  const [terminal, setTerminal] = useState([]);
  const [targets, setTargets] = useState([]);
  const [error, setError] = useState(null);

  // Load latest profile + targets on mount — but only after auth resolves
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    (async () => {
      try {
        const p = await api.get("/onboarding/latest");
        if (cancelled || !p.data || !p.data.id) return;
        setProfileId(p.data.id);
        setForm({
          company_name: p.data.company_name || "",
          industry: p.data.industry || "",
          company_size: p.data.company_size || "",
          annual_revenue: p.data.annual_revenue || "",
          icp_description: p.data.icp_description || "",
          value_proposition: p.data.value_proposition || "",
          target_geographies: p.data.target_geographies || [],
        });
        const t = await api.get("/targets", { params: { profile_id: p.data.id } });
        if (cancelled) return;
        if (t.data.targets?.length) {
          setTargets(t.data.targets);
          const initialPromoted = {};
          t.data.targets.forEach((tgt) => { if (tgt.promoted_deal_id) initialPromoted[tgt.id] = tgt.promoted_deal_id; });
          setPromoted(initialPromoted);
          setPhase("results");
        }
      } catch (e) {
        // No prior profile yet — fresh user, leave form empty
        if (e?.response?.status && e.response.status !== 404) {
          console.error("Failed to load onboarding profile:", e);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [user]);

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const toggleGeo = (g) => setForm((f) => ({ ...f, target_geographies: f.target_geographies.includes(g) ? f.target_geographies.filter((x) => x !== g) : [...f.target_geographies, g] }));

  const canNext = () => {
    if (step === 0) return form.company_name && form.industry && form.company_size;
    if (step === 1) return form.icp_description.length >= 20;
    if (step === 2) return form.value_proposition.length >= 20;
    return true;
  };

  const submit = async () => {
    setError(null);
    setPhase("thinking");
    setTerminal([]);
    try {
      const r = await api.post("/onboarding", form);
      const pid = r.data.id;
      setProfileId(pid);

      // Stream terminal lines while LLM runs
      let i = 0;
      const interval = setInterval(() => {
        if (i < TERMINAL_LINES.length) {
          setTerminal((t) => [...t, TERMINAL_LINES[i]]);
          i += 1;
        }
      }, 600);

      const gen = await api.post("/targets/generate", { profile_id: pid });
      clearInterval(interval);
      setTerminal((t) => [...t, ...TERMINAL_LINES.slice(i)]);

      setTargets(gen.data.targets || []);
      setTimeout(() => setPhase("results"), 800);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "Generation failed");
      setPhase("form");
    }
  };

  const reset = () => {
    setStep(0);
    setPhase("form");
    setTargets([]);
    setTerminal([]);
    setPromoted({});
  };

  const promote = async (target) => {
    setPromoting(target.id);
    try {
      const r = await api.post(`/targets/${target.id}/promote`);
      setPromoted((p) => ({ ...p, [target.id]: r.data.deal.id }));
    } catch (e) {
      console.error(e);
    } finally {
      setPromoting(null);
    }
  };

  // ---------- RENDER ----------
  return (
    <div className="p-6 lg:p-10" data-testid="onboarding-page">
      <div className="flex items-end justify-between mb-8 flex-wrap gap-4">
        <div>
          <div className="nx-label mb-2">[ BETA · ONBOARDING ]</div>
          <h1 className="font-serif text-4xl lg:text-5xl tracking-tight">
            Deploy your <span className="italic" style={{ color: "var(--nx-cyan)" }}>autonomous CRO.</span>
          </h1>
          <p className="text-zinc-400 mt-3 max-w-2xl">In 60 seconds, Nexus studies your business and generates your first 10 high-value targets — live.</p>
        </div>
        {phase === "results" && (
          <button onClick={reset} className="nx-btn-ghost" data-testid="restart-onboarding">
            <Rocket size={14} /> New profile
          </button>
        )}
      </div>

      {phase === "form" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* Step nav */}
          <div className="lg:col-span-3 nx-glass p-6 self-start">
            <div className="nx-label mb-4">PROGRESS</div>
            <ol className="space-y-3">
              {STEPS.map((s, i) => (
                <li key={s.key} className="flex items-center gap-3" data-testid={`step-indicator-${i}`}>
                  <div
                    className="w-7 h-7 flex items-center justify-center text-xs font-mono"
                    style={{
                      border: `1px solid ${i <= step ? "var(--nx-cyan)" : "var(--nx-border-strong)"}`,
                      color: i <= step ? "var(--nx-cyan)" : "var(--nx-text-faint)",
                      background: i === step ? "rgba(0,245,212,0.08)" : "transparent",
                    }}
                  >
                    {i < step ? <CheckCircle2 size={14} /> : i + 1}
                  </div>
                  <div className={i === step ? "text-zinc-100" : "text-zinc-500"}>{s.label}</div>
                </li>
              ))}
            </ol>
          </div>

          {/* Form */}
          <div className="lg:col-span-9 nx-glass p-8" data-testid="onboarding-form">
            <AnimatePresence mode="wait">
              <motion.div key={step} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }}>
                {step === 0 && (
                  <div>
                    <h2 className="font-serif text-3xl mb-6">Tell us about your company</h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                      <Field label="COMPANY NAME">
                        <input className="nx-input" value={form.company_name} onChange={(e) => update("company_name", e.target.value)} placeholder="Acme Industries" data-testid="input-company-name" />
                      </Field>
                      <Field label="INDUSTRY">
                        <select className="nx-input" value={form.industry} onChange={(e) => update("industry", e.target.value)} data-testid="input-industry">
                          <option value="">Select…</option>
                          {INDUSTRIES.map((i) => <option key={i} value={i}>{i}</option>)}
                        </select>
                      </Field>
                      <Field label="COMPANY SIZE">
                        <select className="nx-input" value={form.company_size} onChange={(e) => update("company_size", e.target.value)} data-testid="input-company-size">
                          <option value="">Select…</option>
                          {SIZES.map((i) => <option key={i} value={i}>{i}</option>)}
                        </select>
                      </Field>
                      <Field label="ANNUAL REVENUE">
                        <select className="nx-input" value={form.annual_revenue} onChange={(e) => update("annual_revenue", e.target.value)} data-testid="input-revenue">
                          <option value="">Select…</option>
                          {REVENUE_BANDS.map((i) => <option key={i} value={i}>{i}</option>)}
                        </select>
                      </Field>
                    </div>
                  </div>
                )}

                {step === 1 && (
                  <div>
                    <h2 className="font-serif text-3xl mb-2">Define your ideal customer.</h2>
                    <p className="text-zinc-500 mb-6 text-sm">Be specific. Industry, size, role, geography, triggers. The more precise, the sharper the targets.</p>
                    <Field label="ICP DESCRIPTION">
                      <textarea
                        className="nx-input min-h-[140px]"
                        rows={6}
                        value={form.icp_description}
                        onChange={(e) => update("icp_description", e.target.value)}
                        placeholder="Mid-market SaaS companies ($10M-$100M ARR) in North America scaling their go-to-market team. Decision makers: VP Sales, CRO, or Head of RevOps. Strong fit when company has recently raised Series B/C and is hiring SDR/AE roles in volume."
                        data-testid="input-icp"
                      />
                    </Field>
                    <Field label="TARGET GEOGRAPHIES">
                      <div className="flex flex-wrap gap-2 mt-2">
                        {["North America", "EMEA", "APAC", "LATAM", "Global"].map((g) => (
                          <button
                            key={g}
                            onClick={() => toggleGeo(g)}
                            className="px-3 py-1.5 text-xs uppercase tracking-wider transition"
                            style={{
                              border: `1px solid ${form.target_geographies.includes(g) ? "var(--nx-cyan)" : "var(--nx-border-strong)"}`,
                              color: form.target_geographies.includes(g) ? "var(--nx-cyan)" : "var(--nx-text-dim)",
                              background: form.target_geographies.includes(g) ? "rgba(0,245,212,0.06)" : "transparent",
                            }}
                            data-testid={`geo-${g.toLowerCase()}`}
                          >
                            {g}
                          </button>
                        ))}
                      </div>
                    </Field>
                  </div>
                )}

                {step === 2 && (
                  <div>
                    <h2 className="font-serif text-3xl mb-2">What makes you unmistakable?</h2>
                    <p className="text-zinc-500 mb-6 text-sm">Your value prop. Quantified, specific, defensible.</p>
                    <Field label="VALUE PROPOSITION">
                      <textarea
                        className="nx-input min-h-[140px]"
                        rows={6}
                        value={form.value_proposition}
                        onChange={(e) => update("value_proposition", e.target.value)}
                        placeholder="We help mid-market RevOps teams cut sales cycle by 38% and increase win rate by 24% by deploying autonomous AI agents that handle prospecting, outreach, and pipeline orchestration. Our customers replace 6-12 junior SDRs and AEs with one AI deployment."
                        data-testid="input-valueprop"
                      />
                    </Field>
                  </div>
                )}

                {step === 3 && (
                  <div>
                    <h2 className="font-serif text-3xl mb-6">Confirm and deploy.</h2>
                    <div className="space-y-4 text-sm" data-testid="review-summary">
                      <Row label="Company" value={form.company_name} />
                      <Row label="Industry / Size" value={`${form.industry} · ${form.company_size}`} />
                      <Row label="Revenue" value={form.annual_revenue || "—"} />
                      <Row label="ICP" value={form.icp_description} multiline />
                      <Row label="Value Prop" value={form.value_proposition} multiline />
                      <Row label="Geographies" value={form.target_geographies.join(", ") || "Global"} />
                    </div>
                    {error && <div className="mt-4 text-sm" style={{ color: "var(--nx-danger)" }} data-testid="onboarding-error">{error}</div>}
                  </div>
                )}
              </motion.div>
            </AnimatePresence>

            <div className="mt-10 flex items-center justify-between border-t pt-6" style={{ borderColor: "var(--nx-border)" }}>
              <button
                disabled={step === 0}
                onClick={() => setStep((s) => Math.max(0, s - 1))}
                className="nx-btn-ghost disabled:opacity-30 disabled:cursor-not-allowed"
                data-testid="step-back"
              >
                Back
              </button>

              {step < STEPS.length - 1 ? (
                <button onClick={() => setStep((s) => s + 1)} disabled={!canNext()} className="nx-btn-primary disabled:opacity-40 disabled:cursor-not-allowed" data-testid="step-next">
                  Continue <ChevronRight size={14} />
                </button>
              ) : (
                <button onClick={submit} className="nx-btn-primary" data-testid="step-submit">
                  <Sparkles size={14} /> Deploy Nexus AI
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {phase === "thinking" && (
        <div className="nx-glass p-8 relative overflow-hidden min-h-[520px]" data-testid="thinking-panel">
          <div className="flex items-center justify-between mb-6">
            <div>
              <div className="nx-label">[ AI PROCESSING ]</div>
              <h2 className="font-serif text-3xl mt-1">Generating your targets…</h2>
            </div>
            <AgentStatus status="thinking" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="md:col-span-2 nx-panel p-6 font-mono text-sm leading-relaxed h-[400px] overflow-y-auto" data-testid="terminal-output">
              {terminal.map((line, i) => (
                <motion.div key={`${i}-${line}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-zinc-300">
                  {line}
                </motion.div>
              ))}
              <span className="text-zinc-300">
                <Loader2 className="inline animate-spin mr-2" size={12} color="var(--nx-cyan)" />
                <span className="nx-cursor">_</span>
              </span>
              <div className="nx-scan-beam mt-2 h-1" />
            </div>

            <div className="nx-panel p-6">
              <div className="nx-label mb-4">AGENTS ENGAGED</div>
              {["LeadScout-7", "Researcher-3", "Outreach-Composer", "Negotiator-Prime", "Forecaster"].map((a) => (
                <div key={a} className="py-2 border-b last:border-b-0" style={{ borderColor: "var(--nx-border)" }}>
                  <div className="flex items-center justify-between">
                    <div className="text-sm text-zinc-200">{a}</div>
                    <AgentStatus status="thinking" size="xs" />
                  </div>
                </div>
              ))}
              <div className="mt-6 text-xs text-zinc-500">
                Powered by Claude Sonnet 4.5 · Avg generation: 18s
              </div>
            </div>
          </div>
        </div>
      )}

      {phase === "results" && (
        <div data-testid="results-panel">
          <div className="nx-glass p-6 mb-6 flex items-center justify-between flex-wrap gap-3">
            <div>
              <div className="nx-label mb-1">DEPLOYMENT COMPLETE</div>
              <div className="font-serif text-2xl">{targets.length} high-value targets identified.</div>
            </div>
            <AgentStatus status="closing" label="READY FOR OUTREACH" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {targets.map((t, i) => (
              <motion.div
                key={t.id || i}
                initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
                className="nx-glass nx-card-hover p-6 relative overflow-hidden"
                data-testid={`target-card-${i}`}
              >
                <div className="absolute top-0 right-0 px-3 py-1.5 text-[10px]" style={{ background: "var(--nx-cyan)", color: "#050505", letterSpacing: "0.14em" }}>
                  FIT {t.fit_score}
                </div>
                <div className="flex items-start gap-3 mb-4">
                  <div className="w-10 h-10 flex items-center justify-center border" style={{ borderColor: "var(--nx-border-strong)" }}>
                    <Building2 size={16} color="var(--nx-cyan)" />
                  </div>
                  <div>
                    <div className="font-serif text-xl leading-tight">{t.company_name}</div>
                    <div className="text-xs text-zinc-500 mt-0.5">{t.industry} · {t.headquarters}</div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 text-xs mb-4">
                  <Meta label="EMPLOYEES" value={t.employee_count} />
                  <Meta label="REVENUE" value={t.estimated_revenue} />
                  <Meta label="DEAL SIZE" value={t.estimated_deal_size} accent />
                  <Meta label="SIGNAL" value={`${t.signal_strength}/100`} accent />
                </div>

                <div className="border-l-2 pl-3 mb-3" style={{ borderColor: "var(--nx-cyan)" }}>
                  <div className="nx-label" style={{ fontSize: 9 }}>INTENT SIGNAL</div>
                  <div className="text-sm text-zinc-200 mt-1">{t.intent_signal}</div>
                </div>

                <div className="border-l-2 pl-3 mb-4" style={{ borderColor: "var(--nx-orange)" }}>
                  <div className="nx-label" style={{ fontSize: 9 }}>DECISION MAKER</div>
                  <div className="text-sm text-zinc-200 mt-1">{t.decision_maker_name}</div>
                  <div className="text-xs text-zinc-500">{t.decision_maker_title}</div>
                </div>

                <div className="text-xs text-zinc-400 mb-4">
                  <span className="nx-label" style={{ fontSize: 9 }}>RECOMMENDED PLAY:</span> {t.recommended_play}
                </div>

                <button
                  onClick={() => promoted[t.id] ? navigate("/app/pipeline") : promote(t)}
                  disabled={promoting === t.id}
                  className={promoted[t.id] ? "nx-btn-primary w-full justify-center" : "nx-btn-ghost w-full justify-center"}
                  data-testid={`target-promote-${i}`}
                >
                  {promoting === t.id ? (
                    <><Loader2 className="animate-spin" size={14} /> Promoting…</>
                  ) : promoted[t.id] ? (
                    <><GitBranch size={14} /> View in pipeline <ArrowUpRight size={14} /></>
                  ) : (
                    <><Sparkles size={14} /> Promote to pipeline</>
                  )}
                </button>
              </motion.div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const Field = ({ label, children }) => (
  <label className="block">
    <div className="nx-label mb-2">{label}</div>
    {children}
  </label>
);

const Row = ({ label, value, multiline }) => (
  <div className={`grid ${multiline ? "grid-cols-1 md:grid-cols-[140px_1fr]" : "grid-cols-[140px_1fr]"} gap-3 py-3 border-b`} style={{ borderColor: "var(--nx-border)" }}>
    <div className="nx-label">{label}</div>
    <div className="text-zinc-200 text-sm whitespace-pre-wrap">{value}</div>
  </div>
);

const Meta = ({ label, value, accent }) => (
  <div>
    <div className="nx-label" style={{ fontSize: 9 }}>{label}</div>
    <div className={`font-mono mt-1 ${accent ? "" : "text-zinc-300"}`} style={accent ? { color: "var(--nx-cyan)" } : {}}>{value}</div>
  </div>
);
