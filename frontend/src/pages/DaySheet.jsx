import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Printer, Truck, MapPin, Users, Clock, StickyNote } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, LoadingRows, Pill } from "@/components/Bits";
import { PF, f } from "@/lib/fields";
import { fmtDate, todayISO } from "@/lib/format";

const Row = ({ icon: Icon, label, value }) => (
  <div className="flex items-start gap-2 text-sm">
    <Icon className="w-4 h-4 text-slate-400 mt-0.5 shrink-0 print:text-black" />
    <span className="text-slate-500 shrink-0 print:text-black">{label}:</span>
    <span className="font-semibold text-[#1B2A4A] min-w-0 break-words print:text-black">{value}</span>
  </div>
);

export default function DaySheet() {
  const { loadTable, records, tableState } = useApp();
  const [date, setDate] = useState(todayISO());

  useEffect(() => {
    loadTable("projects");
  }, [loadTable]);

  const { loading, error } = tableState("projects");
  const jobs = records("projects")
    .filter((p) => (f(p, PF.jobDate) || "").slice(0, 10) === date && f(p, PF.status) !== "Cancelled")
    .sort((a, b) => (f(a, PF.jobName) || "").localeCompare(f(b, PF.jobName) || ""));

  return (
    <div data-testid="day-sheet-page">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5 print:hidden">
        <Button asChild variant="outline" size="sm" className="gap-1.5" data-testid="day-sheet-back-btn">
          <Link to="/projects"><ArrowLeft className="w-4 h-4" /> Back to Projects</Link>
        </Button>
        <div className="flex items-center gap-2">
          <Input
            data-testid="day-sheet-date-input"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="w-[160px]"
          />
          <Button data-testid="day-sheet-print-btn" onClick={() => window.print()} className="gap-1.5 bg-[#E8743B] hover:bg-[#d4632e]">
            <Printer className="w-4 h-4" /> Print
          </Button>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-6 print:border-0 print:p-0" data-testid="day-sheet">
        <div className="flex items-center justify-between border-b border-slate-200 pb-4 mb-5">
          <div>
            <div className="font-display text-2xl font-extrabold text-[#1B2A4A] print:text-black">Haul Yeah Moving — Crew Day Sheet</div>
            <div className="text-sm text-slate-500 print:text-black" data-testid="day-sheet-date-label">{fmtDate(date)}</div>
          </div>
          <img src="/logo.png" alt="Haul Yeah Moving" className="h-12 rounded" />
        </div>

        {loading && !records("projects").length ? (
          <LoadingRows />
        ) : error && !records("projects").length ? (
          <EmptyState>{error}</EmptyState>
        ) : jobs.length === 0 ? (
          <EmptyState>No jobs on the books for this day. Pick another date up top.</EmptyState>
        ) : (
          <div className="space-y-5">
            {jobs.map((p, idx) => (
              <div key={p.id} data-testid="day-sheet-job" className="border border-slate-200 rounded-lg p-4 print:break-inside-avoid">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                  <div className="font-display font-bold text-lg text-[#1B2A4A] print:text-black">
                    Job {idx + 1}: {f(p, PF.jobName) || "Unnamed job"}
                  </div>
                  <Pill value={f(p, PF.status) || "—"} />
                </div>
                <div className="grid sm:grid-cols-2 gap-x-6 gap-y-2">
                  <Row icon={MapPin} label="From" value={f(p, PF.fromAddr) || "—"} />
                  <Row icon={MapPin} label="To" value={f(p, PF.toAddr) || "—"} />
                  <Row icon={Truck} label="Truck" value={f(p, PF.truck) || "—"} />
                  <Row icon={Users} label="Crew" value={f(p, PF.crewSize) ? `${f(p, PF.crewSize)} movers` : "—"} />
                  <Row icon={Clock} label="Est. hours" value={f(p, PF.estHours) ? `${f(p, PF.estHours)} hrs` : "—"} />
                  <Row icon={Clock} label="Start time" value="____________" />
                </div>
                {f(p, PF.notes) && (
                  <div className="flex items-start gap-2 text-sm mt-3 border-t border-slate-100 pt-3">
                    <StickyNote className="w-4 h-4 text-slate-400 mt-0.5 shrink-0 print:text-black" />
                    <span className="whitespace-pre-wrap break-words print:text-black">{f(p, PF.notes)}</span>
                  </div>
                )}
              </div>
            ))}
            <div className="text-xs text-slate-400 print:text-black pt-2">
              Drive safe, lift smart, and text the office when each job wraps. — Haul Yeah Moving
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
