import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { BadgeDollarSign, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { attributionApi, saveAttributionApi, commissionRatesApi, teamMembersApi, apiErrorMessage } from "@/lib/api";
import { LF, f } from "@/lib/fields";
import { fmtMoneyCents, fmtDate } from "@/lib/format";

const SIZE_TO_MOVE_TYPE = {
  "Studio/1BR": "1-bedroom", "2BR": "2-bedroom", "3BR": "3-bedroom", "4BR+": "4+", "Labor-only (no truck)": "Labor-only",
};

export const commissionFor = (quote, moveType, rates) => {
  const q = Number(quote) || 0;
  if (!rates || q <= 0) return 0;
  if (q >= rates.big_min) return Math.round(q * rates.big_pct) / 100;
  if (q >= rates.medium_min) return Math.round(q * rates.medium_pct) / 100;
  return Number(rates.small_flat?.[moveType]) || 0;
};

const STATUS_CHIP = {
  pending: "bg-amber-100 text-amber-800 border-amber-300",
  locked: "bg-emerald-100 text-emerald-800 border-emerald-300",
  voided: "bg-red-100 text-red-700 border-red-300",
  none: "bg-slate-100 text-slate-500 border-slate-300",
};
const STATUS_TEXT = {
  pending: "Pending — waiting on full payment",
  locked: "Locked in",
  voided: "Voided — refunded",
  none: "No deposit yet — nothing earned",
};

export const CommissionCard = ({ lead, isOwner }) => {
  const [form, setForm] = useState(null);
  const [reps, setReps] = useState([]);
  const [rates, setRates] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    attributionApi(lead.id)
      .then((d) => {
        const a = d.attribution;
        setForm({
          ...a,
          move_type: a.move_type || SIZE_TO_MOVE_TYPE[f(lead, LF.homeSize)] || "",
          quote_amount: a.quote_amount ?? (Number(f(lead, LF.quote)) || ""),
          job_date: a.job_date || (f(lead, LF.moveDate) || "").slice(0, 10),
        });
      })
      .catch(() => {});
  }, [lead]);

  useEffect(() => {
    load();
    commissionRatesApi().then((d) => setRates(d.rates)).catch(() => {});
    teamMembersApi().then((d) => setReps(d.members.filter((m) => m.teams.includes("sales")))).catch(() => {});
  }, [load]);

  if (!form) return null;

  const status = !form.closed_by ? null : form.refunded ? "voided" : form.fully_paid ? "locked" : form.deposit_paid ? "pending" : "none";
  const amount = commissionFor(form.quote_amount, form.move_type, rates);
  const set = (k, v) => setForm((s) => ({ ...s, [k]: v }));

  const save = async () => {
    setBusy(true);
    const payload = {
      lead_name: f(lead, LF.name) || "",
      quote_sent_by: form.quote_sent_by || "",
      closed_by: form.closed_by || "",
      move_type: form.move_type || "",
      quote_amount: form.quote_amount === "" ? 0 : Number(form.quote_amount),
      job_date: form.job_date || "",
    };
    if (isOwner) {
      payload.deposit_paid = !!form.deposit_paid;
      payload.fully_paid = !!form.fully_paid;
      payload.refunded = !!form.refunded;
    }
    try {
      await saveAttributionApi(lead.id, payload);
      toast.success("Commission info saved.");
      load();
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
    <div className="bg-white border border-slate-200 rounded-lg p-5" data-testid="commission-card">
      <h2 className="font-display font-bold text-[#1B2A4A] mb-3 flex items-center gap-2">
        <BadgeDollarSign className="w-4 h-4 text-[#E8743B]" /> Sales credit & commission
      </h2>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>Quote sent by <span className="text-slate-400 font-normal">(stat only)</span></Label>
          <RepSelect field="quote_sent_by" testId="commission-quote-sent-by" />
        </div>
        <div>
          <Label>Closed by <span className="text-slate-400 font-normal">(earns it)</span></Label>
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
          <Label>Quote amount ($)</Label>
          <Input data-testid="commission-quote-amount" type="number" min="0" value={form.quote_amount} onChange={(e) => set("quote_amount", e.target.value)} />
        </div>
        <div className="col-span-2">
          <Label>Job date</Label>
          <Input data-testid="commission-job-date" type="date" value={form.job_date} onChange={(e) => set("job_date", e.target.value)} />
        </div>
      </div>

      {isOwner && (
        <div className="mt-3 space-y-2 border-t border-slate-100 pt-3" data-testid="commission-owner-flags">
          {[
            { k: "deposit_paid", label: "Deposit paid", date: form.deposit_paid_at },
            { k: "fully_paid", label: "Fully paid", date: form.fully_paid_at },
            { k: "refunded", label: "Refunded (voids commission)", date: null },
          ].map(({ k, label, date }) => (
            <div key={k} className="flex items-center justify-between text-sm">
              <span className={k === "refunded" ? "text-red-600 font-semibold" : "text-slate-600"}>
                {label}
                {date && form[k] && <span className="text-xs text-slate-400 ml-1.5">({fmtDate(date)})</span>}
              </span>
              <Switch data-testid={`commission-${k}-switch`} checked={!!form[k]} onCheckedChange={(v) => set(k, v)} />
            </div>
          ))}
          <p className="text-[11px] text-slate-400">Deposit and full payment flip on automatically when a Square invoice for this lead gets paid.</p>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-sm text-slate-600">Commission:</span>
        <span data-testid="commission-preview" className="font-display font-extrabold text-lg text-[#1B2A4A]">{fmtMoneyCents(amount)}</span>
        {status && (
          <span data-testid="commission-status-chip" className={`border rounded-full px-2 py-0.5 text-[11px] font-bold ${STATUS_CHIP[status]}`}>
            {STATUS_TEXT[status]}
          </span>
        )}
      </div>

      <Button data-testid="commission-save-btn" size="sm" className="mt-3 gap-1.5 bg-[#E8743B] hover:bg-[#d4632e]" disabled={busy} onClick={save}>
        <Save className="w-4 h-4" /> Save commission info
      </Button>
    </div>
  );
};
