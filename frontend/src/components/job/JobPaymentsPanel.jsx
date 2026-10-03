import React, { useState } from "react";
import { DollarSign, Plus, RotateCcw, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { fmtMoney } from "@/lib/format";
import { recordJobPaymentApi, recordJobRefundApi, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";

const fmtWhen = (iso) =>
  iso ? new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }) : "—";

const METHODS = [
  { value: "cash", label: "Cash" },
  { value: "zelle", label: "Zelle" },
  { value: "ach", label: "ACH / bank transfer" },
  { value: "check", label: "Check" },
  { value: "other", label: "Other" },
];

const MethodBadge = ({ method }) => (
  <span className="text-[10px] uppercase tracking-wide rounded-full bg-surface-sunk px-2 py-0.5 text-ink-2">{method}</span>
);

const Stat = ({ label, value, testId, tone = "" }) => (
  <div className="rounded-md border border-border bg-surface-sunk p-3">
    <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">{label}</p>
    <p data-testid={testId} className={`text-lg font-bold ${tone || "text-primary"}`}>{value}</p>
  </div>
);

export function JobPaymentsPanel({ ident, initial, canRecord }) {
  const [block, setBlock] = useState(initial || { money: null, entries: [] });
  const [payOpen, setPayOpen] = useState(false);
  const [refundOpen, setRefundOpen] = useState(false);

  const money = block?.money || {};
  const entries = block?.entries || [];

  return (
    <div className="space-y-4" data-testid="job-payments-panel">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h4 className="font-bold text-primary flex items-center gap-2"><DollarSign className="w-4 h-4 text-accent-ink" /> Payments &amp; balance</h4>
        {canRecord && (
          <div className="flex items-center gap-2">
            <Button data-testid="record-payment-btn" size="sm" className="gap-1.5" onClick={() => setPayOpen(true)}>
              <Plus className="w-3.5 h-3.5" /> Record payment
            </Button>
            <Button data-testid="record-refund-btn" size="sm" variant="outline" className="gap-1.5" onClick={() => setRefundOpen(true)}>
              <RotateCcw className="w-3.5 h-3.5" /> Record refund
            </Button>
          </div>
        )}
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Job total" value={money.job_total != null ? fmtMoney(money.job_total) : "—"} testId="money-job-total" />
        <Stat label="Collected" value={money.collected != null ? fmtMoney(money.collected) : "—"} testId="money-collected" tone="text-success" />
        <Stat label="Balance due" value={money.balance_due != null ? fmtMoney(money.balance_due) : "—"} testId="money-balance-due" tone={money.balance_due > 0 ? "text-warning" : "text-primary"} />
        <div className="rounded-md border border-border bg-surface-sunk p-3 flex flex-col justify-center" data-testid="money-paid-status">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">Status</p>
          {money.paid_in_full ? (
            <span className="inline-flex items-center gap-1.5 text-success font-bold"><CheckCircle2 className="w-4 h-4" /> Paid in full</span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-warning font-bold"><AlertCircle className="w-4 h-4" /> {money.collected > 0 ? "Partially paid" : "Unpaid"}</span>
          )}
          {money.overpaid && <span className="text-[11px] text-info mt-0.5">Overpaid — check for a refund due</span>}
        </div>
      </div>

      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wide text-faint mb-1">Ledger ({entries.length})</p>
        {entries.length === 0 ? (
          <p className="text-sm text-faint" data-testid="ledger-empty">No payments recorded yet.</p>
        ) : (
          <div className="space-y-1.5">
            {entries.map((e) => (
              <div key={e.id} data-testid="ledger-row" className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm border-b border-border/60 pb-1.5 last:border-0">
                <span className={`font-bold ${e.kind === "refund" || e.signed_amount < 0 ? "text-destructive" : "text-success"}`}>
                  {e.signed_amount < 0 ? "−" : "+"}{fmtMoney(Math.abs(e.signed_amount))}
                </span>
                <MethodBadge method={e.method} />
                <span className="text-ink-2 capitalize">{e.kind}{e.type && e.type !== e.kind ? ` · ${e.type}` : ""}</span>
                <Badge variant="outline" className="text-[10px]">{e.status}</Badge>
                {e.needs_project_review && <Badge variant="outline" className="text-[10px] text-warning border-warning/40">needs Project link</Badge>}
                <span className="text-faint ml-auto">{fmtWhen(e.occurred_at)}</span>
                <span className="w-full text-[11px] text-faint">
                  {e.source === "manual" ? `Entered by ${e.entered_by || "—"}` : `Source: ${e.source}`}
                  {e.note ? ` · “${e.note}”` : ""}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {canRecord && (
        <RecordPaymentDialog ident={ident} open={payOpen} onOpenChange={setPayOpen} onDone={setBlock} />
      )}
      {canRecord && (
        <RecordRefundDialog ident={ident} open={refundOpen} onOpenChange={setRefundOpen} collected={money.collected || 0} onDone={setBlock} />
      )}
    </div>
  );
}

function RecordPaymentDialog({ ident, open, onOpenChange, onDone }) {
  const [method, setMethod] = useState("cash");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const amt = Number(amount);
    if (!amt || amt <= 0) { toast.error("Enter an amount over $0."); return; }
    setBusy(true);
    try {
      const res = await recordJobPaymentApi(ident, { method, amount: amt, type: "payment", note: note || null });
      toast.success(`Recorded ${fmtMoney(amt)} (${method}).`);
      onDone(res);
      onOpenChange(false);
      setAmount(""); setNote("");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="record-payment-dialog">
        <DialogHeader><DialogTitle>Record a payment</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Method</Label>
            <Select value={method} onValueChange={setMethod}>
              <SelectTrigger data-testid="payment-method-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                {METHODS.map((m) => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="pay-amount">Amount (USD)</Label>
            <Input id="pay-amount" data-testid="payment-amount-input" type="number" min="0.01" step="0.01"
              value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="500.00" />
          </div>
          <div>
            <Label htmlFor="pay-note">Note / reference (optional)</Label>
            <Input id="pay-note" data-testid="payment-note-input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Zelle confirmation #…" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button data-testid="payment-submit-btn" onClick={submit} disabled={busy} className="gap-1.5">
            {busy && <Loader2 className="w-4 h-4 animate-spin" />} Record payment
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RecordRefundDialog({ ident, open, onOpenChange, collected, onDone }) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const amt = Number(amount);
    if (!amt || amt <= 0) { toast.error("Enter a refund amount over $0."); return; }
    if (reason.trim().length < 3) { toast.error("Add a short reason for the refund."); return; }
    setBusy(true);
    try {
      const res = await recordJobRefundApi(ident, { amount: amt, reason: reason.trim(), method: "square" });
      toast.success(`Refunded ${fmtMoney(amt)}.`);
      onDone(res);
      onOpenChange(false);
      setAmount(""); setReason("");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="record-refund-dialog">
        <DialogHeader><DialogTitle>Record a refund</DialogTitle></DialogHeader>
        <p className="text-xs text-faint">Reverses money already collected. The original payment is kept in the ledger. Collected so far: <strong className="text-primary">{fmtMoney(collected)}</strong>.</p>
        <div className="space-y-3">
          <div>
            <Label htmlFor="refund-amount">Refund amount (USD)</Label>
            <Input id="refund-amount" data-testid="refund-amount-input" type="number" min="0.01" step="0.01"
              value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="200.00" />
          </div>
          <div>
            <Label htmlFor="refund-reason">Reason</Label>
            <Input id="refund-reason" data-testid="refund-reason-input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Customer cancelled add-on" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button data-testid="refund-submit-btn" variant="destructive" onClick={submit} disabled={busy} className="gap-1.5">
            {busy && <Loader2 className="w-4 h-4 animate-spin" />} Record refund
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
