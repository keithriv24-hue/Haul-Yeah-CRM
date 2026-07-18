import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Calculator as CalcIcon, Save } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, Private, Money } from "@/components/Bits";
import { computeQuote } from "@/lib/pricing";
import { LF, f } from "@/lib/fields";
import { PREFILL_BY_SIZE, QUOTE_COACH_LINE, quoteSaveFields } from "@/lib/quote";
import { fmtDate, fmtMoney } from "@/lib/format";

export default function Calculator() {
  const { loadTable, records, updateRecord, rates } = useApp();
  const [leadId, setLeadId] = useState("");
  const [crew, setCrew] = useState("3");
  const [hours, setHours] = useState("5");
  const [travel, setTravel] = useState("truck");
  const [flights, setFlights] = useState("0");
  const [piano, setPiano] = useState("none");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadTable("leads");
  }, [loadTable]);

  const leads = records("leads").filter((l) => !["Booked", "Lost", "Cold"].includes(f(l, LF.status)));
  const lead = records("leads").find((l) => l.id === leadId) || null;

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
  };

  const q = computeQuote({
    crew: Number(crew),
    hours: Number(hours) || 0,
    travel,
    flights: Number(flights) || 0,
    piano,
  }, rates);

  const save = async () => {
    if (!lead) return;
    setSaving(true);
    try {
      await updateRecord("leads", lead.id, quoteSaveFields(lead, q, crew, hours));
      toast.success(`Quote saved to ${f(lead, LF.name) || "lead"}. Status is now Quoted.`);
    } catch {}
    setSaving(false);
  };

  return (
    <div data-testid="calculator-page" className="max-w-lg">
      <PageTitle title="Quote Calculator" subtitle="Price a move in seconds." />
      <InstructionBanner>Pick the job details to get a price range. Choose a lead to save the quote to their card.</InstructionBanner>

      <div className="bg-white border border-slate-200 rounded-lg p-4 space-y-3 mb-4">
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
          {lead && PREFILL_BY_SIZE[f(lead, LF.homeSize)] && (
            <p className="text-xs text-slate-500 mt-1">Crew and hours pre-filled from home size ({f(lead, LF.homeSize)}). Adjust as needed.</p>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Crew size</Label>
            <Select value={crew} onValueChange={setCrew}>
              <SelectTrigger data-testid="calc-crew-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                {["2", "3", "4", "5"].map((c) => <SelectItem key={c} value={c}>{c} movers</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Estimated hours</Label>
            <Input data-testid="calc-hours-input" type="number" min="1" step="0.5" value={hours} onChange={(e) => setHours(e.target.value)} />
          </div>
          <div>
            <Label>Travel type</Label>
            <Select value={travel} onValueChange={setTravel}>
              <SelectTrigger data-testid="calc-travel-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="truck">With truck ({fmtMoney(rates.travelTruck)})</SelectItem>
                <SelectItem value="labor">Labor-only ({fmtMoney(rates.travelLabor)})</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Stair flights</Label>
            <Input data-testid="calc-flights-input" type="number" min="0" value={flights} onChange={(e) => setFlights(e.target.value)} />
          </div>
          <div className="col-span-2">
            <Label>Piano</Label>
            <Select value={piano} onValueChange={setPiano}>
              <SelectTrigger data-testid="calc-piano-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No piano</SelectItem>
                <SelectItem value="upright">Upright piano ({fmtMoney(rates.pianoUpright)} flat)</SelectItem>
                <SelectItem value="grand">Grand piano ({fmtMoney(rates.pianoGrand)} flat)</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      <div className="border border-[#1B2A4A]/15 bg-[#1B2A4A]/[0.04] rounded-lg p-4 space-y-1 mb-4">
        <div className="flex justify-between text-sm text-slate-600">
          <span>Labor ({crew} × {hours || 0} hrs × {fmtMoney(rates.manHour)})</span><Money value={q.base} />
        </div>
        <div className="flex justify-between text-sm text-slate-600"><span>Travel fee</span><Money value={q.travelFee} /></div>
        {q.stairs > 0 && <div className="flex justify-between text-sm text-slate-600"><span>Stairs</span><Money value={q.stairs} /></div>}
        {q.pianoFee > 0 && <div className="flex justify-between text-sm text-slate-600"><span>Piano</span><Money value={q.pianoFee} /></div>}
        <div className="flex justify-between font-display font-extrabold text-xl text-[#1B2A4A] pt-2 border-t border-slate-200">
          <span>Quote range</span>
          <span data-testid="calc-range-value"><Money value={q.low} /> – <Money value={q.high} /></span>
        </div>
        <div className="flex justify-between text-sm font-semibold text-[#E8743B]">
          <span>Deposit (25% of high)</span><span data-testid="calc-deposit-value"><Money value={q.deposit} /></span>
        </div>
        <p className="text-xs text-slate-500 pt-1">{QUOTE_COACH_LINE}</p>
      </div>

      <Button data-testid="calc-save-btn" onClick={save} disabled={saving || !lead || !Number(hours)} className="w-full gap-2 bg-[#E8743B] hover:bg-[#d4632e]">
        <Save className="w-4 h-4" /> {saving ? "Saving…" : lead ? `Save quote to ${f(lead, LF.name) || "lead"}` : "Pick a lead to save"}
      </Button>
    </div>
  );
}
