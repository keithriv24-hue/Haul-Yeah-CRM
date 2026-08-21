import React, { useCallback, useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  LayoutDashboard, Users, BookUser, Truck, KanbanSquare, PenLine, Receipt,
  CreditCard, Handshake, HelpCircle, Eye, EyeOff, RefreshCw, KeyRound, LogOut, Calculator, SlidersHorizontal, MessageSquareText, Video, UserRound,
  HardHat, ClipboardList, AlarmClock, CalendarDays, Briefcase, Sun, Megaphone, UsersRound, Trophy, Swords, Medal,
  BadgeDollarSign, BellRing, Radio, Wrench, MoreHorizontal, Search, Boxes,
} from "lucide-react";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/components/AuthGate";
import { NotificationsBell } from "@/components/NotificationsBell";
import { CrewContactsBubble } from "@/components/CrewContactsBubble";
import useGpsPing from "@/lib/useGpsPing";
import { teamNotificationsApi, alertsUnreadApi, markAlertsReadApi, getScopeAccessApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";

/**
 * Navigation is grouped by what the person is trying to get done, not by the
 * order the pages were built. Owner sees ~24 destinations; flat, that is
 * unusable on a phone, so the phone gets four fixed tabs plus a More sheet and
 * the desktop gets a grouped sidebar.
 */
const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, roles: ["owner"], group: "Today" },
  { to: "/dispatch", label: "Dispatch", icon: Radio, roles: ["owner"], group: "Today" },
  { to: "/jobs", label: "Jobs", icon: Briefcase, roles: ["owner"], group: "Today" },
  { to: "/day-sheet", label: "Day Sheet", icon: ClipboardList, roles: ["owner", "employee"], group: "Today" },
  { to: "/crew", label: "Crew", icon: HardHat, roles: ["owner"], group: "Today" },
  { to: "/fleet", label: "Fleet", icon: Wrench, roles: ["owner"], group: "Today" },
  { to: "/projects", label: "Projects", icon: Truck, roles: ["owner", "employee"], group: "Today" },

  { to: "/today", label: "Today", icon: Sun, roles: ["crew"], group: "My day" },
  { to: "/jobs", label: "My Jobs", icon: ClipboardList, roles: ["crew"], group: "My day" },
  { to: "/clock", label: "Time Clock", icon: AlarmClock, roles: ["crew"], group: "My day" },
  { to: "/days-off", label: "Days Off", icon: CalendarDays, roles: ["crew"], group: "My day" },

  { to: "/leads", label: "Leads", icon: Users, roles: ["owner", "sales"], group: "Sales" },
  { to: "/calculator", label: "Quote Calculator", icon: Calculator, roles: ["sales"], group: "Sales" },
  { to: "/scope-calculator", label: "Scope Calculator", icon: Boxes, roles: ["owner", "sales"], group: "Sales" },
  { to: "/script", label: "Script", icon: MessageSquareText, roles: ["owner", "sales"], group: "Sales" },
  { to: "/commissions", label: "Commissions", icon: BadgeDollarSign, roles: ["owner", "sales"], group: "Sales" },
  { to: "/contacts", label: "Contacts", icon: BookUser, roles: ["owner"], group: "Sales" },

  { to: "/invoices", label: "Invoices", icon: Receipt, roles: ["owner"], group: "Money" },
  { to: "/subscriptions", label: "Subscriptions", icon: CreditCard, roles: ["owner"], group: "Money" },
  { to: "/partner", label: "Partner View", icon: Handshake, roles: ["owner"], group: "Money" },

  { to: "/team", label: "Team", icon: UsersRound, roles: ["owner", "sales", "marketing", "crew", "employee"], group: "Team" },
  { to: "/leaderboard", label: "Leaderboard", icon: Trophy, roles: ["owner", "sales", "marketing", "crew", "employee"], group: "Team" },
  { to: "/challenges", label: "Challenges", icon: Swords, roles: ["owner", "sales", "marketing", "crew", "employee"], group: "Team" },
  { to: "/team-admin", label: "Team HQ", icon: Medal, roles: ["owner"], group: "Team" },

  { to: "/marketing", label: "Marketing", icon: Megaphone, roles: ["owner", "marketing"], group: "Business" },
  { to: "/tasks", label: "To-Do", icon: KanbanSquare, roles: ["owner", "sales", "marketing", "crew", "employee"], group: "Business" },
  { to: "/blog", label: "Blog", icon: PenLine, roles: ["owner", "sales", "marketing", "crew", "employee"], group: "Business" },
  { to: "/notifications", label: "Notifications", icon: BellRing, roles: ["owner", "sales", "marketing"], group: "Business" },
  { to: "/settings", label: "Settings", icon: SlidersHorizontal, roles: ["owner"], group: "Business" },
  { to: "/help", label: "Help", icon: HelpCircle, roles: ["owner"], group: "Business" },
];

/** Four fixed thumb targets per role. Everything else lives behind More. */
const PRIMARY_TABS = {
  owner: ["/", "/leads", "/jobs", "/crew"],
  sales: ["/leads", "/calculator", "/script", "/team"],
  marketing: ["/marketing", "/tasks", "/blog", "/team"],
  crew: ["/today", "/jobs", "/clock", "/team"],
  employee: ["/projects", "/day-sheet", "/tasks", "/team"],
};

const GROUP_ORDER = ["Today", "My day", "Sales", "Money", "Team", "Business"];

const ROLE_LABEL = { owner: "Owner", sales: "Sales", employee: "Crew", crew: "Crew", marketing: "Marketing" };

const LiveIndicator = () => {
  const { health } = useApp();
  const ok = health.airtable_configured;
  return (
    <span
      data-testid="live-indicator"
      className="hidden lg:inline-flex items-center gap-2 rounded-md bg-surface-sunk px-2.5 py-1.5 text-[11.5px] font-semibold text-ink-2"
    >
      <span
        aria-hidden="true"
        className={`w-1.5 h-1.5 rounded-full ${ok ? "bg-success animate-tick" : ok === false ? "bg-warning" : "bg-faint"}`}
      />
      {ok ? "Live from Airtable" : ok === false ? "Airtable key needed" : "Checking…"}
    </span>
  );
};

/** Jump-to palette. Pure client-side navigation over the nav list — no backend. */
const JumpTo = ({ items }) => {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const go = (to) => {
    setOpen(false);
    navigate(to);
  };

  return (
    <>
      <button
        data-testid="jump-to-btn"
        onClick={() => setOpen(true)}
        className="group flex items-center gap-2 rounded-lg border border-border bg-surface px-3 h-9 text-[13px] text-faint transition-colors hover:border-border-strong hover:text-ink-2 md:min-w-[220px]"
      >
        <Search className="w-4 h-4" aria-hidden="true" />
        <span className="hidden md:inline">Jump to a page…</span>
        <kbd className="ml-auto hidden lg:inline text-[10.5px] font-semibold tracking-wide text-faint">⌘K</kbd>
      </button>
      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput placeholder="Jump to a page…" data-testid="jump-to-input" />
        <CommandList>
          <CommandEmpty>No page by that name.</CommandEmpty>
          {GROUP_ORDER.map((g) => {
            const list = items.filter((n) => n.group === g);
            if (!list.length) return null;
            return (
              <CommandGroup key={g} heading={g}>
                {list.map(({ to, label, icon: Icon }) => (
                  <CommandItem key={`${g}-${to}`} value={`${label} ${g}`} onSelect={() => go(to)}>
                    <Icon className="mr-2 w-4 h-4 text-faint" aria-hidden="true" />
                    {label}
                  </CommandItem>
                ))}
              </CommandGroup>
            );
          })}
        </CommandList>
      </CommandDialog>
    </>
  );
};

const Badge = ({ count, testId, className = "" }) =>
  count > 0 ? (
    <span
      data-testid={testId}
      className={`min-w-[18px] h-[18px] px-1 inline-flex items-center justify-center rounded-full bg-accent text-accent-foreground text-[10px] font-bold tnum ${className}`}
    >
      {count > 9 ? "9+" : count}
    </span>
  ) : null;

export default function Layout() {
  const { privacy, togglePrivacy, refreshAll, refreshing, health } = useApp();
  const { role, canSwitch, switchRole, user } = useAuth();
  const [assignedCalc, setAssignedCalc] = useState(false);
  useEffect(() => {
    if (role === "crew" || role === "marketing") {
      getScopeAccessApi().then((d) => setAssignedCalc(!!d.tier)).catch(() => setAssignedCalc(false));
    } else {
      setAssignedCalc(false);
    }
  }, [role]);
  const navItems = useMemo(() => {
    const items = NAV.filter((n) => n.roles.includes(role || "owner"));
    if (assignedCalc && !items.some((n) => n.to === "/scope-calculator")) {
      items.push({ to: "/scope-calculator", label: "Scope Calculator", icon: Boxes, roles: [role], group: "Sales" });
    }
    return items;
  }, [role, assignedCalc]);
  const multiRoles = (user?.roles || []).length > 1 ? user.roles : null;
  const switchOptions = multiRoles || (canSwitch ? ["owner", "sales", "employee", "marketing"] : null);
  const [moreOpen, setMoreOpen] = useState(false);
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

  const location = useLocation();
  const isTeamRole = ["sales", "marketing", "crew", "employee"].includes(role);
  const hasAlerts = ["owner", "sales", "marketing"].includes(role);
  const [notifItems, setNotifItems] = useState([]);
  const [seenMarks, setSeenMarks] = useState({ task: "", blog: "" });
  const [alertsUnread, setAlertsUnread] = useState(0);

  useEffect(() => {
    setMoreOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!hasAlerts) return;
    const load = () => alertsUnreadApi().then(setAlertsUnread).catch(() => {});
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [role, hasAlerts]);

  useEffect(() => {
    if (!hasAlerts || !location.pathname.startsWith("/notifications")) return;
    markAlertsReadApi().then(() => setAlertsUnread(0)).catch(() => {});
  }, [location.pathname, hasAlerts]);

  useEffect(() => {
    if (!isTeamRole) return;
    setSeenMarks({
      task: localStorage.getItem(`hy_seen_task_${role}`) || "",
      blog: localStorage.getItem(`hy_seen_blog_${role}`) || "",
    });
    const load = () => teamNotificationsApi().then(setNotifItems).catch(() => {});
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [role, isTeamRole]);

  useEffect(() => {
    if (!isTeamRole) return;
    const type = location.pathname.startsWith("/tasks") ? "task" : location.pathname.startsWith("/blog") ? "blog" : null;
    if (!type) return;
    const now = new Date().toISOString();
    localStorage.setItem(`hy_seen_${type}_${role}`, now);
    setSeenMarks((s) => ({ ...s, [type]: now }));
  }, [location.pathname, role, isTeamRole]);

  const badgeCounts = {};
  if (isTeamRole) {
    badgeCounts["/tasks"] = notifItems.filter((n) => n.type === "task" && n.created_at > seenMarks.task).length;
    badgeCounts["/blog"] = notifItems.filter((n) => n.type === "blog" && n.created_at > seenMarks.blog).length;
  }
  if (hasAlerts) {
    badgeCounts["/notifications"] = alertsUnread;
  }

  const tabPaths = PRIMARY_TABS[role] || PRIMARY_TABS.owner;
  const tabs = tabPaths.map((p) => navItems.find((n) => n.to === p)).filter(Boolean);
  const moreBadge = navItems
    .filter((n) => !tabPaths.includes(n.to))
    .reduce((s, n) => s + (badgeCounts[n.to] || 0), 0);

  const testId = (label, prefix) => `${prefix}-${label.toLowerCase().replace(/\s+/g, "-")}`;

  const showOwnerTools = role !== "crew" && role !== "marketing";
  const showPrivacy = role !== "employee" && role !== "crew";

  const PrivacyButton = ({ testid, className = "" }) => (
    <Button
      data-testid={testid}
      variant={privacy ? "accent" : "outline"}
      size="sm"
      onClick={togglePrivacy}
      className={`gap-1.5 ${className}`}
    >
      {privacy ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
      {privacy ? "Privacy on" : "Privacy off"}
    </Button>
  );

  const RefreshButton = ({ testid, className = "" }) => (
    <Button
      data-testid={testid}
      variant="outline"
      size="sm"
      onClick={refreshAll}
      disabled={refreshing}
      className={`gap-1.5 ${className}`}
    >
      <RefreshCw className={`w-4 h-4 transition-transform ${refreshing ? "animate-spin" : ""}`} />
      Refresh
    </Button>
  );

  return (
    <div className="min-h-screen bg-background">
      {/* ---------------- desktop sidebar ---------------- */}
      <aside className="hidden md:flex print:hidden fixed inset-y-0 left-0 w-[248px] flex-col bg-primary-deep text-white z-50">
        <div className="px-5 pt-5 pb-4">
          <img src="/logo.png" alt="Haul Yeah Moving" data-testid="sidebar-logo" className="h-11 w-auto rounded-md" />
        </div>

        <nav className="flex-1 overflow-y-auto no-scrollbar pb-3">
          {GROUP_ORDER.map((group) => {
            const list = navItems.filter((n) => n.group === group);
            if (!list.length) return null;
            return (
              <div key={group} className="mb-1">
                <p className="px-5 pt-3 pb-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-white/50">{group}</p>
                {list.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={`${group}-${to}`}
                    to={to}
                    end={to === "/"}
                    data-testid={testId(label, "nav")}
                    className={({ isActive }) =>
                      `mx-2.5 flex items-center gap-2.5 rounded-lg px-2.5 py-[7px] text-[13.5px] font-medium transition-colors duration-[160ms] ease-out-soft ${
                        isActive ? "bg-surface text-primary font-semibold" : "text-white/70 hover:bg-surface/10 hover:text-white"
                      }`
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <Icon className={`w-[17px] h-[17px] shrink-0 ${isActive ? "text-accent" : ""}`} aria-hidden="true" />
                        <span className="truncate">{label}</span>
                        <Badge count={badgeCounts[to]} testId={`nav-badge${to.replace("/", "-")}`} className="ml-auto" />
                      </>
                    )}
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>

        <div className="border-t border-white/10 p-3 space-y-2">
          {switchOptions ? (
            <Select value={role || switchOptions[0]} onValueChange={handleSwitch}>
              <SelectTrigger
                data-testid="role-switch-select"
                className="w-full h-9 rounded-lg border-white/20 bg-white/10 text-[12px] font-semibold text-white"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {switchOptions.map((r) => (
                  <SelectItem key={r} value={r} data-testid={`switch-option-${r}`}>{ROLE_LABEL[r] || r} view</SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <span
              data-testid="role-chip"
              className="flex items-center justify-center rounded-lg bg-white/10 px-2.5 py-1.5 text-[12px] font-semibold text-white"
            >
              {ROLE_LABEL[role] || "Owner"} account
            </span>
          )}
          <Button
            data-testid="logout-btn"
            variant="ghost"
            size="sm"
            onClick={logout}
            className="w-full gap-1.5 text-white/70 hover:bg-surface/10 hover:text-white"
          >
            <LogOut className="w-4 h-4" />
            Log out
          </Button>
        </div>
      </aside>

      {/* ---------------- main column ---------------- */}
      <div className="md:pl-[248px] print:pl-0">
        <header className="sticky top-0 z-40 bg-background/90 backdrop-blur-md border-b border-border print:hidden">
          <div className="flex items-center gap-2 px-4 md:px-7 h-14">
            <img src="/logo.png" alt="Haul Yeah Moving" data-testid="mobile-logo" className="md:hidden h-8 w-auto rounded" />
            <div className="hidden md:block">
              <JumpTo items={navItems} />
            </div>
            <div className="flex items-center gap-1.5 md:gap-2 ml-auto">
              <LiveIndicator />
              {showOwnerTools && <RefreshButton testid="refresh-data-btn" className="hidden md:inline-flex" />}
              {showPrivacy && <PrivacyButton testid="privacy-toggle-btn" className="hidden md:inline-flex" />}
              <NotificationsBell />
              {showOwnerTools && (
                <Button data-testid="new-meet-btn" asChild variant="ghost" size="icon" className="hidden md:inline-flex">
                  <a href="https://meet.google.com/new" target="_blank" rel="noreferrer" aria-label="Start a Google Meet">
                    <Video className="w-4 h-4" />
                  </a>
                </Button>
              )}
            </div>
          </div>
          {health.airtable_configured === false && showOwnerTools && (
            <div
              data-testid="key-missing-banner"
              className="flex items-start gap-2 border-t border-warning/25 bg-warning/10 px-4 md:px-7 py-2.5 text-[13px] text-warning"
            >
              <KeyRound className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
              <span>
                One step left: add your Airtable token as <strong>AIRTABLE_API_KEY</strong> in the app's secrets panel, then press Refresh. Never paste the token in chat or code.
              </span>
            </div>
          )}
        </header>

        <main
          key={location.pathname}
          className="px-4 md:px-7 py-5 md:py-7 pb-[104px] md:pb-12 max-w-[1180px] mx-auto animate-fade-up print:p-0 print:max-w-none"
        >
          <Outlet />
        </main>
      </div>

      {/* ---------------- mobile tab bar ---------------- */}
      <nav className="md:hidden print:hidden fixed bottom-0 inset-x-0 z-50 bg-primary-deep border-t border-white/10 safe-bottom">
        <div className="flex items-stretch">
          {tabs.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              data-testid={testId(label, "tab")}
              className={({ isActive }) =>
                `press relative flex flex-1 flex-col items-center gap-1 py-2.5 text-[10.5px] font-semibold transition-colors duration-[160ms] ${
                  isActive ? "text-white" : "text-white/55"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <span className="relative">
                    <Icon className={`w-[22px] h-[22px] ${isActive ? "text-accent" : ""}`} aria-hidden="true" />
                    <Badge
                      count={badgeCounts[to]}
                      testId={`tab-badge${to.replace("/", "-")}`}
                      className="absolute -top-1.5 -right-2.5"
                    />
                  </span>
                  <span className="max-w-full truncate px-0.5">{label}</span>
                  {isActive && <span aria-hidden="true" className="absolute top-0 h-[2.5px] w-9 rounded-b bg-accent" />}
                </>
              )}
            </NavLink>
          ))}

          <Sheet open={moreOpen} onOpenChange={setMoreOpen}>
            <SheetTrigger asChild>
              <button
                data-testid="tab-more-btn"
                className="press flex flex-1 flex-col items-center gap-1 py-2.5 text-[10.5px] font-semibold text-white/55"
              >
                <span className="relative">
                  <MoreHorizontal className="w-[22px] h-[22px]" aria-hidden="true" />
                  <Badge count={moreBadge} testId="tab-badge-more" className="absolute -top-1.5 -right-2.5" />
                </span>
                <span>More</span>
              </button>
            </SheetTrigger>

            <SheetContent side="bottom" className="max-h-[86vh] overflow-y-auto rounded-t-2xl border-border bg-surface p-0">
              <div className="px-5 pt-5 pb-3">
                <SheetTitle className="font-display text-xl font-extrabold text-primary">Everything else</SheetTitle>
                <p className="text-[13px] text-ink-2 mt-1">Your four most-used screens stay on the bar below.</p>
              </div>

              <div className="px-3 pb-3">
                {GROUP_ORDER.map((group) => {
                  const list = navItems.filter((n) => n.group === group && !tabPaths.includes(n.to));
                  if (!list.length) return null;
                  return (
                    <div key={group} className="mb-4">
                      <p className="label-eyebrow px-2 mb-1.5">{group}</p>
                      <div className="grid grid-cols-2 gap-1.5">
                        {list.map(({ to, label, icon: Icon }) => (
                          <NavLink
                            key={`${group}-${to}`}
                            to={to}
                            data-testid={testId(label, "more")}
                            className={({ isActive }) =>
                              `press flex items-center gap-2.5 rounded-lg px-3 py-3 text-[14px] font-semibold transition-colors ${
                                isActive ? "bg-primary text-white" : "bg-surface-sunk text-ink hover:bg-muted"
                              }`
                            }
                          >
                            {({ isActive }) => (
                              <>
                                <Icon className={`w-[18px] h-[18px] shrink-0 ${isActive ? "text-accent" : "text-faint"}`} aria-hidden="true" />
                                <span className="truncate">{label}</span>
                                <Badge count={badgeCounts[to]} className="ml-auto" />
                              </>
                            )}
                          </NavLink>
                        ))}
                      </div>
                    </div>
                  );
                })}

                <div className="border-t border-border pt-4 mt-1 space-y-2.5">
                  <p className="label-eyebrow px-2">This device</p>
                  <div className="grid grid-cols-2 gap-2 px-0.5">
                    {showPrivacy && <PrivacyButton testid="tab-privacy-btn" className="w-full" />}
                    {showOwnerTools && <RefreshButton testid="tab-refresh-btn" className="w-full" />}
                  </div>
                  {canSwitch && (
                    <div className="px-0.5">
                      <Select value={role || "owner"} onValueChange={handleSwitch}>
                        <SelectTrigger data-testid="tab-account-select" className="w-full h-11">
                          <span className="flex items-center gap-2 text-[13.5px] font-semibold">
                            <UserRound className="w-4 h-4 text-faint" />
                            <SelectValue />
                          </span>
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="owner">Owner view</SelectItem>
                          <SelectItem value="sales">Sales view</SelectItem>
                          <SelectItem value="employee">Crew view</SelectItem>
                          <SelectItem value="marketing">Marketing view</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                  <div className="px-0.5 pb-2">
                    <Button data-testid="tab-logout-btn" variant="outline" onClick={logout} className="w-full gap-2">
                      <LogOut className="w-4 h-4" /> Log out
                    </Button>
                  </div>
                </div>
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </nav>

      {role === "crew" && <CrewContactsBubble />}
    </div>
  );
}
