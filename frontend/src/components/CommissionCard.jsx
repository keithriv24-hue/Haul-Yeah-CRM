import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { BadgeDollarSign, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { attributionApi, saveAttributionApi, teamMembersApi, apiErrorMessage } from "@/lib/api";
import { LF, f } from "@/lib/fields";
import { fmtMoneyCents } from "@/lib/format";

const SIZE_TO_MOVE_TYPE = {
  "Studio/1BR": "1-bedroom", "2BR": "2-bedroom", "3BR": "3-bedroom", "4BR+": "4+", "Labor-only (no truck)": "Labor-only",
};

const STATUS_CHIP = {
  pending: "bg-warning/12 text-warning border-warning/30",
  locked: "bg-success/12 text-success border-success/30",
  voided: "bg-destructive/12 text-destructive border-destructive/30",
  none: "bg-surface-sunk text-faint border-border-strong",
};
const STATUS_TEXT = {
  pending: "Pending — waiting on full payment",
  locked: "Locked in",
  voided: "Voided — refunded",
  none: "No deposit yet — nothing earned",
};

export const CommissionCard = ({ lead, isOwner }) => {
  const [form, setForm] = useState(null);
  const [calc, setCalc] = useState({ base: 0, commission: 0, status: null, job_total: 0 });
  const [origClosedBy, setOrigClosedBy] = useState("");
  const [reps, setReps] = useState([]);
  const [busy, setBusy] = useState(false);

  const apply = useCallback((d) => {
    const a = d.attribution;
    setForm((prev) => ({
      ...(prev || {}),
      ...a,
      move_type: a.move_type || (prev?.move_type) || SIZE_TO_MOVE_TYPE[f(lead, LF.homeSize)] || "",
      job_date: a.job_date || (f(lead, LF.moveDate) || "").slice(0, 10),
    }));
    setOrigClosedBy(a.closed_by || "");
    setCalc({ base: d.base ?? 0, commission: d.commission ?? 0, status: d.status, job_total: d.job_total ?? 0 });
  }, [lead]);

  const load = useCallback(() => {
    attributionApi(lead.id).then(apply).catch(() => {});
  }, [lead, apply]);

  useEffect(() => {
    load();
    teamMembersApi().then((d) => setReps(d.members.filter((m) => m.teams.includes("sales")))).catch(() => {});
  }, [load]);

  if (!form) return null;

  const status = calc.status;
  const amount = calc.commission;
  const set = (k, v) => setForm((s) => ({ ...s, [k]: v }));

  const save = async () => {
    // reassigning an already-credited commission to a different person needs the owner + a reason
    const reassigning = origClosedBy && (form.closed_by || "") !== origClosedBy;
    let reason;
    if (reassigning) {
      if (!isOwner) { toast.error("This commission is already credited — only the owner can reassign it."); return; }
      reason = window.prompt("Why are you reassigning this commission credit? (required, logged)");
      if (!reason || !reason.trim()) { toast.error("A reason is required to reassign credit."); return; }
    }
    setBusy(true);
    const payload = {
      lead_name: f(lead, LF.name) || "",
      quote_sent_by: form.quote_sent_by || "",
      closed_by: form.closed_by || "",
      move_type: form.move_type || "",
      job_date: form.job_date || "",
    };
    if (reason) payload.reason = reason.trim();
    if (isOwner) payload.refunded = !!form.refunded;
    try {
      const d = await saveAttributionApi(lead.id, payload);
      toast.success("Commission info saved.");
      apply(d);
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  const RepSelect = ({ field, testId }) => (
    <Select value={form[field] || "none"} onValueChange={(v) => set(field, v === "none" ? "" : v)}>
      <SelectTrigger data-testid={testId}><SelectValue /></SelectTrigger>
      <SelectContent>
        <SelectItem value="none">— nobody yet —</SelectItem>
        {reps.map((r) => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}
      </SelectContent>
    </Select>
  );

  return (
    <div className="surface p-5" data-testid="commission-card">
      <h2 className="font-display font-bold text-primary mb-3 flex items-center gap-2">
        <BadgeDollarSign className="w-4 h-4 text-accent-ink" /> Sales credit & commission
      </h2>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>Quote sent by <span className="text-faint font-normal">(stat only)</span></Label>
          <RepSelect field="quote_sent_by" testId="commission-quote-sent-by" />
        </div>
        <div>
          <Label>Closed by <span className="text-faint font-normal">(earns it)</span></Label>
          <RepSelect field="closed_by" testId="commission-closed-by" />
        </div>
        <div>
          <Label>Move type</Label>
          <Select value={form.move_type || "none"} onValueChange={(v) => set("move_type", v === "none" ? "" : v)}>
            <SelectTrigger data-testid="commission-move-type"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">— pick one —</SelectItem>
              {["Labor-only", "Studio", "1-bedroom", "2-bedroom", "3-bedroom", "4+"].map((m) => (
                <SelectItem key={m} value={m}>{m}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>Commission base <span className="text-faint font-normal">(net collected)</span></Label>
          <div data-testid="commission-base" className="h-9 flex items-center px-3 rounded-md border border-border bg-surface-sunk text-sm font-semibold text-primary">
            {fmtMoneyCents(calc.base)}
            {calc.job_total > 0 && <span className="text-faint font-normal ml-1.5">of {fmtMoneyCents(calc.job_total)}</span>}
          </div>
        </div>
        <div className="col-span-2">
          <Label>Job date</Label>
          <Input data-testid="commission-job-date" type="date" value={form.job_date} onChange={(e) => set("job_date", e.target.value)} />
        </div>
      </div>

      {isOwner && (
        <div className="mt-3 space-y-2 border-t border-border pt-3" data-testid="commission-owner-flags">
          <div className="flex items-center justify-between text-sm">
            <span className="text-destructive font-semibold">Void this commission (manual override)</span>
            <Switch data-testid="commission-refunded-switch" checked={!!form.refunded} onCheckedChange={(v) => set("refunded", v)} />
          </div>
          <p className="text-[11px] text-faint">Pending/locked status and the dollar base now come straight from the payment ledger — refunds shrink the base automatically. Use this toggle only to force-void a credit.</p>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-sm text-ink-2">Commission:</span>
        <span data-testid="commission-preview" className="font-display font-extrabold text-lg text-primary">{fmtMoneyCents(amount)}</span>
        {status && (
          <span data-testid="commission-status-chip" className={`border rounded-full px-2 py-0.5 text-[11px] font-bold ${STATUS_CHIP[status]}`}>
            {STATUS_TEXT[status]}
          </span>
        )}
      </div>

      <Button data-testid="commission-save-btn" size="sm" className="mt-3 gap-1.5 bg-accent hover:bg-accent-press" disabled={busy} onClick={save}>
        <Save className="w-4 h-4" /> Save commission info
      </Button>
    </div>
  );
};
