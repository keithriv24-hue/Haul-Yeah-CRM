import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Save } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageTitle } from "@/components/Bits";
import { apiErrorMessage, getScopePricingApi, saveScopePricingApi } from "@/lib/api";
import { IntegrationsCard } from "@/components/IntegrationsCard";
import { GmailCard } from "@/components/GmailCard";
import { MetaCard } from "@/components/MetaCard";

const fmtStamp = (iso) =>
  iso ? `Last updated ${new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}` : "Using the starting value";
const strMap = (vals) => Object.fromEntries(Object.entries(vals || {}).map(([k, v]) => [k, String(v)]));

const SCOPE_FIELDS = [
  { key: "manHourRate", label: "Man-hour rate ($)", max: 10000 },
  { key: "cushionPercent", label: "Cushion (%)", max: 100 },
  { key: "tripFeeTruck", label: "Trip fee — truck ($)", max: 100000 },
  { key: "tripFeeLabor", label: "Trip fee — labor only ($)", max: 100000 },
  { key: "floorTruck", label: "Price floor — truck ($)", max: 100000 },
  { key: "floorLabor", label: "Price floor — labor only ($)", max: 100000 },
  { key: "roundingIncrement", label: "Rounding increment ($)", min: 1, max: 10000 },
  { key: "depositPercent", label: "Deposit (%)", max: 100 },
  { key: "manHoursPer100CuFt", label: "Man-hours per 100 cu ft (calibration default)", max: 100 },
];

const ScopePricingCard = () => {
  const [saved, setSaved] = useState(null);
  const [stamps, setStamps] = useState({});
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getScopePricingApi().then((d) => {
      const { _updatedAt, ...vals } = d;
      setSaved(vals);
      setStamps(_updatedAt || {});
      setForm(strMap(vals));
    }).catch(() => {});
  }, []);

  const changed = (key) => saved && form[key] !== undefined && Number(form[key]) !== Number(saved[key]);
  const anyChanged = saved && SCOPE_FIELDS.some(({ key }) => changed(key));

  const save = async () => {
    for (const { key, label, min = 0, max } of SCOPE_FIELDS) {
      const n = Number(String(form[key] ?? "").trim());
      if (String(form[key] ?? "").trim() === "" || Number.isNaN(n) || n < min || n > max) {
        toast.error(`${label} must be a number between ${min} and ${max}.`);
        return;
      }
    }
    setSaving(true);
    try {
      const payload = {};
      SCOPE_FIELDS.forEach(({ key }) => { payload[key] = Number(form[key]); });
      const d = await saveScopePricingApi(payload);
      const { _updatedAt, ...vals } = d;
      setSaved(vals);
      setStamps(_updatedAt || {});
      setForm(strMap(vals));
      toast.success("Scope pricing saved. Future scope quotes use these values.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setSaving(false);
  };

  if (!saved) return null;
  return (
    <div data-testid="scope-pricing-card" className="surface p-4 mb-4">
      <p className="text-xs font-bold uppercase tracking-wide text-faint mb-1">Job Scope Calculator pricing (owner only)</p>
      <p className="text-[11px] text-faint mb-3">Every scope quote is priced from these values. Saved quotes keep the values they were priced with.</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {SCOPE_FIELDS.map(({ key, label, min = 0, max }) => (
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
      <div className="flex justify-end mt-3">
        <Button data-testid="scope-pricing-save-btn" size="sm" className="gap-1.5 bg-accent hover:bg-accent-press" disabled={!anyChanged || saving} onClick={save}>
          <Save className="w-3.5 h-3.5" /> {saving ? "Saving…" : "Save scope pricing"}
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
      <PageTitle title="Settings" subtitle="Scope pricing, review link, and integrations." />

      <ScopePricingCard />

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
