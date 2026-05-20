import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { Activity, Radar, GitBranch, Rocket, ChevronLeft, Cpu } from "lucide-react";

const NAV = [
  { to: "/app/dashboard",   label: "COMMAND CENTER", icon: Activity, testid: "nav-dashboard" },
  { to: "/app/lead-engine", label: "LEAD ENGINE",    icon: Radar,    testid: "nav-lead-engine" },
  { to: "/app/pipeline",    label: "PIPELINE",       icon: GitBranch, testid: "nav-pipeline" },
  { to: "/app/onboarding",  label: "BETA ONBOARD",   icon: Rocket,   testid: "nav-onboarding" },
];

export const AppShell = ({ children }) => {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen relative" style={{ background: "var(--nx-bg)" }}>
      <div className="nx-noise" />
      <div className="fixed inset-0 nx-grid-bg pointer-events-none" style={{ opacity: 0.5 }} />

      <div className="relative z-10 flex">
        {/* Sidebar */}
        <aside
          className="w-[240px] min-h-screen border-r flex flex-col"
          style={{ borderColor: "var(--nx-border)", background: "rgba(8,8,9,0.7)", backdropFilter: "blur(12px)" }}
          data-testid="app-sidebar"
        >
          <button
            onClick={() => navigate("/")}
            className="p-6 flex items-center gap-3 border-b hover:opacity-80 transition"
            style={{ borderColor: "var(--nx-border)" }}
            data-testid="sidebar-logo"
          >
            <div className="relative w-8 h-8 flex items-center justify-center" style={{ background: "var(--nx-cyan)", color: "#050505" }}>
              <Cpu size={16} strokeWidth={2.5} />
            </div>
            <div className="text-left">
              <div className="font-serif text-xl leading-none">Nexus</div>
              <div className="nx-label" style={{ fontSize: 9 }}>AUTONOMOUS CRO</div>
            </div>
          </button>

          <nav className="flex-1 px-3 py-6 flex flex-col gap-1">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                data-testid={n.testid}
                className={({ isActive }) =>
                  `group flex items-center gap-3 px-3 py-2.5 text-[11px] tracking-[0.14em] uppercase transition border-l-2 ${
                    isActive
                      ? "text-[#00f5d4] border-[#00f5d4] bg-[rgba(0,245,212,0.04)]"
                      : "text-zinc-500 border-transparent hover:text-zinc-200 hover:bg-white/[0.02]"
                  }`
                }
              >
                <n.icon size={14} strokeWidth={1.75} />
                <span>{n.label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="p-4 border-t" style={{ borderColor: "var(--nx-border)" }}>
            <button
              onClick={() => navigate("/")}
              className="w-full nx-label flex items-center gap-2 hover:text-zinc-200 transition"
              data-testid="back-to-landing"
            >
              <ChevronLeft size={12} /> Back to site
            </button>
            <div className="mt-4 flex items-center gap-2">
              <span className="nx-dot nx-dot-scanning" />
              <span className="nx-label" style={{ fontSize: 9 }}>7 AGENTS ONLINE</span>
            </div>
          </div>
        </aside>

        {/* Main */}
        <main className="flex-1 min-h-screen">{children}</main>
      </div>
    </div>
  );
};

export default AppShell;
