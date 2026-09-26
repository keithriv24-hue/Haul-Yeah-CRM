import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Truck, Plus, ClipboardList, Users, ShieldCheck, ShieldAlert, ShieldQuestion, Send, ChevronRight, AlertTriangle, RefreshCw } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/components/AuthGate";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, EmptyState, LoadingRows, SearchBar, searchMatch } from "@/components/Bits";
import { PF, PROJECT_STATUSES, TRUCKS, STATUS_PILL } from "@/lib/fields";
import { fmtDate, fmtMoney } from "@/lib/format";
import { jobMgmtListApi, updateRecordApi, listUsersApi, listTrucksApi, createAssignmentApi, apiErrorMessage } from "@/lib/api";

const g = (job, id) => job.fields?.[id];

const LIFECYCLE = [
  { key: "upcoming", label: "Upcoming", statuses: ["Pending Deposit", "Scheduled"] },
  { key: "in_progress", label: "In Progress", statuses: ["In Progress"] },
  { key: "completed", label: "Completed", statuses: ["Completed"] },
  { key: "cancelled", label: "Cancelled", statuses: ["Cancelled"] },
  { key: "all", label: "All Jobs", statuses: null },
];

const localDate = (offset = 0) => {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const weekBounds = () => {
  const d = new Date();
  const start = new Date(d); start.setDate(d.getDate() - d.getDay());
  const end = new Date(start); end.setDate(start.getDate() + 6);
  const iso = (x) => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
  return [iso(start), iso(end)];
};
const dateInRange = (jobDate, mode) => {
  const jd = (jobDate || "").slice(0, 10);
  if (!mode || mode === "all") return true;
  if (!jd) return false;
  if (mode === "today") return jd === localDate(0);
  if (mode === "tomorrow") return jd === localDate(1);
  if (mode === "week") { const [s, e] = weekBounds(); return jd >= s && jd <= e; }
  if (mode === "month") return jd.slice(0, 7) === localDate(0).slice(0, 7);
  return true;
};

const COMPLIANCE_CHIP = {
  compliant: { tone: "bg-success/12 text-success border-success/30", Icon: ShieldCheck, label: "Compliant" },
  warning: { tone: "bg-warning/12 text-warning border-warning/30", Icon: ShieldAlert, label: "Warning" },
  failed: { tone: "bg-destructive/12 text-destructive border-destructive/30", Icon: ShieldAlert, label: "Failed" },
  overridden: { tone: "bg-primary/10 text-primary border-primary/30", Icon: ShieldCheck, label: "Overridden" },
  unknown: { tone: "bg-surface-sunk text-faint border-border", Icon: ShieldQuestion, label: "Not checked" },
};

const ComplianceChip = ({ status }) => {
  const c = COMPLIANCE_CHIP[status] || COMPLIANCE_CHIP.unknown;
  return (
    <Badge variant="outline" data-testid="job-compliance-chip" className={`text-[10px] gap-1 ${c.tone}`}>
      <c.Icon className="w-3 h-3" /> {c.label}
    </Badge>
  );
};

const PaymentChip = ({ payment }) => {
  const full = payment?.full === "paid";
  const dep = payment?.deposit === "paid";
  const label = full ? "Paid in full" : dep ? "Deposit paid" : payment?.deposit === "pending" ? "Payment pending" : "Unpaid";
  const tone = full ? "bg-success/12 text-success border-success/30"
    : dep ? "bg-info/12 text-info border-info/30"
    : "bg-surface-sunk text-faint border-border";
  return <Badge variant="outline" data-testid="job-payment-chip" className={`text-[10px] ${tone}`}>{label}</Badge>;
};

const JobRow = ({ job, canSeeMoney, canEditStatus, onStatusChange }) => {
  const m = job.mgmt || {};
  const status = g(job, PF.status) || "Pending Deposit";
  const quote = g(job, PF.quote);
  return (
    <div data-testid="job-row" className="surface p-4 hover:border-accent/40 transition-colors">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <Link to={`/projects/${job.id}`} data-testid={`job-open-${job.id}`} className="font-display font-bold text-primary hover:text-accent-ink truncate">
              {g(job, PF.jobName) || m.customer?.name || "Job"}
            </Link>
            {m.invoice_number && <span className="text-xs text-faint">#{m.invoice_number}</span>}
          </div>
          <div className="text-xs text-faint mt-0.5">
            {m.customer?.name || "—"}{m.customer?.phone ? ` · ${m.customer.phone}` : ""} · {fmtDate(g(job, PF.jobDate))}
          </div>
          <div className="flex flex-wrap items-center gap-1.5 mt-2">
            <Badge variant="outline" className={`text-[10px] ${STATUS_PILL[status] || ""}`}>{status}</Badge>
            <PaymentChip payment={m.payment} />
            <ComplianceChip status={m.compliance} />
            {m.has_portal && <Badge variant="outline" className="text-[10px] gap-1 bg-accent/10 text-accent-ink border-accent/25"><Send className="w-3 h-3" /> Customer page</Badge>}
            {m.paperwork_alert?.active && (
              <Badge variant="outline" data-testid="job-paperwork-flag"
                className={`text-[10px] gap-1 ${m.paperwork_alert.level === "red" ? "bg-red-500/15 text-red-600 border-red-500/40 animate-pulse" : "bg-warning/12 text-warning border-warning/40"}`}>
                <AlertTriangle className="w-3 h-3" /> Paperwork {m.paperwork_alert.level === "red" ? "< 24h" : "due"}
              </Badge>
            )}
            {m.portal_review && <Badge variant="outline" className="text-[10px] bg-warning/12 text-warning border-warning/30">{m.portal_review.rating}★</Badge>}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-sm text-ink-2">
            <span className="inline-flex items-center gap-1.5"><Users className="w-3.5 h-3.5 text-faint" />{m.crew_count ? m.crew.map((c) => c.name?.split(" ")[0]).join(", ") : <span className="text-faint">No crew</span>}</span>
            <span className="inline-flex items-center gap-1.5"><Truck className="w-3.5 h-3.5 text-faint" />{m.truck_name || <span className="text-faint">No truck</span>}</span>
            {canSeeMoney && quote != null && <span className="font-semibold text-primary">{fmtMoney(quote)}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {canEditStatus && (
            <Select value={status} onValueChange={(v) => onStatusChange(job.id, v)}>
              <SelectTrigger data-testid="job-row-status-select" className={`w-[140px] h-8 text-xs font-semibold border ${STATUS_PILL[status] || ""}`}><SelectValue /></SelectTrigger>
              <SelectContent>{PROJECT_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
            </Select>
          )}
          <Button data-testid="job-open-btn" asChild variant="outline" size="sm" className="gap-1">
            <Link to={`/projects/${job.id}`}>Open <ChevronRight className="w-3.5 h-3.5" /></Link>
          </Button>
        </div>
      </div>
    </div>
  );
};

const blankProject = { jobName: "", jobDate: "", fromAddr: "", toAddr: "", crewSize: "", estHours: "", quote: "", truck: "", notes: "" };

const NewProjectDialog = ({ open, onOpenChange, onSaved }) => {
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
      setForm(blankProject); setCrewSel({}); setWarnings([]); setCreatedId(null);
      listUsersApi().then(setUsers).catch(() => {});
      listTrucksApi().then(setTrucks).catch(() => {});
    }
  }, [open]);

  const crewUsers = users.filter((u) => (u.roles || [u.role]).includes("crew") && u.active);
  const toggleCrew = (uid) => setCrewSel((s) => { const n = { ...s }; if (n[uid]) delete n[uid]; else n[uid] = "Helper"; return n; });

  const save = async (ignoreWarnings = false) => {
    if (!form.jobName.trim()) { toast.error("Give the project a job name first."); return; }
    const crew = Object.entries(crewSel).map(([user_id, position]) => ({ user_id, position }));
    if (crew.length && !form.jobDate) { toast.error("Pick a job date so it can go on the crew's schedule."); return; }
    setSaving(true);
    try {
      let projId = createdId;
      if (!projId) {
        const rec = await createRecord("projects", {
          [PF.jobName]: form.jobName.trim(), [PF.status]: "Pending Deposit", [PF.jobDate]: form.jobDate,
          [PF.fromAddr]: form.fromAddr, [PF.toAddr]: form.toAddr,
          [PF.crewSize]: form.crewSize === "" ? null : Number(form.crewSize),
          [PF.estHours]: form.estHours === "" ? null : Number(form.estHours),
          [PF.quote]: form.quote === "" ? null : Number(form.quote), [PF.truck]: form.truck, [PF.notes]: form.notes,
        });
        projId = rec.id; setCreatedId(projId);
      }
      if (crew.length) {
        const truck = trucks.find((t) => t.name === form.truck);
        try {
          await createAssignmentApi({
            project_id: projId, job_name: form.jobName.trim(), job_date: form.jobDate, arrival_time: "",
            start_address: form.fromAddr, end_address: form.toAddr, truck_id: truck ? truck.id : null,
            job_size: "", crew, ignore_warnings: ignoreWarnings,
          });
        } catch (e) {
          const det = e?.response?.data?.detail;
          if (e?.response?.status === 409 && det?.warnings) { setWarnings(det.warnings); setSaving(false); return; }
          toast.error(`Project saved, but scheduling failed. ${apiErrorMessage(e)}`); setSaving(false); return;
        }
        toast.success("Project added — the crew's been notified and it's on their schedule.");
      } else {
        toast.success("Project added.");
      }
      onOpenChange(false);
      onSaved && onSaved();
    } catch { /* handled in createRecord */ }
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="new-project-modal" className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">New job</DialogTitle>
          <DialogDescription>For jobs that didn't come through a booked lead — added straight to the board.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2"><Label>Job name *</Label><Input data-testid="project-name-input" value={form.jobName} onChange={set("jobName")} placeholder="Smith move — 2BR" /></div>
          <div><Label>Job date</Label><Input data-testid="project-date-input" type="date" value={form.jobDate} onChange={set("jobDate")} /></div>
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
          <div className="col-span-2"><Label>From address</Label><Input data-testid="project-from-input" value={form.fromAddr} onChange={set("fromAddr")} /></div>
          <div className="col-span-2"><Label>To address</Label><Input data-testid="project-to-input" value={form.toAddr} onChange={set("toAddr")} /></div>
          <div><Label>Crew size</Label><Input data-testid="project-crew-new-input" type="number" min="0" value={form.crewSize} onChange={set("crewSize")} /></div>
          <div><Label>Est. hours</Label><Input data-testid="project-hours-new-input" type="number" min="0" value={form.estHours} onChange={set("estHours")} /></div>
          <div><Label>Quote ($)</Label><Input data-testid="project-quote-new-input" type="number" min="0" value={form.quote} onChange={set("quote")} /></div>
          <div className="col-span-2"><Label>Notes</Label><Textarea value={form.notes} onChange={set("notes")} rows={2} /></div>
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
                      <SelectContent><SelectItem value="Driver">Driver</SelectItem><SelectItem value="Helper">Helper</SelectItem></SelectContent>
                    </Select>
                  )}
                </div>
              ))}
            </div>
          </div>
          {warnings.length > 0 && (
            <div data-testid="project-schedule-warnings" className="col-span-2 bg-warning/10 border border-warning/25 rounded-md p-3 space-y-1">
              <p className="text-xs font-bold text-warning flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> Hold on:</p>
              {warnings.map((w, i) => <p key={i} className="text-xs text-warning">• {w}</p>)}
            </div>
          )}
        </div>
        {warnings.length > 0 ? (
          <Button data-testid="project-force-schedule-btn" onClick={() => save(true)} disabled={saving} className="w-full gap-2 bg-warning hover:bg-warning">Schedule anyway</Button>
        ) : (
          <Button data-testid="project-save-btn" onClick={() => save(false)} disabled={saving} className="w-full gap-2 bg-accent hover:bg-accent-press">
            <Plus className="w-4 h-4" /> {saving ? "Saving…" : "Add job"}
          </Button>
        )}
      </DialogContent>
    </Dialog>
  );
};

const FILTER_SELECT = "h-8 text-xs w-auto min-w-[120px]";

export default function Projects() {
  const { role } = useAuth();
  const isOwner = (role || "owner") === "owner";
  const canEditStatus = ["owner", "employee"].includes(role || "owner");
  const [resp, setResp] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("upcoming");
  const [query, setQuery] = useState("");
  const [dateFilter, setDateFilter] = useState("all");
  const [payFilter, setPayFilter] = useState("all");
  const [compFilter, setCompFilter] = useState("all");
  const [crewFilter, setCrewFilter] = useState("all");
  const [newOpen, setNewOpen] = useState(false);

  const load = useCallback((refresh = 0) => {
    setLoading(true);
    jobMgmtListApi(refresh)
      .then((d) => { setResp(d); setError(null); })
      .catch((e) => setError(apiErrorMessage(e)))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const jobs = useMemo(() => resp?.jobs || [], [resp]);
  const canSeeMoney = !!resp?.can_see_money;

  const counts = useMemo(() => {
    const c = {};
    LIFECYCLE.forEach((t) => {
      c[t.key] = t.statuses ? jobs.filter((j) => t.statuses.includes(g(j, PF.status))).length : jobs.length;
    });
    return c;
  }, [jobs]);

  const crewNames = useMemo(() => {
    const s = new Set();
    jobs.forEach((j) => (j.mgmt?.crew || []).forEach((c) => c.name && s.add(c.name)));
    return [...s].sort();
  }, [jobs]);

  const statusChange = async (id, v) => {
    setResp((r) => ({ ...r, jobs: r.jobs.map((j) => (j.id === id ? { ...j, fields: { ...j.fields, [PF.status]: v } } : j)) }));
    try {
      await updateRecordApi("projects", id, { [PF.status]: v });
      toast.success(`Moved to ${v}.`);
    } catch (e) {
      toast.error(`Couldn't update status. ${apiErrorMessage(e)}`);
      load();
    }
  };

  const shown = useMemo(() => {
    const life = LIFECYCLE.find((t) => t.key === tab);
    return jobs.filter((j) => {
      if (life?.statuses && !life.statuses.includes(g(j, PF.status))) return false;
      if (!dateInRange(g(j, PF.jobDate), dateFilter)) return false;
      const pay = j.mgmt?.payment || {};
      if (payFilter === "full" && pay.full !== "paid") return false;
      if (payFilter === "deposit" && !(pay.deposit === "paid" || pay.full === "paid")) return false;
      if (payFilter === "unpaid" && (pay.deposit === "paid" || pay.full === "paid")) return false;
      if (compFilter !== "all" && (j.mgmt?.compliance || "unknown") !== compFilter) return false;
      if (crewFilter !== "all" && !(j.mgmt?.crew || []).some((c) => c.name === crewFilter)) return false;
      const m = j.mgmt || {};
      return searchMatch(query, g(j, PF.jobName), m.customer?.name, m.customer?.phone, m.customer?.email,
        m.invoice_number, g(j, PF.fromAddr), g(j, PF.toAddr), g(j, PF.jobDate), ...(m.crew || []).map((c) => c.name));
    });
  }, [jobs, tab, dateFilter, payFilter, compFilter, crewFilter, query]);

  return (
    <div data-testid="projects-page">
      <PageTitle
        title="Jobs"
        subtitle="Every job — upcoming, happening now, and done. Open any one to see the whole story."
        action={
          <div className="flex gap-2">
            <Button data-testid="jobs-refresh-btn" variant="outline" className="gap-1.5" onClick={() => load(1)}><RefreshCw className="w-4 h-4" /> Refresh</Button>
            <Button asChild data-testid="day-sheet-btn" variant="outline" className="gap-1.5"><Link to="/day-sheet"><ClipboardList className="w-4 h-4" /> Day sheet</Link></Button>
            {isOwner && <Button data-testid="new-project-btn" onClick={() => setNewOpen(true)} className="gap-1.5 bg-accent hover:bg-accent-press"><Plus className="w-4 h-4" /> New job</Button>}
          </div>
        }
      />
      <InstructionBanner>Find any job by status, date, crew, payment, or compliance. Tap a job to review crew, timing, money, compliance, quality, and its customer page.</InstructionBanner>

      {/* Lifecycle tabs */}
      <div data-testid="jobs-lifecycle-tabs" className="flex flex-wrap gap-1.5 mb-3">
        {LIFECYCLE.map((t) => (
          <button key={t.key} data-testid={`jobs-tab-${t.key}`} onClick={() => setTab(t.key)}
            className={`px-3 py-1.5 rounded-full text-sm font-semibold border transition-colors ${tab === t.key ? "bg-primary text-white border-primary" : "bg-surface text-ink-2 border-border hover:border-accent/40"}`}>
            {t.label} <span className={tab === t.key ? "text-white/70" : "text-faint"}>({counts[t.key] ?? 0})</span>
          </button>
        ))}
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <SearchBar value={query} onChange={setQuery} placeholder="Search customer, phone, email, job #, address, crew…" testId="projects-search-input" className="sm:max-w-xs" />
        <Select value={dateFilter} onValueChange={setDateFilter}>
          <SelectTrigger data-testid="jobs-filter-date" className={FILTER_SELECT}><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any date</SelectItem><SelectItem value="today">Today</SelectItem>
            <SelectItem value="tomorrow">Tomorrow</SelectItem><SelectItem value="week">This week</SelectItem>
            <SelectItem value="month">This month</SelectItem>
          </SelectContent>
        </Select>
        <Select value={payFilter} onValueChange={setPayFilter}>
          <SelectTrigger data-testid="jobs-filter-payment" className={FILTER_SELECT}><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any payment</SelectItem><SelectItem value="deposit">Deposit paid</SelectItem>
            <SelectItem value="full">Paid in full</SelectItem><SelectItem value="unpaid">Unpaid</SelectItem>
          </SelectContent>
        </Select>
        <Select value={compFilter} onValueChange={setCompFilter}>
          <SelectTrigger data-testid="jobs-filter-compliance" className={FILTER_SELECT}><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any compliance</SelectItem><SelectItem value="compliant">Compliant</SelectItem>
            <SelectItem value="warning">Warning</SelectItem><SelectItem value="failed">Failed</SelectItem>
            <SelectItem value="overridden">Overridden</SelectItem><SelectItem value="unknown">Not checked</SelectItem>
          </SelectContent>
        </Select>
        {crewNames.length > 0 && (
          <Select value={crewFilter} onValueChange={setCrewFilter}>
            <SelectTrigger data-testid="jobs-filter-crew" className={FILTER_SELECT}><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Any crew</SelectItem>
              {crewNames.map((n) => <SelectItem key={n} value={n}>{n}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
      </div>

      {loading && !resp ? (
        <LoadingRows />
      ) : error && !jobs.length ? (
        <EmptyState><Truck className="w-6 h-6 mx-auto mb-2 text-faint" />{error}</EmptyState>
      ) : shown.length === 0 ? (
        <EmptyState>
          <Truck className="w-6 h-6 mx-auto mb-2 text-faint" />
          {jobs.length === 0 ? "No jobs yet. Book a lead from the Leads page to create one." : "No jobs match these filters."}
        </EmptyState>
      ) : (
        <div className="space-y-3" data-testid="jobs-list">
          {shown.map((j) => (
            <JobRow key={j.id} job={j} canSeeMoney={canSeeMoney} canEditStatus={canEditStatus} onStatusChange={statusChange} />
          ))}
        </div>
      )}

      {isOwner && <NewProjectDialog open={newOpen} onOpenChange={setNewOpen} onSaved={() => load(1)} />}
    </div>
  );
}
