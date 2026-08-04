import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, ChevronDown, ChevronRight, Clock } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { InspectionDialog } from "@/components/fleet/InspectionDialog";
import { jobChecklistsApi, toggleChecklistItemApi, apiErrorMessage } from "@/lib/api";

export const JobChecklists = ({ assignmentId, truckId, truckName, onStatusAdvance, clockedIn }) => {
  const locked = clockedIn === false;
  const [lists, setLists] = useState(null);
  const [openKey, setOpenKey] = useState(null);
  const [busy, setBusy] = useState(false);
  const [inspOpen, setInspOpen] = useState(false);

  const reload = () =>
    jobChecklistsApi(assignmentId).then((d) => setLists(d.checklists)).catch(() => {});

  useEffect(() => {
    jobChecklistsApi(assignmentId)
      .then((d) => {
        setLists(d.checklists);
        const first = d.checklists.find((l) => l.done_count < l.total);
        setOpenKey(first ? first.key : null);
      })
      .catch((e) => toast.error(apiErrorMessage(e)));
  }, [assignmentId]);

  const toggle = async (listKey, idx, done) => {
    if (locked) {
      toast.error("Clock in first — checklists unlock once you're on the clock.");
      return;
    }
    if (listKey === "warehouse_departure" && idx === 0 && done && truckId) {
      setInspOpen(true);
      return;
    }
    setBusy(true);
    try {
      const d = await toggleChecklistItemApi(assignmentId, listKey, idx, done);
      setLists(d.checklists);
      if (d.advanced_to) {
        toast.success(`Checklist complete — job moved to "${d.advanced_to}".`);
        onStatusAdvance && onStatusAdvance();
      }
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  if (lists === null) return <p className="text-xs text-slate-400 mt-2">Loading checklists…</p>;
  return (
    <div data-testid="job-checklists" className="mt-2 space-y-1.5">
      {locked && (
        <p data-testid="checklists-clock-in-notice" className="flex items-center gap-1.5 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
          <Clock className="w-3.5 h-3.5 shrink-0" /> Clock in first — checklists unlock once you're on the clock.
        </p>
      )}
      <InspectionDialog open={inspOpen} onOpenChange={setInspOpen} truckId={truckId} truckName={truckName}
        assignmentId={assignmentId} onDone={() => { reload(); onStatusAdvance && onStatusAdvance(); }} />
      {lists.map((l) => {
        const open = openKey === l.key;
        const complete = l.done_count === l.total;
        return (
          <div key={l.key} data-testid={`checklist-${l.key}`} className="border border-slate-200 rounded-md bg-white">
            <button
              data-testid={`checklist-header-${l.key}`}
              className="w-full flex items-center gap-2 px-3 py-2 text-left"
              onClick={() => setOpenKey(open ? null : l.key)}
            >
              {open ? <ChevronDown className="w-3.5 h-3.5 text-slate-400" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-400" />}
              <span className="text-sm font-semibold text-[#1B2A4A] flex-1">{l.label}</span>
              {complete ? (
                <Badge variant="outline" className="text-[9px] bg-emerald-100 text-emerald-700 border-emerald-300 gap-0.5">
                  <CheckCircle2 className="w-2.5 h-2.5" /> Done
                </Badge>
              ) : (
                <Badge variant="outline" className="text-[9px] bg-slate-100 text-slate-600 border-slate-300">
                  {l.done_count}/{l.total}
                </Badge>
              )}
            </button>
            {open && (
              <div className="px-3 pb-2.5 space-y-1.5">
                {l.items.map((it) => (
                  <label key={it.idx} data-testid="checklist-item" className="flex items-start gap-2 text-sm cursor-pointer">
                    <Checkbox
                      data-testid="checklist-item-checkbox"
                      checked={it.done}
                      disabled={busy || locked}
                      onCheckedChange={(v) => toggle(l.key, it.idx, !!v)}
                      className="mt-0.5"
                    />
                    <span className={it.done ? "text-slate-400 line-through" : "text-slate-700"}>
                      {it.label}
                      {it.done && it.by && <span className="text-[10px] text-slate-400 ml-1">— {it.by}</span>}
                    </span>
                  </label>
                ))}
                {l.auto_status && !complete && (
                  <p className="text-[10px] text-slate-400">Finishing this list moves the job to "{l.auto_status}".</p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
