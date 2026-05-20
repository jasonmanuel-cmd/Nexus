import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { api } from "../lib/api";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
export default function AuthCallback() {
  const navigate = useNavigate();
  const hasProcessed = useRef(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const hash = window.location.hash || "";
    const match = hash.match(/session_id=([^&]+)/);
    if (!match) {
      navigate("/login", { replace: true });
      return;
    }
    const sessionId = decodeURIComponent(match[1]);
    (async () => {
      try {
        const r = await api.post("/auth/session", { session_id: sessionId });
        // Clear hash and redirect
        window.history.replaceState(null, "", window.location.pathname);
        navigate("/app/dashboard", { replace: true, state: { user: r.data.user } });
      } catch (e) {
        setError(e?.response?.data?.detail || e.message || "Authentication failed");
      }
    })();
  }, [navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--nx-bg)" }} data-testid="auth-callback">
      <div className="nx-glass p-10 text-center max-w-md">
        <Loader2 className="mx-auto animate-spin mb-4" size={28} color="var(--nx-cyan)" />
        <div className="font-serif text-2xl mb-2">Securing your session</div>
        <div className="nx-label">EXCHANGING CREDENTIALS · ENCRYPTING SESSION</div>
        {error && <div className="text-sm mt-6" style={{ color: "var(--nx-danger)" }}>{error}</div>}
      </div>
    </div>
  );
}
