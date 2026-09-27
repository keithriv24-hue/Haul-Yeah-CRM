import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Phone, MessageSquare, Flag, ShieldQuestion, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { myFlagsApi, disputeFlagApi, reportProblemApi, apiErrorMessage } from "@/lib/api";

const FLAG_TONE = {
  open: "bg-warning/10 border-warning/30 text-warning",
  unverified: "bg-info/10 border-info/30 text-info",
  disputed: "bg-primary/10 border-primary/25 text-primary",
  resolved: "bg-surface-sunk border-border text-faint",
};

// Crew member's own timekeeping flags with a dispute path (they can never see anyone else's).
export const MyFlagsStrip = () => {
  const [flags, setFlags] = useState([]);
  const [disputing, setDisputing] = useState(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => { myFlagsApi().then(setFlags).catch(() => setFlags([])); }, []);
  useEffect(() => { load(); }, [load]);

  const active = flags.filter((f) => f.status !== "resolved");
  if (active.length === 0) return null;

  const submit = async () => {
    if (reason.trim().length < 3) { toast.error("Tell the owner what actually happened."); return; }
    setBusy(true);
    try {
      await disputeFlagApi(disputing.id, reason.trim());
      toast.success("Sent to the owner to review.");
      setDisputing(null); setReason(""); load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy(false);
  };

  return (
    <div data-testid="my-flags-strip" className="rounded-lg border border-warning/30 bg-warning/5 p-4">
      <p className="text-xs font-bold uppercase tracking-wide text-warning flex items-center gap-1.5">
        <ShieldQuestion className="w-3.5 h-3.5" /> Timekeeping to review ({active.length})
      </p>
      <div className="mt-2 space-y-2">
        {active.map((f) => (
          <div key={f.id} data-testid={`my-flag-${f.id}`} className="flex flex-wrap items-center gap-2 text-[13px]">
            <Badge variant="outline" className={`text-[10px] ${FLAG_TONE[f.status] || FLAG_TONE.open}`}>{f.label}</Badge>
            <span className="text-ink-2 flex-1 min-w-[160px]">{f.detail} <span className="text-faint">· {f.job_name}</span></span>
            {f.status === "disputed"
              ? <span className="text-[11px] text-faint italic">Disputed — waiting on the owner</span>
              : <Button data-testid={`dispute-flag-${f.id}`} size="sm" variant="outline" className="h-7 text-xs" onClick={() => { setDisputing(f); setReason(""); }}>Dispute</Button>}
          </div>
        ))}
      </div>
      <Dialog open={!!disputing} onOpenChange={(v) => !v && setDisputing(null)}>
        <DialogContent data-testid="dispute-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">Dispute this flag</DialogTitle>
            <DialogDescription>{disputing?.label} — {disputing?.detail}. Tell the owner what really happened; nothing changes your pay automatically.</DialogDescription>
          </DialogHeader>
          <Textarea data-testid="dispute-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. I clocked in on the other job first, then came here." />
          <DialogFooter>
            <Button variant="outline" onClick={() => setDisputing(null)}>Cancel</Button>
            <Button data-testid="dispute-submit" disabled={busy} onClick={submit} className="bg-primary hover:bg-[#152238]">Send to owner</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// Report-a-problem (any crew) + Contact-Crew-Lead (helpers only). Never changes job status.
export const JobHelperActions = ({ assignmentId, leadFlow }) => {
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const isHelper = leadFlow && !leadFlow.is_lead;
  const phone = leadFlow?.primary_phone;

  const submit = async () => {
    if (msg.trim().length < 3) { toast.error("Add a quick note about the problem."); return; }
    setBusy(true);
    try {
      await reportProblemApi(assignmentId, msg.trim());
      toast.success("Sent to your Crew Lead and the owner.");
      setOpen(false); setMsg("");
    } catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy(false);
  };

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      {isHelper && phone && (
        <>
          <a data-testid="contact-lead-call" href={`tel:${phone}`} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-medium text-ink-2 hover:bg-surface-sunk">
            <Phone className="w-3.5 h-3.5 text-accent-ink" /> Call {leadFlow.primary_name?.split(" ")[0] || "lead"}
          </a>
          <a data-testid="contact-lead-text" href={`sms:${phone}`} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-medium text-ink-2 hover:bg-surface-sunk">
            <MessageSquare className="w-3.5 h-3.5 text-accent-ink" /> Text
          </a>
        </>
      )}
      {isHelper && !phone && leadFlow?.primary_name && (
        <span className="text-[11px] text-faint">Crew Lead: <strong className="text-ink-2">{leadFlow.primary_name}</strong></span>
      )}
      <Button data-testid="report-problem-btn" size="sm" variant="outline" className="gap-1.5 text-xs" onClick={() => setOpen(true)}>
        <Flag className="w-3.5 h-3.5 text-destructive" /> Report a problem
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="report-problem-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">Report a problem</DialogTitle>
            <DialogDescription>This pings your Crew Lead and the owner right away. It doesn't change the job status or any checklist.</DialogDescription>
          </DialogHeader>
          <Textarea data-testid="report-problem-input" value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="What's going on? (e.g. elevator is out, customer isn't packed, truck issue)" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button data-testid="report-problem-submit" disabled={busy} onClick={submit} className="bg-destructive hover:bg-destructive gap-1.5">
              <Flag className="w-4 h-4" /> Send
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export const StillClockedInNudge = ({ show }) => {
  if (!show) return null;
  return (
    <div data-testid="still-clocked-in-nudge" className="rounded-lg border border-warning/40 bg-warning/10 p-3 flex items-start gap-2">
      <Clock className="w-4 h-4 text-warning shrink-0 mt-0.5" />
      <p className="text-sm text-primary">
        <strong>You're still on the clock</strong> and the job is marked complete. Clock out from the Time tab when you're done for the day.
      </p>
    </div>
  );
};
