import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Save } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Private } from "@/components/Bits";
import { computeQuote, invoiceLineItems } from "@/lib/pricing";
import { getRates, listCalcItemsApi, saveQuoteBreakdownApi } from "@/lib/api";
import { LF, f } from "@/lib/fields";
import { PREFILL_BY_SIZE, QUOTE_COACH_LINE, quoteSaveFields, quoteStructuredFields } from "@/lib/quote";
import { fmtMoney, fmtMoneyCents } from "@/lib/format";

const clamp = (v, min, max) => Math.min(max, Math.max(min, v));
const HOME_SIZES = ["Studio/1BR", "2BR", "3BR", "4BR+"];
const FALLBACK_PIANOS = [
  { id: "piano-upright", name: "Piano (upright)", price: 500, active: true },
  { id: "piano-grand", name: "Piano (baby grand)", price: 800, active: true },
];

export function useLivePricing(fallbackRates) {
  const [liveRates, setLiveRates] = useState(null);
  const [items, setItems] = useState([]);
  const refresh = useCallback(() => {
    getRates().then(setLiveRates).catch(() => {});
    listCalcItemsApi().then(setItems).catch(() => {});
  }, []);
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 30000);
    return () => clearInterval(id);
  }, [refresh]);
  return { rates: liveRates || fallbackRates, items };
}

const QuoteLines = ({ q, rates, crew }) => (
  <>
    <div className="flex justify-between text-sm text-ink-2">
      <span>Crew charge ({crew} × {q.hours} hrs × {fmtMoney(rates.manHour)})</span>
      <Private><span data-testid="line-crew">{fmtMoneyCents(q.crewCharge)}</span></Private>
    </div>
    {q.minHoursApplied && (
      <p data-testid="min-hours-note" className="text-[11px] text-warning">6-hour minimum applied for this home size.</p>
    )}
    <div className="flex justify-between text-sm text-ink-2">
      <span>Travel fee (covers first {rates.mileageAllowance} miles)</span>
      <Private><span data-testid="line-travel">{fmtMoneyCents(q.travelFee)}</span></Private>
    </div>
    {q.mileageOverage > 0 && (
      <div className="flex justify-between text-sm text-ink-2">
        <span>Mileage — {q.overMiles} mi beyond the first {rates.mileageAllowance} × {fmtMoneyCents(rates.overageRate)}/mi</span>
        <Private><span data-testid="line-overage">{fmtMoneyCents(q.mileageOverage)}</span></Private>
      </div>
    )}
    {q.stairs > 0 && (
      <div className="flex justify-between text-sm text-ink-2">
        <span>Stairs</span>
        <Private><span data-testid="line-stairs">{fmtMoneyCents(q.stairs)}</span></Private>
      </div>
    )}
    {q.itemLines.map((l) => (
      <div key={l.id} className="flex justify-between text-sm text-ink-2">
        <span>{l.name}</span>
        <Private><span data-testid="line-item">{fmtMoneyCents(l.amount)}</span></Private>
      </div>
    ))}
    <div className="flex justify-between text-sm font-semibold text-ink-2 pt-2 border-t border-border">
      <span>Subtotal</span>
      <Private><span data-testid="line-subtotal">{fmtMoneyCents(q.subtotal)}</span></Private>
    </div>
    <div className="flex justify-between items-center pt-2 border-t border-border">
      <span className="font-display font-extrabold text-lg text-primary">Final Quote</span>
      <Private>
        <span data-testid="final-quote-value" className="font-display font-extrabold text-2xl text-accent-ink">
          {q.quoteLow !== q.quoteHigh ? `${fmtMoney(q.quoteLow)} – ${fmtMoney(q.quoteHigh)}` : fmtMoney(q.quoteHigh)}
        </span>
      </Private>
    </div>
    <div className="flex justify-between text-sm font-semibold text-primary">
      <span>Deposit due to book ({rates.depositPercent}% of high end)</span>
      <Private><span data-testid="deposit-value">{fmtMoneyCents(q.deposit)}</span></Private>
    </div>
    <div className="flex justify-between text-sm text-ink-2">
      <span>Balance due on completion</span>
      <Private><span data-testid="balance-value">{fmtMoneyCents(q.balance)}</span></Private>
    </div>
    <p className="text-xs text-faint pt-1">{QUOTE_COACH_LINE}</p>
  </>
);

// THE one universal quote calculator. Every entry point (Calculator page, lead Quote
// modal, anywhere else) renders this exact component — identical inputs, math, output.
export const QuoteCalculator = ({ lead = null, onSaved }) => {
  const { updateRecord, rates: ctxRates } = useApp();
  const { rates, items } = useLivePricing(ctxRates);
  const [size, setSize] = useState("");
  const [crew, setCrew] = useState("3");
  const [hours, setHours] = useState("5");
  const [travel, setTravel] = useState("truck");
  const [flights, setFlights] = useState("0");
  const [elevator, setElevator] = useState("no");
  const [piano, setPiano] = useState("none");
  const [miles, setMiles] = useState("0");
  const [saving, setSaving] = useState(false);

  const applySize = (s) => {
    setSize(s);
    const pre = PREFILL_BY_SIZE[s];
    if (pre) {
      setCrew(pre.crew);
      setHours(pre.hours);
    }
  };

  useEffect(() => {
    const leadSize = f(lead, LF.homeSize) || "";
    if (PREFILL_BY_SIZE[leadSize]) applySize(leadSize);
    if (lead) setTravel(leadSize === "Labor-only (no truck)" ? "labor" : "truck");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lead?.id]);

  const pianoItems = (items.filter((it) => it.active && it.id.startsWith("piano")).length
    ? items.filter((it) => it.active && it.id.startsWith("piano"))
    : FALLBACK_PIANOS);
  const minHours = ["3BR", "4BR+"].includes(size) ? 6 : 0;

  const q = computeQuote({
    crew: clamp(Number(crew) || 2, 2, 4),
    hours: clamp(Number(hours) || 0, 0, 24),
    minHours,
    travel,
    miles: clamp(Number(miles) || 0, 0, 5000),
    flights: clamp(Number(flights) || 0, 0, 50),
    itemQty: piano === "none" ? {} : { [piano]: 1 },
  }, rates, pianoItems);

  const save = async () => {
    if (!lead) return;
    setSaving(true);
    try {
      const base = quoteSaveFields(lead, q, crew, q.hours, { elevator: elevator === "yes" });
      try {
        await updateRecord("leads", lead.id, { ...base, ...quoteStructuredFields(q, crew) });
      } catch {
        await updateRecord("leads", lead.id, base);
        toast.info("Quote saved, but Crew Size / Est Hours / Deposit Amount didn't stick — check those Airtable columns.");
      }
      saveQuoteBreakdownApi(lead.id, {
        lines: invoiceLineItems(q), finalQuote: q.finalQuote, quoteLow: q.quoteLow, quoteHigh: q.quoteHigh,
        deposit: q.deposit, crew: Number(crew), hours: q.hours, elevator: elevator === "yes",
        customerName: f(lead, LF.name) || "", customerPhone: f(lead, LF.phone) || "",
        fromAddress: f(lead, LF.from) || "", toAddress: f(lead, LF.to) || "", moveDate: f(lead, LF.moveDate) || "",
      }).then((r) => {
        if (r.sms_sent) toast.success("Quote PDF texted to the customer automatically.");
        else if (r.sms_note && !r.sms_note.startsWith("Customer already")) toast.info(r.sms_note);
      }).catch(() => {});
      toast.success(`Quote saved to ${f(lead, LF.name) || "lead"}. Status is now Quoted.`);
      onSaved?.();
    } catch {}
    setSaving(false);
  };

  return (
    <div data-testid="quote-calculator" className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>Home size</Label>
          <Select value={size} onValueChange={applySize}>
            <SelectTrigger data-testid="calc-size-select"><SelectValue placeholder="Pick a size" /></SelectTrigger>
            <SelectContent>
              {HOME_SIZES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>Crew size</Label>
          <Select value={crew} onValueChange={setCrew}>
            <SelectTrigger data-testid="calc-crew-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              {["2", "3", "4"].map((c) => <SelectItem key={c} value={c}>{c} movers</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>Estimated hours{minHours ? " (min 6)" : ""}</Label>
          <Input data-testid="calc-hours-input" type="number" min={minHours || 0.5} max="24" step="0.5" value={hours} onChange={(e) => setHours(e.target.value)} />
        </div>
        <div>
          <Label>Travel type</Label>
          <Select value={travel} onValueChange={setTravel}>
            <SelectTrigger data-testid="calc-travel-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="truck">Truck ({fmtMoney(rates.travelTruck)})</SelectItem>
              <SelectItem value="labor">Labor-only ({fmtMoney(rates.travelLabor)})</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>Flights of stairs (all)</Label>
          <Input data-testid="calc-flights-input" type="number" min="0" max="50" value={flights} onChange={(e) => setFlights(e.target.value)} />
          <p className="text-[11px] text-faint mt-0.5">{fmtMoney(rates.stairFlight)} per flight.</p>
        </div>
        <div>
          <Label>Elevator available</Label>
          <Select value={elevator} onValueChange={setElevator}>
            <SelectTrigger data-testid="calc-elevator-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="no">No elevator</SelectItem>
              <SelectItem value="yes">Yes — elevator</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>Piano</Label>
          <Select value={piano} onValueChange={setPiano}>
            <SelectTrigger data-testid="calc-piano-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">No piano</SelectItem>
              {pianoItems.map((it) => (
                <SelectItem key={it.id} value={it.id}>{it.name} ({fmtMoney(it.price)})</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>Round-trip miles</Label>
          <Input data-testid="calc-miles-input" type="number" min="0" max="5000" value={miles} onChange={(e) => setMiles(e.target.value)} />
          <p className="text-[11px] text-faint mt-0.5">First {rates.mileageAllowance} miles are free, then {fmtMoneyCents(rates.overageRate)}/mi.</p>
        </div>
      </div>

      <div className="border border-primary/15 bg-primary/[0.04] rounded-lg p-4 space-y-1">
        <QuoteLines q={q} rates={rates} crew={crew} />
      </div>

      <Button data-testid="calc-save-btn" onClick={save} disabled={saving || !lead || !Number(hours)} className="w-full gap-2 bg-accent hover:bg-accent-press">
        <Save className="w-4 h-4" /> {saving ? "Saving…" : lead ? `Save quote to ${f(lead, LF.name) || "lead"}` : "Pick a lead to save"}
      </Button>
    </div>
  );
};
