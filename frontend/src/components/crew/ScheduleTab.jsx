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
  Assigned: "bg-surface-sunk text-ink-2 border-border-strong",
  "En Route": "bg-info/12 text-info border-info/30",
  Arrived: "bg-warning/12 text-warning border-warning/30",
  "In Progress": "bg-primary/10 text-primary border-primary/25",
  Complete: "bg-success/12 text-success border-success/30",
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
        <Button data-testid="assign-job-btn" className="gap-1.5 bg-accent hover:bg-accent-press" onClick={() => { setEditing(null); setModalOpen(true); }}>
          <CalendarPlus className="w-4 h-4" /> Assign a job
        </Button>
        <Button data-testid="toggle-past-btn" variant="outline" size="sm" onClick={() => setShowPast((s) => !s)}>
          {showPast ? "Hide past jobs" : "Show past jobs"}
        </Button>
      </div>

      {assignments === null && <p className="text-sm text-faint">Loading schedule…</p>}
      {assignments !== null && visible.length === 0 && (
        <p className="text-sm text-faint bg-surface border border-dashed border-border rounded-lg p-6 text-center">
          No jobs assigned yet. Hit "Assign a job" to put your crew on a move.
        </p>
      )}

      {Object.keys(byDate).sort().map((date) => (
        <div key={date}>
          <h3 className="text-sm font-bold uppercase tracking-wide text-faint mb-2">{fmtDate(date)}{date === today ? " — today" : ""}</h3>
          <div className="space-y-2">
            {byDate[date].map((a) => (
              <div key={a.id} data-testid="assignment-card" className="surface p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-bold text-primary">{a.job_name}</p>
                    <p className="text-xs text-faint">{a.arrival_time ? `Arrive ${a.arrival_time}` : "No arrival time set"}</p>
                  </div>
                  <Badge variant="outline" className={`text-[10px] ${EXEC_STYLE[a.exec_status] || EXEC_STYLE.Assigned}`}>{a.exec_status}</Badge>
                </div>
                <div className="mt-2 text-sm space-y-1">
                  {a.start_address && (
                    <a href={mapsLink(a.start_address)} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-primary underline decoration-dotted underline-offset-2">
                      <MapPin className="w-3.5 h-3.5 text-accent-ink" /> {a.start_address}
                    </a>
                  )}
                  <div className="flex flex-wrap items-center gap-2 text-xs text-faint">
                    {a.truck_name && <span className="inline-flex items-center gap-1"><Truck className="w-3.5 h-3.5" /> {a.truck_name}</span>}
                    {(a.crew || []).map((c) => (
                      <Badge key={c.user_id} variant="outline" className="text-[10px] bg-accent/10 text-accent-ink border-accent/25">
                        {c.name} — {c.position}
                      </Badge>
                    ))}
                    {(a.crew || []).length === 0 && <span className="text-warning font-semibold">No crew on this yet</span>}
                  </div>
                </div>
                <div className="flex gap-2 mt-3">
                  <Button data-testid="edit-assignment-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => { setEditing(a); setModalOpen(true); }}>
                    <Pencil className="w-3.5 h-3.5" /> Edit
                  </Button>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button data-testid="delete-assignment-btn" variant="outline" size="sm" className="gap-1 text-xs text-destructive border-destructive/25 hover:bg-destructive/10 hover:text-destructive">
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
                        <AlertDialogAction data-testid="confirm-delete-assignment" onClick={() => remove(a)} className="bg-destructive hover:bg-destructive/90">Yes, remove</AlertDialogAction>
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
