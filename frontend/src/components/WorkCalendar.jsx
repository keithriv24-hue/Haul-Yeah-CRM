import React, { useEffect, useState } from "react";
import dayjs from "dayjs";
import { ChevronLeft, ChevronRight, Truck, Users, Clock3, CloudUpload, CloudOff, CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { calendarJobsApi, timelogStatusApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const hoursLabel = (mins) => `${Math.floor(mins / 60)}h ${mins % 60}m`;
const fmtTime = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "");

const STATUS_STYLE = {
  Assigned: "bg-slate-100 text-slate-600 border-slate-300",
  "En Route": "bg-sky-100 text-sky-800 border-sky-300",
  Arrived: "bg-amber-100 text-amber-800 border-amber-300",
  "In Progress": "bg-indigo-100 text-indigo-800 border-indigo-300",
  Complete: "bg-emerald-100 text-emerald-800 border-emerald-300",
};

const SyncBadge = () => {
  const [s, setS] = useState(null);
  useEffect(() => {
    const load = () => timelogStatusApi().then(setS).catch(() => {});
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, []);
  if (!s) return null;
  if (!s.configured)
    return (
      <span data-testid="timelog-sync-badge" className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2.5 py-1">
        <CloudOff className="w-3.5 h-3.5" /> Airtable key missing — punches saved, will sync once it's added
      </span>
    );
  if (s.pending > 0)
    return (
      <span
        data-testid="timelog-sync-badge"
        title={(s.pending_jobs || []).map((j) => `${j.job_name}: ${j.error || "retrying"}`).join("\n")}
        className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2.5 py-1"
      >
        <CloudUpload className="w-3.5 h-3.5" /> {s.pending} job log{s.pending > 1 ? "s" : ""} syncing to Airtable…
      </span>
    );
  return (
    <span data-testid="timelog-sync-badge" className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2.5 py-1">
      <CheckCircle2 className="w-3.5 h-3.5" /> Airtable job log synced
    </span>
  );
};

const CalJobCard = ({ job }) => (
  <div data-testid="cal-job-card" className="border border-slate-200 rounded-lg p-4">
    <div className="flex flex-wrap items-start justify-between gap-2">
      <p className="font-bold text-[#1B2A4A]">{job.job_name}</p>
      <div className="flex items-center gap-2">
        <Badge variant="outline" className={`text-[10px] ${STATUS_STYLE[job.exec_status] || STATUS_STYLE.Assigned}`}>{job.exec_status}</Badge>
        <span data-testid="cal-job-hours" className="text-sm font-bold text-[#1B2A4A] inline-flex items-center gap-1">
          <Clock3 className="w-3.5 h-3.5 text-[#E8743B]" />
          {job.worked_minutes != null ? hoursLabel(job.worked_minutes) : job.on_clock ? "still on the clock" : "no punches yet"}
        </span>
      </div>
    </div>
    {job.first_in && (
      <p className="text-[11px] text-slate-400 mt-0.5">
        {fmtTime(job.first_in)}{job.last_out ? ` → ${fmtTime(job.last_out)}` : " → …"}
      </p>
    )}
    <div className="flex flex-wrap gap-1.5 mt-2">
      {job.crew.map((c) => (
        <Badge key={c.name} variant="outline" data-testid="cal-crew-chip" className="text-[10px] bg-orange-50 text-orange-800 border-orange-200">
          {c.name} <span className="ml-1 font-black">{c.position === "Driver" ? "DRIVER" : "HELPER"}</span>
        </Badge>
      ))}
      {job.crew.length === 0 && <span className="text-xs text-amber-600 font-semibold">No crew was assigned</span>}
    </div>
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1 mt-3 text-xs text-slate-600">
      <span data-testid="cal-job-size"><span className="text-slate-400 font-semibold">Size:</span> {job.job_size || "—"}</span>
      <span className="inline-flex items-center gap-1"><Users className="w-3 h-3 text-slate-400" /> {job.crew_size} crew</span>
      <span data-testid="cal-job-truck" className="inline-flex items-center gap-1">
        <Truck className="w-3 h-3 text-slate-400" /> {job.truck_name || "no truck"}{job.truck_plate ? ` · ${job.truck_plate}` : ""}
      </span>
    </div>
    {(job.delay_factors || []).length > 0 && (
      <div className="flex flex-wrap gap-1 mt-2">
        {job.delay_factors.map((d) => (
          <Badge key={d} variant="outline" data-testid="cal-delay-chip" className={`text-[10px] ${d === "None" ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-amber-50 text-amber-700 border-amber-200"}`}>
            {d}
          </Badge>
        ))}
      </div>
    )}
    {job.notes && <p data-testid="cal-job-notes" className="text-xs text-slate-500 bg-slate-50 rounded p-2 mt-2">"{job.notes}"</p>}
  </div>
);

export const WorkCalendar = () => {
  const [month, setMonth] = useState(() => dayjs().startOf("month"));
  const [days, setDays] = useState({});
  const [selected, setSelected] = useState(() => dayjs().format("YYYY-MM-DD"));

  useEffect(() => {
    calendarJobsApi(month.format("YYYY-MM")).then((d) => setDays(d.days)).catch(() => setDays({}));
  }, [month]);

  const firstDay = month.day();
  const cells = [...Array(firstDay).fill(null), ...Array.from({ length: month.daysInMonth() }, (_, i) => i + 1)];
  const today = dayjs().format("YYYY-MM-DD");
  const selectedJobs = days[selected] || [];

  return (
    <div data-testid="work-calendar" className="bg-white border border-slate-200 rounded-lg p-5 mb-8">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <div>
          <h2 className="font-display font-bold text-lg text-[#1B2A4A]">Work calendar</h2>
          <p className="text-xs text-slate-500">Tap a day to see who worked, on what truck, and for how long.</p>
        </div>
        <SyncBadge />
      </div>
      <div className="grid lg:grid-cols-[340px,1fr] gap-6">
        <div>
          <div className="flex items-center justify-between mb-2">
            <Button data-testid="cal-prev-month" variant="outline" size="sm" onClick={() => setMonth((m) => m.subtract(1, "month"))}>
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <p data-testid="cal-month-label" className="font-bold text-[#1B2A4A] text-sm">{month.format("MMMM YYYY")}</p>
            <Button data-testid="cal-next-month" variant="outline" size="sm" onClick={() => setMonth((m) => m.add(1, "month"))}>
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
          <div className="grid grid-cols-7 gap-1 text-center">
            {WEEKDAYS.map((d) => (
              <div key={d} className="text-[10px] uppercase tracking-wide text-slate-400 font-bold py-1">{d}</div>
            ))}
            {cells.map((d, i) => {
              if (d === null) return <div key={`b${i}`} />;
              const dateStr = month.date(d).format("YYYY-MM-DD");
              const has = (days[dateStr] || []).length > 0;
              const isSel = dateStr === selected;
              return (
                <button
                  key={dateStr}
                  data-testid="cal-day-cell"
                  data-date={dateStr}
                  onClick={() => setSelected(dateStr)}
                  className={`aspect-square rounded-md text-sm font-semibold flex flex-col items-center justify-center gap-0.5 transition-colors ${
                    isSel ? "bg-[#1B2A4A] text-white" : has ? "bg-orange-50 text-[#1B2A4A] hover:bg-orange-100" : "bg-slate-50 text-slate-500 hover:bg-slate-100"
                  } ${dateStr === today && !isSel ? "ring-2 ring-[#E8743B]" : ""}`}
                >
                  {d}
                  {has && <span className="w-1.5 h-1.5 rounded-full bg-[#E8743B]" />}
                </button>
              );
            })}
          </div>
        </div>
        <div>
          <p className="text-sm font-bold uppercase tracking-wide text-slate-500 mb-2">{fmtDate(selected)}</p>
          {selectedJobs.length === 0 ? (
            <p data-testid="cal-no-jobs" className="text-sm text-slate-400 border border-dashed border-slate-200 rounded-lg p-6 text-center">No jobs.</p>
          ) : (
            <div className="space-y-3">{selectedJobs.map((j) => <CalJobCard key={j.id} job={j} />)}</div>
          )}
        </div>
      </div>
    </div>
  );
};
