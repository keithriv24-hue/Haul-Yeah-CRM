import React, { useState } from "react";
import { toast } from "sonner";
import { Calculator, Save } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { computeQuote, invoiceLineItems } from "@/lib/pricing";
import { fmtMoney } from "@/lib/format";
import { useApp } from "@/context/AppContext";
import { saveQuoteBreakdownApi } from "@/lib/api";
import { LF, f } from "@/lib/fields";
import { PREFILL_BY_SIZE, quoteSaveFields } from "@/lib/quote";
import { QtyStepper, QuoteLines, useLivePricing } from "@/pages/Calculator";

const clamp = (v, min, max) => Math.min(max, Math.max(min, v));

export default function QuoteModal({ lead, open, onOpenChange }) {
  const { updateRecord, rates: ctxRates } = useApp();
  const { rates, items } = useLivePricing(ctxRates);
  const size = f(lead, LF.homeSize);
  const pre = PREFILL_BY_SIZE[size] || { crew: "3", hours: "5" };
  const [crew, setCrew] = useState(pre.crew);
  const [hours, setHours] = useState(pre.hours);
  const [travel, setTravel] = useState(size === "Labor-only (no truck)" ? "labor" : "truck");
  const [miles, setMiles] = useState("0");
  const [flights, setFlights] = useState("0");
  const [packing, setPacking] = useState("0");
  const [itemQty, setItemQty] = useState({});
  const [saving, setSaving] = useState(false);

  const activeItems = items.filter((it) => it.active);

  const q = computeQuote({
    crew: clamp(Number(crew) || 2, 2, 4),
    hours: clamp(Number(hours) || 0, 0, 24),
    minHours: ["3BR", "4BR+"].includes(size) ? 6 : 0,
    travel,
    miles: clamp(Number(miles) || 0, 0, 5000),
    flights: clamp(Number(flights) || 0, 0, 50),
    packingHours: clamp(Number(packing) || 0, 0, 200),
    itemQty,
  }, rates, activeItems);

  const save = async () => {
    setSaving(true);
    try {
      await updateRecord("leads", lead.id, quoteSaveFields(lead, q, crew, q.hours));
      saveQuoteBreakdownApi(lead.id, {
        lines: invoiceLineItems(q), finalQuote: q.finalQuote, deposit: q.deposit,
        crew: Number(crew), hours: q.hours,
        customerName: f(lead, LF.name) || "", customerPhone: f(lead, LF.phone) || "",
        fromAddress: f(lead, LF.from) || "", toAddress: f(lead, LF.to) || "", moveDate: f(lead, LF.moveDate) || "",
      }).then((r) => {
        if (r.sms_sent) toast.success("Quote PDF texted to the customer automatically.");
        else if (r.sms_note && !r.sms_note.startsWith("Customer already")) toast.info(r.sms_note);
      }).catch(() => {});
      toast.success("Quote saved. Lead is now Quoted.");
      onOpenChange(false);
    } catch {}
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="quote-modal" className="max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <Calculator className="w-5 h-5 text-[#E8743B]" /> Quote for {f(lead, LF.name) || "lead"}
          </DialogTitle>
          <DialogDescription>Fill in the job — the price updates as you type.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Crew size</Label>
            <Select value={crew} onValueChange={setCrew}>
              <SelectTrigger data-testid="quote-crew-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                {["2", "3", "4"].map((c) => <SelectItem key={c} value={c}>{c} movers</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Estimated hours</Label>
            <Input data-testid="quote-hours-input" type="number" min="0.5" max="24" step="0.5" value={hours} onChange={(e) => setHours(e.target.value)} />
          </div>
          <div>
            <Label>Travel type</Label>
            <Select value={travel} onValueChange={setTravel}>
              <SelectTrigger data-testid="quote-travel-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="truck">Truck ({fmtMoney(rates.travelTruck)})</SelectItem>
                <SelectItem value="labor">Labor-only ({fmtMoney(rates.travelLabor)})</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Round-trip miles</Label>
            <Input data-testid="quote-miles-input" type="number" min="0" max="5000" value={miles} onChange={(e) => setMiles(e.target.value)} />
          </div>
          <div>
            <Label>Flights of stairs</Label>
            <Input data-testid="quote-flights-input" type="number" min="0" max="50" value={flights} onChange={(e) => setFlights(e.target.value)} />
          </div>
          <div>
            <Label>Packing (man-hours)</Label>
            <Input data-testid="quote-packing-input" type="number" min="0" max="200" step="0.5" value={packing} onChange={(e) => setPacking(e.target.value)} />
          </div>
        </div>
        {activeItems.length > 0 && (
          <div className="space-y-2">
            {activeItems.map((it) => (
              <div key={it.id} data-testid="quote-item-row" className="flex items-center justify-between">
                <span className="text-sm text-[#1B2A4A]">{it.name} <span className="text-slate-400">({fmtMoney(it.price)})</span></span>
                <QtyStepper
                  qty={itemQty[it.id] || 0}
                  onChange={(v) => setItemQty((s) => ({ ...s, [it.id]: v }))}
                  testId={`quote-item-${it.id}`}
                />
              </div>
            ))}
          </div>
        )}
        <div className="border border-[#1B2A4A]/15 bg-[#1B2A4A]/[0.04] rounded-lg p-4 space-y-1">
          <QuoteLines q={q} rates={rates} crew={crew} hours={q.hours} />
        </div>
        <Button data-testid="quote-save-btn" onClick={save} disabled={saving || !Number(hours)} className="w-full gap-2 bg-[#E8743B] hover:bg-[#d4632e]">
          <Save className="w-4 h-4" /> {saving ? "Saving…" : "Save quote to lead"}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
