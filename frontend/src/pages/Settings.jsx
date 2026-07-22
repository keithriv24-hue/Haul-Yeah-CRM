import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Save, RotateCcw, Plus, Trash2, Undo2 } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { InstructionBanner, PageTitle } from "@/components/Bits";
import { apiErrorMessage, listCalcItemsApi, saveCalcItemsApi } from "@/lib/api";

const FIELDS = [
  { key: "manHour", label: "Billing rate ($/man-hour)", max: 10000 },
  { key: "cushionPercent", label: "Cushion (%)", max: 100 },
  { key: "travelTruck", label: "Travel fee — truck ($ flat)", max: 100000 },
  { key: "travelLabor", label: "Travel fee — labor-only ($ flat)", max: 100000 },
  { key: "mileageAllowance", label: "Mileage allowance (round-trip mi included)", max: 100000 },
  { key: "overageRate", label: "Overage rate ($/extra mile)", max: 1000 },
  { key: "stairFlight", label: "Stairs fee ($/flight)", max: 100000 },
  { key: "packingRate", label: "Packing rate ($/man-hour)", max: 10000 },
  { key: "depositPercent", label: "Deposit (%)", max: 100 },
  { key: "roundingIncrement", label: "Round final quote UP to nearest ($)", min: 1, max: 10000 },
];

const disp = (key, v) => {
  const n = Number(v);
  if (key.includes("Percent")) return `${n}%`;
  if (key === "mileageAllowance") return `${n} mi`;
  return `$${n.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
};
const disp$ = (v) => `$${Number(v).toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
const fmtStamp = (iso) =>
  iso ? `Last updated ${new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}` : "Using the starting value";
const strMap = (vals) => Object.fromEntries(Object.entries(vals || {}).map(([k, v]) => [k, String(v)]));

import { IntegrationsCard } from "@/components/IntegrationsCard";
import { GmailCard } from "@/components/GmailCard";
import { MetaCard } from "@/components/MetaCard";

export default function Settings() {
  const { rates, saveRates, business, saveBusiness } = useApp();
  const [savedRates, setSavedRates] = useState(null);
  const [stamps, setStamps] = useState({});
  const [form, setForm] = useState({});
  const [savedItems, setSavedItems] = useState([]);
  const [draftItems, setDraftItems] = useState([]);
  const [savedLink, setSavedLink] = useState("");
  const [reviewLink, setReviewLink] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const { _updatedAt, ...vals } = rates || {};
    setSavedRates(vals);
    setStamps(_updatedAt || {});
    setForm(strMap(vals));
  }, [rates]);

  useEffect(() => {
    setSavedLink(business.reviewLink || "");
    setReviewLink(business.reviewLink || "");
  }, [business]);

  const loadItems = useCallback(async () => {
    try {
      const items = await listCalcItemsApi();
      setSavedItems(items);
      setDraftItems(items.map((it) => ({ ...it, price: String(it.price), deleted: false })));
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  }, []);
  useEffect(() => {
    loadItems();
  }, [loadItems]);

  const rateChanged = (key) => savedRates && form[key] !== undefined && Number(form[key]) !== Number(savedRates[key]);
  const rateChanges = savedRates
    ? FIELDS.filter(({ key }) => rateChanged(key)).map(({ key, label }) => `${label}: ${disp(key, savedRates[key])} → ${disp(key, form[key])}`)
    : [];

  const itemChanges = [];
  draftItems.forEach((d) => {
    if (!d.id) {
      if (!d.deleted && d.name.trim()) itemChanges.push(`Add item: ${d.name.trim()} — ${disp$(Number(d.price) || 0)}`);
      return;
    }
    const s = savedItems.find((x) => x.id === d.id);
    if (!s) return;
    if (d.deleted) {
      itemChanges.push(`Delete item: ${s.name}`);
      return;
    }
    if (d.name.trim() !== s.name) itemChanges.push(`Rename item: ${s.name} → ${d.name.trim()}`);
    if (Number(d.price) !== s.price) itemChanges.push(`${s.name}: ${disp$(s.price)} → ${disp$(Number(d.price) || 0)}`);
    if (d.active !== s.active) itemChanges.push(d.active ? `Show to reps again: ${s.name}` : `Hide from reps: ${s.name}`);
  });

  const linkChanged = reviewLink.trim() !== (savedLink || "");
  const allChanges = [...rateChanges, ...itemChanges, ...(linkChanged ? ["Google review link updated"] : [])];
  const hasChanges = allChanges.length > 0;

  const validate = () => {
    for (const { key, label, min = 0, max } of FIELDS) {
      const raw = String(form[key] ?? "").trim();
      const n = Number(raw);
      if (raw === "" || Number.isNaN(n) || n < min || n > max) {
        toast.error(`${label} must be a number between ${min} and ${max}.`);
        return false;
      }
    }
    for (const d of draftItems) {
      if (d.deleted) continue;
      if (!d.name.trim() && (d.id || d.price)) {
        toast.error("Every item needs a name.");
        return false;
      }
      const p = Number(d.price);
      if (d.name.trim() && (String(d.price).trim() === "" || Number.isNaN(p) || p < 0 || p > 100000)) {
        toast.error(`"${d.name}" needs a price between $0 and $100,000.`);
        return false;
      }
    }
    return true;
  };

  const applyChanges = async () => {
    setSaving(true);
    try {
      if (rateChanges.length) {
        const clean = {};
        FIELDS.forEach(({ key }) => {
          clean[key] = Number(form[key]);
        });
        await saveRates(clean);
      }
      if (itemChanges.length) {
        const upserts = draftItems
          .filter((d) => !d.deleted && d.name.trim())
          .map((d) => ({ id: d.id || null, name: d.name.trim(), price: Number(d.price) || 0, active: d.active }));
        const deletes = draftItems.filter((d) => d.deleted && d.id).map((d) => d.id);
        const items = await saveCalcItemsApi({ upserts, deletes });
        setSavedItems(items);
        setDraftItems(items.map((it) => ({ ...it, price: String(it.price), deleted: false })));
      }
      if (linkChanged) {
        await saveBusiness({ reviewLink: reviewLink.trim() });
        setSavedLink(reviewLink.trim());
      }
      setConfirmOpen(false);
      toast.success("Changes are live. The calculator uses them right now.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setSaving(false);
  };

  const discard = () => {
    setForm(strMap(savedRates));
    setDraftItems(savedItems.map((it) => ({ ...it, price: String(it.price), deleted: false })));
    setReviewLink(savedLink);
    toast("Draft cleared — back to the saved values.");
  };

  const setDraftItem = (idx, patch) =>
    setDraftItems((list) => list.map((d, i) => (i === idx ? { ...d, ...patch } : d)));

  const addItem = () =>
    setDraftItems((list) => [...list, { id: null, tempId: `new-${Date.now()}`, name: "", price: "", active: true, deleted: false }]);

  const changedInput = "ring-2 ring-[#E8743B]/70 bg-orange-50";

  return (
    <div data-testid="settings-page" className="max-w-2xl pb-28">
      <PageTitle title="Settings" subtitle="Calculator pricing for the whole team." />
      <InstructionBanner>
        Edits stay in a draft (highlighted orange) until you press "Save Changes" and confirm. Reps keep quoting with the old numbers until then.
      </InstructionBanner>

      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-4">
        <p className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-3">Pricing rules</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {FIELDS.map(({ key, label, min = 0, max }) => (
            <div key={key}>
              <Label>{label}</Label>
              <Input
                data-testid={`rate-${key}-input`}
                type="number"
                min={min}
                max={max}
                step="0.01"
                value={form[key] ?? ""}
                onChange={(e) => setForm((s) => ({ ...s, [key]: e.target.value }))}
                className={rateChanged(key) ? changedInput : ""}
              />
              <p data-testid={`rate-${key}-stamp`} className="text-[10px] text-slate-400 mt-0.5">{fmtStamp(stamps[key])}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-4">
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Specialty items (reps see active ones with a quantity stepper)</p>
          <Button data-testid="add-item-btn" size="sm" variant="outline" className="gap-1 text-xs" onClick={addItem}>
            <Plus className="w-3.5 h-3.5" /> Add item
          </Button>
        </div>
        <div className="space-y-2">
          {draftItems.map((d, idx) => {
            const s = d.id ? savedItems.find((x) => x.id === d.id) : null;
            const edited = !d.id || d.deleted || (s && (d.name.trim() !== s.name || Number(d.price) !== s.price || d.active !== s.active));
            return (
              <div key={d.id || d.tempId} data-testid="item-row" className={`flex items-center gap-2 rounded-md p-1 ${d.deleted ? "opacity-50" : ""}`}>
                <Input
                  data-testid="item-name-input"
                  className={`flex-1 h-9 ${!d.deleted && edited ? changedInput : ""} ${d.deleted ? "line-through" : ""}`}
                  placeholder="Item name (e.g. Gun safe)"
                  value={d.name}
                  disabled={d.deleted}
                  onChange={(e) => setDraftItem(idx, { name: e.target.value })}
                />
                <div className="relative">
                  <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 text-sm">$</span>
                  <Input
                    data-testid="item-price-input"
                    className={`w-24 h-9 pl-6 ${!d.deleted && edited ? changedInput : ""}`}
                    type="number"
                    min="0"
                    value={d.price}
                    disabled={d.deleted}
                    onChange={(e) => setDraftItem(idx, { price: e.target.value })}
                  />
                </div>
                <div className="flex items-center gap-1" title={d.active ? "Reps can see this" : "Hidden from reps"}>
                  <Switch data-testid="item-active-switch" checked={d.active} disabled={d.deleted} onCheckedChange={(v) => setDraftItem(idx, { active: v })} />
                </div>
                {d.deleted ? (
                  <Button data-testid="item-undo-btn" variant="ghost" size="sm" className="h-8 px-2" onClick={() => setDraftItem(idx, { deleted: false })}>
                    <Undo2 className="w-3.5 h-3.5" />
                  </Button>
                ) : (
                  <Button
                    data-testid="item-delete-btn"
                    variant="ghost"
                    size="sm"
                    className="h-8 px-2 text-red-600 hover:text-red-700"
                    onClick={() => (d.id ? setDraftItem(idx, { deleted: true }) : setDraftItems((list) => list.filter((_, i) => i !== idx)))}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                )}
              </div>
            );
          })}
          {draftItems.length === 0 && <p className="text-sm text-slate-400">No items yet — add your first one.</p>}
        </div>
        <p className="text-[11px] text-slate-400 mt-2">Flip the switch off to hide an item from reps but keep its history. Trash removes it for good.</p>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-4">
        <Label>Google review link</Label>
        <Input
          data-testid="review-link-input"
          type="url"
          placeholder="https://g.page/r/…/review"
          value={reviewLink}
          onChange={(e) => setReviewLink(e.target.value)}
          className={linkChanged ? changedInput : ""}
        />
        <p className="text-xs text-slate-500 mt-2">The "Ask for review" text on completed jobs uses this link.</p>
      </div>

      <IntegrationsCard />
      <GmailCard />
      <MetaCard />

      <div className="fixed bottom-16 md:bottom-4 left-0 md:left-60 right-0 px-4 z-40">
        <div className="max-w-2xl mx-auto md:mx-0 bg-white border border-slate-200 rounded-lg shadow-lg p-3 flex items-center gap-3">
          <p data-testid="pending-changes-count" className="text-sm text-slate-600 flex-1">
            {hasChanges ? <><strong className="text-[#E8743B]">{allChanges.length}</strong> unsaved change{allChanges.length > 1 ? "s" : ""}</> : "No unsaved changes"}
          </p>
          <Button data-testid="discard-changes-btn" variant="outline" size="sm" className="gap-1.5" disabled={!hasChanges || saving} onClick={discard}>
            <RotateCcw className="w-3.5 h-3.5" /> Discard changes
          </Button>
          <Button
            data-testid="save-changes-btn"
            size="sm"
            className="gap-1.5 bg-[#E8743B] hover:bg-[#d4632e]"
            disabled={!hasChanges || saving}
            onClick={() => validate() && setConfirmOpen(true)}
          >
            <Save className="w-3.5 h-3.5" /> Save Changes
          </Button>
        </div>
      </div>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent data-testid="confirm-save-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-display">Apply these changes?</AlertDialogTitle>
            <AlertDialogDescription>Reps start quoting with the new values the moment you confirm.</AlertDialogDescription>
          </AlertDialogHeader>
          <div className="max-h-60 overflow-y-auto space-y-1.5">
            {allChanges.map((c, i) => (
              <p key={i} data-testid="confirm-change-line" className="text-sm text-[#1B2A4A] bg-orange-50 border border-orange-200 rounded px-3 py-1.5">
                {c}
              </p>
            ))}
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="confirm-cancel-btn">Keep editing</AlertDialogCancel>
            <AlertDialogAction data-testid="confirm-apply-btn" disabled={saving} onClick={(e) => { e.preventDefault(); applyChanges(); }} className="bg-[#E8743B] hover:bg-[#d4632e]">
              {saving ? "Applying…" : "Yes, make it live"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
