import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  ChevronLeft, ChevronRight, MapPin, Truck, CalendarPlus, AlertTriangle, GripVertical, X, Clock, History,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { PageTitle, InstructionBanner, KpiCard } from "@/components/Bits";
import { AssignmentModal } from "@/components/crew/AssignmentModal";
import { JobTimeline } from "@/components/JobTimeline";
import { JobChecklists } from "@/components/JobChecklists";
import { dispatchBoardApi, updateAssignmentApi, listUsersApi, listTrucksApi, apiErrorMessage } from "@/lib/api";
import { fmtMoney, fmtDate, mapsLink } from "@/lib/format";

const todayET = () => new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });

const EXEC_STYLE = {
  Assigned: "bg-surface-sunk text-ink-2 border-border-strong",
  "En Route": "bg-info/12 text-info border-info/30",
  Arrived: "bg-warning/12 text-warning border-warning/30",
  "In Progress": "bg-primary/10 text-primary border-primary/25",
  Complete: "bg-success/12 text-success border-success/30",
};

const payloadFrom = (a, patch = {}) => ({
  project_id: a.project_id || null,
  job_name: a.job_name,
  job_date: a.job_date,
  arrival_time: a.arrival_time || "",
  start_address: a.start_address || "",
  end_address: a.end_address || "",
  truck_id: a.truck_id || null,
  job_size: a.job_size || "",
  crew: (a.crew || []).map((c) => ({ user_id: c.user_id, position: c.position })),
  ignore_warnings: false,
  ...patch,
});

const shiftDay = (iso, delta) => {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + delta);
  return d.toISOString().slice(0, 10);
};

const ProgressRing = ({ done, total }) => {
  const pct = total ? done / total : 0;
  const r = 8;
  const c = 2 * Math.PI * r;
  return (
    <span data-testid="job-checklist-ring" className="inline-flex items-center gap-1" title={`${done}/${total} checklist items done`}>
      <svg width="22" height="22" viewBox="0 0 22 22" className="-rotate-90">
        <circle cx="11" cy="11" r={r} fill="none" stroke="#e2e8f0" strokeWidth="3" />
        <circle cx="11" cy="11" r={r} fill="none" stroke={pct === 1 ? "#10b981" : "#E8743B"} strokeWidth="3"
          strokeDasharray={c} strokeDashoffset={c * (1 - pct)} strokeLinecap="round" />
      </svg>
      <span className="text-[10px] font-bold text-faint">{done}/{total}</span>
    </span>
  );
};

export default function Dispatch() {
  const [date, setDate] = useState(todayET());
  const [board, setBoard] = useState(null);
  const [users, setUsers] = useState([]);
  const [trucks, setTrucks] = useState([]);
  const [dragOver, setDragOver] = useState(null);
  const [pending, setPending] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    dispatchBoardApi(date).then(setBoard).catch((e) => toast.error(apiErrorMessage(e)));
  }, [date]);

  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    listUsersApi().then(setUsers).catch(() => {});
    listTrucksApi().then(setTrucks).catch(() => {});
  }, []);

  const apply = async (assignment, patch, andThen = null) => {
    setBusy(true);
    try {
      await updateAssignmentApi(assignment.id, payloadFrom(assignment, patch));
      if (andThen) await andThen();
      load();
    } catch (e) {
      const det = e?.response?.data?.detail;
      if (e?.response?.status === 409 && det?.warnings) {
        setPending({ assignment, patch, andThen, warnings: det.warnings });
      } else {
        toast.error(apiErrorMessage(e));
      }
    }
    setBusy(false);
  };

  const forcePending = async () => {
    const { assignment, patch, andThen } = pending;
    setPending(null);
    setBusy(true);
    try {
      await updateAssignmentApi(assignment.id, payloadFrom(assignment, { ...patch, ignore_warnings: true }));
      if (andThen) await andThen();
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  const onDrop = (target) => (e) => {
    e.preventDefault();
    setDragOver(null);
    let data;
    try {
      data = JSON.parse(e.dataTransfer.getData("text/plain"));
    } catch {
      return;
    }
    if (data.kind === "crew") {
      if ((target.crew || []).some((c) => c.user_id === data.user_id)) {
        if (data.from !== target.id) toast.info(`${data.name} is already on this job.`);
        return;
      }
      const newCrew = [...(target.crew || []).map((c) => ({ user_id: c.user_id, position: c.position })),
        { user_id: data.user_id, position: data.position || "Helper" }];
      const source = data.from ? (board?.assignments || []).find((a) => a.id === data.from) : null;
      const andThen = source
        ? () => updateAssignmentApi(source.id, payloadFrom(source, {
            crew: (source.crew || []).filter((c) => c.user_id !== data.user_id).map((c) => ({ user_id: c.user_id, position: c.position })),
            ignore_warnings: true,
          }))
        : null;
      apply(target, { crew: newCrew }, andThen);
    } else if (data.kind === "truck") {
      if (target.truck_id === data.truck_id) return;
      apply(target, { truck_id: data.truck_id });
    }
  };

  const removeCrew = (a, userId) =>
    apply(a, { crew: (a.crew || []).filter((c) => c.user_id !== userId).map((c) => ({ user_id: c.user_id, position: c.position })) });

  const togglePosition = (a, userId) =>
    apply(a, {
      crew: (a.crew || []).map((c) =>
        c.user_id === userId ? { user_id: c.user_id, position: c.position === "Driver" ? "Helper" : "Driver" } : { user_id: c.user_id, position: c.position }),
    });

  const removeTruck = (a) => apply(a, { truck_id: null });

  const dragPayload = (obj) => (e) => {
    e.dataTransfer.setData("text/plain", JSON.stringify(obj));
    e.dataTransfer.effectAllowed = "move";
  };

  const counts = board?.counts || {};
  const assignments = board?.assignments || [];

  return (
    <div data-testid="dispatch-page" className="pb-8">
      <PageTitle
        title="Dispatch"
        subtitle="Run the day from one board — drag crew and trucks straight onto jobs."
        action={
          <Button data-testid="dispatch-assign-btn" className="gap-1.5 bg-accent hover:bg-accent-press" onClick={() => { setEditing(null); setModalOpen(true); }}>
            <CalendarPlus className="w-4 h-4" /> Assign a job
          </Button>
        }
      />
      <InstructionBanner testId="dispatch-banner">
        Drag a crew member or truck from the right panel onto a job card. Click a crew chip's role to flip Driver/Helper. Status chips update live as the crew works.
      </InstructionBanner>

      <div className="flex items-center gap-2 mb-4">
        <Button data-testid="dispatch-date-prev" variant="outline" size="sm" className="h-8 px-2" onClick={() => setDate((d) => shiftDay(d, -1))}>
          <ChevronLeft className="w-4 h-4" />
        </Button>
        <span data-testid="dispatch-date-label" className="font-display font-bold text-primary min-w-[150px] text-center">
          {fmtDate(date)}{board?.is_today ? " — today" : ""}
        </span>
        <Button data-testid="dispatch-date-next" variant="outline" size="sm" className="h-8 px-2" onClick={() => setDate((d) => shiftDay(d, 1))}>
          <ChevronRight className="w-4 h-4" />
        </Button>
        {date !== todayET() && (
          <Button data-testid="dispatch-date-today" variant="outline" size="sm" className="h-8 text-xs" onClick={() => setDate(todayET())}>
            Jump to today
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-5">
        <KpiCard testId="dispatch-kpi-revenue" label="Revenue today" value={fmtMoney(board?.revenue_today || 0)} sub="Paid Square invoices" />
        <KpiCard testId="dispatch-kpi-jobs" label="Jobs" value={counts.total ?? "—"} sub={`${counts.needs_crew || 0} need crew`} isPrivate={false} />
        <KpiCard testId="dispatch-kpi-active" label="Active now" value={counts.active ?? "—"} sub="En route / on site" isPrivate={false} />
        <KpiCard testId="dispatch-kpi-complete" label="Complete" value={counts.complete ?? "—"} sub="Done today" isPrivate={false} />
        <KpiCard testId="dispatch-kpi-behind" label="Behind schedule" value={counts.behind ?? "—"} sub="15+ min past arrival" isPrivate={false} alert={(counts.behind || 0) > 0} />
      </div>

      <div className="grid lg:grid-cols-[minmax(0,1fr)_280px] gap-4 items-start">
        <div className="space-y-3">
          {board === null && <p className="text-sm text-faint">Loading the board…</p>}
          {board !== null && assignments.length === 0 && (
            <p data-testid="dispatch-empty" className="text-sm text-faint bg-surface border border-dashed border-border rounded-lg p-8 text-center">
              Nothing scheduled for this day. Hit "Assign a job" to put a move on the board.
            </p>
          )}
          {assignments.map((a) => (
            <div
              key={a.id}
              data-testid="dispatch-job-card"
              onDragOver={(e) => { e.preventDefault(); setDragOver(a.id); }}
              onDragLeave={() => setDragOver((v) => (v === a.id ? null : v))}
              onDrop={onDrop(a)}
              className={`bg-surface rounded-lg border p-4 transition-colors ${dragOver === a.id ? "border-accent ring-2 ring-accent/40" : "border-border"}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-bold text-primary">{a.job_name}</p>
                  <p className="text-xs text-faint flex items-center gap-1">
                    <Clock className="w-3 h-3" /> {a.arrival_time ? `Arrive ${a.arrival_time}` : "No arrival time"}
                    {a.job_size && <span className="text-faint">· {a.job_size}</span>}
                  </p>
                </div>
                <div className="flex items-center gap-1.5">
                  {a.behind && (
                    <Badge data-testid="dispatch-behind-badge" className="text-[10px] bg-destructive text-white border-destructive animate-pulse gap-1">
                      <AlertTriangle className="w-3 h-3" /> Behind
                    </Badge>
                  )}
                  {a.clocked_in > 0 && (
                    <Badge data-testid="dispatch-clocked-badge" variant="outline" className="text-[10px] bg-success/10 text-success border-success/30 gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" /> {a.clocked_in} on the clock
                    </Badge>
                  )}
                  <Badge data-testid="dispatch-status-chip" variant="outline" className={`text-[10px] ${EXEC_STYLE[a.exec_status] || EXEC_STYLE.Assigned}`}>
                    {a.exec_status}
                  </Badge>
                </div>
              </div>
              {(a.start_address || a.end_address) && (
                <div className="mt-2 text-xs text-faint space-y-0.5">
                  {a.start_address && (
                    <a href={mapsLink(a.start_address)} target="_blank" rel="noreferrer" className="flex items-center gap-1 underline decoration-dotted underline-offset-2">
                      <MapPin className="w-3 h-3 text-accent-ink" /> {a.start_address}
                    </a>
                  )}
                  {a.end_address && (
                    <a href={mapsLink(a.end_address)} target="_blank" rel="noreferrer" className="flex items-center gap-1 underline decoration-dotted underline-offset-2">
                      <MapPin className="w-3 h-3 text-faint" /> {a.end_address}
                    </a>
                  )}
                </div>
              )}
              <div className="flex flex-wrap items-center gap-1.5 mt-3">
                {(a.crew || []).map((c) => (
                  <span
                    key={c.user_id}
                    data-testid="job-crew-chip"
                    draggable
                    onDragStart={dragPayload({ kind: "crew", user_id: c.user_id, name: c.name, position: c.position, from: a.id })}
                    className="inline-flex items-center gap-1 bg-accent/10 border border-accent/25 text-accent-ink rounded-full pl-1.5 pr-1 py-0.5 text-[11px] font-semibold cursor-grab active:cursor-grabbing"
                  >
                    <GripVertical className="w-3 h-3 text-accent-ink" />
                    {c.name}
                    <button
                      data-testid="job-position-toggle"
                      title="Flip Driver/Helper"
                      disabled={busy}
                      onClick={() => togglePosition(a, c.user_id)}
                      className="bg-surface border border-accent/25 rounded-full px-1.5 text-[9px] font-bold text-accent-ink hover:bg-accent/15"
                    >
                      {c.position}
                    </button>
                    <button data-testid="job-crew-remove" disabled={busy} onClick={() => removeCrew(a, c.user_id)} className="text-accent-ink hover:text-destructive">
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
                {(a.crew || []).length === 0 && (
                  <span data-testid="job-no-crew" className="text-[11px] font-semibold text-warning border border-dashed border-warning/30 rounded-full px-2.5 py-1">
                    Drop crew here
                  </span>
                )}
                {a.truck_name ? (
                  <span data-testid="job-truck-chip" className="inline-flex items-center gap-1 bg-surface-sunk border border-border-strong text-ink-2 rounded-full px-2 py-0.5 text-[11px] font-semibold">
                    <Truck className="w-3 h-3" /> {a.truck_name}
                    <button data-testid="job-truck-remove" disabled={busy} onClick={() => removeTruck(a)} className="text-faint hover:text-destructive">
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ) : (
                  <span data-testid="job-no-truck" className="text-[11px] font-semibold text-faint border border-dashed border-border-strong rounded-full px-2.5 py-1">
                    Drop a truck here
                  </span>
                )}
                <span className="ml-auto flex items-center gap-2.5">
                  <ProgressRing done={a.checklist_done || 0} total={a.checklist_total || 25} />
                  <button
                    data-testid="dispatch-open-detail"
                    className="text-[11px] font-semibold text-primary hover:underline inline-flex items-center gap-1"
                    onClick={() => setDetail(a)}
                  >
                    <History className="w-3 h-3" /> Timeline
                  </button>
                  <button
                    data-testid="dispatch-edit-job"
                    className="text-[11px] font-semibold text-accent-ink hover:underline"
                    onClick={() => { setEditing(a); setModalOpen(true); }}
                  >
                    Edit details
                  </button>
                </span>
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-4">
          <div data-testid="dispatch-crew-pool" className="surface p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-faint mb-2">Crew pool</p>
            <div className="space-y-1.5">
              {(board?.crew || []).map((u) => (
                <div
                  key={u.id}
                  data-testid="dispatch-crew-chip"
                  draggable={!u.off}
                  onDragStart={dragPayload({ kind: "crew", user_id: u.id, name: u.name })}
                  className={`flex items-center gap-2 border rounded-md px-2 py-1.5 ${u.off ? "opacity-50 border-border" : "cursor-grab active:cursor-grabbing border-border hover:border-accent"}`}
                >
                  <GripVertical className="w-3.5 h-3.5 text-faint/70 shrink-0" />
                  <span className={`w-2 h-2 rounded-full shrink-0 ${u.clocked_in ? "bg-success animate-pulse" : "bg-muted"}`} title={u.clocked_in ? "On the clock" : "Not clocked in"} />
                  <span className="text-sm font-semibold text-primary flex-1 truncate">{u.name}</span>
                  {u.off && <Badge variant="outline" className="text-[9px] bg-destructive/10 text-destructive border-destructive/25">OFF</Badge>}
                  {board?.is_today && u.clocked_in && u.jobs_today === 0 && (
                    <Badge data-testid="crew-unscheduled-badge" variant="outline" className="text-[9px] bg-warning/10 text-warning border-warning/30 gap-0.5">
                      <AlertTriangle className="w-2.5 h-2.5" /> On clock, no job
                    </Badge>
                  )}
                  {u.jobs_today > 0 && <Badge variant="outline" className="text-[9px] bg-accent/10 text-accent-ink border-accent/25">{u.jobs_today} today</Badge>}
                  <span className="flex gap-0.5" title={`${u.jobs_week} job${u.jobs_week === 1 ? "" : "s"} this week`}>
                    {Array.from({ length: Math.min(u.jobs_week, 5) }).map((_, i) => (
                      <span key={i} className="w-1.5 h-3 rounded-sm bg-accent/70" />
                    ))}
                    {u.jobs_week === 0 && <span className="w-1.5 h-3 rounded-sm bg-muted" />}
                  </span>
                </div>
              ))}
              {(board?.crew || []).length === 0 && <p className="text-xs text-faint">No active crew accounts yet.</p>}
            </div>
            <p className="text-[10px] text-faint mt-2">Bars = jobs this week. Green dot = clocked in right now.</p>
          </div>

          <div data-testid="dispatch-truck-pool" className="surface p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-faint mb-2">Trucks</p>
            <div className="space-y-1.5">
              {(board?.trucks || []).map((t) => (
                <div
                  key={t.id}
                  data-testid="dispatch-truck-chip"
                  draggable
                  onDragStart={dragPayload({ kind: "truck", truck_id: t.id, name: t.name })}
                  className="flex items-center gap-2 border border-border rounded-md px-2 py-1.5 cursor-grab active:cursor-grabbing hover:border-accent"
                >
                  <GripVertical className="w-3.5 h-3.5 text-faint/70 shrink-0" />
                  <Truck className="w-3.5 h-3.5 text-faint shrink-0" />
                  <span className="text-sm font-semibold text-primary flex-1 truncate">{t.name}</span>
                  {t.on_job && <Badge variant="outline" className="text-[9px] bg-info/10 text-info border-info/25 truncate max-w-[90px]">{t.on_job}</Badge>}
                </div>
              ))}
              {(board?.trucks || []).length === 0 && <p className="text-xs text-faint">No trucks yet — add them on the Crew page.</p>}
            </div>
          </div>
        </div>
      </div>

      <AssignmentModal open={modalOpen} onOpenChange={setModalOpen} initial={editing} users={users} trucks={trucks} onSaved={load} />

      <Dialog open={!!detail} onOpenChange={(v) => !v && setDetail(null)}>
        <DialogContent data-testid="dispatch-detail-dialog" className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">{detail?.job_name}</DialogTitle>
            <DialogDescription>
              {detail ? fmtDate(detail.job_date) : ""}{detail?.arrival_time ? ` · arrive ${detail.arrival_time}` : ""}
            </DialogDescription>
          </DialogHeader>
          {detail && (
            <Tabs defaultValue="timeline">
              <TabsList className="w-full">
                <TabsTrigger data-testid="detail-tab-timeline" value="timeline" className="flex-1">Timeline</TabsTrigger>
                <TabsTrigger data-testid="detail-tab-checklists" value="checklists" className="flex-1">Checklists</TabsTrigger>
              </TabsList>
              <TabsContent value="timeline"><JobTimeline assignmentId={detail.id} /></TabsContent>
              <TabsContent value="checklists">
                <JobChecklists assignmentId={detail.id} truckId={detail.truck_id} truckName={detail.truck_name} onStatusAdvance={load} />
              </TabsContent>
            </Tabs>
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!pending} onOpenChange={(v) => !v && setPending(null)}>
        <AlertDialogContent data-testid="dispatch-conflict-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-display">Heads up — possible conflict</AlertDialogTitle>
            <AlertDialogDescription>You can still assign it, but double-check first:</AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-1">
            {(pending?.warnings || []).map((w, i) => (
              <p key={i} data-testid="dispatch-conflict-line" className="text-sm text-warning bg-warning/10 border border-warning/25 rounded px-3 py-1.5 flex items-start gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {w}
              </p>
            ))}
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="dispatch-conflict-cancel">Never mind</AlertDialogCancel>
            <AlertDialogAction data-testid="dispatch-conflict-force" onClick={(e) => { e.preventDefault(); forcePending(); }} className="bg-warning hover:bg-warning">
              Assign anyway
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
