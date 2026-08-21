import React, { useState } from "react";
import { ChevronLeft, ChevronRight, CalendarDays } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/AuthGate";
import { Private } from "@/components/Bits";
import { PF, f, STATUS_PILL } from "@/lib/fields";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DOT = {
  "Pending Deposit": "bg-warning",
  Scheduled: "bg-info",
  "In Progress": "bg-primary",
  Completed: "bg-success",
};

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export default function JobsCalendar({ projects }) {
  const { role } = useAuth();
  const isOwner = (role || "owner") === "owner";
  const now = new Date();
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() });

  const visible = projects.filter((p) => {
    const s = f(p, PF.status);
    return isOwner ? s !== "Cancelled" : ["Scheduled", "In Progress"].includes(s);
  });

  const byDate = {};
  visible.forEach((p) => {
    const d = (f(p, PF.jobDate) || "").slice(0, 10);
    if (d) (byDate[d] = byDate[d] || []).push(p);
  });

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
    <div data-testid="jobs-calendar" className="surface p-4 mb-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <h2 className="font-display font-bold text-lg text-primary flex items-center gap-2">
          <CalendarDays className="w-5 h-5 text-accent-ink" /> Calendar
        </h2>
        <div className="flex items-center gap-1.5">
          <Button data-testid="calendar-prev-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => shiftMonth(-1)}>
            <ChevronLeft className="w-3.5 h-3.5" /> Prev
          </Button>
          <span data-testid="calendar-month-label" className="text-sm font-bold text-primary w-36 text-center">
            {MONTHS[ym.m]} {ym.y}
          </span>
          <Button data-testid="calendar-next-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => shiftMonth(1)}>
            Next <ChevronRight className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-1 text-center text-[10px] font-bold uppercase tracking-wide text-faint mb-1">
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
              className={`min-h-[52px] rounded-md border p-1 sm:min-h-[70px] ${day ? "border-border bg-surface" : "border-transparent bg-transparent"} ${isToday ? "ring-2 ring-accent" : ""}`}
            >
              {day && (
                <>
                  <div className={`text-[11px] font-bold tnum ${isToday ? "text-accent-ink" : "text-faint"}`}>{day}</div>
                  {/* A phone cell is ~44px wide. Three characters of a job name is
                      not information, so small screens get one dot per job and the
                      full labels appear from sm: up. */}
                  <div className="mt-1 flex flex-wrap gap-1 sm:hidden">
                    {jobs.slice(0, 4).map((p) => (
                      <span
                        key={p.id}
                        data-testid="calendar-job-pill"
                        title={f(p, PF.jobName) || "Job"}
                        aria-label={f(p, PF.jobName) || "Job"}
                        className={`h-1.5 w-1.5 rounded-full ${DOT[f(p, PF.status)] || "bg-faint"}`}
                      />
                    ))}
                    {jobs.length > 4 && <span className="text-[9px] font-bold leading-none text-faint">+{jobs.length - 4}</span>}
                  </div>
                  <div className="hidden space-y-0.5 sm:block">
                    {jobs.map((p) => (
                      <div
                        key={p.id}
                        data-testid="calendar-job-pill"
                        title={f(p, PF.jobName) || "Job"}
                        className={`truncate rounded px-1 py-0.5 text-[10px] font-semibold leading-tight ${STATUS_PILL[f(p, PF.status)] || "bg-surface-sunk text-ink-2"}`}
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
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 sm:hidden">
        {Object.entries(DOT).map(([label, cls]) => (
          <span key={label} className="inline-flex items-center gap-1.5 text-[11px] text-faint">
            <span className={`h-1.5 w-1.5 rounded-full ${cls}`} aria-hidden="true" /> {label}
          </span>
        ))}
      </div>
      <p className="text-[12.5px] text-faint mt-2">
        {isOwner ? "Shows every job that isn't cancelled." : "Shows jobs that are Scheduled or In Progress."}
      </p>
    </div>
  );
}
