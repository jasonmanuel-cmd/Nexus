import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { api, fmtUSD } from "../lib/api";

export default function CheckoutReturn() {
  const [params] = useSearchParams();
  // Square redirects with transactionId / orderId — but we stored session_id locally.
  // We let the user navigate back to /app/subscribe where we can show subscription state.
  const sessionId = params.get("session_id") || params.get("transactionId") || params.get("orderId");
  const navigate = useNavigate();
  const [status, setStatus] = useState({ phase: "polling", data: null, error: null });
  const attemptsRef = useRef(0);
  const timerRef = useRef(null);

  useEffect(() => {
    // First, check current subscription state via /payments/subscription
    const checkSub = async () => {
      try {
        const r = await api.get("/payments/subscription");
        if (r.data.active) {
          setStatus({ phase: "success", data: r.data });
          return true;
        }
      } catch (e) {
        console.error("Subscription status check failed:", e);
      }
      return false;
    };

    const poll = async () => {
      attemptsRef.current += 1;
      if (await checkSub()) return;
      if (attemptsRef.current >= 6) {
        setStatus({ phase: "timeout" });
        return;
      }
      timerRef.current = setTimeout(poll, 2500);
    };
    poll();
    return () => clearTimeout(timerRef.current);
  }, [sessionId]);

  return (
    <div className="p-6 lg:p-10 flex items-center justify-center min-h-[80vh]" data-testid="checkout-return">
      <div className="nx-glass p-10 max-w-lg w-full text-center">
        {status.phase === "polling" && (
          <>
            <Loader2 className="mx-auto animate-spin mb-4" size={28} color="var(--nx-cyan)" />
            <div className="font-serif text-3xl mb-2">Confirming payment</div>
            <div className="nx-label">VERIFYING WITH SQUARE · {attemptsRef.current}/6</div>
          </>
        )}
        {status.phase === "success" && (
          <>
            <CheckCircle2 className="mx-auto mb-4" size={36} color="var(--nx-cyan)" />
            <div className="font-serif text-3xl mb-2">Subscription active.</div>
            <div className="nx-label mb-6">
              PLAN: {status.data?.package?.name?.toUpperCase()} · {fmtUSD(status.data?.package?.amount || 0)}/MO
            </div>
            <button onClick={() => navigate("/app/dashboard")} className="nx-btn-primary w-full justify-center" data-testid="go-dashboard">
              Enter command center
            </button>
          </>
        )}
        {status.phase === "timeout" && (
          <>
            <AlertCircle className="mx-auto mb-4" size={28} color="var(--nx-orange)" />
            <div className="font-serif text-2xl mb-2">Payment confirmation pending</div>
            <div className="text-zinc-400 text-sm mb-6">Square is processing your payment. We'll mark your subscription active shortly via webhook.</div>
            <div className="flex gap-3">
              <button onClick={() => navigate("/app/subscribe")} className="nx-btn-ghost flex-1 justify-center">Back to billing</button>
              <button onClick={() => navigate("/app/dashboard")} className="nx-btn-primary flex-1 justify-center">Dashboard</button>
            </div>
          </>
        )}
        {status.phase === "error" && (
          <>
            <AlertCircle className="mx-auto mb-4" size={28} color="var(--nx-danger)" />
            <div className="font-serif text-2xl mb-2">Payment failed</div>
            <div className="text-zinc-400 text-sm mb-6">{status.error}</div>
            <button onClick={() => navigate("/app/subscribe")} className="nx-btn-ghost w-full justify-center">Try again</button>
          </>
        )}
      </div>
    </div>
  );
}
