import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import Landing from "@/pages/Landing";
import Dashboard from "@/pages/Dashboard";
import LeadEngine from "@/pages/LeadEngine";
import Pipeline from "@/pages/Pipeline";
import Onboarding from "@/pages/Onboarding";
import Login from "@/pages/Login";
import AuthCallback from "@/pages/AuthCallback";
import Subscribe from "@/pages/Subscribe";
import CheckoutReturn from "@/pages/CheckoutReturn";
import Outbox from "@/pages/Outbox";
import AppShell from "@/components/AppShell";
import ProtectedRoute from "@/components/ProtectedRoute";
import { AuthProvider } from "@/lib/AuthContext";

const Shell = ({ children }) => (
  <ProtectedRoute>
    <AppShell>{children}</AppShell>
  </ProtectedRoute>
);

function HashAuthRouter() {
  const location = useLocation();
  // Synchronous check - render-time, NOT in useEffect (prevents race conditions)
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/app" element={<Navigate to="/app/dashboard" replace />} />
      <Route path="/app/dashboard"      element={<Shell><Dashboard /></Shell>} />
      <Route path="/app/lead-engine"    element={<Shell><LeadEngine /></Shell>} />
      <Route path="/app/pipeline"       element={<Shell><Pipeline /></Shell>} />
      <Route path="/app/onboarding"     element={<Shell><Onboarding /></Shell>} />
      <Route path="/app/outbox"         element={<Shell><Outbox /></Shell>} />
      <Route path="/app/subscribe"      element={<Shell><Subscribe /></Shell>} />
      <Route path="/app/checkout-return" element={<Shell><CheckoutReturn /></Shell>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App dark">
      <BrowserRouter>
        <AuthProvider>
          <HashAuthRouter />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
