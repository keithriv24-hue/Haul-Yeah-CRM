import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Save } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageTitle } from "@/components/Bits";
import { apiErrorMessage, getRates, saveRatesApi } from "@/lib/api";
import { IntegrationsCard } from "@/components/IntegrationsCard";
import { GmailCard } from "@/components/GmailCard";
import { MetaCard } from "@/components/MetaCard";

const fmtStamp = (iso) =>
  iso ? `Updated ${new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}` : "Starting value";
const strMap = (vals) => Object.fromEntries(Object.entries(vals || {}).map(([k, v]) => [k, String(v)]));

/* Pricing Spec v2.0 — every dollar the Scope Calculator uses lives here. */
const PRICING_GROUPS = [
  { title: "Core rates", fields: [
    { key: "manHourRate", label: "Man-hour rate ($, flat)" },
    { key: "cushionPercent", label: "Cushion (%) — folded in, never itemized", max: 100 },
    { key: "depositPercent", label: "Deposit (%)", max: 100 },
    { key: "roundingIncrement", label: "Round UP to nearest ($)", min: 1 },
    { key: "manHoursPer100CuFt", label: "Man-hours per 100 cu ft (calibration)", max: 100 },
  ] },
  { title: "Trip fees, floors & minimums", fields: [
    { key: "tripFeeTruck", label: "Trip fee — truck ($)" },
    { key: "tripFeeLabor", label: "Trip fee — labor only ($)" },
    { key: "floorTruck", label: "Price floor — truck ($)" },
    { key: "floorLabor", label: "Price floor — labor only ($)" },
    { key: "minHoursTruck", label: "Minimum hours — truck", max: 24 },
    { key: "minHoursLabor", label: "Minimum hours — labor only", max: 24 },
  ] },
  { title: "Distance zones (one-way miles)", note: "Past zone 3 the calculator refuses to price it — those jobs are quoted individually.", fields: [
    { key: "zone1MaxMiles", label: "Zone 1 — up to (mi)" },
    { key: "zone1Fee", label: "Zone 1 fee ($)" },
    { key: "zone2MaxMiles", label: "Zone 2 — up to (mi)" },
    { key: "zone2Fee", label: "Zone 2 fee ($)" },
    { key: "zone3MaxMiles", label: "Zone 3 — up to (mi)" },
    { key: "zone3Fee", label: "Zone 3 fee ($)" },
  ] },
  { title: "Stairs, carries & handling (flat fees)", fields: [
    { key: "stairFlightFee", label: "Stairs — per flight, each end ($)" },
    { key: "longCarryFee", label: "Long carry >50 ft — per location ($)" },
    { key: "disassemblyFee", label: "Disassembly — per major piece ($)" },
    { key: "extraStopFee", label: "Extra stop ($)" },
  ] },
  { title: "Specialty surcharges", fields: [
    { key: "surchargeUprightPiano", label: "Upright piano ($)" },
    { key: "surchargeGrandPiano", label: "Grand piano ($)" },
    { key: "surchargePoolTable", label: "Pool table — slate ($)" },
    { key: "surchargeSafeT1", label: "Safe under 300 lb ($)" },
    { key: "surchargeSafeT2", label: "Safe 300–700 lb ($)" },
    { key: "surchargeSafeT3", label: "Safe over 700 lb ($)" },
    { key: "surchargeGymT1", label: "Treadmill / single machine ($)" },
    { key: "surchargeGymT2", label: "Rack / multi-station gym ($)" },
    { key: "surchargeMotorcycle", label: "Motorcycle / ATV ($)" },
  ] },
  { title: "Materials", fields: [
    { key: "materialMattressBag", label: "Mattress bag ($ ea)" },
    { key: "materialWardrobeBox", label: "Wardrobe box ($ ea)" },
    { key: "materialTvBox", label: "TV box ($ ea)" },
  ] },
  { title: "Rules", note: "3BR+ moves never bill under the hard hour floor — even with a manual hours override.", fields: [
    { key: "hardFloorBedrooms", label: "Hard hour floor from (bedrooms)", max: 10 },
    { key: "hardFloorHours", label: "Hard hour floor (hours)", max: 24 },
  ] },
  { title: "Package defaults (crew / hours by home size)", fields: [
    { key: "pkgStudioCrew", label: "Studio/1BR — crew", max: 12 },
    { key: "pkgStudioHours", label: "Studio/1BR — hours", max: 24 },
    { key: "pkg2brCrew", label: "2BR — crew", max: 12 },
    { key: "pkg2brHours", label: "2BR — hours", max: 24 },
    { key: "pkg3brCrew", label: "3BR — crew", max: 12 },
    { key: "pkg3brHours", label: "3BR — hours", max: 24 },
    { key: "pkg4brCrew", label: "4BR+ — crew", max: 12 },
    { key: "pkg4brHours", label: "4BR+ — hours", max: 24 },
  ] },
];
const ALL_FIELDS = PRICING_GROUPS.flatMap((g) => g.fields);

const PricingCard = () => {
  const [saved, setSaved] = useState(null);
  const [stamps, setStamps] = useState({});
  const [form, setForm] = useState({});
  const [states, setStates] = useState("NJ");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getRates().then((d) => {
      const { _updatedAt, ...vals } = d;
      setSaved(vals);
      setStamps(_updatedAt || {});
      setForm(strMap(vals));
      setStates(vals.serviceStates || "NJ");
    }).catch(() => {});
  }, []);

  const changed = (key) => saved && form[key] !== undefined && Number(form[key]) !== Number(saved[key]);
  const statesChanged = saved && states.trim().toUpperCase() !== String(saved.serviceStates || "NJ");
  const anyChanged = (saved && ALL_FIELDS.some(({ key }) => changed(key))) || statesChanged;

  const save = async () => {
    for (const { key, label, min = 0, max = 100000 } of ALL_FIELDS) {
      const n = Number(String(form[key] ?? "").trim());
      if (String(form[key] ?? "").trim() === "" || Number.isNaN(n) || n < min || n > max) {
        toast.error(`${label} must be a number between ${min} and ${max}.`);
        return;
      }
    }
    setSaving(true);
    try {
      const payload = { serviceStates: states.trim().toUpperCase() || "NJ" };
      ALL_FIELDS.forEach(({ key }) => { payload[key] = Number(form[key]); });
      const d = await saveRatesApi(payload);
      const { _updatedAt, ...vals } = d;
      setSaved(vals);
      setStamps(_updatedAt || {});
      setForm(strMap(vals));
      setStates(vals.serviceStates || "NJ");
      toast.success("Pricing saved. Every new quote prices from these values — saved scopes keep their snapshots.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setSaving(false);
  };

  if (!saved) return null;
  return (
    <div data-testid="scope-pricing-card" className="surface p-4 mb-4">
      <p className="text-xs font-bold uppercase tracking-wide text-faint mb-1">Pricing (v2.0) — single source of truth, owner only</p>
      <p className="text-[11px] text-faint mb-3">The Scope Calculator prices exclusively from these values. Saved scopes keep the values they were priced with.</p>
      {PRICING_GROUPS.map((g) => (
        <div key={g.title} className="mb-4">
          <p className="text-[10px] tracking-[.14em] uppercase text-accent-ink font-bold mb-1.5">{g.title}</p>
          {g.note && <p className="text-[11px] text-faint mb-2">{g.note}</p>}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {g.fields.map(({ key, label, min = 0, max = 100000 }) => (
              <div key={key}>
                <Label>{label}</Label>
                <Input
                  data-testid={`scope-${key}-input`}
                  type="number"
                  min={min}
                  max={max}
                  step="0.01"
                  value={form[key] ?? ""}
                  onChange={(e) => setForm((s) => ({ ...s, [key]: e.target.value }))}
                  className={changed(key) ? "ring-2 ring-accent/70 bg-accent/10" : ""}
                />
                <p data-testid={`scope-${key}-stamp`} className="text-[10px] text-faint mt-0.5">{fmtStamp(stamps[key])}</p>
              </div>
            ))}
          </div>
        </div>
      ))}
      <div className="mb-3">
        <p className="text-[10px] tracking-[.14em] uppercase text-accent-ink font-bold mb-1.5">Service area</p>
        <Label>States we quote (comma-separated) — anything else is refused</Label>
        <Input
          data-testid="scope-serviceStates-input"
          value={states}
          onChange={(e) => setStates(e.target.value)}
          className={statesChanged ? "ring-2 ring-accent/70 bg-accent/10" : ""}
        />
        <p className="text-[10px] text-faint mt-0.5">NJ only — no interstate authority. A pickup or drop-off in NY, PA, DE (anywhere else) blocks the quote.</p>
      </div>
      <div className="flex justify-end mt-3">
        <Button data-testid="scope-pricing-save-btn" size="sm" className="gap-1.5 bg-accent hover:bg-accent-press" disabled={!anyChanged || saving} onClick={save}>
          <Save className="w-3.5 h-3.5" /> {saving ? "Saving…" : "Save pricing"}
        </Button>
      </div>
    </div>
  );
};

export default function Settings() {
  const { business, saveBusiness } = useApp();
  const [savedLink, setSavedLink] = useState("");
  const [reviewLink, setReviewLink] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setSavedLink(business.reviewLink || "");
    setReviewLink(business.reviewLink || "");
  }, [business]);

  const linkChanged = reviewLink.trim() !== (savedLink || "");

  const saveLink = async () => {
    setSaving(true);
    try {
      await saveBusiness({ reviewLink: reviewLink.trim() });
      setSavedLink(reviewLink.trim());
      toast.success("Review link saved.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setSaving(false);
  };

  return (
    <div data-testid="settings-page" className="max-w-2xl pb-16">
      <PageTitle title="Settings" subtitle="Pricing, review link, and integrations." />

      <PricingCard />

      <div className="surface p-4 mb-4">
        <Label>Google review link</Label>
        <Input
          data-testid="review-link-input"
          type="url"
          placeholder="https://g.page/r/…/review"
          value={reviewLink}
          onChange={(e) => setReviewLink(e.target.value)}
          className={linkChanged ? "ring-2 ring-accent/70 bg-accent/10" : ""}
        />
        <div className="flex items-center justify-between mt-2 gap-3">
          <p className="text-xs text-faint">The "Ask for review" text on completed jobs uses this link.</p>
          {linkChanged && (
            <Button data-testid="review-link-save-btn" size="sm" className="gap-1.5 bg-accent hover:bg-accent-press" disabled={saving} onClick={saveLink}>
              <Save className="w-3.5 h-3.5" /> {saving ? "Saving…" : "Save"}
            </Button>
          )}
        </div>
      </div>

      <IntegrationsCard />
      <GmailCard />
      <MetaCard />
    </div>
  );
}
