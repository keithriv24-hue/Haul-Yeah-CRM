import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Save } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InstructionBanner, PageTitle } from "@/components/Bits";
import { apiErrorMessage } from "@/lib/api";

const FIELDS = [
  { key: "manHour", label: "Price per man-hour ($)" },
  { key: "travelTruck", label: "Travel fee with truck ($)" },
  { key: "travelLabor", label: "Travel fee labor-only ($)" },
  { key: "stairFlight", label: "Stairs, per flight ($)" },
  { key: "pianoUpright", label: "Upright piano, flat ($)" },
  { key: "pianoGrand", label: "Grand piano, flat ($)" },
];

export default function Settings() {
  const { rates, saveRates } = useApp();
  const [form, setForm] = useState(rates);
  const [saving, setSaving] = useState(false);
  useEffect(() => setForm(rates), [rates]);

  const save = async () => {
    const clean = {};
    for (const { key, label } of FIELDS) {
      const n = Number(form[key]);
      if (Number.isNaN(n) || n < 0) {
        toast.error(`${label} must be a number, 0 or more.`);
        return;
      }
      clean[key] = n;
    }
    setSaving(true);
    try {
      await saveRates(clean);
      toast.success("Rates saved. Every account now uses the new prices.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setSaving(false);
  };

  return (
    <div data-testid="settings-page" className="max-w-lg">
      <PageTitle title="Settings" subtitle="Calculator pricing for the whole team." />
      <InstructionBanner>Change what the calculator charges. Press "Save preferences" to update every account.</InstructionBanner>

      <div className="bg-white border border-slate-200 rounded-lg p-4 grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        {FIELDS.map(({ key, label }) => (
          <div key={key}>
            <Label>{label}</Label>
            <Input
              data-testid={`rate-${key}-input`}
              type="number"
              min="0"
              step="1"
              value={form[key] ?? ""}
              onChange={(e) => setForm((s) => ({ ...s, [key]: e.target.value }))}
            />
          </div>
        ))}
      </div>

      <Button data-testid="save-preferences-btn" onClick={save} disabled={saving} className="w-full gap-2 bg-[#E8743B] hover:bg-[#d4632e]">
        <Save className="w-4 h-4" /> {saving ? "Saving…" : "Save preferences"}
      </Button>
      <p className="text-xs text-slate-500 mt-3">
        The 10% cushion on the high end and the 25% deposit never change. Sales reps see the new rates the next time they open the calculator.
      </p>
    </div>
  );
}
