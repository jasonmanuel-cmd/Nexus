import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowUpRight, Cpu, Radar, GitBranch, Rocket, Zap, Brain, ShieldCheck, Activity, Sparkles, TrendingUp, Workflow, Mail, Users, CheckCircle2, Loader2, Copy } from "lucide-react";
import AgentStatus from "../components/AgentStatus";
import { useAuth } from "../lib/AuthContext";
import { api, fmtCompact } from "../lib/api";

const HERO_BG = "https://images.unsplash.com/photo-1772862991841-f0e3e1502d7b?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2OTV8MHwxfHNlYXJjaHwyfHxhYnN0cmFjdCUyMGRhcmslMjB0ZWNobm9sb2d5JTIwbmV0d29yayUyMG5vZGVzfGVufDB8fHx8MTc3OTI2ODM0NXww&ixlib=rb-4.1.0&q=85";

const SPONSORS = [
  "https://images.unsplash.com/photo-1761044590687-29916cbe4203?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMjV8MHwxfHNlYXJjaHw0fHxjb21wYW55JTIwbG9nbyUyMGRhcmslMjBiYWNrZ3JvdW5kfGVufDB8fHx8MTc3OTI2ODA0MHww&ixlib=rb-4.1.0&q=85",
  "https://images.unsplash.com/photo-1772760110621-d7b6f54c1e42?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMjV8MHwxfHNlYXJjaHwyfHxjb21wYW55JTIwbG9nbyUyMGRhcmslMjBiYWNrZ3JvdW5kfGVufDB8fHx8MTc3OTI2ODA0MHww&ixlib=rb-4.1.0&q=85",
  "https://images.pexels.com/photos/18203253/pexels-photo-18203253.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
  "https://images.pexels.com/photos/9949424/pexels-photo-9949424.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
  "https://images.unsplash.com/photo-1590664177914-9da6d6e8f0f6?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMjV8MHwxfHNlYXJjaHwxfHxjb21wYW55JTIwbG9nbyUyMGRhcmslMjBiYWNrZ3JvdW5kfGVufDB8fHx8MTc3OTI2ODA0MHww&ixlib=rb-4.1.0&q=85",
];

const Nav = () => {
  const { user } = useAuth();
  const startHref = user ? "/app/onboarding" : "/login";
  const launchHref = user ? "/app/dashboard" : "/login";
  return (
  <header
    className="fixed top-0 left-0 right-0 z-50 border-b"
    style={{ borderColor: "var(--nx-border)", background: "rgba(5,5,5,0.75)", backdropFilter: "blur(18px)" }}
    data-testid="landing-nav"
  >
    <div className="max-w-7xl mx-auto px-6 lg:px-10 h-16 flex items-center justify-between">
      <Link to="/" className="flex items-center gap-3" data-testid="landing-logo">
        <div className="w-8 h-8 flex items-center justify-center" style={{ background: "var(--nx-cyan)", color: "#050505" }}>
          <Cpu size={16} strokeWidth={2.5} />
        </div>
        <div>
          <div className="font-serif text-xl leading-none">Nexus</div>
          <div className="nx-label" style={{ fontSize: 8 }}>AUTONOMOUS CRO</div>
        </div>
      </Link>
      <nav className="hidden md:flex items-center gap-10">
        {["Product", "Agents", "Pricing", "Customers"].map((l) => (
          <a key={l} href={`#${l.toLowerCase()}`} className="nx-label hover:text-[#00f5d4] transition" data-testid={`nav-${l.toLowerCase()}`}>
            {l}
          </a>
        ))}
      </nav>
      <div className="flex items-center gap-3">
        <Link to={launchHref} className="nx-btn-ghost hidden sm:inline-flex" data-testid="nav-launch-app">
          {user ? "Launch app" : "Sign in"} <ArrowUpRight size={14} />
        </Link>
        <Link to={startHref} className="nx-btn-primary" data-testid="nav-start-beta">
          Start beta <ArrowUpRight size={14} />
        </Link>
      </div>
    </div>
  </header>
  );
};

const Hero = () => {
  const { user } = useAuth();
  const startHref = user ? "/app/onboarding" : "/login";
  const dashHref = user ? "/app/dashboard" : "/login";
  const [stats, setStats] = useState(null);
  useEffect(() => {
    api.get("/landing/hero-stats")
      .then((r) => setStats(r.data))
      .catch((e) => console.error("hero stats load failed", e));
  }, []);
  const heroPanels = stats
    ? [
        { label: "PIPELINE", value: `$${fmtCompact(stats.pipeline_value)}`, sub: `${stats.active_deals} active deals`, icon: TrendingUp },
        { label: "TARGETS / 30D", value: fmtCompact(stats.targets_identified), sub: "ICP-matched, ranked", icon: Activity },
        { label: "ACCURACY", value: `${stats.accuracy_pct}%`, sub: "intent-signal precision", icon: ShieldCheck },
        { label: "AGENTS", value: String(stats.agents_online), sub: "always on", icon: Brain },
      ]
    : [
        { label: "PIPELINE", value: "$4.2M", sub: "loading…", icon: TrendingUp },
        { label: "TARGETS / 30D", value: "—", sub: "loading…", icon: Activity },
        { label: "ACCURACY", value: "94.2%", sub: "loading…", icon: ShieldCheck },
        { label: "AGENTS", value: "7", sub: "always on", icon: Brain },
      ];
  return (
  <section className="relative pt-32 pb-20 overflow-hidden">
    <div className="absolute inset-0 -z-10">
      <img src={HERO_BG} alt="" className="w-full h-full object-cover opacity-25" />
      <div className="absolute inset-0" style={{ background: "linear-gradient(180deg, rgba(5,5,5,0.6) 0%, rgba(5,5,5,0.92) 70%, #050505 100%)" }} />
    </div>

    <div className="max-w-7xl mx-auto px-6 lg:px-10">
      <div className="mb-8 inline-flex items-center gap-3 px-3 py-1.5 nx-glass" data-testid="hero-badge">
        <AgentStatus status="scanning" label="LIVE • 7 AGENTS DEPLOYED" />
      </div>

      {/* Bento hero */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Headline */}
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7 }}
          className="lg:col-span-8 nx-glass p-8 lg:p-12 relative overflow-hidden"
          data-testid="hero-headline"
        >
          <div className="nx-label mb-6">[ NEXUS / V1 / FEB 2026 ]</div>
          <h1 className="font-serif text-5xl sm:text-6xl lg:text-7xl tracking-tight leading-[0.95]">
            Your first<br/>
            <span className="italic">autonomous</span><br/>
            <span style={{ color: "var(--nx-cyan)" }}>Chief Revenue Officer.</span>
          </h1>
          <p className="mt-8 text-zinc-400 text-base sm:text-lg max-w-2xl leading-relaxed">
            Nexus deploys a team of 7 AI agents that find your highest-intent buyers,
            build the relationships, negotiate the deal, and close revenue —
            <span className="text-zinc-200"> while you sleep.</span>
          </p>
          <div className="mt-10 flex flex-wrap items-center gap-4">
            <Link to={startHref} className="nx-btn-primary" data-testid="hero-cta-primary">
              Generate your first 10 targets <ArrowUpRight size={14} />
            </Link>
            <Link to={dashHref} className="nx-btn-ghost" data-testid="hero-cta-secondary">
              See the command center <ArrowUpRight size={14} />
            </Link>
          </div>

          {/* Decorative ticker line */}
          <div className="absolute bottom-0 left-0 right-0 h-px overflow-hidden">
            <div className="h-full nx-scan-beam" />
          </div>
        </motion.div>

        {/* Live agent panel */}
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15, duration: 0.7 }}
          className="lg:col-span-4 nx-glass p-6 relative overflow-hidden"
          data-testid="hero-agent-panel"
        >
          <div className="flex items-center justify-between mb-4">
            <div className="nx-label">AGENT FEED</div>
            <AgentStatus status="scanning" />
          </div>
          <div className="space-y-3">
            {[
              { agent: "LeadScout-7", action: "Detected funding signal", target: "Vantix Health", status: "scanning" },
              { agent: "Negotiator-Prime", action: "Drafted counter-proposal", target: "Kestrel Defense", status: "closing" },
              { agent: "Outreach-Composer", action: "Sequence personalized", target: "Linearflow", status: "thinking" },
              { agent: "Pipeline-Analyst", action: "Velocity recalibrated", target: "Q1 Pipeline", status: "idle" },
            ].map((a, i) => (
              <motion.div
                key={a.agent}
                initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 + i * 0.1 }}
                className="border-l-2 pl-3 py-1"
                style={{ borderColor: a.status === "closing" ? "#fafafa" : a.status === "scanning" ? "var(--nx-cyan)" : a.status === "thinking" ? "var(--nx-orange)" : "#52525b" }}
              >
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-zinc-300">{a.agent}</span>
                  <AgentStatus status={a.status} size="xs" />
                </div>
                <div className="text-xs text-zinc-500 mt-1">{a.action}</div>
                <div className="text-xs text-zinc-300 mt-0.5">→ {a.target}</div>
              </motion.div>
            ))}
          </div>
        </motion.div>

        {/* Bento small panels */}
        {heroPanels.map((s, i) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 + i * 0.08 }}
            className="lg:col-span-3 nx-glass nx-card-hover p-5"
            data-testid={`hero-stat-${i}`}
          >
            <div className="flex items-start justify-between">
              <div className="nx-label">{s.label}</div>
              <s.icon size={14} className="text-zinc-500" />
            </div>
            <div className="mt-4 text-3xl font-mono" style={{ color: "var(--nx-cyan)" }}>{s.value}</div>
            <div className="text-xs text-zinc-500 mt-1">{s.sub}</div>
          </motion.div>
        ))}
      </div>
    </div>
  </section>
  );
};

const Sponsors = () => (
  <section className="py-12 border-y" style={{ borderColor: "var(--nx-border)" }}>
    <div className="max-w-7xl mx-auto px-6 lg:px-10">
      <div className="nx-label mb-6 text-center">TRUSTED BY REVENUE LEADERS AT</div>
      <div className="overflow-hidden">
        <div className="flex gap-16 nx-marquee w-max">
          {[...SPONSORS, ...SPONSORS].map((s, i) => (
            <img key={`${s}-${i}`} src={s} alt="" className="h-10 w-24 object-cover opacity-50 hover:opacity-100 transition grayscale" />
          ))}
        </div>
      </div>
    </div>
  </section>
);

const FEATURES = [
  {
    icon: Radar,
    title: "Autonomous Lead Engine",
    body: "Scans 12,400+ sources in real time. Detects funding rounds, hiring spikes, tech migrations and exec changes before your competitors even notice.",
    span: "lg:col-span-7",
    accent: true,
  },
  {
    icon: Workflow,
    title: "Pipeline Orchestration",
    body: "Deals move themselves. Agents triage, prioritize, and execute next-best-action across every stage.",
    span: "lg:col-span-5",
  },
  {
    icon: Brain,
    title: "Multithreaded Reasoning",
    body: "Each prospect gets a personalized strategy built from 200+ signals — not a template.",
    span: "lg:col-span-5",
  },
  {
    icon: Zap,
    title: "Sub-second Decisions",
    body: "When a buyer signals intent, Nexus reacts in under 800ms. Outreach, follow-up, scheduling — all autonomous.",
    span: "lg:col-span-7",
    accent: true,
  },
];

const Features = () => (
  <section id="product" className="py-28 relative">
    <div className="max-w-7xl mx-auto px-6 lg:px-10">
      <div className="mb-16 max-w-3xl">
        <div className="nx-label mb-4">[ THE PRODUCT ]</div>
        <h2 className="font-serif text-4xl sm:text-5xl lg:text-6xl tracking-tight leading-[1.02]">
          Built like a <span className="italic">trading desk</span>. <br/>
          Operates like a <span style={{ color: "var(--nx-cyan)" }}>chief revenue officer.</span>
        </h2>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {FEATURES.map((f, i) => (
          <motion.div
            key={f.title}
            initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.6, delay: i * 0.05 }}
            className={`${f.span} nx-glass nx-card-hover p-8 relative overflow-hidden`}
            data-testid={`feature-${i}`}
          >
            {f.accent && (
              <div className="absolute -top-12 -right-12 w-48 h-48 rounded-full" style={{ background: "radial-gradient(circle, rgba(0,245,212,0.18), transparent 70%)" }} />
            )}
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 flex items-center justify-center border" style={{ borderColor: "var(--nx-border-strong)", background: "rgba(0,245,212,0.06)" }}>
                <f.icon size={18} color="var(--nx-cyan)" strokeWidth={1.5} />
              </div>
              <div className="nx-label">/ {String(i + 1).padStart(2, "0")}</div>
            </div>
            <h3 className="font-serif text-3xl mb-3 leading-tight">{f.title}</h3>
            <p className="text-zinc-400 leading-relaxed">{f.body}</p>
          </motion.div>
        ))}
      </div>
    </div>
  </section>
);

const Agents = () => {
  const agents = [
    { name: "LeadScout-7", desc: "Surfaces buying intent from public + proprietary signals.", status: "scanning" },
    { name: "Outreach-Composer", desc: "Writes hyper-personalized multi-touch sequences.", status: "thinking" },
    { name: "Researcher-3", desc: "Maps org charts and decision-maker influence.", status: "scanning" },
    { name: "Meeting-Booker", desc: "Negotiates calendars across timezones automatically.", status: "closing" },
    { name: "Negotiator-Prime", desc: "Drafts contracts, handles redlines, optimizes pricing.", status: "closing" },
    { name: "Pipeline-Analyst", desc: "Continuously recalibrates win probability per deal.", status: "thinking" },
    { name: "Forecaster", desc: "Builds your forecast in real time — board-ready.", status: "idle" },
  ];
  return (
    <section id="agents" className="py-28 relative" style={{ background: "linear-gradient(180deg, transparent, rgba(0,245,212,0.02), transparent)" }}>
      <div className="max-w-7xl mx-auto px-6 lg:px-10">
        <div className="mb-16 max-w-3xl">
          <div className="nx-label mb-4">[ THE AGENTS ]</div>
          <h2 className="font-serif text-4xl sm:text-5xl lg:text-6xl tracking-tight leading-[1.02]">
            A revenue org<br/>in <span className="italic" style={{ color: "var(--nx-cyan)" }}>seven agents.</span>
          </h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {agents.map((a, i) => (
            <motion.div
              key={a.name}
              initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.04 }}
              className="nx-panel nx-card-hover p-6 relative"
              data-testid={`agent-${i}`}
            >
              <div className="flex items-center justify-between mb-4">
                <div className="text-xs text-zinc-500">AGENT_{String(i+1).padStart(2,"0")}</div>
                <AgentStatus status={a.status} />
              </div>
              <div className="font-mono text-lg text-zinc-100 mb-2">{a.name}</div>
              <p className="text-sm text-zinc-500 leading-relaxed">{a.desc}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

const Pricing = () => {
  const { user } = useAuth();
  const tiers = [
    { name: "Operator", price: "$4,800", period: "/mo", features: ["3 AI agents", "500 prospects/mo", "Standard intent signals", "Email & calendar automation"], cta: "Start trial", pkgId: "operator" },
    { name: "Scale",    price: "$18,500", period: "/mo", features: ["7 AI agents", "Unlimited prospects", "Premium intent + dark social", "Full pipeline orchestration", "Slack & CRM bidirectional"], cta: "Start trial", featured: true, pkgId: "scale" },
    { name: "Enterprise", price: "Custom", period: "", features: ["Custom agent fleet", "Dedicated revenue model", "On-prem signal sources", "White-glove deployment", "SOC2 + SSO + audit"], cta: "Talk to sales", pkgId: null },
  ];
  const target = (pkgId) => {
    if (!pkgId) return "mailto:sales@nexus.ai";
    return user ? "/app/subscribe" : "/login";
  };
  return (
    <section id="pricing" className="py-28">
      <div className="max-w-7xl mx-auto px-6 lg:px-10">
        <div className="mb-16 max-w-3xl">
          <div className="nx-label mb-4">[ PRICING ]</div>
          <h2 className="font-serif text-4xl sm:text-5xl lg:text-6xl tracking-tight leading-[1.02]">
            Less than one<br/>
            <span className="italic">junior AE.</span>{" "}
            <span style={{ color: "var(--nx-cyan)" }}>Replaces twelve.</span>
          </h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {tiers.map((t) => (
            <div
              key={t.name}
              className={`nx-panel p-8 relative ${t.featured ? "ring-1" : ""}`}
              style={t.featured ? { borderColor: "var(--nx-cyan)", boxShadow: "0 0 40px -10px rgba(0,245,212,0.25)" } : {}}
              data-testid={`pricing-${t.name.toLowerCase()}`}
            >
              {t.featured && (
                <div className="absolute -top-3 left-8 px-3 py-1 text-[10px] tracking-[0.18em]" style={{ background: "var(--nx-cyan)", color: "#050505" }}>
                  MOST DEPLOYED
                </div>
              )}
              <div className="nx-label mb-3">{t.name.toUpperCase()}</div>
              <div className="flex items-baseline gap-1 mb-6">
                <span className="font-serif text-5xl">{t.price}</span>
                <span className="text-zinc-500">{t.period}</span>
              </div>
              <ul className="space-y-3 mb-8">
                {t.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm text-zinc-300">
                    <span className="w-1 h-1 mt-2 rounded-full" style={{ background: "var(--nx-cyan)" }} /> {f}
                  </li>
                ))}
              </ul>
              <Link to={target(t.pkgId)} className={t.featured ? "nx-btn-primary w-full justify-center" : "nx-btn-ghost w-full justify-center"} data-testid={`pricing-cta-${t.name.toLowerCase()}`}>
                {t.cta} <ArrowUpRight size={14} />
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

const FinalCTA = () => {
  const { user } = useAuth();
  const startHref = user ? "/app/onboarding" : "/login";
  const dashHref = user ? "/app/dashboard" : "/login";
  return (
  <section id="customers" className="py-28 relative overflow-hidden">
    <div className="absolute inset-0 -z-10">
      <div className="absolute inset-0" style={{ background: "radial-gradient(800px 400px at 50% 50%, rgba(0,245,212,0.08), transparent 60%)" }} />
    </div>
    <div className="max-w-5xl mx-auto px-6 lg:px-10 text-center">
      <Sparkles className="mx-auto mb-6" size={28} color="var(--nx-cyan)" />
      <h2 className="font-serif text-5xl sm:text-6xl lg:text-7xl tracking-tight leading-[0.98]">
        Onboard once.<br/>
        <span style={{ color: "var(--nx-cyan)" }}>Watch revenue compound.</span>
      </h2>
      <p className="mt-8 text-zinc-400 max-w-2xl mx-auto text-lg">
        In 60 seconds, Nexus will study your business and generate your first 10 high-value prospects — live.
      </p>
      <div className="mt-10 flex items-center justify-center gap-4 flex-wrap">
        <Link to={startHref} className="nx-btn-primary" data-testid="final-cta-onboard">
          <Rocket size={14} /> Begin onboarding
        </Link>
        <Link to={dashHref} className="nx-btn-ghost" data-testid="final-cta-demo">
          <GitBranch size={14} /> See live demo
        </Link>
      </div>
    </div>
  </section>
  );
};

const Footer = () => (
  <footer className="border-t py-12" style={{ borderColor: "var(--nx-border)" }}>
    <div className="max-w-7xl mx-auto px-6 lg:px-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
      <div>
        <div className="font-serif text-2xl">Nexus</div>
        <div className="nx-label mt-1">© 2026 Nexus Labs · The autonomous CRO</div>
      </div>
      <div className="flex flex-wrap items-center gap-8 nx-label">
        <span>SOC 2 TYPE II</span>
        <span>GDPR</span>
        <span>ISO 27001</span>
        <span>HIPAA-READY</span>
      </div>
    </div>
  </footer>
);

const Waitlist = () => {
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState({ phase: "idle", message: "" });
  const [count, setCount] = useState(null);

  useEffect(() => {
    api.get("/landing/waitlist/count").then((r) => setCount(r.data.count)).catch(() => {});
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!email) return;
    setStatus({ phase: "loading" });
    try {
      const ref = new URLSearchParams(window.location.search).get("ref");
      const r = await api.post("/landing/waitlist", { email, company, role, referrer: ref });
      setStatus({
        phase: "success",
        message: r.data.already_joined
          ? `You're already on the list — position #${r.data.position}.`
          : `You're in. Position #${r.data.position}.`,
      });
      if (!r.data.already_joined) setCount((c) => (c || 0) + 1);
    } catch (err) {
      setStatus({ phase: "error", message: err?.response?.data?.detail || "Could not join waitlist" });
    }
  };

  return (
    <section id="beta" className="py-28 relative" data-testid="waitlist-section">
      <div className="absolute inset-0 -z-10">
        <div className="absolute inset-0" style={{ background: "radial-gradient(900px 500px at 20% 50%, rgba(0,245,212,0.06), transparent 60%)" }} />
      </div>
      <div className="max-w-6xl mx-auto px-6 lg:px-10 grid grid-cols-1 lg:grid-cols-2 gap-10 items-start">
        <div>
          <div className="nx-label mb-4">[ BETA · LIMITED ACCESS ]</div>
          <h2 className="font-serif text-4xl sm:text-5xl lg:text-6xl tracking-tight leading-[1.02]">
            Want Nexus first?<br/>
            <span className="italic" style={{ color: "var(--nx-cyan)" }}>Join the closed beta.</span>
          </h2>
          <p className="mt-6 text-zinc-400 leading-relaxed max-w-lg">
            We're onboarding 50 mid-market revenue teams per month. The waitlist runs first-come, first-deployed.
            {count !== null && (
              <span className="text-zinc-200"> {count}+ leaders already in queue.</span>
            )}
          </p>
          <div className="mt-8 flex items-center gap-4 text-xs text-zinc-500">
            <span className="flex items-center gap-2"><Users size={12} color="var(--nx-cyan)" /> Founders & CROs</span>
            <span className="flex items-center gap-2"><ShieldCheck size={12} color="var(--nx-cyan)" /> SOC2 · GDPR</span>
            <span className="flex items-center gap-2"><Sparkles size={12} color="var(--nx-cyan)" /> 7-day free trial</span>
          </div>
        </div>

        <form onSubmit={submit} className="nx-glass p-8" data-testid="waitlist-form">
          {status.phase === "success" ? (
            <div className="text-center py-8" data-testid="waitlist-success">
              <CheckCircle2 className="mx-auto mb-4" size={36} color="var(--nx-cyan)" />
              <div className="font-serif text-2xl mb-2">{status.message}</div>
              <div className="text-zinc-500 text-sm">We'll email you when your slot opens.</div>
            </div>
          ) : (
            <>
              <div className="nx-label mb-4">RESERVE YOUR SEAT</div>
              <div className="space-y-3">
                <input
                  type="email"
                  required
                  placeholder="work@yourcompany.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-4 py-3 bg-transparent border text-sm focus:outline-none"
                  style={{ borderColor: "var(--nx-border-strong)", color: "#fafafa" }}
                  data-testid="waitlist-email"
                />
                <input
                  type="text"
                  placeholder="Company (optional)"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  className="w-full px-4 py-3 bg-transparent border text-sm focus:outline-none"
                  style={{ borderColor: "var(--nx-border-strong)", color: "#fafafa" }}
                  data-testid="waitlist-company"
                />
                <input
                  type="text"
                  placeholder="Your role (CRO, VP Sales, RevOps…)"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="w-full px-4 py-3 bg-transparent border text-sm focus:outline-none"
                  style={{ borderColor: "var(--nx-border-strong)", color: "#fafafa" }}
                  data-testid="waitlist-role"
                />
              </div>
              <button
                type="submit"
                disabled={status.phase === "loading"}
                className="nx-btn-primary w-full justify-center mt-5"
                data-testid="waitlist-submit"
              >
                {status.phase === "loading"
                  ? <><Loader2 className="animate-spin" size={14} /> Reserving…</>
                  : <><Rocket size={14} /> Reserve my seat</>}
              </button>
              {status.phase === "error" && (
                <div className="text-xs mt-3" style={{ color: "var(--nx-danger)" }} data-testid="waitlist-error">
                  {status.message}
                </div>
              )}
              <div className="text-[10px] text-zinc-600 mt-4 text-center">
                We only email you about Nexus. No marketing list resale, ever.
              </div>
            </>
          )}
        </form>
      </div>
    </section>
  );
};

const Affiliate = () => {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!email) return;
    setBusy(true);
    try {
      const r = await api.post("/landing/affiliate/signup", { email, name });
      setResult(r.data);
    } catch (err) {
      setResult({ error: err?.response?.data?.detail || "Signup failed" });
    } finally {
      setBusy(false);
    }
  };

  const fullRef = result?.code
    ? `${window.location.origin}/?ref=${result.code}`
    : "";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(fullRef);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      console.error("Clipboard write failed:", e);
    }
  };

  return (
    <section id="partners" className="py-28 relative" data-testid="affiliate-section" style={{ background: "rgba(255,255,255,0.015)" }}>
      <div className="max-w-6xl mx-auto px-6 lg:px-10 grid grid-cols-1 lg:grid-cols-5 gap-10 items-center">
        <div className="lg:col-span-3">
          <div className="nx-label mb-4">[ PARTNER PROGRAM · 20% REV SHARE ]</div>
          <h2 className="font-serif text-4xl sm:text-5xl tracking-tight leading-[1.04]">
            RevOps consultants & GTM advisors.<br/>
            <span style={{ color: "var(--nx-cyan)" }}>Refer Nexus. Get paid for life.</span>
          </h2>
          <p className="mt-6 text-zinc-400 leading-relaxed">
            Every customer you refer pays Nexus $4,800–$18,500 per month.
            You keep <span className="text-zinc-200">20% recurring</span> — that's up to <span className="text-zinc-200">$44,400/year</span> per Scale-tier customer.
            We'll send you a personal referral link in under 30 seconds.
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-6 text-xs text-zinc-500">
            <span className="flex items-center gap-2"><CheckCircle2 size={12} color="var(--nx-cyan)" /> Lifetime commission</span>
            <span className="flex items-center gap-2"><CheckCircle2 size={12} color="var(--nx-cyan)" /> Monthly payouts</span>
            <span className="flex items-center gap-2"><CheckCircle2 size={12} color="var(--nx-cyan)" /> No cap, no minimums</span>
          </div>
        </div>

        <form onSubmit={submit} className="lg:col-span-2 nx-glass p-7" data-testid="affiliate-form">
          {result?.code ? (
            <div data-testid="affiliate-success">
              <div className="nx-label mb-3">YOUR REFERRAL LINK</div>
              <div className="flex items-center gap-2 p-3 border" style={{ borderColor: "var(--nx-border-strong)" }}>
                <code className="text-xs text-zinc-200 truncate flex-1" data-testid="affiliate-link">{fullRef}</code>
                <button type="button" onClick={copy} className="nx-btn-ghost" data-testid="affiliate-copy">
                  {copied ? <CheckCircle2 size={12} color="var(--nx-cyan)" /> : <Copy size={12} />} {copied ? "Copied" : "Copy"}
                </button>
              </div>
              <div className="text-xs text-zinc-500 mt-3">
                Code: <span className="font-mono text-zinc-300">{result.code}</span> · Referrals so far: <span className="font-mono text-zinc-300">{result.referrals_count}</span>
              </div>
              <div className="text-[10px] text-zinc-600 mt-4">
                Add <span className="font-mono">?ref={result.code}</span> to any Nexus URL to attribute the visitor to you.
              </div>
            </div>
          ) : (
            <>
              <div className="nx-label mb-4">BECOME A PARTNER</div>
              <div className="space-y-3">
                <input
                  type="text"
                  placeholder="Your name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-4 py-3 bg-transparent border text-sm focus:outline-none"
                  style={{ borderColor: "var(--nx-border-strong)", color: "#fafafa" }}
                  data-testid="affiliate-name"
                />
                <input
                  type="email"
                  required
                  placeholder="Payout email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-4 py-3 bg-transparent border text-sm focus:outline-none"
                  style={{ borderColor: "var(--nx-border-strong)", color: "#fafafa" }}
                  data-testid="affiliate-email"
                />
              </div>
              <button type="submit" disabled={busy} className="nx-btn-primary w-full justify-center mt-4" data-testid="affiliate-submit">
                {busy ? <><Loader2 className="animate-spin" size={14} /> Generating…</> : <><Sparkles size={14} /> Generate my referral link</>}
              </button>
              {result?.error && (
                <div className="text-xs mt-3" style={{ color: "var(--nx-danger)" }}>{result.error}</div>
              )}
            </>
          )}
        </form>
      </div>
    </section>
  );
};

export default function Landing() {
  return (
    <div className="relative" data-testid="landing-page">
      <div className="nx-noise" />
      <Nav />
      <Hero />
      <Sponsors />
      <Features />
      <Agents />
      <Pricing />
      <Waitlist />
      <Affiliate />
      <FinalCTA />
      <Footer />
    </div>
  );
}
