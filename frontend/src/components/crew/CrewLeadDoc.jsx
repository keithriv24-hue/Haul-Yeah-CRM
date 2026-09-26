import React, { useState } from "react";
import { toast } from "sonner";
import {
  CheckCircle2, Circle, ShieldAlert, ShieldCheck, AlertTriangle, Pencil, RotateCcw, ClipboardList,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { correctCrewLeadApi, departOverrideApi, apiErrorMessage } from "@/lib/api";

const fmtDateTime = (iso) =>
  iso ? new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—";

// Render the extra payload a crew-lead tap carried (inspection results, damage, delay factors…).
const stepDetailLines = (key, detail = {}) => {
  const out = [];
  if (detail.inspection) {
    out.push(detail.inspection.passed
      ? "Pre-trip check passed"
      : `Pre-trip exceptions: ${(detail.inspection.failed || []).join(", ") || "—"}`);
  }
  if (detail.override) out.push(`Departed under owner clearance (${detail.override.resolution || "override"})`);
  if (detail.sms) {
    const map = { sent: "On-the-way text sent", already_sent: "On-the-way text already sent",
      failed: "On-the-way text FAILED", no_customer_job: "No linked customer — no text" };
    out.push(map[detail.sms.status] || `Text: ${detail.sms.status}`);
  }
  if (key === "no_damage") out.push(detail.damage_found ? "Existing damage found (photos on file)" : "No existing damage");
  if (Array.isArray(detail.delay_factors) && detail.delay_factors.length) out.push(`Slowed by: ${detail.delay_factors.join(", ")}`);
  if (detail.as_found) out.push(`As-found: ${detail.as_found}`);
  if (detail.lead_identity) out.push(`Signed by: ${detail.lead_identity}`);
  if (key === "clock_out") {
    out.push(detail.no_defects === false ? "Post-trip DEFECT reported" : "Post-trip: no defects");
    if (detail.posttrip && !detail.posttrip.passed) out.push(`Post-trip exceptions: ${(detail.posttrip.failed || []).join(", ")}`);
  }
  return out;
};

export const CrewLeadDoc = ({ assignment, canCorrect, onChanged }) => {
  const cl = assignment.crew_lead || {};
  const steps = cl.steps || [];
  const [correcting, setCorrecting] = useState(null); // step object
  const [action, setAction] = useState("note");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [resolution, setResolution] = useState("corrected");
  const [reviewReason, setReviewReason] = useState("");

  const openCorrect = (step) => { setCorrecting(step); setAction("note"); setReason(""); setNote(""); };

  const submitCorrection = async () => {
    if (reason.trim().length < 5) { toast.error("Give a reason (at least 5 characters)."); return; }
    setBusy(true);
    try {
      await correctCrewLeadApi(assignment.id, {
        tap_key: correcting.key, action, reason: reason.trim(), note: note.trim() || null,
      });
      toast.success(action === "clear" ? "Tap invalidated — the Crew Lead can redo it." : "Note added to the record.");
      setCorrecting(null);
      onChanged?.();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy(false);
  };

  const submitReview = async () => {
    if (reviewReason.trim().length < 10) { toast.error("Give a real reason (at least 10 characters)."); return; }
    setBusy(true);
    try {
      await departOverrideApi(assignment.id, reviewReason.trim(), resolution);
      toast.success(resolution === "corrected" ? "Recorded: defect corrected & verified." : "Recorded: departure authorized.");
      setReviewOpen(false); setReviewReason("");
      onChanged?.();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy(false);
  };

  const laterSteps = correcting
    ? steps.filter((s) => steps.indexOf(steps.find((x) => x.key === correcting.key)) < steps.indexOf(s) && s.done)
    : [];

  return (
    <div data-testid="crew-lead-doc" className="mt-3 border-t border-border pt-3 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <ClipboardList className="w-4 h-4 text-accent-ink" />
        <span className="text-[11px] font-bold uppercase tracking-wide text-accent-ink">Crew Lead documentation</span>
        <Badge variant="outline" className="text-[10px]" data-testid="crew-lead-doc-progress">{cl.taps_done || 0} / {cl.taps_total || 8} taps</Badge>
      </div>

      <div className="text-sm text-primary flex flex-wrap gap-x-4 gap-y-1">
        <span data-testid="crew-lead-doc-primary"><span className="text-faint">Crew Lead:</span> <strong>{cl.primary_name || "—"}</strong>
          {cl.source === "driver_default" && <span className="text-[10px] text-warning ml-1">(driver default — confirm)</span>}
        </span>
        {cl.secondary_name && <span data-testid="crew-lead-doc-secondary"><span className="text-faint">Backup:</span> <strong>{cl.secondary_name}</strong></span>}
      </div>

      {/* Critical-defect departure block — owner review */}
      {cl.depart_blocker && (
        <div data-testid="crew-lead-doc-blocker" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
          <p className="font-bold text-destructive flex items-center gap-1.5"><ShieldAlert className="w-4 h-4" /> Departure blocked — critical defect</p>
          <p className="text-primary mt-0.5">{(cl.depart_blocker.failed_labels || []).join(", ")}</p>
          {canCorrect && (
            <Button data-testid="crew-lead-review-block-btn" size="sm" className="mt-2 gap-1.5 bg-destructive hover:bg-destructive"
              onClick={() => { setResolution("corrected"); setReviewReason(""); setReviewOpen(true); }}>
              <ShieldCheck className="w-3.5 h-3.5" /> Review departure block
            </Button>
          )}
        </div>
      )}
      {cl.depart_override && !cl.depart_blocker && (
        <div data-testid="crew-lead-doc-override" className="rounded-md border border-warning/40 bg-warning/10 p-3 text-xs text-primary">
          <p className="font-semibold text-warning">
            {cl.depart_override.resolution === "corrected" ? "Defect corrected & verified" : "Departure authorized despite defect"}
          </p>
          <p className="mt-0.5">{cl.depart_override.reason} — {cl.depart_override.by} · {fmtDateTime(cl.depart_override.at)}</p>
        </div>
      )}

      {/* The eight milestones */}
      <div className="space-y-1.5">
        {steps.map((s) => {
          const lines = s.done ? stepDetailLines(s.key, s.detail) : [];
          return (
            <div key={s.key} data-testid={`crew-lead-doc-step-${s.key}`} className="flex items-start gap-2.5 text-[13px]">
              {s.done ? <CheckCircle2 className="w-4 h-4 text-success shrink-0 mt-0.5" /> : <Circle className="w-4 h-4 text-faint shrink-0 mt-0.5" />}
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-x-2">
                  <span className={s.done ? "text-primary font-medium" : "text-faint"}>{s.label}</span>
                  {s.done && s.by && <span className="text-[11px] text-faint">{s.by} · {fmtDateTime(s.at)}</span>}
                  {s.done && canCorrect && (
                    <button data-testid={`crew-lead-correct-${s.key}`} onClick={() => openCorrect(s)}
                      className="text-[11px] text-accent-ink hover:underline inline-flex items-center gap-0.5">
                      <Pencil className="w-3 h-3" /> Correct
                    </button>
                  )}
                </div>
                {lines.map((l, i) => (
                  <p key={i} className={`text-[11px] ${l.includes("FAILED") || l.includes("DEFECT") || l.includes("exceptions") || l.includes("damage found") ? "text-destructive" : "text-faint"}`}>{l}</p>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Corrections history */}
      {(cl.corrections || []).length > 0 && (
        <div data-testid="crew-lead-doc-corrections" className="rounded-md bg-surface-sunk p-2.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-faint mb-1">Owner corrections (original taps kept)</p>
          <ul className="space-y-1">
            {cl.corrections.map((c, i) => (
              <li key={i} className="text-[11px] text-ink-2">
                <span className="font-semibold text-primary">{c.action === "clear" ? "Invalidated" : "Note"}</span> on “{c.tap_key}” — {c.reason}
                {c.note ? ` (${c.note})` : ""} <span className="text-faint">· {c.by} · {fmtDateTime(c.at)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Correction dialog */}
      <Dialog open={!!correcting} onOpenChange={(v) => !v && setCorrecting(null)}>
        <DialogContent data-testid="crew-lead-correct-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">Correct “{correcting?.label}”</DialogTitle>
            <DialogDescription>
              The original tap stays in the record and history — this only adds your correction on top.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="flex gap-2">
              <button data-testid="crew-lead-correct-note" onClick={() => setAction("note")}
                className={`flex-1 rounded-md border px-3 py-2 text-sm font-semibold ${action === "note" ? "border-accent bg-accent/10 text-accent-ink" : "border-border text-ink-2"}`}>
                Add a note
              </button>
              <button data-testid="crew-lead-correct-clear" onClick={() => setAction("clear")}
                className={`flex-1 rounded-md border px-3 py-2 text-sm font-semibold inline-flex items-center justify-center gap-1.5 ${action === "clear" ? "border-destructive bg-destructive/10 text-destructive" : "border-border text-ink-2"}`}>
                <RotateCcw className="w-3.5 h-3.5" /> Invalidate tap
              </button>
            </div>
            {action === "clear" && (
              <div className="rounded-md border border-warning/40 bg-warning/10 p-2.5 text-xs text-primary">
                <p className="font-semibold text-warning flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> The Crew Lead will need to redo this step.</p>
                {laterSteps.length > 0 && (
                  <p className="mt-0.5">Also affects the later steps already logged: {laterSteps.map((s) => s.label).join(", ")}.</p>
                )}
              </div>
            )}
            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-faint mb-1">Reason (required)</p>
              <Textarea data-testid="crew-lead-correct-reason" value={reason} onChange={(e) => setReason(e.target.value)}
                placeholder="Why are you correcting this? Kept on the audit trail." />
            </div>
            {action === "note" && (
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-faint mb-1">Note (optional)</p>
                <Textarea data-testid="crew-lead-correct-note-input" value={note} onChange={(e) => setNote(e.target.value)} />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCorrecting(null)}>Cancel</Button>
            <Button data-testid="crew-lead-correct-submit" disabled={busy} onClick={submitCorrection}
              className={action === "clear" ? "bg-destructive hover:bg-destructive" : "bg-accent hover:bg-accent-press"}>
              {action === "clear" ? "Invalidate tap" : "Add note"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Departure-block review dialog */}
      <Dialog open={reviewOpen} onOpenChange={setReviewOpen}>
        <DialogContent data-testid="crew-lead-review-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">Review departure block</DialogTitle>
            <DialogDescription>
              Failed: <strong>{(cl.depart_blocker?.failed_labels || []).join(", ")}</strong>. Record your decision — the failed
              inspection is preserved either way. This does NOT depart the truck; the Crew Lead still taps Depart.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-2">
              <button data-testid="crew-lead-review-corrected" onClick={() => setResolution("corrected")}
                className={`w-full text-left rounded-md border px-3 py-2 text-sm ${resolution === "corrected" ? "border-success bg-success/10" : "border-border"}`}>
                <span className="font-semibold text-primary">Defect corrected &amp; verified</span>
                <span className="block text-xs text-faint">You checked it — the truck is safe to roll.</span>
              </button>
              <button data-testid="crew-lead-review-override" onClick={() => setResolution("override")}
                className={`w-full text-left rounded-md border px-3 py-2 text-sm ${resolution === "override" ? "border-warning bg-warning/10" : "border-border"}`}>
                <span className="font-semibold text-primary">Authorized override</span>
                <span className="block text-xs text-faint">Departing despite the defect — you accept responsibility.</span>
              </button>
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-faint mb-1">Reason (required)</p>
              <Textarea data-testid="crew-lead-review-reason" value={reviewReason} onChange={(e) => setReviewReason(e.target.value)}
                placeholder="What did you find / why is departure OK? Kept on the audit trail." />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReviewOpen(false)}>Cancel</Button>
            <Button data-testid="crew-lead-review-submit" disabled={busy} onClick={submitReview} className="bg-primary hover:bg-[#152238]">
              Record decision
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
