import React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { toast } from "sonner";
import {
  LayoutDashboard, Users, BookUser, Truck, KanbanSquare, PenLine, Receipt,
  CreditCard, Handshake, HelpCircle, Eye, EyeOff, RefreshCw, KeyRound, LogOut, Calculator, SlidersHorizontal, MessageSquareText, Video, UserRound,
  HardHat, ClipboardList, AlarmClock, CalendarDays, Briefcase, Sun, Megaphone,
} from "lucide-react";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/components/AuthGate";
import { NotificationsBell } from "@/components/NotificationsBell";
import { CrewContactsBubble } from "@/components/CrewContactsBubble";
import useGpsPing from "@/lib/useGpsPing";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, roles: ["owner"] },
  { to: "/leads", label: "Leads", icon: Users, roles: ["owner", "sales"] },
  { to: "/calculator", label: "Quote Calculator", icon: Calculator, roles: ["sales"] },
  { to: "/script", label: "Script", icon: MessageSquareText, roles: ["sales"] },
  { to: "/contacts", label: "Contacts", icon: BookUser, roles: ["owner"] },
  { to: "/projects", label: "Projects", icon: Truck, roles: ["owner", "employee"] },
  { to: "/crew", label: "Crew", icon: HardHat, roles: ["owner"] },
  { to: "/jobs", label: "Jobs", icon: Briefcase, roles: ["owner"] },
  { to: "/marketing", label: "Marketing", icon: Megaphone, roles: ["owner", "marketing"] },
  { to: "/today", label: "Today", icon: Sun, roles: ["crew"] },
  { to: "/jobs", label: "My Jobs", icon: ClipboardList, roles: ["crew"] },
  { to: "/clock", label: "Time Clock", icon: AlarmClock, roles: ["crew"] },
  { to: "/days-off", label: "Days Off", icon: CalendarDays, roles: ["crew"] },
  { to: "/tasks", label: "To-Do", icon: KanbanSquare, roles: ["owner", "sales", "marketing", "crew", "employee"] },
  { to: "/blog", label: "Blog", icon: PenLine, roles: ["owner", "sales", "marketing", "crew", "employee"] },
  { to: "/invoices", label: "Invoices", icon: Receipt, roles: ["owner"] },
  { to: "/subscriptions", label: "Subscriptions", icon: CreditCard, roles: ["owner"] },
  { to: "/partner", label: "Partner View", icon: Handshake, roles: ["owner"] },
  { to: "/settings", label: "Settings", icon: SlidersHorizontal, roles: ["owner"] },
  { to: "/help", label: "Help", icon: HelpCircle, roles: ["owner"] },
];

const ROLE_LABEL = { owner: "Owner", sales: "Sales", employee: "Crew", crew: "Crew", marketing: "Marketing" };

const LiveIndicator = () => {
  const { health } = useApp();
  const ok = health.airtable_configured;
  return (
    <span data-testid="live-indicator" className="hidden sm:inline-flex items-center gap-2 text-xs font-semibold text-slate-600 border border-slate-200 bg-white rounded-full px-3 py-1.5">
      <span className={`w-2 h-2 rounded-full ${ok ? "bg-emerald-500 animate-pulse" : ok === false ? "bg-amber-500" : "bg-slate-300"}`} />
      {ok ? "Data: live from Airtable" : ok === false ? "Airtable key needed" : "Checking…"}
    </span>
  );
};

export default function Layout() {
  const { privacy, togglePrivacy, refreshAll, refreshing, health } = useApp();
  const { role, canSwitch, switchRole, user } = useAuth();
  const navItems = NAV.filter((n) => n.roles.includes(role || "owner"));
  const multiRoles = (user?.roles || []).length > 1 ? user.roles : null;
  const switchOptions = multiRoles || (canSwitch ? ["owner", "sales", "employee", "marketing"] : null);
  useGpsPing(role);

  const handleSwitch = (r) => {
    switchRole(r)
      .then((newRole) => toast.success(`You're now in the ${ROLE_LABEL[newRole]} view.`))
      .catch(() => toast.error("Could not switch accounts. Try again."));
  };

  const logout = () => {
    localStorage.removeItem("hy_token");
    localStorage.removeItem("hy_role");
    localStorage.removeItem("hy_can_switch");
    window.dispatchEvent(new Event("hy-logout"));
  };

  return (
    <div className="min-h-screen bg-[#F2F4F8]">
      <aside className="hidden md:flex print:hidden fixed inset-y-0 left-0 w-60 flex-col bg-[#1B2A4A] text-white z-50">
        <div className="px-5 pt-6 pb-5 border-b border-white/10">
          <img src="/logo.png" alt="Haul Yeah Moving" data-testid="sidebar-logo" className="w-full rounded-lg" />
          <div className="text-[11px] text-white/50 mt-3">Weekend moves, flat price, no surprises.</div>
        </div>
        <nav className="flex-1 overflow-y-auto py-4">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              data-testid={`nav-${label.toLowerCase().replace(/\s+/g, "-")}`}
              className={({ isActive }) =>
                `flex items-center gap-3 px-5 py-2.5 text-sm font-medium border-l-4 transition-colors ${
                  isActive ? "border-[#E8743B] bg-white/10 text-white" : "border-transparent text-white/65 hover:text-white hover:bg-white/5"
                }`
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-white/10 p-4 space-y-2">
          {switchOptions ? (
            <Select value={role || switchOptions[0]} onValueChange={handleSwitch}>
              <SelectTrigger data-testid="role-switch-select" className="w-full h-8 text-xs font-bold uppercase tracking-wide text-white border-white/20 bg-white/10">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {switchOptions.map((r) => (
                  <SelectItem key={r} value={r} data-testid={`switch-option-${r}`}>{ROLE_LABEL[r] || r} view</SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <span data-testid="role-chip" className="flex items-center justify-center text-xs font-bold uppercase tracking-wide bg-white/10 text-white border border-white/20 rounded-full px-2.5 py-1">
              {ROLE_LABEL[role] || "Owner"} account
            </span>
          )}
          {role !== "employee" && role !== "crew" && (
            <Button
              data-testid="privacy-toggle-btn"
              size="sm"
              onClick={togglePrivacy}
              className={`w-full gap-1.5 ${privacy ? "bg-[#E8743B] hover:bg-[#d4632e] text-white" : "bg-white/10 hover:bg-white/20 text-white"}`}
            >
              {privacy ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              {privacy ? "Privacy on" : "Privacy off"}
            </Button>
          )}
          <div className={`grid gap-2 ${role === "crew" || role === "marketing" ? "grid-cols-1" : "grid-cols-2"}`}>
            {role !== "crew" && role !== "marketing" && (
              <Button
                data-testid="refresh-data-btn"
                variant="outline"
                size="sm"
                onClick={refreshAll}
                disabled={refreshing}
                className="gap-1.5 bg-transparent border-white/20 text-white hover:bg-white/10 hover:text-white"
              >
                <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
                Refresh
              </Button>
            )}
            <Button
              data-testid="logout-btn"
              variant="outline"
              size="sm"
              onClick={logout}
              className="gap-1.5 bg-transparent border-white/20 text-white hover:bg-white/10 hover:text-white"
            >
              <LogOut className="w-4 h-4" />
              Log out
            </Button>
          </div>
        </div>
      </aside>

      <div className="md:pl-60 print:pl-0">
        <header className="sticky top-0 z-40 bg-white/85 backdrop-blur-md border-b border-slate-200 print:hidden">
          <div className="flex items-center justify-between gap-2 px-4 md:px-8 h-14">
            <div className="md:hidden">
              <img src="/logo.png" alt="Haul Yeah Moving" data-testid="mobile-logo" className="h-9 w-auto rounded" />
            </div>
            <div className="hidden md:block" />
            <div className="flex items-center gap-2">
              {(role === "owner" || role === "crew") && <NotificationsBell />}
              {role !== "crew" && role !== "marketing" && <LiveIndicator />}
              {role !== "crew" && role !== "marketing" && (
                <Button data-testid="new-meet-btn" asChild variant="outline" size="sm" className="gap-1.5">
                  <a href="https://meet.google.com/new" target="_blank" rel="noreferrer">
                    <Video className="w-4 h-4" />
                    <span className="hidden sm:inline">New Meet</span>
                  </a>
                </Button>
              )}
            </div>
          </div>
          {health.airtable_configured === false && role !== "crew" && role !== "marketing" && (
            <div data-testid="key-missing-banner" className="flex items-center gap-2 bg-amber-50 border-t border-amber-200 text-amber-800 text-sm px-4 md:px-8 py-2.5">
              <KeyRound className="w-4 h-4 shrink-0" />
              <span>
                One step left: add your Airtable token as <strong>AIRTABLE_API_KEY</strong> in the app's secrets panel. Then press Refresh. Never paste the token in chat or code.
              </span>
            </div>
          )}
        </header>

        <main className="px-4 md:px-8 py-6 pb-24 md:pb-10 max-w-7xl mx-auto print:p-0 print:max-w-none">
          <Outlet />
        </main>
      </div>

      <nav className="md:hidden print:hidden fixed bottom-0 inset-x-0 z-50 bg-[#1B2A4A] border-t border-white/10">
        <div className="flex overflow-x-auto no-scrollbar px-1 pb-[env(safe-area-inset-bottom)]">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              data-testid={`tab-${label.toLowerCase().replace(/\s+/g, "-")}`}
              className={({ isActive }) =>
                `flex flex-col items-center gap-0.5 min-w-[72px] px-2 py-2 text-[10px] font-semibold transition-colors ${
                  isActive ? "text-[#E8743B]" : "text-white/60"
                }`
              }
            >
              <Icon className="w-5 h-5" />
              {label}
            </NavLink>
          ))}
          <div className="w-px self-stretch bg-white/15 my-1.5 shrink-0" />
          {canSwitch && (
            <Select value={role || "owner"} onValueChange={handleSwitch}>
              <SelectTrigger
                data-testid="tab-account-select"
                className="flex flex-col items-center justify-center gap-0.5 min-w-[72px] h-auto px-2 py-2 text-[10px] font-semibold text-white/60 bg-transparent border-0 shadow-none rounded-none focus:ring-0 [&>svg:last-of-type]:hidden"
              >
                <UserRound className="w-5 h-5" />
                Account
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="owner">Owner view</SelectItem>
                <SelectItem value="sales">Sales view</SelectItem>
                <SelectItem value="employee">Crew view</SelectItem>
                <SelectItem value="marketing">Marketing view</SelectItem>
              </SelectContent>
            </Select>
          )}
          {role !== "crew" && role !== "marketing" && (
            <button
              data-testid="tab-refresh-btn"
              onClick={refreshAll}
              disabled={refreshing}
              className="flex flex-col items-center gap-0.5 min-w-[72px] px-2 py-2 text-[10px] font-semibold text-white/60"
            >
              <RefreshCw className={`w-5 h-5 ${refreshing ? "animate-spin" : ""}`} />
              Refresh
            </button>
          )}
          {role !== "employee" && role !== "crew" && (
            <button
              data-testid="tab-privacy-btn"
              onClick={togglePrivacy}
              className={`flex flex-col items-center gap-0.5 min-w-[72px] px-2 py-2 text-[10px] font-semibold ${privacy ? "text-[#E8743B]" : "text-white/60"}`}
            >
              {privacy ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              {privacy ? "Privacy on" : "Privacy off"}
            </button>
          )}
          <button
            data-testid="tab-logout-btn"
            onClick={logout}
            className="flex flex-col items-center gap-0.5 min-w-[72px] px-2 py-2 text-[10px] font-semibold text-white/60"
          >
            <LogOut className="w-5 h-5" />
            Log out
          </button>
        </div>
      </nav>

      {role === "crew" && <CrewContactsBubble />}
    </div>
  );
}
