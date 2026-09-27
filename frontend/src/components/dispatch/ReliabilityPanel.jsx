import React, { useState } from "react";
import { toast } from "sonner";
import { ShieldAlert, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { resolveFlagApi, apiErrorMessage } from "@/lib/api";

const TONE = {
  open: "bg-warning/10 border-warning/30 text-warning",
  unverified: "bg-info/10 border-info/30 text-info",
  disputed: "bg-primary/10 border-primary/25 text-primary",
};

// Owner-only reliability review on the Dispatch board. Resolving is a review action with a required
// reason — it never docks pay, changes assignments, or touches credits/badges.
export const ReliabilityPanel = ({ flags = [], onResolved }) => {
  const [resolving, setResolving] = useState(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (reason.trim().length < 3) { toast.error("Add a short reason for the record."); return; }
    setBusy(true);
    try {
      await resolveFlagApi(resolving.id, reason.trim());
      toast.success("Flag resolved.");
      setResolving(null); setReason(""); onResolved?.();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy(false);
  };

  return (
    <div data-testid="dispatch-reliability-panel" className="surface p-4">
      <p className="text-xs font-bold uppercase tracking-wide text-faint mb-2 flex items-center gap-1.5">
        <ShieldAlert className="w-3.5 h-3.5 text-warning" /> Reliability ({flags.length})
      </p>
      {flags.length === 0 ? (
        <p className="text-xs text-faint" data-testid="reliability-empty">No timekeeping flags today. 👍</p>
      ) : (
        <div className="space-y-2">
          {flags.map((f) => (
            <div key={f.id} data-testid={`reliability-flag-${f.id}`} className="rounded-md border border-border p-2.5">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant="outline" className={`text-[9px] ${TONE[f.status] || TONE.open}`}>{f.label}</Badge>
                <span className="text-sm font-semibold text-primary">{f.user_name}</span>
                {f.status === "disputed" && <Badge variant="outline" className="text-[9px] bg-primary/10 text-primary border-primary/25">disputed</Badge>}
              </div>
              <p className="text-[11px] text-ink-2 mt-1">{f.detail}</p>
              <p className="text-[10px] text-faint">{f.job_name}</p>
              {f.dispute_reason && <p className="text-[11px] text-primary mt-1 italic">Crew says: {f.dispute_reason}</p>}
              <Button data-testid={`resolve-flag-${f.id}`} size="sm" variant="outline" className="mt-2 h-7 text-xs gap-1" onClick={() => { setResolving(f); setReason(""); }}>
                <Check className="w-3.5 h-3.5" /> Resolve
              </Button>
            </div>
          ))}
        </div>
      )}
      <Dialog open={!!resolving} onOpenChange={(v) => !v && setResolving(null)}>
        <DialogContent data-testid="resolve-flag-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">Resolve — {resolving?.label}</DialogTitle>
            <DialogDescription>{resolving?.user_name}: {resolving?.detail}. Recording your review keeps the history clean. This does not change pay or assignments.</DialogDescription>
          </DialogHeader>
          <Textarea data-testid="resolve-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Confirmed with the crew — was on an earlier job, not a no-show." />
          <DialogFooter>
            <Button variant="outline" onClick={() => setResolving(null)}>Cancel</Button>
            <Button data-testid="resolve-submit" disabled={busy} onClick={submit} className="bg-primary hover:bg-[#152238]">Resolve</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
