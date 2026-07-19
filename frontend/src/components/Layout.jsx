import React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { toast } from "sonner";
import {
  LayoutDashboard, Users, BookUser, Truck, KanbanSquare, PenLine, Receipt,
  CreditCard, Handshake, HelpCircle, Eye, EyeOff, RefreshCw, KeyRound, LogOut, Calculator, SlidersHorizontal, MessageSquareText, Video,
} from "lucide-react";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/components/AuthGate";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, roles: ["owner"] },
  { to: "/leads", label: "Leads", icon: Users, roles: ["owner", "sales"] },
  { to: "/calculator", label: "Quote Calculator", icon: Calculator, roles: ["sales"] },
  { to: "/script", label: "Script", icon: MessageSquareText, roles: ["sales"] },
  { to: "/contacts", label: "Contacts", icon: BookUser, roles: ["owner"] },
  { to: "/projects", label: "Projects", icon: Truck, roles: ["owner", "employee"] },
  { to: "/tasks", label: "To-Do", icon: KanbanSquare, roles: ["owner", "employee"] },
  { to: "/blog", label: "Blog", icon: PenLine, roles: ["owner"] },
  { to: "/invoices", label: "Invoices", icon: Receipt, roles: ["owner"] },
  { to: "/subscriptions", label: "Subscriptions", icon: CreditCard, roles: ["owner"] },
  { to: "/partner", label: "Partner View", icon: Handshake, roles: ["owner"] },
  { to: "/settings", label: "Settings", icon: SlidersHorizontal, roles: ["owner"] },
  { to: "/help", label: "Help", icon: HelpCircle, roles: ["owner"] },
];

const ROLE_LABEL = { owner: "Owner", sales: "Sales", employee: "Crew" };

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
  const { role, canSwitch, switchRole } = useAuth();
  const navItems = NAV.filter((n) => n.roles.includes(role || "owner"));

  const handleSwitch = (r) => {
    switchRole(r)
      .then((newRole) => toast.success(`You're now in the ${ROLE_LABEL[newRole]} view.`))
      .catch(() => toast.error("Could not switch accounts. Try again."));
  };

  return (
    <div className="min-h-screen bg-[#F2F4F8]">
      <aside className="hidden md:flex fixed inset-y-0 left-0 w-60 flex-col bg-[#1B2A4A] text-white z-50">
        <div className="px-5 pt-6 pb-5 border-b border-white/10">
          <div className="font-display text-2xl font-extrabold tracking-tight leading-none">
            HAUL <span className="text-[#E8743B]">YEAH</span>
          </div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-white/60 mt-1">Moving CRM</div>
          <div className="text-[11px] text-white/50 mt-2">Weekend moves, flat price, no surprises.</div>
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
      </aside>

      <div className="md:pl-60">
        <header className="sticky top-0 z-40 bg-white/85 backdrop-blur-md border-b border-slate-200">
          <div className="flex items-center justify-between gap-2 px-4 md:px-8 h-14">
            <div className="md:hidden font-display text-lg font-extrabold text-[#1B2A4A]">
              HAUL <span className="text-[#E8743B]">YEAH</span>
            </div>
            <div className="hidden md:block" />
            <div className="flex items-center gap-2">
              {canSwitch ? (
                <Select value={role || "owner"} onValueChange={handleSwitch}>
                  <SelectTrigger data-testid="role-switch-select" className="w-[130px] h-8 text-xs font-bold uppercase tracking-wide text-[#1B2A4A] border-[#1B2A4A]/20 bg-[#1B2A4A]/5">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="owner">Owner view</SelectItem>
                    <SelectItem value="sales">Sales view</SelectItem>
                    <SelectItem value="employee">Crew view</SelectItem>
                  </SelectContent>
                </Select>
              ) : (
                <span data-testid="role-chip" className="inline-flex items-center text-xs font-bold uppercase tracking-wide bg-[#1B2A4A]/5 text-[#1B2A4A] border border-[#1B2A4A]/20 rounded-full px-2.5 py-1">
                  {ROLE_LABEL[role] || "Owner"}
                </span>
              )}
              <LiveIndicator />
              <Button data-testid="new-meet-btn" asChild variant="outline" size="sm" className="gap-1.5">
                <a href="https://meet.google.com/new" target="_blank" rel="noreferrer">
                  <Video className="w-4 h-4" />
                  <span className="hidden sm:inline">New Meet</span>
                </a>
              </Button>
              <Button
                data-testid="refresh-data-btn"
                variant="outline"
                size="sm"
                onClick={refreshAll}
                disabled={refreshing}
                className="gap-1.5"
              >
                <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
                Refresh
              </Button>
              {role !== "employee" && (
                <Button
                  data-testid="privacy-toggle-btn"
                  size="sm"
                  onClick={togglePrivacy}
                  className={`gap-1.5 ${privacy ? "bg-[#E8743B] hover:bg-[#d4632e] text-white" : "bg-[#1B2A4A] hover:bg-[#26395f] text-white"}`}
                >
                  {privacy ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  {privacy ? "Privacy on" : "Privacy off"}
                </Button>
              )}
              <Button
                data-testid="logout-btn"
                variant="outline"
                size="sm"
                onClick={() => {
                  localStorage.removeItem("hy_token");
                  localStorage.removeItem("hy_role");
                  localStorage.removeItem("hy_can_switch");
                  window.dispatchEvent(new Event("hy-logout"));
                }}
                className="gap-1.5"
              >
                <LogOut className="w-4 h-4" />
                <span className="hidden sm:inline">Log out</span>
                <span className="sm:hidden">Out</span>
              </Button>
            </div>
          </div>
          {health.airtable_configured === false && (
            <div data-testid="key-missing-banner" className="flex items-center gap-2 bg-amber-50 border-t border-amber-200 text-amber-800 text-sm px-4 md:px-8 py-2.5">
              <KeyRound className="w-4 h-4 shrink-0" />
              <span>
                One step left: add your Airtable token as <strong>AIRTABLE_API_KEY</strong> in the app's secrets panel. Then press Refresh. Never paste the token in chat or code.
              </span>
            </div>
          )}
        </header>

        <main className="px-4 md:px-8 py-6 pb-24 md:pb-10 max-w-7xl mx-auto">
          <Outlet />
        </main>
      </div>

      <nav className="md:hidden fixed bottom-0 inset-x-0 z-50 bg-[#1B2A4A] border-t border-white/10">
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
        </div>
      </nav>
    </div>
  );
}
