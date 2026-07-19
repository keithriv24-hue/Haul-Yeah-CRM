import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CalendarPlus, MapPin, Truck, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { AssignmentModal } from "@/components/crew/AssignmentModal";
import { listAssignmentsApi, deleteAssignmentApi, listUsersApi, listTrucksApi, apiErrorMessage } from "@/lib/api";
import { fmtDate, todayISO, mapsLink } from "@/lib/format";

const EXEC_STYLE = {
  Assigned: "bg-slate-100 text-slate-600 border-slate-300",
  "En Route": "bg-sky-100 text-sky-800 border-sky-300",
  Arrived: "bg-amber-100 text-amber-800 border-amber-300",
  "In Progress": "bg-indigo-100 text-indigo-800 border-indigo-300",
  Complete: "bg-emerald-100 text-emerald-800 border-emerald-300",
};

export const ScheduleTab = () => {
  const [assignments, setAssignments] = useState(null);
  const [users, setUsers] = useState([]);
  const [trucks, setTrucks] = useState([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [showPast, setShowPast] = useState(false);

  const load = useCallback(async () => {
    try {
      const [a, u, t] = await Promise.all([listAssignmentsApi(), listUsersApi(), listTrucksApi()]);
      setAssignments(a);
      setUsers(u);
      setTrucks(t);
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const remove = async (a) => {
    try {
      await deleteAssignmentApi(a.id);
      toast.success("Assignment removed — the crew was told.");
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  const today = todayISO();
  const visible = (assignments || []).filter((a) => showPast || a.job_date >= today);
  const byDate = visible.reduce((acc, a) => {
    (acc[a.job_date] = acc[a.job_date] || []).push(a);
    return acc;
  }, {});

  return (
    <div className="mt-4 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button data-testid="assign-job-btn" className="gap-1.5 bg-[#E8743B] hover:bg-[#d4632e]" onClick={() => { setEditing(null); setModalOpen(true); }}>
          <CalendarPlus className="w-4 h-4" /> Assign a job
        </Button>
        <Button data-testid="toggle-past-btn" variant="outline" size="sm" onClick={() => setShowPast((s) => !s)}>
          {showPast ? "Hide past jobs" : "Show past jobs"}
        </Button>
      </div>

      {assignments === null && <p className="text-sm text-slate-400">Loading schedule…</p>}
      {assignments !== null && visible.length === 0 && (
        <p className="text-sm text-slate-400 bg-white border border-dashed border-slate-200 rounded-lg p-6 text-center">
          No jobs assigned yet. Hit "Assign a job" to put your crew on a move.
        </p>
      )}

      {Object.keys(byDate).sort().map((date) => (
        <div key={date}>
          <h3 className="text-sm font-bold uppercase tracking-wide text-slate-500 mb-2">{fmtDate(date)}{date === today ? " — today" : ""}</h3>
          <div className="space-y-2">
            {byDate[date].map((a) => (
              <div key={a.id} data-testid="assignment-card" className="bg-white rounded-lg border border-slate-200 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-bold text-[#1B2A4A]">{a.job_name}</p>
                    <p className="text-xs text-slate-500">{a.arrival_time ? `Arrive ${a.arrival_time}` : "No arrival time set"}</p>
                  </div>
                  <Badge variant="outline" className={`text-[10px] ${EXEC_STYLE[a.exec_status] || EXEC_STYLE.Assigned}`}>{a.exec_status}</Badge>
                </div>
                <div className="mt-2 text-sm space-y-1">
                  {a.start_address && (
                    <a href={mapsLink(a.start_address)} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-[#1B2A4A] underline decoration-dotted underline-offset-2">
                      <MapPin className="w-3.5 h-3.5 text-[#E8743B]" /> {a.start_address}
                    </a>
                  )}
                  <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    {a.truck_name && <span className="inline-flex items-center gap-1"><Truck className="w-3.5 h-3.5" /> {a.truck_name}</span>}
                    {(a.crew || []).map((c) => (
                      <Badge key={c.user_id} variant="outline" className="text-[10px] bg-orange-50 text-orange-800 border-orange-200">
                        {c.name} — {c.position}
                      </Badge>
                    ))}
                    {(a.crew || []).length === 0 && <span className="text-amber-600 font-semibold">No crew on this yet</span>}
                  </div>
                </div>
                <div className="flex gap-2 mt-3">
                  <Button data-testid="edit-assignment-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => { setEditing(a); setModalOpen(true); }}>
                    <Pencil className="w-3.5 h-3.5" /> Edit
                  </Button>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button data-testid="delete-assignment-btn" variant="outline" size="sm" className="gap-1 text-xs text-red-600 border-red-200 hover:bg-red-50 hover:text-red-700">
                        <Trash2 className="w-3.5 h-3.5" /> Delete
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle className="font-display">Take this job off the schedule?</AlertDialogTitle>
                        <AlertDialogDescription>The crew on it will get a notification that it's gone.</AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Keep it</AlertDialogCancel>
                        <AlertDialogAction data-testid="confirm-delete-assignment" onClick={() => remove(a)} className="bg-red-600 hover:bg-red-700">Yes, remove</AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      <AssignmentModal open={modalOpen} onOpenChange={setModalOpen} initial={editing} users={users} trucks={trucks} onSaved={load} />
    </div>
  );
};
