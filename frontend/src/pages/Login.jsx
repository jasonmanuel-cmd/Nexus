import React from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Cpu, ShieldCheck, Lock } from "lucide-react";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
export default function Login() {
  const handleGoogle = () => {
    const redirectUrl = window.location.origin + "/auth/callback";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen relative flex items-center justify-center" style={{ background: "var(--nx-bg)" }} data-testid="login-page">
      <div className="nx-noise" />
      <div className="fixed inset-0 nx-grid-bg" style={{ opacity: 0.5 }} />
      <div className="relative z-10 grid grid-cols-1 lg:grid-cols-2 gap-6 max-w-5xl w-full px-6">
        <div className="nx-glass p-10 flex flex-col justify-between">
          <Link to="/" className="flex items-center gap-3" data-testid="login-logo">
            <div className="w-8 h-8 flex items-center justify-center" style={{ background: "var(--nx-cyan)", color: "#050505" }}>
              <Cpu size={16} strokeWidth={2.5} />
            </div>
            <div>
              <div className="font-serif text-xl leading-none">Nexus</div>
              <div className="nx-label" style={{ fontSize: 9 }}>AUTONOMOUS CRO</div>
            </div>
          </Link>
          <div>
            <div className="nx-label mb-4">[ DEPLOY YOUR AGENTS ]</div>
            <h1 className="font-serif text-5xl tracking-tight leading-[0.98]">
              Sign in to deploy <span className="italic" style={{ color: "var(--nx-cyan)" }}>your autonomous CRO.</span>
            </h1>
            <p className="text-zinc-400 mt-6 max-w-md leading-relaxed">
              Continue with Google. We provision your private command center in under 4 seconds.
            </p>
          </div>
          <div className="flex items-center gap-4 nx-label">
            <Lock size={12} /> ENCRYPTED · SOC 2 · GDPR
          </div>
        </div>

        <div className="nx-glass p-10 flex flex-col justify-center">
          <div className="nx-label mb-3">CONTINUE</div>
          <h2 className="font-serif text-3xl mb-8">Access your command center</h2>
          <button
            onClick={handleGoogle}
            className="w-full flex items-center justify-center gap-3 py-4 px-6 transition group"
            style={{ background: "#fafafa", color: "#050505", borderRadius: 2 }}
            data-testid="google-signin-btn"
          >
            <svg width="18" height="18" viewBox="0 0 18 18">
              <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"/>
              <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z"/>
              <path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"/>
              <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/>
            </svg>
            <span className="text-sm font-medium tracking-wider">Continue with Google</span>
            <ArrowUpRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
          </button>
          <div className="mt-8 border-t pt-6" style={{ borderColor: "var(--nx-border)" }}>
            <div className="nx-label mb-3">YOU'LL GET</div>
            <ul className="space-y-2 text-sm text-zinc-300">
              <li>· 7-agent autonomous CRO fleet</li>
              <li>· Live command-center dashboard</li>
              <li>· AI-generated high-intent targets</li>
              <li>· Visual pipeline automation</li>
            </ul>
          </div>
          <div className="mt-8 text-xs text-zinc-500">
            By continuing, you agree to Nexus' Terms &amp; Privacy. <ShieldCheck className="inline" size={12} />
          </div>
        </div>
      </div>
    </div>
  );
}
