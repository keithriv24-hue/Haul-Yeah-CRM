import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Save } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, Private } from "@/components/Bits";
import { computeQuote, invoiceLineItems } from "@/lib/pricing";
import { getRates, listCalcItemsApi, saveQuoteBreakdownApi } from "@/lib/api";
import { LF, f } from "@/lib/fields";
import { PREFILL_BY_SIZE, QUOTE_COACH_LINE, CREW_GUIDE, quoteSaveFields } from "@/lib/quote";
import { ScriptPanel } from "@/components/ScriptPanel";
import { fmtDate, fmtMoney, fmtMoneyCents } from "@/lib/format";

const clamp = (v, min, max) => Math.min(max, Math.max(min, v));

export const QtyStepper = ({ qty, onChange, testId }) => (
  <div className="flex items-center gap-2">
    <button
      type="button"
      data-testid={`${testId}-minus`}
      onClick={() => onChange(Math.max(0, qty - 1))}
      disabled={qty <= 0}
      className="w-9 h-9 rounded-full border border-slate-300 text-xl font-bold text-[#1B2A4A] disabled:opacity-30 hover:bg-slate-50 transition-colors"
    >
      −
    </button>
    <span data-testid={`${testId}-qty`} className={`w-7 text-center font-bold text-lg ${qty > 0 ? "text-[#E8743B]" : "text-slate-400"}`}>{qty}</span>
    <button
      type="button"
      data-testid={`${testId}-plus`}
      onClick={() => onChange(Math.min(20, qty + 1))}
      className="w-9 h-9 rounded-full border border-slate-300 text-xl font-bold text-[#1B2A4A] hover:bg-slate-50 transition-colors"
    >
      +
    </button>
  </div>
);

export const QuoteLines = ({ q, rates, crew, hours }) => (
  <>
    <div className="flex justify-between text-sm text-slate-600">
      <span>Crew charge ({crew} × {q.hours ?? hours ?? 0} hrs × {fmtMoney(rates.manHour)})</span>
      <Private><span data-testid="line-crew">{fmtMoneyCents(q.crewCharge)}</span></Private>
    </div>
    {q.minHoursApplied && (
      <p data-testid="min-hours-note" className="text-[11px] text-amber-700">6-hour minimum applied for this home size.</p>
    )}
    <div className="flex justify-between text-sm text-slate-600">
      <span>Travel fee (covers first {rates.mileageAllowance} miles)</span>
      <Private><span data-testid="line-travel">{fmtMoneyCents(q.travelFee)}</span></Private>
    </div>
    {q.mileageOverage > 0 && (
      <div className="flex justify-between text-sm text-slate-600">
        <span>Mileage — {q.overMiles} mi beyond the first {rates.mileageAllowance} × {fmtMoneyCents(rates.overageRate)}/mi</span>
        <Private><span data-testid="line-overage">{fmtMoneyCents(q.mileageOverage)}</span></Private>
      </div>
    )}
    {q.stairs > 0 && (
      <div className="flex justify-between text-sm text-slate-600">
        <span>Stairs</span>
        <Private><span data-testid="line-stairs">{fmtMoneyCents(q.stairs)}</span></Private>
      </div>
    )}
    {q.packing > 0 && (
      <div className="flex justify-between text-sm text-slate-600">
        <span>Packing help</span>
        <Private><span data-testid="line-packing">{fmtMoneyCents(q.packing)}</span></Private>
      </div>
    )}
    {q.itemLines.map((l) => (
      <div key={l.id} className="flex justify-between text-sm text-slate-600">
        <span>{l.name} × {l.qty}</span>
        <Private><span data-testid="line-item">{fmtMoneyCents(l.amount)}</span></Private>
      </div>
    ))}
    <div className="flex justify-between text-sm font-semibold text-slate-700 pt-2 border-t border-slate-200">
      <span>Subtotal</span>
      <Private><span data-testid="line-subtotal">{fmtMoneyCents(q.subtotal)}</span></Private>
    </div>
    <div className="flex justify-between items-center pt-2 border-t border-slate-200">
      <span className="font-display font-extrabold text-lg text-[#1B2A4A]">Final Quote</span>
      <Private>
        <span data-testid="final-quote-value" className="font-display font-extrabold text-3xl text-[#E8743B]">{fmtMoney(q.finalQuote)}</span>
      </Private>
    </div>
    <div className="flex justify-between text-sm font-semibold text-[#1B2A4A]">
      <span>Deposit due to book ({rates.depositPercent}%)</span>
      <Private><span data-testid="deposit-value">{fmtMoneyCents(q.deposit)}</span></Private>
    </div>
    <div className="flex justify-between text-sm text-slate-600">
      <span>Balance due on completion</span>
      <Private><span data-testid="balance-value">{fmtMoneyCents(q.balance)}</span></Private>
    </div>
    <p className="text-xs text-slate-500 pt-1">{QUOTE_COACH_LINE}</p>
  </>
);

export const CrewGuideCard = () => (
  <div data-testid="crew-guide-card" className="bg-white border border-slate-200 rounded-lg p-4">
    <p className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-2">Crew guide (quick reference)</p>
    <div className="space-y-1">
      {CREW_GUIDE.map((g) => (
        <div key={g.size} className="flex justify-between text-sm">
          <span className="text-slate-600">{g.size}</span>
          <span className="font-semibold text-[#1B2A4A]">{g.plan}</span>
        </div>
      ))}
    </div>
  </div>
);

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

export default function Calculator() {
  const { loadTable, records, updateRecord, rates: ctxRates } = useApp();
  const { rates, items } = useLivePricing(ctxRates);
  const [leadId, setLeadId] = useState("");
  const [jobName, setJobName] = useState("");
  const [moveDate, setMoveDate] = useState("");
  const [crew, setCrew] = useState("3");
  const [hours, setHours] = useState("5");
  const [travel, setTravel] = useState("truck");
  const [miles, setMiles] = useState("0");
  const [flights, setFlights] = useState("0");
  const [packing, setPacking] = useState("0");
  const [itemQty, setItemQty] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadTable("leads");
  }, [loadTable]);

  const leads = records("leads").filter((l) => !["Booked", "Lost", "Cold"].includes(f(l, LF.status)));
  const lead = records("leads").find((l) => l.id === leadId) || null;
  const activeItems = items.filter((it) => it.active);
  const leadSize = f(lead, LF.homeSize) || "";
  const minHours = ["3BR", "4BR+"].includes(leadSize) ? 6 : 0;

  const pickLead = (id) => {
    setLeadId(id);
    const picked = records("leads").find((l) => l.id === id);
    const size = f(picked, LF.homeSize);
    const pre = PREFILL_BY_SIZE[size];
    if (pre) {
      setCrew(pre.crew);
      setHours(pre.hours);
    }
    setTravel(size === "Labor-only (no truck)" ? "labor" : "truck");
    setJobName(f(picked, LF.name) || "");
    setMoveDate((f(picked, LF.moveDate) || "").slice(0, 10));
  };

  const q = computeQuote({
    crew: clamp(Number(crew) || 2, 2, 4),
    hours: clamp(Number(hours) || 0, 0, 24),
    minHours,
    travel,
    miles: clamp(Number(miles) || 0, 0, 5000),
    flights: clamp(Number(flights) || 0, 0, 50),
    packingHours: clamp(Number(packing) || 0, 0, 200),
    itemQty,
  }, rates, activeItems);

  const save = async () => {
    if (!lead) return;
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
      toast.success(`Quote saved to ${f(lead, LF.name) || "lead"}. Status is now Quoted.`);
    } catch {}
    setSaving(false);
  };

  return (
    <div data-testid="calculator-page" className="grid lg:grid-cols-[minmax(0,32rem)_minmax(0,1fr)] gap-6 items-start">
      <div className="space-y-4 max-w-lg">
      <PageTitle title="Quote Calculator" subtitle="Price a move in seconds." />
      <InstructionBanner>Fill in the job. The price updates as you type. The call script is right beside you.</InstructionBanner>

      <div className="bg-white border border-slate-200 rounded-lg p-4 space-y-3">
        <div>
          <Label>Save quote to lead (optional)</Label>
          <Select value={leadId} onValueChange={pickLead}>
            <SelectTrigger data-testid="calc-lead-select"><SelectValue placeholder="Just calculating — no lead picked" /></SelectTrigger>
            <SelectContent>
              {leads.map((l) => (
                <SelectItem key={l.id} value={l.id}>
                  <Private>{f(l, LF.name) || "No name"}</Private> · {fmtDate(f(l, LF.moveDate))} · {f(l, LF.homeSize) || "size TBD"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Customer / job name</Label>
            <Input data-testid="calc-jobname-input" value={jobName} onChange={(e) => setJobName(e.target.value)} placeholder="Smith move" />
          </div>
          <div>
            <Label>Move date</Label>
            <Input data-testid="calc-movedate-input" type="date" value={moveDate} onChange={(e) => setMoveDate(e.target.value)} />
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
            <Label>Estimated hours</Label>
            <Input data-testid="calc-hours-input" type="number" min="0.5" max="24" step="0.5" value={hours} onChange={(e) => setHours(e.target.value)} />
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
            <Label>Round-trip miles</Label>
            <Input data-testid="calc-miles-input" type="number" min="0" max="5000" value={miles} onChange={(e) => setMiles(e.target.value)} />
            <p className="text-[11px] text-slate-400 mt-0.5">First {rates.mileageAllowance} miles are free.</p>
          </div>
          <div>
            <Label>Flights of stairs (all)</Label>
            <Input data-testid="calc-flights-input" type="number" min="0" max="50" value={flights} onChange={(e) => setFlights(e.target.value)} />
          </div>
          <div>
            <Label>Packing help (man-hours)</Label>
            <Input data-testid="calc-packing-input" type="number" min="0" max="200" step="0.5" value={packing} onChange={(e) => setPacking(e.target.value)} />
          </div>
        </div>
      </div>

      {activeItems.length > 0 && (
        <div data-testid="calc-items-card" className="bg-white border border-slate-200 rounded-lg p-4">
          <p className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-2">Big / special items</p>
          <div className="space-y-2">
            {activeItems.map((it) => (
              <div key={it.id} data-testid="calc-item-row" className="flex items-center justify-between">
                <span className="text-sm text-[#1B2A4A]">{it.name} <span className="text-slate-400">({fmtMoney(it.price)} each)</span></span>
                <QtyStepper
                  qty={itemQty[it.id] || 0}
                  onChange={(v) => setItemQty((s) => ({ ...s, [it.id]: v }))}
                  testId={`calc-item-${it.id}`}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="border border-[#1B2A4A]/15 bg-[#1B2A4A]/[0.04] rounded-lg p-4 space-y-1">
        <QuoteLines q={q} rates={rates} crew={crew} hours={q.hours} />
      </div>

      <CrewGuideCard />

      <Button data-testid="calc-save-btn" onClick={save} disabled={saving || !lead || !Number(hours)} className="w-full gap-2 bg-[#E8743B] hover:bg-[#d4632e]">
        <Save className="w-4 h-4" /> {saving ? "Saving…" : lead ? `Save quote to ${f(lead, LF.name) || "lead"}` : "Pick a lead to save"}
      </Button>
      </div>

      <div className="lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto">
        <ScriptPanel />
      </div>
    </div>
  );
}
