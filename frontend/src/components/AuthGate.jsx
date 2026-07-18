import React, { createContext, useContext, useEffect, useState } from "react";
import { Lock, LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { loginApi, authMe, apiErrorMessage } from "@/lib/api";

const AuthContext = createContext({ role: null });
export const useAuth = () => useContext(AuthContext);

export default function AuthGate({ children }) {
  const [authed, setAuthed] = useState(null);
  const [role, setRole] = useState(() => localStorage.getItem("hy_role"));
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("hy_token");
    if (!token) {
      setAuthed(false);
      return;
    }
    authMe()
      .then((d) => {
        setRole(d.role);
        localStorage.setItem("hy_role", d.role);
        setAuthed(true);
      })
      .catch(() => setAuthed(false));
  }, []);

  useEffect(() => {
    const onLogout = () => setAuthed(false);
    window.addEventListener("hy-logout", onLogout);
    return () => window.removeEventListener("hy-logout", onLogout);
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!password) return;
    setBusy(true);
    setError("");
    try {
      const { token, role: r } = await loginApi(password);
      localStorage.setItem("hy_token", token);
      localStorage.setItem("hy_role", r);
      setRole(r);
      setAuthed(true);
    } catch (err) {
      setError(apiErrorMessage(err));
    }
    setBusy(false);
  };

  if (authed === null) {
    return (
      <div className="min-h-screen bg-[#1B2A4A] flex items-center justify-center">
        <div className="text-white/60 text-sm">Checking your session…</div>
      </div>
    );
  }

  if (!authed) {
    return (
      <div className="min-h-screen bg-[#1B2A4A] flex items-center justify-center px-4">
        <form onSubmit={submit} data-testid="login-form" className="w-full max-w-sm bg-white rounded-lg p-8 border border-white/10">
          <div className="font-display text-3xl font-extrabold tracking-tight text-[#1B2A4A]">
            HAUL <span className="text-[#E8743B]">YEAH</span>
          </div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-400 mt-1 mb-6">Moving CRM</div>
          <p className="text-sm text-slate-600 mb-4">Enter your password to open the app. Owner, sales, and crew each have their own. This device stays logged in.</p>
          <div className="relative mb-3">
            <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <Input
              data-testid="login-password-input"
              type="password"
              autoFocus
              className="pl-9"
              placeholder="Owner password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error && <p data-testid="login-error" className="text-sm text-red-600 mb-3">{error}</p>}
          <Button data-testid="login-submit-button" type="submit" disabled={busy || !password} className="w-full gap-2 bg-[#E8743B] hover:bg-[#d4632e]">
            <LogIn className="w-4 h-4" /> {busy ? "Checking…" : "Unlock"}
          </Button>
          <p className="text-[11px] text-slate-400 mt-4">Weekend moves, flat price, no surprises.</p>
        </form>
      </div>
    );
  }

  return <AuthContext.Provider value={{ role }}>{children}</AuthContext.Provider>;
}
