import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Landing from "@/pages/Landing";
import Dashboard from "@/pages/Dashboard";
import LeadEngine from "@/pages/LeadEngine";
import Pipeline from "@/pages/Pipeline";
import Onboarding from "@/pages/Onboarding";
import AppShell from "@/components/AppShell";

const ShellRoute = ({ children }) => <AppShell>{children}</AppShell>;

function App() {
  return (
    <div className="App dark">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/app" element={<Navigate to="/app/dashboard" replace />} />
          <Route path="/app/dashboard"   element={<ShellRoute><Dashboard /></ShellRoute>} />
          <Route path="/app/lead-engine" element={<ShellRoute><LeadEngine /></ShellRoute>} />
          <Route path="/app/pipeline"    element={<ShellRoute><Pipeline /></ShellRoute>} />
          <Route path="/app/onboarding"  element={<ShellRoute><Onboarding /></ShellRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
