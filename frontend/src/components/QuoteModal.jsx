import React, { useState } from "react";
import { toast } from "sonner";
import { Calculator, Save } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { computeQuote } from "@/lib/pricing";
import { fmtMoney } from "@/lib/format";
import { useApp } from "@/context/AppContext";
import { LF, f } from "@/lib/fields";
import { PREFILL_BY_SIZE, QUOTE_COACH_LINE, quoteSaveFields } from "@/lib/quote";
import { Money } from "@/components/Bits";

export default function QuoteModal({ lead, open, onOpenChange }) {
  const { updateRecord, rates } = useApp();
  const size = f(lead, LF.homeSize);
  const pre = PREFILL_BY_SIZE[size] || { crew: "3", hours: "5" };
  const [crew, setCrew] = useState(pre.crew);
  const [hours, setHours] = useState(pre.hours);
  const [travel, setTravel] = useState(size === "Labor-only (no truck)" ? "labor" : "truck");
  const [flights, setFlights] = useState("0");
  const [piano, setPiano] = useState("none");
  const [saving, setSaving] = useState(false);

  const q = computeQuote({
    crew: Number(crew),
    hours: Number(hours) || 0,
    travel,
    flights: Number(flights) || 0,
    piano,
  }, rates);

  const save = async () => {
    setSaving(true);
    try {
      await updateRecord("leads", lead.id, quoteSaveFields(lead, q, crew, hours));
      toast.success("Quote saved. Lead is now Quoted.");
      onOpenChange(false);
    } catch {}
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="quote-modal" className="max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <Calculator className="w-5 h-5 text-[#E8743B]" /> Quote for {f(lead, LF.name) || "lead"}
          </DialogTitle>
          <DialogDescription>Pick the job details. We show a price range — never one fixed number.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Crew size</Label>
            <Select value={crew} onValueChange={setCrew}>
              <SelectTrigger data-testid="quote-crew-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                {["2", "3", "4", "5"].map((c) => <SelectItem key={c} value={c}>{c} movers</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Estimated hours</Label>
            <Input data-testid="quote-hours-input" type="number" min="1" step="0.5" value={hours} onChange={(e) => setHours(e.target.value)} />
          </div>
          <div>
            <Label>Travel type</Label>
            <Select value={travel} onValueChange={setTravel}>
              <SelectTrigger data-testid="quote-travel-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="truck">With truck ({fmtMoney(rates.travelTruck)})</SelectItem>
                <SelectItem value="labor">Labor-only ({fmtMoney(rates.travelLabor)})</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Stair flights</Label>
            <Input data-testid="quote-flights-input" type="number" min="0" value={flights} onChange={(e) => setFlights(e.target.value)} />
          </div>
          <div className="col-span-2">
            <Label>Piano</Label>
            <Select value={piano} onValueChange={setPiano}>
              <SelectTrigger data-testid="quote-piano-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No piano</SelectItem>
                <SelectItem value="upright">Upright piano ({fmtMoney(rates.pianoUpright)} flat)</SelectItem>
                <SelectItem value="grand">Grand piano ({fmtMoney(rates.pianoGrand)} flat)</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="border border-[#1B2A4A]/15 bg-[#1B2A4A]/[0.04] rounded-lg p-4 space-y-1">
          <div className="flex justify-between text-sm text-slate-600">
            <span>Labor ({crew} × {hours || 0} hrs × {fmtMoney(rates.manHour)})</span><Money value={q.base} />
          </div>
          <div className="flex justify-between text-sm text-slate-600"><span>Travel fee</span><Money value={q.travelFee} /></div>
          {q.stairs > 0 && <div className="flex justify-between text-sm text-slate-600"><span>Stairs</span><Money value={q.stairs} /></div>}
          {q.pianoFee > 0 && <div className="flex justify-between text-sm text-slate-600"><span>Piano</span><Money value={q.pianoFee} /></div>}
          <div className="flex justify-between font-display font-extrabold text-lg text-[#1B2A4A] pt-2 border-t border-slate-200">
            <span>Quote range</span>
            <span data-testid="quote-range-value"><Money value={q.low} /> – <Money value={q.high} /></span>
          </div>
          <div className="flex justify-between text-sm font-semibold text-[#E8743B]">
            <span>Deposit (25% of high)</span><span data-testid="quote-deposit-value"><Money value={q.deposit} /></span>
          </div>
          <p className="text-xs text-slate-500 pt-1">{QUOTE_COACH_LINE}</p>
        </div>
        <Button data-testid="quote-save-btn" onClick={save} disabled={saving || !Number(hours)} className="w-full gap-2 bg-[#E8743B] hover:bg-[#d4632e]">
          <Save className="w-4 h-4" /> {saving ? "Saving…" : "Save quote to lead"}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
