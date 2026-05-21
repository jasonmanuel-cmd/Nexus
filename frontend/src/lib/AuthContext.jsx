import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "./api";

const AuthCtx = createContext({ user: null, loading: true, refresh: () => {}, logout: () => {} });

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const r = await api.get("/auth/me");
      setUser(r.data);
    } catch (e) {
      // Unauthenticated or session expired — clear user state
      if (e?.response?.status && e.response.status !== 401) {
        console.error("Auth refresh failed:", e);
      }
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // If returning from OAuth callback, AuthCallback handles it
    if (window.location.hash?.includes("session_id=")) {
      setLoading(false);
      return;
    }
    refresh();
  }, [refresh]);

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } catch (e) {
      console.error("Logout request failed:", e);
    }
    setUser(null);
    window.location.href = "/";
  };

  return <AuthCtx.Provider value={{ user, loading, refresh, logout }}>{children}</AuthCtx.Provider>;
};

export const useAuth = () => useContext(AuthCtx);
