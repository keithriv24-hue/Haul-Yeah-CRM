import React, { useEffect, useState } from "react";
import { useApp } from "@/context/AppContext";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, Private } from "@/components/Bits";
import { LF, f } from "@/lib/fields";
import { CREW_GUIDE } from "@/lib/quote";
import { QuoteCalculator } from "@/components/QuoteCalculator";
import { ScriptPanel } from "@/components/ScriptPanel";
import { fmtDate } from "@/lib/format";

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

export default function Calculator() {
  const { loadTable, records } = useApp();
  const [leadId, setLeadId] = useState("");

  useEffect(() => {
    loadTable("leads");
  }, [loadTable]);

  const leads = records("leads").filter((l) => !["Booked", "Lost", "Cold"].includes(f(l, LF.status)));
  const lead = records("leads").find((l) => l.id === leadId) || null;

  return (
    <div data-testid="calculator-page" className="grid lg:grid-cols-[minmax(0,32rem)_minmax(0,1fr)] gap-6 items-start">
      <div className="space-y-4 max-w-lg">
        <PageTitle title="Quote Calculator" subtitle="Price a move in seconds." />
        <InstructionBanner>Fill in the job. The price updates as you type. The call script is right beside you.</InstructionBanner>

        <div className="bg-white border border-slate-200 rounded-lg p-4 space-y-3">
          <div>
            <Label>Save quote to lead (optional)</Label>
            <Select value={leadId} onValueChange={setLeadId}>
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
          <QuoteCalculator lead={lead} />
        </div>

        <CrewGuideCard />
      </div>

      <div className="lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto">
        <ScriptPanel />
      </div>
    </div>
  );
}
