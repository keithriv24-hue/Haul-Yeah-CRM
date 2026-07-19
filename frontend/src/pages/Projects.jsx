import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ChevronDown, ChevronUp, Truck, ShieldAlert, CalendarPlus, Star, Check, ClipboardList } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, Private, Money, EmptyState, LoadingRows } from "@/components/Bits";
import { PF, LF, f, PROJECT_STATUSES, TRUCKS, STATUS_PILL } from "@/lib/fields";
import { fmtDate, fmtMoney, calendarTemplate, smsLink, reviewSmsBody } from "@/lib/format";
import { useAuth } from "@/components/AuthGate";
import JobsCalendar from "@/components/JobsCalendar";

const NumField = ({ record, fieldId, label, testId }) => {
  const { updateRecord } = useApp();
  const [val, setVal] = useState(f(record, fieldId) ?? "");
  useEffect(() => setVal(f(record, fieldId) ?? ""), [record, fieldId]);
  const save = () => {
    const n = val === "" ? null : Number(val);
    if (n === (f(record, fieldId) ?? null)) return;
    updateRecord("projects", record.id, { [fieldId]: n }).catch(() => setVal(f(record, fieldId) ?? ""));
  };
  return (
    <label className="text-xs text-slate-500 flex flex-col gap-1">
      {label}
      <Input data-testid={testId} type="number" className="h-8 w-24" value={val} onChange={(e) => setVal(e.target.value)} onBlur={save} />
    </label>
  );
};

const ProjectCard = ({ project }) => {
  const { updateRecord, records, business } = useApp();
  const { role } = useAuth();
  const isOwner = (role || "owner") === "owner";
  const [open, setOpen] = useState(false);
  const status = f(project, PF.status) || "Pending Deposit";
  const crew = Number(f(project, PF.crewSize)) || 0;
  const hours = Number(f(project, PF.estHours)) || 0;
  const quote = Number(f(project, PF.quote)) || 0;
  const finalRev = Number(f(project, PF.finalRevenue)) || 0;
  const internal = project.internal || null;
  const linkedLead = isOwner ? records("leads").find((r) => r.id === (f(project, PF.lead) || [])[0]) : null;
  const custPhone = linkedLead ? f(linkedLead, LF.phone) : null;
  const custName = linkedLead ? f(linkedLead, LF.name) : "";
  const reviewAsked = /review asked/i.test(f(project, PF.notes) || "");

  const markReviewAsked = () => {
    if (reviewAsked) return;
    const old = f(project, PF.notes) || "";
    const line = `Review asked ${new Date().toLocaleDateString("en-US")}.`;
    updateRecord("projects", project.id, { [PF.notes]: old ? `${old}\n${line}` : line })
      .then(() => toast.success("Marked as asked — you won't text them twice."))
      .catch(() => {});
  };

  return (
    <div data-testid="project-card" className="bg-white border border-slate-200 rounded-lg p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <Private className="font-display font-bold text-lg text-[#1B2A4A] truncate block">{f(project, PF.jobName) || "Job"}</Private>
          <div className="text-xs text-slate-500 mt-0.5">
            {fmtDate(f(project, PF.jobDate))} · {crew || "?"} crew × {hours || "?"} hrs · {f(project, PF.truck) || "No truck set"}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {isOwner && (
            <div className="text-right">
              <div className="text-sm font-bold text-[#1B2A4A]">Quote: <Money value={quote || null} /></div>
              <div className={`text-xs font-semibold ${f(project, PF.depositCollected) ? "text-emerald-600" : "text-amber-600"}`}>
                {f(project, PF.depositCollected) ? "Deposit in" : "Deposit not in"}
              </div>
            </div>
          )}
          <Select value={status} onValueChange={(v) => updateRecord("projects", project.id, { [PF.status]: v }).catch(() => {})}>
            <SelectTrigger data-testid="project-status-select" className={`w-[150px] h-8 text-xs font-semibold border ${STATUS_PILL[status] || ""}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>{PROJECT_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
          </Select>
          {isOwner && status === "Completed" && (
            <Button
              data-testid="project-review-btn"
              asChild
              variant="outline"
              size="sm"
              className={`gap-1 text-xs ${reviewAsked
                ? "border-emerald-300 text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800"
                : "border-amber-300 text-amber-700 hover:bg-amber-50 hover:text-amber-800"}`}
              disabled={!custPhone}
              title={reviewAsked ? "You already asked — tapping texts them again" : custPhone ? "Text them a review ask" : "No phone on the linked lead"}
            >
              <a href={custPhone ? smsLink(custPhone, reviewSmsBody(custName, business.reviewLink)) : undefined} onClick={markReviewAsked}>
                {reviewAsked ? <Check className="w-3.5 h-3.5" /> : <Star className="w-3.5 h-3.5" />}
                {reviewAsked ? "Review asked" : "Ask for review"}
              </a>
            </Button>
          )}
          <Button data-testid="project-details-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => setOpen(!open)}>
            {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />} Details
          </Button>
        </div>
      </div>

      {open && (
        <div className="mt-4 pt-4 border-t border-slate-100 grid md:grid-cols-2 gap-4">
          <div className="space-y-3">
            <div className="flex flex-wrap gap-3">
              <NumField record={project} fieldId={PF.crewSize} label="Crew size" testId="project-crew-input" />
              <NumField record={project} fieldId={PF.estHours} label="Est. hours" testId="project-hours-input" />
              {isOwner && <NumField record={project} fieldId={PF.quote} label="Quote ($)" testId="project-quote-input" />}
              {isOwner && <NumField record={project} fieldId={PF.finalRevenue} label="Final revenue ($)" testId="project-revenue-input" />}
            </div>
            <label className="text-xs text-slate-500 flex flex-col gap-1 w-40">
              Truck
              <Select value={f(project, PF.truck) || ""} onValueChange={(v) => updateRecord("projects", project.id, { [PF.truck]: v }).catch(() => {})}>
                <SelectTrigger data-testid="project-truck-select" className="h-8 text-xs"><SelectValue placeholder="Pick truck" /></SelectTrigger>
                <SelectContent>{TRUCKS.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
            </label>
            {isOwner && (
              <label className="flex items-center gap-2 text-sm">
                <Checkbox
                  data-testid="project-deposit-checkbox"
                  checked={!!f(project, PF.depositCollected)}
                  onCheckedChange={(v) => updateRecord("projects", project.id, { [PF.depositCollected]: !!v }).catch(() => {})}
                />
                Deposit collected
              </label>
            )}
            <div className="text-xs text-slate-600 space-y-1">
              <div>From: <Private>{f(project, PF.fromAddr) || "—"}</Private></div>
              <div>To: <Private>{f(project, PF.toAddr) || "—"}</Private></div>
              {f(project, PF.notes) && <div className="whitespace-pre-wrap">Notes: {f(project, PF.notes)}</div>}
            </div>
            <Button asChild variant="outline" size="sm" className="gap-1 text-xs" data-testid="project-calendar-btn">
              <a
                href={calendarTemplate(f(project, PF.jobName) || "Moving job", f(project, PF.jobDate), `From: ${f(project, PF.fromAddr) || ""} To: ${f(project, PF.toAddr) || ""}`)}
                target="_blank"
                rel="noreferrer"
              >
                <CalendarPlus className="w-3.5 h-3.5" /> Add to Google Calendar
              </a>
            </Button>
          </div>
          {isOwner && internal && (
            <div className="border border-slate-200 bg-slate-50 rounded-lg p-4 h-fit">
              <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-500 mb-2">
                <ShieldAlert className="w-3.5 h-3.5 text-red-500" /> Internal margin math — never show customers
              </div>
              <Private block>
                <div className="text-sm space-y-1 text-slate-700">
                  <div className="flex justify-between"><span>Crew cost ({crew} crew × {hours} hrs)</span><span>{fmtMoney(internal.crew_cost)}</span></div>
                  <div className="flex justify-between"><span>Revenue ({finalRev ? "final" : "quoted"})</span><span>{fmtMoney(finalRev || quote)}</span></div>
                  <div className={`flex justify-between font-bold pt-1 border-t border-slate-200 ${internal.margin >= 0 ? "text-emerald-700" : "text-red-600"}`}>
                    <span>Est. margin</span><span data-testid="project-margin">{fmtMoney(internal.margin)}</span>
                  </div>
                </div>
              </Private>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default function Projects() {
  const { loadTable, records, tableState } = useApp();
  const { role } = useAuth();
  const isOwner = (role || "owner") === "owner";
  useEffect(() => {
    loadTable("projects");
    if (isOwner) loadTable("leads");
  }, [loadTable, isOwner]);

  const projects = [...records("projects")].sort((a, b) => (f(a, PF.jobDate) || "9999").localeCompare(f(b, PF.jobDate) || "9999"));
  const { loading, error } = tableState("projects");

  return (
    <div data-testid="projects-page">
      <PageTitle
        title="Projects"
        subtitle="Your booked jobs, next date first."
        action={
          <Button asChild data-testid="day-sheet-btn" variant="outline" className="gap-1.5">
            <Link to="/day-sheet"><ClipboardList className="w-4 h-4" /> Day sheet</Link>
          </Button>
        }
      />
      <InstructionBanner>
        {isOwner
          ? "Your booked jobs, next date first. Update the status as the day goes. Open Details for crew, truck, and margin."
          : "Your jobs, next date first. Update the status as the day goes. Open Details for addresses, crew, and truck."}
      </InstructionBanner>
      <JobsCalendar projects={records("projects")} />
      <h2 className="font-display font-bold text-lg text-[#1B2A4A] mb-3">All jobs</h2>
      {loading && !projects.length ? (
        <LoadingRows />
      ) : error && !projects.length ? (
        <EmptyState>{error}</EmptyState>
      ) : projects.length === 0 ? (
        <EmptyState>
          <Truck className="w-6 h-6 mx-auto mb-2 text-slate-400" />
          No jobs yet. Book a lead from the Leads page to create one.
        </EmptyState>
      ) : (
        <div className="space-y-3">{projects.map((p) => <ProjectCard key={p.id} project={p} />)}</div>
      )}
    </div>
  );
}
