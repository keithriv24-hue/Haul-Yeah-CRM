import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ChevronDown, ChevronUp, Truck, ShieldAlert, CalendarPlus, Star, Check, ClipboardList, Plus, AlertTriangle } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, Private, Money, EmptyState, LoadingRows, SearchBar, searchMatch, ConfirmDeleteButton } from "@/components/Bits";
import { PF, LF, f, PROJECT_STATUSES, TRUCKS, STATUS_PILL } from "@/lib/fields";
import { fmtDate, fmtMoney, calendarTemplate, smsLink, reviewSmsBody, mapsLink } from "@/lib/format";
import { useAuth } from "@/components/AuthGate";
import { listUsersApi, listTrucksApi, createAssignmentApi, apiErrorMessage } from "@/lib/api";
import JobsCalendar from "@/components/JobsCalendar";
import { ComplianceSection } from "@/components/ComplianceSection";

const NumField = ({ record, fieldId, label, testId, disabled = false }) => {
  const { updateRecord } = useApp();
  const [val, setVal] = useState(f(record, fieldId) ?? "");
  useEffect(() => setVal(f(record, fieldId) ?? ""), [record, fieldId]);
  const save = () => {
    const n = val === "" ? null : Number(val);
    if (n === (f(record, fieldId) ?? null)) return;
    updateRecord("projects", record.id, { [fieldId]: n }).catch(() => setVal(f(record, fieldId) ?? ""));
  };
  return (
    <label className="text-xs text-faint flex flex-col gap-1">
      {label}
      <Input data-testid={testId} type="number" className="h-8 w-24" value={val} disabled={disabled} onChange={(e) => setVal(e.target.value)} onBlur={save} />
    </label>
  );
};

const ProjectCard = ({ project }) => {
  const { updateRecord, deleteRecord, records, business } = useApp();
  const { role } = useAuth();
  const isOwner = (role || "owner") === "owner";
  const canEditOps = ["owner", "employee"].includes(role || "owner");
  const canEditCompliance = ["owner", "sales"].includes(role || "owner");
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
    <div data-testid="project-card" className="surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <Private className="font-display font-bold text-lg text-primary truncate block">{f(project, PF.jobName) || "Job"}</Private>
          <div className="text-xs text-faint mt-0.5">
            {fmtDate(f(project, PF.jobDate))} · {crew || "?"} crew × {hours || "?"} hrs · {f(project, PF.truck) || "No truck set"}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {isOwner && (
            <div className="text-right">
              <div className="text-sm font-bold text-primary">Quote: <Money value={quote || null} /></div>
              <div className={`text-xs font-semibold ${f(project, PF.depositCollected) ? "text-success" : "text-warning"}`}>
                {f(project, PF.depositCollected) ? "Deposit in" : "Deposit not in"}
              </div>
            </div>
          )}
          <Select value={status} onValueChange={(v) => updateRecord("projects", project.id, { [PF.status]: v }).catch(() => {})} disabled={!canEditOps}>
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
                ? "border-success/30 text-success hover:bg-success/10 hover:text-success"
                : "border-warning/30 text-warning hover:bg-warning/10 hover:text-warning"}`}
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
          {isOwner && (
            <ConfirmDeleteButton
              what={`the "${f(project, PF.jobName) || "job"}" project`}
              testId="project-delete-btn"
              onConfirm={() => deleteRecord("projects", project.id).then(() => toast.success("Project deleted.")).catch(() => {})}
            />
          )}
        </div>
      </div>

      {open && (
        <>
        <div className="mt-4 pt-4 border-t border-border grid md:grid-cols-2 gap-4">
          <div className="space-y-3">
            <div className="flex flex-wrap gap-3">
              <NumField record={project} fieldId={PF.crewSize} label="Crew size" testId="project-crew-input" disabled={!canEditOps} />
              <NumField record={project} fieldId={PF.estHours} label="Est. hours" testId="project-hours-input" disabled={!canEditOps} />
              {isOwner && <NumField record={project} fieldId={PF.quote} label="Quote ($)" testId="project-quote-input" />}
              {isOwner && <NumField record={project} fieldId={PF.finalRevenue} label="Final revenue ($)" testId="project-revenue-input" />}
            </div>
            <label className="text-xs text-faint flex flex-col gap-1 w-40">
              Truck
              <Select value={f(project, PF.truck) || ""} onValueChange={(v) => updateRecord("projects", project.id, { [PF.truck]: v }).catch(() => {})} disabled={!canEditOps}>
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
            <div className="text-xs text-ink-2 space-y-1">
              <div>
                From:{" "}
                {f(project, PF.fromAddr) ? (
                  <a
                    data-testid="project-from-map-link"
                    href={mapsLink(f(project, PF.fromAddr))}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary font-semibold underline decoration-dotted underline-offset-2 hover:text-accent-ink"
                  >
                    <Private>{f(project, PF.fromAddr)}</Private>
                  </a>
                ) : ("—")}
              </div>
              <div>
                To:{" "}
                {f(project, PF.toAddr) ? (
                  <a
                    data-testid="project-to-map-link"
                    href={mapsLink(f(project, PF.toAddr))}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary font-semibold underline decoration-dotted underline-offset-2 hover:text-accent-ink"
                  >
                    <Private>{f(project, PF.toAddr)}</Private>
                  </a>
                ) : ("—")}
              </div>
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
            <div className="border border-border bg-surface-sunk rounded-lg p-4 h-fit">
              <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-faint mb-2">
                <ShieldAlert className="w-3.5 h-3.5 text-destructive" /> Internal margin math — never show customers
              </div>
              <Private block>
                <div className="text-sm space-y-1 text-ink-2">
                  <div className="flex justify-between"><span>Crew cost ({crew} crew × {hours} hrs)</span><span>{fmtMoney(internal.crew_cost)}</span></div>
                  <div className="flex justify-between"><span>Revenue ({finalRev ? "final" : "quoted"})</span><span>{fmtMoney(finalRev || quote)}</span></div>
                  <div className={`flex justify-between font-bold pt-1 border-t border-border ${internal.margin >= 0 ? "text-success" : "text-destructive"}`}>
                    <span>Est. margin</span><span data-testid="project-margin">{fmtMoney(internal.margin)}</span>
                  </div>
                </div>
              </Private>
            </div>
          )}
        </div>
        <ComplianceSection projectId={project.id} canEdit={canEditCompliance} canOverride={isOwner} />
        </>
      )}
    </div>
  );
};

const blankProject = { jobName: "", jobDate: "", fromAddr: "", toAddr: "", crewSize: "", estHours: "", quote: "", truck: "", notes: "" };

const NewProjectDialog = ({ open, onOpenChange }) => {
  const { createRecord } = useApp();
  const [form, setForm] = useState(blankProject);
  const [saving, setSaving] = useState(false);
  const [users, setUsers] = useState([]);
  const [trucks, setTrucks] = useState([]);
  const [crewSel, setCrewSel] = useState({});
  const [warnings, setWarnings] = useState([]);
  const [createdId, setCreatedId] = useState(null);
  const set = (k) => (e) => setForm((s) => ({ ...s, [k]: e.target.value }));

  useEffect(() => {
    if (open) {
      setForm(blankProject);
      setCrewSel({});
      setWarnings([]);
      setCreatedId(null);
      listUsersApi().then(setUsers).catch(() => {});
      listTrucksApi().then(setTrucks).catch(() => {});
    }
  }, [open]);

  const crewUsers = users.filter((u) => (u.roles || [u.role]).includes("crew") && u.active);
  const toggleCrew = (uid) =>
    setCrewSel((s) => {
      const next = { ...s };
      if (next[uid]) delete next[uid];
      else next[uid] = "Helper";
      return next;
    });

  const save = async (ignoreWarnings = false) => {
    if (!form.jobName.trim()) {
      toast.error("Give the project a job name first.");
      return;
    }
    const crew = Object.entries(crewSel).map(([user_id, position]) => ({ user_id, position }));
    if (crew.length && !form.jobDate) {
      toast.error("Pick a job date so it can go on the crew's schedule.");
      return;
    }
    setSaving(true);
    try {
      let projId = createdId;
      if (!projId) {
        const rec = await createRecord("projects", {
          [PF.jobName]: form.jobName.trim(),
          [PF.status]: "Pending Deposit",
          [PF.jobDate]: form.jobDate,
          [PF.fromAddr]: form.fromAddr,
          [PF.toAddr]: form.toAddr,
          [PF.crewSize]: form.crewSize === "" ? null : Number(form.crewSize),
          [PF.estHours]: form.estHours === "" ? null : Number(form.estHours),
          [PF.quote]: form.quote === "" ? null : Number(form.quote),
          [PF.truck]: form.truck,
          [PF.notes]: form.notes,
        });
        projId = rec.id;
        setCreatedId(projId);
      }
      if (crew.length) {
        const truck = trucks.find((t) => t.name === form.truck);
        try {
          await createAssignmentApi({
            project_id: projId,
            job_name: form.jobName.trim(),
            job_date: form.jobDate,
            arrival_time: "",
            start_address: form.fromAddr,
            end_address: form.toAddr,
            truck_id: truck ? truck.id : null,
            job_size: "",
            crew,
            ignore_warnings: ignoreWarnings,
          });
        } catch (e) {
          const det = e?.response?.data?.detail;
          if (e?.response?.status === 409 && det?.warnings) {
            setWarnings(det.warnings);
            setSaving(false);
            return;
          }
          toast.error(`Project saved, but scheduling failed. ${apiErrorMessage(e)}`);
          setSaving(false);
          return;
        }
        toast.success("Project added — the crew's been notified and it's on their schedule.");
      } else {
        toast.success("Project added.");
      }
      onOpenChange(false);
    } catch {}
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="new-project-modal" className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">New project</DialogTitle>
          <DialogDescription>For jobs that didn't come through a booked lead — added straight to the board.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <Label>Job name *</Label>
            <Input data-testid="project-name-input" value={form.jobName} onChange={set("jobName")} placeholder="Smith move — 2BR" />
          </div>
          <div>
            <Label>Job date</Label>
            <Input data-testid="project-date-input" type="date" value={form.jobDate} onChange={set("jobDate")} />
          </div>
          <div>
            <Label>Truck</Label>
            <Select value={form.truck} onValueChange={(v) => setForm((s) => ({ ...s, truck: v }))}>
              <SelectTrigger data-testid="project-truck-new-select"><SelectValue placeholder="Pick truck" /></SelectTrigger>
              <SelectContent>
                {(trucks.filter((t) => t.active).length ? trucks.filter((t) => t.active).map((t) => t.name) : TRUCKS).map((t) => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="col-span-2">
            <Label>From address</Label>
            <Input data-testid="project-from-input" value={form.fromAddr} onChange={set("fromAddr")} />
          </div>
          <div className="col-span-2">
            <Label>To address</Label>
            <Input data-testid="project-to-input" value={form.toAddr} onChange={set("toAddr")} />
          </div>
          <div>
            <Label>Crew size</Label>
            <Input data-testid="project-crew-new-input" type="number" min="0" value={form.crewSize} onChange={set("crewSize")} />
          </div>
          <div>
            <Label>Est. hours</Label>
            <Input data-testid="project-hours-new-input" type="number" min="0" value={form.estHours} onChange={set("estHours")} />
          </div>
          <div>
            <Label>Quote ($)</Label>
            <Input data-testid="project-quote-new-input" type="number" min="0" value={form.quote} onChange={set("quote")} />
          </div>
          <div className="col-span-2">
            <Label>Notes</Label>
            <Textarea value={form.notes} onChange={set("notes")} rows={2} />
          </div>
          <div className="col-span-2">
            <Label>Put it on the crew's schedule (optional)</Label>
            <div className="space-y-2 mt-1.5">
              {crewUsers.length === 0 && <p className="text-xs text-faint">No active crew accounts yet — add them on the Crew page's Team tab.</p>}
              {crewUsers.map((u) => (
                <div key={u.id} data-testid="project-crew-row" className="flex items-center gap-3">
                  <Checkbox data-testid="project-crew-checkbox" id={`proj-crew-${u.id}`} checked={!!crewSel[u.id]} onCheckedChange={() => toggleCrew(u.id)} />
                  <label htmlFor={`proj-crew-${u.id}`} className="text-sm flex-1 cursor-pointer">{u.name}</label>
                  {crewSel[u.id] && (
                    <Select value={crewSel[u.id]} onValueChange={(v) => setCrewSel((s) => ({ ...s, [u.id]: v }))}>
                      <SelectTrigger data-testid="project-position-select" className="w-28 h-8 text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Driver">Driver</SelectItem>
                        <SelectItem value="Helper">Helper</SelectItem>
                      </SelectContent>
                    </Select>
                  )}
                </div>
              ))}
              {Object.keys(crewSel).length > 0 && (
                <p className="text-[11px] text-faint">They'll get notified and see it under My Jobs and their schedule.</p>
              )}
            </div>
          </div>
          {warnings.length > 0 && (
            <div data-testid="project-schedule-warnings" className="col-span-2 bg-warning/10 border border-warning/25 rounded-md p-3 space-y-1">
              <p className="text-xs font-bold text-warning flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> Hold on:</p>
              {warnings.map((w, i) => (
                <p key={i} className="text-xs text-warning">• {w}</p>
              ))}
            </div>
          )}
        </div>
        {warnings.length > 0 ? (
          <Button data-testid="project-force-schedule-btn" onClick={() => save(true)} disabled={saving} className="w-full gap-2 bg-warning hover:bg-warning">
            Schedule anyway
          </Button>
        ) : (
          <Button data-testid="project-save-btn" onClick={() => save(false)} disabled={saving} className="w-full gap-2 bg-accent hover:bg-accent-press">
            <Plus className="w-4 h-4" /> {saving ? "Saving…" : "Add project"}
          </Button>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default function Projects() {
  const { loadTable, records, tableState } = useApp();
  const { role } = useAuth();
  const isOwner = (role || "owner") === "owner";
  const [query, setQuery] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  useEffect(() => {
    loadTable("projects");
    if (isOwner) loadTable("leads");
  }, [loadTable, isOwner]);

  const projects = [...records("projects")]
    .filter((p) => searchMatch(query, f(p, PF.jobName), f(p, PF.fromAddr), f(p, PF.toAddr), f(p, PF.status), f(p, PF.truck), f(p, PF.notes)))
    .sort((a, b) => (f(a, PF.jobDate) || "9999").localeCompare(f(b, PF.jobDate) || "9999"));
  const { loading, error } = tableState("projects");

  return (
    <div data-testid="projects-page">
      <PageTitle
        title="Projects"
        subtitle="Your booked jobs, next date first."
        action={
          <div className="flex gap-2">
            <Button asChild data-testid="day-sheet-btn" variant="outline" className="gap-1.5">
              <Link to="/day-sheet"><ClipboardList className="w-4 h-4" /> Day sheet</Link>
            </Button>
            {isOwner && (
              <Button data-testid="new-project-btn" onClick={() => setNewOpen(true)} className="gap-1.5 bg-accent hover:bg-accent-press">
                <Plus className="w-4 h-4" /> New project
              </Button>
            )}
          </div>
        }
      />
      <InstructionBanner>
        {isOwner
          ? "Your booked jobs, next date first. Update the status as the day goes. Open Details for crew, truck, and margin."
          : "Your jobs, next date first. Update the status as the day goes. Open Details for addresses, crew, and truck."}
      </InstructionBanner>
      <JobsCalendar projects={records("projects")} />
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <h2 className="label-eyebrow">All jobs</h2>
        <SearchBar value={query} onChange={setQuery} placeholder="Search job, address, or truck…" testId="projects-search-input" className="sm:ml-auto sm:max-w-xs" />
      </div>
      {loading && !projects.length ? (
        <LoadingRows />
      ) : error && !projects.length ? (
        <EmptyState>{error}</EmptyState>
      ) : projects.length === 0 ? (
        <EmptyState>
          <Truck className="w-6 h-6 mx-auto mb-2 text-faint" />
          {query ? "No jobs match that search." : "No jobs yet. Book a lead from the Leads page to create one."}
        </EmptyState>
      ) : (
        <div className="space-y-3">{projects.map((p) => <ProjectCard key={p.id} project={p} />)}</div>
      )}
      {isOwner && <NewProjectDialog open={newOpen} onOpenChange={setNewOpen} />}
    </div>
  );
}
