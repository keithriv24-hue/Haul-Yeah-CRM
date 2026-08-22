import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Printer, Truck, MapPin, Users, Clock, StickyNote, Building2, DoorOpen } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, LoadingRows, Pill } from "@/components/Bits";
import { PF, f, leadAccess } from "@/lib/fields";
import { fmtDate, todayISO, mapsLink } from "@/lib/format";

const Row = ({ icon: Icon, label, value, href, testId }) => (
  <div className="flex items-start gap-2 text-sm">
    <Icon className="w-4 h-4 text-faint mt-0.5 shrink-0 print:text-black" />
    <span className="text-faint shrink-0 print:text-black">{label}:</span>
    {href ? (
      <a
        data-testid={testId}
        href={href}
        target="_blank"
        rel="noreferrer"
        className="font-semibold text-primary min-w-0 break-words underline decoration-dotted underline-offset-2 hover:text-accent-ink print:text-black print:no-underline"
      >
        {value}
      </a>
    ) : (
      <span className="font-semibold text-primary min-w-0 break-words print:text-black">{value}</span>
    )}
  </div>
);

export default function DaySheet() {
  const { loadTable, loadSchema, records, tableState, schemas } = useApp();
  const [date, setDate] = useState(todayISO());

  useEffect(() => {
    loadTable("projects");
    loadTable("leads");
    loadSchema("leads");
  }, [loadTable, loadSchema]);

  const leadFor = (p) => {
    const ids = f(p, PF.lead) || [];
    return ids.length ? records("leads").find((l) => l.id === ids[0]) : null;
  };

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
          <Button data-testid="day-sheet-print-btn" onClick={() => window.print()} className="gap-1.5 bg-accent hover:bg-accent-press">
            <Printer className="w-4 h-4" /> Print
          </Button>
        </div>
      </div>

      <div className="surface p-6 print:border-0 print:p-0" data-testid="day-sheet">
        <div className="flex items-center justify-between border-b border-border pb-4 mb-5">
          <div>
            <div className="font-display text-2xl font-extrabold text-primary tnum print:text-black">Haul Yeah Moving — Crew Day Sheet</div>
            <div className="text-sm text-faint print:text-black" data-testid="day-sheet-date-label">{fmtDate(date)}</div>
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
            {jobs.map((p, idx) => {
              const lead = leadFor(p);
              const access = lead ? leadAccess(lead, schemas.leads) : { pickup: "", dropoff: "" };
              return (
              <div key={p.id} data-testid="day-sheet-job" className="border border-border rounded-lg p-4 print:break-inside-avoid">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                  <div className="font-display font-bold text-lg text-primary print:text-black">
                    Job {idx + 1}: {f(p, PF.jobName) || "Unnamed job"}
                  </div>
                  <Pill value={f(p, PF.status) || "—"} />
                </div>
                <div className="grid sm:grid-cols-2 gap-x-6 gap-y-2">
                  <Row icon={MapPin} label="From" value={f(p, PF.fromAddr) || "—"} href={f(p, PF.fromAddr) ? mapsLink(f(p, PF.fromAddr)) : null} testId="day-sheet-from-link" />
                  <Row icon={MapPin} label="To" value={f(p, PF.toAddr) || "—"} href={f(p, PF.toAddr) ? mapsLink(f(p, PF.toAddr)) : null} testId="day-sheet-to-link" />
                  {access.pickup && <Row icon={Building2} label="Pickup access" value={access.pickup} testId="day-sheet-pickup-access" />}
                  {access.dropoff && <Row icon={DoorOpen} label="Drop-off access" value={access.dropoff} testId="day-sheet-dropoff-access" />}
                  <Row icon={Truck} label="Truck" value={f(p, PF.truck) || "—"} />
                  <Row icon={Users} label="Crew" value={f(p, PF.crewSize) ? `${f(p, PF.crewSize)} movers` : "—"} />
                  <Row icon={Clock} label="Est. hours" value={f(p, PF.estHours) ? `${f(p, PF.estHours)} hrs` : "—"} />
                  <Row icon={Clock} label="Start time" value="____________" />
                </div>
                {f(p, PF.notes) && (
                  <div className="flex items-start gap-2 text-sm mt-3 border-t border-border pt-3">
                    <StickyNote className="w-4 h-4 text-faint mt-0.5 shrink-0 print:text-black" />
                    <span className="whitespace-pre-wrap break-words print:text-black">{f(p, PF.notes)}</span>
                  </div>
                )}
              </div>
              );
            })}
            <div className="text-xs text-faint print:text-black pt-2">
              Drive safe, lift smart, and text the office when each job wraps. — Haul Yeah Moving
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
