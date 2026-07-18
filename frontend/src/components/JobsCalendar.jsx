import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, CalendarDays, Link2, RefreshCw, Unlink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/AuthGate";
import { Private } from "@/components/Bits";
import { PF, f, STATUS_PILL } from "@/lib/fields";
import { gcalStatusApi, gcalLoginApi, gcalSyncApi, gcalDisconnectApi, apiErrorMessage } from "@/lib/api";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export default function JobsCalendar({ projects }) {
  const { role } = useAuth();
  const isOwner = (role || "owner") === "owner";
  const now = new Date();
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() });
  const [gcal, setGcal] = useState(null);
  const [syncing, setSyncing] = useState(false);

  const visible = projects.filter((p) => {
    const s = f(p, PF.status);
    return isOwner ? s !== "Cancelled" : ["Scheduled", "In Progress"].includes(s);
  });

  const byDate = {};
  visible.forEach((p) => {
    const d = (f(p, PF.jobDate) || "").slice(0, 10);
    if (d) (byDate[d] = byDate[d] || []).push(p);
  });

  useEffect(() => {
    if (isOwner) gcalStatusApi().then(setGcal).catch(() => {});
  }, [isOwner]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("gcal") === "connected") {
      toast.success("Google Calendar connected.");
      window.history.replaceState({}, "", window.location.pathname);
      gcalStatusApi().then(setGcal).catch(() => {});
    } else if (params.get("gcal") === "error") {
      toast.error("Google connection failed. Try again.");
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  const connect = () =>
    gcalLoginApi()
      .then((d) => { window.location.href = d.authorization_url; })
      .catch((e) => toast.error(apiErrorMessage(e)));

  const sync = async () => {
    setSyncing(true);
    try {
      const d = await gcalSyncApi();
      toast.success(`Synced to Google Calendar: ${d.created} new, ${d.updated} updated.`);
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setSyncing(false);
  };

  const disconnect = () =>
    gcalDisconnectApi()
      .then(() => { setGcal((g) => ({ ...g, connected: false, email: null })); toast.success("Google Calendar disconnected."); })
      .catch((e) => toast.error(apiErrorMessage(e)));

  const shiftMonth = (delta) =>
    setYm(({ y, m }) => {
      const d = new Date(y, m + delta, 1);
      return { y: d.getFullYear(), m: d.getMonth() };
    });

  const offset = new Date(ym.y, ym.m, 1).getDay();
  const dim = new Date(ym.y, ym.m + 1, 0).getDate();
  const cells = [...Array(offset).fill(null), ...Array.from({ length: dim }, (_, i) => i + 1)];
  const todayKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const dateKey = (day) => `${ym.y}-${String(ym.m + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;

  return (
    <div data-testid="jobs-calendar" className="bg-white border border-slate-200 rounded-lg p-4 mb-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <h2 className="font-display font-bold text-lg text-[#1B2A4A] flex items-center gap-2">
          <CalendarDays className="w-5 h-5 text-[#E8743B]" /> Calendar
        </h2>
        <div className="flex items-center gap-1.5">
          <Button data-testid="calendar-prev-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => shiftMonth(-1)}>
            <ChevronLeft className="w-3.5 h-3.5" /> Prev
          </Button>
          <span data-testid="calendar-month-label" className="text-sm font-bold text-[#1B2A4A] w-36 text-center">
            {MONTHS[ym.m]} {ym.y}
          </span>
          <Button data-testid="calendar-next-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => shiftMonth(1)}>
            Next <ChevronRight className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {isOwner && (
        <div className="flex flex-wrap items-center gap-2 border border-slate-200 bg-slate-50 rounded-lg px-3 py-2 mb-3">
          {gcal?.connected ? (
            <>
              <span className="text-xs text-slate-600">
                Google Calendar: <strong className="text-emerald-700">connected</strong>{gcal.email ? <> as <Private>{gcal.email}</Private></> : null}
              </span>
              <Button data-testid="gcal-sync-btn" size="sm" className="gap-1 text-xs bg-[#E8743B] hover:bg-[#d4632e]" onClick={sync} disabled={syncing}>
                <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin" : ""}`} /> {syncing ? "Syncing…" : "Sync jobs to Google"}
              </Button>
              <Button data-testid="gcal-disconnect-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={disconnect}>
                <Unlink className="w-3.5 h-3.5" /> Disconnect
              </Button>
            </>
          ) : (
            <>
              <span className="text-xs text-slate-600">
                {gcal && !gcal.creds_configured
                  ? "Google Calendar needs setup: add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the secrets panel."
                  : "Connect your Google account to push booked jobs onto your Google Calendar."}
              </span>
              <Button data-testid="gcal-connect-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={connect}>
                <Link2 className="w-3.5 h-3.5" /> Connect Google Calendar
              </Button>
            </>
          )}
        </div>
      )}

      <div className="grid grid-cols-7 gap-1 text-center text-[10px] font-bold uppercase tracking-wide text-slate-400 mb-1">
        {WEEKDAYS.map((d) => <div key={d}>{d}</div>)}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((day, i) => {
          const key = day ? dateKey(day) : null;
          const jobs = key ? byDate[key] || [] : [];
          const isToday = key === todayKey;
          return (
            <div
              key={i}
              className={`min-h-[64px] rounded-md border p-1 ${day ? "bg-white border-slate-200" : "bg-transparent border-transparent"} ${isToday ? "ring-2 ring-[#E8743B]" : ""}`}
            >
              {day && (
                <>
                  <div className={`text-[10px] font-bold ${isToday ? "text-[#E8743B]" : "text-slate-400"}`}>{day}</div>
                  <div className="space-y-0.5">
                    {jobs.map((p) => (
                      <div
                        key={p.id}
                        data-testid="calendar-job-pill"
                        title={f(p, PF.jobName) || "Job"}
                        className={`text-[9px] leading-tight border rounded px-1 py-0.5 truncate font-semibold ${STATUS_PILL[f(p, PF.status)] || "bg-slate-100 text-slate-600 border-slate-300"}`}
                      >
                        <Private>{f(p, PF.jobName) || "Job"}</Private>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>
      <p className="text-xs text-slate-500 mt-2">
        {isOwner ? "Shows every job that isn't cancelled." : "Shows jobs that are Scheduled or In Progress."}
      </p>
    </div>
  );
}
