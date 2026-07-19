import React, { useState } from "react";
import { ChevronLeft, ChevronRight, CalendarDays } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/AuthGate";
import { Private } from "@/components/Bits";
import { PF, f, STATUS_PILL } from "@/lib/fields";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
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
