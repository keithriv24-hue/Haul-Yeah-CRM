import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  ChevronLeft, ChevronRight, MapPin, Truck, CalendarPlus, AlertTriangle, GripVertical, X, Clock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { PageTitle, InstructionBanner, KpiCard } from "@/components/Bits";
import { AssignmentModal } from "@/components/crew/AssignmentModal";
import { dispatchBoardApi, updateAssignmentApi, listUsersApi, listTrucksApi, apiErrorMessage } from "@/lib/api";
import { fmtMoney, fmtDate, mapsLink } from "@/lib/format";

const todayET = () => new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });

const EXEC_STYLE = {
  Assigned: "bg-slate-100 text-slate-600 border-slate-300",
  "En Route": "bg-sky-100 text-sky-800 border-sky-300",
  Arrived: "bg-amber-100 text-amber-800 border-amber-300",
  "In Progress": "bg-indigo-100 text-indigo-800 border-indigo-300",
  Complete: "bg-emerald-100 text-emerald-800 border-emerald-300",
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

export default function Dispatch() {
  const [date, setDate] = useState(todayET());
  const [board, setBoard] = useState(null);
  const [users, setUsers] = useState([]);
  const [trucks, setTrucks] = useState([]);
  const [dragOver, setDragOver] = useState(null);
  const [pending, setPending] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
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
          <Button data-testid="dispatch-assign-btn" className="gap-1.5 bg-[#E8743B] hover:bg-[#d4632e]" onClick={() => { setEditing(null); setModalOpen(true); }}>
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
        <span data-testid="dispatch-date-label" className="font-display font-bold text-[#1B2A4A] min-w-[150px] text-center">
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
          {board === null && <p className="text-sm text-slate-400">Loading the board…</p>}
          {board !== null && assignments.length === 0 && (
            <p data-testid="dispatch-empty" className="text-sm text-slate-400 bg-white border border-dashed border-slate-200 rounded-lg p-8 text-center">
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
              className={`bg-white rounded-lg border p-4 transition-colors ${dragOver === a.id ? "border-[#E8743B] ring-2 ring-[#E8743B]/40" : "border-slate-200"}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-bold text-[#1B2A4A]">{a.job_name}</p>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <Clock className="w-3 h-3" /> {a.arrival_time ? `Arrive ${a.arrival_time}` : "No arrival time"}
                    {a.job_size && <span className="text-slate-400">· {a.job_size}</span>}
                  </p>
                </div>
                <div className="flex items-center gap-1.5">
                  {a.behind && (
                    <Badge data-testid="dispatch-behind-badge" className="text-[10px] bg-red-600 text-white border-red-600 animate-pulse gap-1">
                      <AlertTriangle className="w-3 h-3" /> Behind
                    </Badge>
                  )}
                  {a.clocked_in > 0 && (
                    <Badge data-testid="dispatch-clocked-badge" variant="outline" className="text-[10px] bg-emerald-50 text-emerald-700 border-emerald-300 gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" /> {a.clocked_in} on the clock
                    </Badge>
                  )}
                  <Badge data-testid="dispatch-status-chip" variant="outline" className={`text-[10px] ${EXEC_STYLE[a.exec_status] || EXEC_STYLE.Assigned}`}>
                    {a.exec_status}
                  </Badge>
                </div>
              </div>
              {(a.start_address || a.end_address) && (
                <div className="mt-2 text-xs text-slate-500 space-y-0.5">
                  {a.start_address && (
                    <a href={mapsLink(a.start_address)} target="_blank" rel="noreferrer" className="flex items-center gap-1 underline decoration-dotted underline-offset-2">
                      <MapPin className="w-3 h-3 text-[#E8743B]" /> {a.start_address}
                    </a>
                  )}
                  {a.end_address && (
                    <a href={mapsLink(a.end_address)} target="_blank" rel="noreferrer" className="flex items-center gap-1 underline decoration-dotted underline-offset-2">
                      <MapPin className="w-3 h-3 text-slate-400" /> {a.end_address}
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
                    className="inline-flex items-center gap-1 bg-orange-50 border border-orange-200 text-orange-900 rounded-full pl-1.5 pr-1 py-0.5 text-[11px] font-semibold cursor-grab active:cursor-grabbing"
                  >
                    <GripVertical className="w-3 h-3 text-orange-300" />
                    {c.name}
                    <button
                      data-testid="job-position-toggle"
                      title="Flip Driver/Helper"
                      disabled={busy}
                      onClick={() => togglePosition(a, c.user_id)}
                      className="bg-white border border-orange-200 rounded-full px-1.5 text-[9px] font-bold text-orange-700 hover:bg-orange-100"
                    >
                      {c.position}
                    </button>
                    <button data-testid="job-crew-remove" disabled={busy} onClick={() => removeCrew(a, c.user_id)} className="text-orange-400 hover:text-red-600">
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
                {(a.crew || []).length === 0 && (
                  <span data-testid="job-no-crew" className="text-[11px] font-semibold text-amber-600 border border-dashed border-amber-300 rounded-full px-2.5 py-1">
                    Drop crew here
                  </span>
                )}
                {a.truck_name ? (
                  <span data-testid="job-truck-chip" className="inline-flex items-center gap-1 bg-slate-100 border border-slate-300 text-slate-700 rounded-full px-2 py-0.5 text-[11px] font-semibold">
                    <Truck className="w-3 h-3" /> {a.truck_name}
                    <button data-testid="job-truck-remove" disabled={busy} onClick={() => removeTruck(a)} className="text-slate-400 hover:text-red-600">
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ) : (
                  <span data-testid="job-no-truck" className="text-[11px] font-semibold text-slate-400 border border-dashed border-slate-300 rounded-full px-2.5 py-1">
                    Drop a truck here
                  </span>
                )}
                <button
                  data-testid="dispatch-edit-job"
                  className="ml-auto text-[11px] font-semibold text-[#E8743B] hover:underline"
                  onClick={() => { setEditing(a); setModalOpen(true); }}
                >
                  Edit details
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-4">
          <div data-testid="dispatch-crew-pool" className="bg-white border border-slate-200 rounded-lg p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-2">Crew pool</p>
            <div className="space-y-1.5">
              {(board?.crew || []).map((u) => (
                <div
                  key={u.id}
                  data-testid="dispatch-crew-chip"
                  draggable={!u.off}
                  onDragStart={dragPayload({ kind: "crew", user_id: u.id, name: u.name })}
                  className={`flex items-center gap-2 border rounded-md px-2 py-1.5 ${u.off ? "opacity-50 border-slate-200" : "cursor-grab active:cursor-grabbing border-slate-200 hover:border-[#E8743B]"}`}
                >
                  <GripVertical className="w-3.5 h-3.5 text-slate-300 shrink-0" />
                  <span className={`w-2 h-2 rounded-full shrink-0 ${u.clocked_in ? "bg-emerald-500 animate-pulse" : "bg-slate-200"}`} title={u.clocked_in ? "On the clock" : "Not clocked in"} />
                  <span className="text-sm font-semibold text-[#1B2A4A] flex-1 truncate">{u.name}</span>
                  {u.off && <Badge variant="outline" className="text-[9px] bg-red-50 text-red-600 border-red-200">OFF</Badge>}
                  {u.jobs_today > 0 && <Badge variant="outline" className="text-[9px] bg-orange-50 text-orange-700 border-orange-200">{u.jobs_today} today</Badge>}
                  <span className="flex gap-0.5" title={`${u.jobs_week} job${u.jobs_week === 1 ? "" : "s"} this week`}>
                    {Array.from({ length: Math.min(u.jobs_week, 5) }).map((_, i) => (
                      <span key={i} className="w-1.5 h-3 rounded-sm bg-[#E8743B]/70" />
                    ))}
                    {u.jobs_week === 0 && <span className="w-1.5 h-3 rounded-sm bg-slate-200" />}
                  </span>
                </div>
              ))}
              {(board?.crew || []).length === 0 && <p className="text-xs text-slate-400">No active crew accounts yet.</p>}
            </div>
            <p className="text-[10px] text-slate-400 mt-2">Bars = jobs this week. Green dot = clocked in right now.</p>
          </div>

          <div data-testid="dispatch-truck-pool" className="bg-white border border-slate-200 rounded-lg p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-2">Trucks</p>
            <div className="space-y-1.5">
              {(board?.trucks || []).map((t) => (
                <div
                  key={t.id}
                  data-testid="dispatch-truck-chip"
                  draggable
                  onDragStart={dragPayload({ kind: "truck", truck_id: t.id, name: t.name })}
                  className="flex items-center gap-2 border border-slate-200 rounded-md px-2 py-1.5 cursor-grab active:cursor-grabbing hover:border-[#E8743B]"
                >
                  <GripVertical className="w-3.5 h-3.5 text-slate-300 shrink-0" />
                  <Truck className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <span className="text-sm font-semibold text-[#1B2A4A] flex-1 truncate">{t.name}</span>
                  {t.on_job && <Badge variant="outline" className="text-[9px] bg-sky-50 text-sky-700 border-sky-200 truncate max-w-[90px]">{t.on_job}</Badge>}
                </div>
              ))}
              {(board?.trucks || []).length === 0 && <p className="text-xs text-slate-400">No trucks yet — add them on the Crew page.</p>}
            </div>
          </div>
        </div>
      </div>

      <AssignmentModal open={modalOpen} onOpenChange={setModalOpen} initial={editing} users={users} trucks={trucks} onSaved={load} />

      <AlertDialog open={!!pending} onOpenChange={(v) => !v && setPending(null)}>
        <AlertDialogContent data-testid="dispatch-conflict-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-display">Heads up — possible conflict</AlertDialogTitle>
            <AlertDialogDescription>You can still assign it, but double-check first:</AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-1">
            {(pending?.warnings || []).map((w, i) => (
              <p key={i} data-testid="dispatch-conflict-line" className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-1.5 flex items-start gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {w}
              </p>
            ))}
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="dispatch-conflict-cancel">Never mind</AlertDialogCancel>
            <AlertDialogAction data-testid="dispatch-conflict-force" onClick={(e) => { e.preventDefault(); forcePending(); }} className="bg-amber-600 hover:bg-amber-700">
              Assign anyway
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
