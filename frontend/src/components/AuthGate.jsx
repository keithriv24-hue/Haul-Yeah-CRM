import React, { createContext, useContext, useEffect, useState } from "react";
import { Lock, LogIn, Eye, EyeOff, UserRound, KeyRound } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { loginApi, authMe, switchRoleApi, changePasswordApi, apiErrorMessage } from "@/lib/api";

const AuthContext = createContext({ role: null });
export const useAuth = () => useContext(AuthContext);

const Shell = ({ children }) => (
  <div className="min-h-screen bg-[#1B2A4A] flex items-center justify-center px-4">{children}</div>
);

export default function AuthGate({ children }) {
  const [authed, setAuthed] = useState(null);
  const [role, setRole] = useState(() => localStorage.getItem("hy_role"));
  const [canSwitch, setCanSwitch] = useState(() => localStorage.getItem("hy_can_switch") === "1");
  const [user, setUser] = useState(null);
  const [mustChange, setMustChange] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [changeError, setChangeError] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("hy_token");
    if (!token) {
      setAuthed(false);
      return;
    }
    authMe()
      .then((d) => {
        setRole(d.role);
        setCanSwitch(!!d.can_switch);
        setUser(d.user || null);
        localStorage.setItem("hy_role", d.role);
        localStorage.setItem("hy_can_switch", d.can_switch ? "1" : "0");
        if (d.user?.must_change_password) setMustChange(true);
        setAuthed(true);
      })
      .catch(() => setAuthed(false));
  }, []);

  useEffect(() => {
    const onLogout = () => {
      setAuthed(false);
      setUser(null);
      setMustChange(false);
    };
    window.addEventListener("hy-logout", onLogout);
    return () => window.removeEventListener("hy-logout", onLogout);
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!password) return;
    setBusy(true);
    setError("");
    try {
      const body = username.trim() ? { email: username.trim(), password } : { password };
      const d = await loginApi(body);
      localStorage.setItem("hy_token", d.token);
      localStorage.setItem("hy_role", d.role);
      localStorage.setItem("hy_can_switch", d.can_switch ? "1" : "0");
      setRole(d.role);
      setCanSwitch(!!d.can_switch);
      setUser(d.user || null);
      if (d.user?.must_change_password) {
        setCurrentPw(password);
        setMustChange(true);
      }
      setAuthed(true);
      setPassword("");
    } catch (err) {
      setError(apiErrorMessage(err));
    }
    setBusy(false);
  };

  const submitNewPassword = async (e) => {
    e.preventDefault();
    setChangeError("");
    if (newPw.length < 8) return setChangeError("Your new password needs at least 8 characters.");
    if (newPw !== confirmPw) return setChangeError("Those two passwords don't match.");
    setBusy(true);
    try {
      await changePasswordApi(currentPw, newPw);
      setUser((u) => (u ? { ...u, must_change_password: false } : u));
      setMustChange(false);
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
      toast.success("Password set. You're in!");
    } catch (err) {
      setChangeError(apiErrorMessage(err));
    }
    setBusy(false);
  };

  if (authed === null) {
    return (
      <Shell>
        <div className="text-white/60 text-sm">Checking your session…</div>
      </Shell>
    );
  }

  if (!authed) {
    return (
      <Shell>
        <form onSubmit={submit} data-testid="login-form" className="w-full max-w-sm bg-white rounded-lg p-8 border border-white/10">
          <img src="/logo.png" alt="Haul Yeah Moving" data-testid="login-logo" className="w-48 rounded-lg" />
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-400 mt-3 mb-6">Moving CRM</div>
          <p className="text-sm text-slate-600 mb-4">Sign in with your username (or email) and password. This device stays logged in.</p>
          <div className="relative mb-3">
            <UserRound className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <Input
              data-testid="login-username-input"
              type="text"
              autoFocus
              autoCapitalize="none"
              autoComplete="username"
              className="pl-9"
              placeholder="Username or email"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </div>
          <div className="relative mb-3">
            <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <Input
              data-testid="login-password-input"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              className="pl-9 pr-10"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button
              type="button"
              data-testid="login-toggle-password-btn"
              aria-label={showPassword ? "Hide password" : "Show password"}
              onClick={() => setShowPassword((s) => !s)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-[#1B2A4A] transition-colors"
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {error && <p data-testid="login-error" className="text-sm text-red-600 mb-3">{error}</p>}
          <Button data-testid="login-submit-button" type="submit" disabled={busy || !password} className="w-full gap-2 bg-[#E8743B] hover:bg-[#d4632e]">
            <LogIn className="w-4 h-4" /> {busy ? "Checking…" : "Sign in"}
          </Button>
          <p className="text-[11px] text-slate-400 mt-4">
            Crew and sales sign in with their email. Old shared passwords still work — leave the top box empty.
          </p>
        </form>
      </Shell>
    );
  }

  if (mustChange) {
    return (
      <Shell>
        <form onSubmit={submitNewPassword} data-testid="change-password-form" className="w-full max-w-sm bg-white rounded-lg p-8 border border-white/10">
          <img src="/logo.png" alt="Haul Yeah Moving" className="w-48 rounded-lg" />
          <h1 className="text-lg font-bold text-[#1B2A4A] mt-4">Set your new password</h1>
          <p className="text-sm text-slate-600 mt-1 mb-4">
            First time in{user?.name ? `, ${user.name.split(" ")[0]}` : ""}! Pick a password only you know (8+ characters).
          </p>
          {!currentPw && (
            <div className="relative mb-3">
              <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <Input
                data-testid="change-current-input"
                type="password"
                className="pl-9"
                placeholder="Current (temporary) password"
                value={currentPw}
                onChange={(e) => setCurrentPw(e.target.value)}
              />
            </div>
          )}
          <div className="relative mb-3">
            <KeyRound className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <Input
              data-testid="change-new-input"
              type="password"
              autoFocus
              className="pl-9"
              placeholder="New password"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
            />
          </div>
          <div className="relative mb-3">
            <KeyRound className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <Input
              data-testid="change-confirm-input"
              type="password"
              className="pl-9"
              placeholder="Type it again"
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
            />
          </div>
          {changeError && <p data-testid="change-password-error" className="text-sm text-red-600 mb-3">{changeError}</p>}
          <Button data-testid="change-password-submit" type="submit" disabled={busy || !newPw || !confirmPw} className="w-full gap-2 bg-[#E8743B] hover:bg-[#d4632e]">
            {busy ? "Saving…" : "Save my password"}
          </Button>
        </form>
      </Shell>
    );
  }

  const switchRole = async (targetRole) => {
    const d = await switchRoleApi(targetRole);
    localStorage.setItem("hy_token", d.token);
    localStorage.setItem("hy_role", d.role);
    localStorage.setItem("hy_can_switch", "1");
    setRole(d.role);
    setCanSwitch(true);
    return d.role;
  };

  const updateUser = (patch) => setUser((u) => (u ? { ...u, ...patch } : u));

  return <AuthContext.Provider value={{ role, canSwitch, switchRole, user, updateUser }}>{children}</AuthContext.Provider>;
}
