import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { api, fmtUSD } from "../lib/api";

export default function CheckoutReturn() {
  const [params] = useSearchParams();
  const sessionId = params.get("session_id");
  const navigate = useNavigate();
  const [status, setStatus] = useState({ phase: "polling", data: null, error: null });
  const attemptsRef = useRef(0);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!sessionId) {
      setStatus({ phase: "error", error: "Missing session id" });
      return;
    }
    const poll = async () => {
      attemptsRef.current += 1;
      try {
        const r = await api.get(`/payments/checkout/status/${sessionId}`);
        if (r.data.payment_status === "paid") {
          setStatus({ phase: "success", data: r.data });
          return;
        }
        if (r.data.status === "expired") {
          setStatus({ phase: "error", error: "Payment session expired" });
          return;
        }
        if (attemptsRef.current >= 8) {
          setStatus({ phase: "timeout", data: r.data });
          return;
        }
        timerRef.current = setTimeout(poll, 2000);
      } catch (e) {
        setStatus({ phase: "error", error: e?.response?.data?.detail || e.message });
      }
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
            <div className="nx-label">VERIFYING WITH STRIPE · {attemptsRef.current}/8</div>
          </>
        )}
        {status.phase === "success" && (
          <>
            <CheckCircle2 className="mx-auto mb-4" size={36} color="var(--nx-cyan)" />
            <div className="font-serif text-3xl mb-2">Subscription active.</div>
            <div className="nx-label mb-6">PACKAGE: {status.data?.package_id?.toUpperCase()} · {fmtUSD((status.data?.amount_total || 0) / 100)}</div>
            <button onClick={() => navigate("/app/dashboard")} className="nx-btn-primary w-full justify-center" data-testid="go-dashboard">
              Enter command center
            </button>
          </>
        )}
        {status.phase === "timeout" && (
          <>
            <AlertCircle className="mx-auto mb-4" size={28} color="var(--nx-orange)" />
            <div className="font-serif text-2xl mb-2">Still processing</div>
            <div className="text-zinc-400 text-sm mb-6">Check back in a minute. We'll email a receipt.</div>
            <button onClick={() => navigate("/app/dashboard")} className="nx-btn-ghost w-full justify-center">Back to dashboard</button>
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
