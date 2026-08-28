import React, { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Save, RotateCcw, FolderOpen, X, PencilRuler, Ban, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { PageTitle } from "@/components/Bits";
import { useApp } from "@/context/AppContext";
import { LF, f, leadAccess } from "@/lib/fields";
import { apiErrorMessage, getScopeApi, getScopeAccessApi, getScopePricingValuesApi, listScopesApi, saveScopeApi } from "@/lib/api";
import {
  TIERS, TRUCK_CF, TRUCK_LBS, ROOMS, ITEMS, PACKING, ACCESS, MATERIALS, NON_TRANSPORT,
  PKGS, STATE_OPTIONS, NO_PRICING, LEGACY_ITEM_KEYS, CUSTOM_BANDS, FIT_WORK_OPTIONS,
  itemBill, materialPrice, scopeOutputs, stateGate,
} from "@/lib/scopeEngine";

/* Haul Yeah Moving — Job Scope Calculator (Pricing Spec v2.0)
   THE only calculator. All math lives in lib/scopeEngine.js; every dollar
   comes from the pricing config served by the backend — nothing hardcoded. */

const money = (n) => "$" + Math.round(n).toLocaleString();
const moneyCents = (n) => "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/* Market sanity bands — owner-only, computed and shown HERE only, never persisted.
   Persisting them would force SCOPE_MONETARY_KEYS / redaction changes for a cosmetic feature. */
const SANITY_BANDS = [
  { k: "appl1", n: "Appliance, single", lo: 500, hi: 1200 },
  { k: "applMulti", n: "Appliance, swap / multi-unit", lo: 900, hi: 1800 },
  { k: "pianoUp", n: "Piano, upright", lo: 600, hi: 1200 },
  { k: "pianoGrand", n: "Piano, grand", lo: 1000, hi: 2000 },
  { k: "safe", n: "Safe / vault", lo: 600, hi: 1800 },
  { k: "gym", n: "Gym equipment", lo: 400, hi: 1000 },
  { k: "pool", n: "Pool table (move only)", lo: 700, hi: 1400 },
];

const guessSanityCat = (qty, custom) => {
  if (qty.grand) return "pianoGrand";
  if (qty.upright) return "pianoUp";
  if (qty.safe1 || qty.safe2 || qty.safe3) return "safe";
  if (qty.pool) return "pool";
  if (qty.tread || qty.gym || qty.plates) return "gym";
  const units = custom.reduce((s, c) => s + (Number(c.qty) || 1) + (c.isSwap ? 1 : 0), 0);
  return units > 1 ? "applMulti" : "appl1";
};

const newCustomItem = () => ({
  id: (crypto.randomUUID && crypto.randomUUID()) || String(Date.now() + Math.random()),
  name: "", band: "under150", qty: 1, builtIn: false, needsDisconnect: false,
  widthIn: 0, pathNarrowestIn: 0, isSwap: false, fitWork: "none",
});

/* 22px visual, ≥44×44 tap area via an invisible expanded hit zone */
const Step = ({ v, set, max = 9, lbl }) => (
  <div className="flex items-center justify-end gap-2.5">
    <button type="button" aria-label={`Fewer ${lbl}`} onClick={() => set(Math.max(0, v - 1))}
      className="relative w-[22px] h-[22px] rounded bg-surface-sunk text-ink-2 text-[13px] font-bold leading-none hover:text-primary before:content-[''] before:absolute before:-inset-[11px]">–</button>
    <span className={`tnum text-[13px] w-[22px] text-center ${v ? "text-primary font-semibold" : "text-faint"}`}>{v}</span>
    <button type="button" aria-label={`More ${lbl}`} onClick={() => set(Math.min(max, v + 1))}
      className="relative w-[22px] h-[22px] rounded bg-surface-sunk text-ink-2 text-[13px] font-bold leading-none hover:text-primary before:content-[''] before:absolute before:-inset-[11px]">+</button>
  </div>
);

const Eyebrow = ({ children, className = "" }) => (
  <p className={`text-[10px] tracking-[.16em] uppercase text-faint font-bold mb-2 ${className}`}>{children}</p>
);

const Stat = ({ label, value, last = false, accent = false }) => (
  <div className={`flex justify-between items-baseline py-1.5 text-[12.5px] ${last ? "" : "border-b border-border"}`}>
    <span className="text-ink-2">{label}</span>
    <span className={`tnum ${accent ? "text-accent-ink font-semibold" : "text-primary"}`}>{value}</span>
  </div>
);

export default function ScopeCalculator() {
  const [params] = useSearchParams();
  const leadId = params.get("lead") || null;
  const leadName = params.get("name") || "";
  const refineId = params.get("refine") || null;

  const [dens, setDens] = useState({});
  const [cnt, setCnt] = useState({});
  const [qty, setQty] = useState({});
  const [custom, setCustom] = useState([]);
  const [sanityCat, setSanityCat] = useState("");   // owner-only display state — never saved
  const [acc, setAcc] = useState({});
  const [mat, setMat] = useState({});
  const [pack, setPack] = useState(0);
  const [rate, setRate] = useState(2.1);
  const [jobType, setJobType] = useState("truck");
  const [miles, setMiles] = useState("");
  const [pickupState, setPickupState] = useState("NJ");
  const [dropoffState, setDropoffState] = useState("NJ");
  const [pkg, setPkg] = useState("");
  const [surveyComplete, setSurveyComplete] = useState(false);
  const [crewOverride, setCrewOverride] = useState(null);
  const [hoursOverride, setHoursOverride] = useState(null);
  const [video, setVideo] = useState({ link: "", received: false, date: "" });
  const [mode, setMode] = useState("range");
  const [open, setOpen] = useState(null);
  const [ownerBlock, setOwnerBlock] = useState(false);
  const [livePricing, setLivePricing] = useState(null);
  const [viewingSaved, setViewingSaved] = useState(null);
  const [refineFrom, setRefineFrom] = useState(null);
  const [savedList, setSavedList] = useState([]);
  const [showSaved, setShowSaved] = useState(false);
  const [label, setLabel] = useState("");
  const [saving, setSaving] = useState(false);
  const [tier, setTier] = useState(null);

  /* Lead context — access info from the Tally form + package prefill from home size */
  const { loadTable, loadSchema, records, schemas } = useApp();
  useEffect(() => {
    if (!leadId) return;
    loadTable("leads");
    loadSchema("leads");
  }, [leadId, loadTable, loadSchema]);
  const lead = leadId ? records("leads").find((x) => x.id === leadId) : null;
  const access = lead ? leadAccess(lead, schemas.leads) : null;

  useEffect(() => {
    getScopeAccessApi().then(({ tier: t }) => {
      setTier(t || "none");
      if (!t) return;
      if (t === "survey") {
        setLivePricing(NO_PRICING);
        return;
      }
      getScopePricingValuesApi().then((vals) => {
        setLivePricing(vals);
        setRate(vals.manHoursPer100CuFt || 2.1);
      }).catch((e) => toast.error(apiErrorMessage(e)));
    }).catch(() => setTier("none"));
  }, []);

  /* eslint-disable react-hooks/exhaustive-deps */
  useEffect(() => {
    if (!refineId) return;
    getScopeApi(refineId).then((doc) => startRefine(doc)).catch((e) => toast.error(apiErrorMessage(e)));
  }, [refineId]);
  /* eslint-enable react-hooks/exhaustive-deps */

  /* Saved snapshots price from their stored values; live pricing fills any
     key the snapshot pre-dates (older scopes saved before spec v2.0). */
  const P = viewingSaved ? { ...(livePricing || {}), ...(viewingSaved.pricing || {}) } : livePricing;

  const inputs = { dens, cnt, qty, custom, acc, mat, pack, rate, jobType, crewOverride, hoursOverride, miles: Number(miles) || 0, pkg };
  /* eslint-disable react-hooks/exhaustive-deps */
  const out = useMemo(() => scopeOutputs(inputs, P || {}), [dens, cnt, qty, custom, acc, mat, pack, rate, jobType, crewOverride, hoursOverride, miles, pkg, P]);
  /* eslint-enable react-hooks/exhaustive-deps */
  const { r, bandLo, bandHi, spread, finalTotal, deposit, inc } = out;

  const gate = stateGate(pickupState, dropoffState, P || {});

  const surveyDone = surveyComplete || video.received; // a received video counts as a completed survey
  const hasBlockers = (r.blockers || []).length > 0;

  useEffect(() => {
    if ((!surveyDone || gate.blocked || hasBlockers) && mode === "final") setMode("range");
  }, [surveyDone, mode, gate.blocked, hasBlockers]);

  const finalMode = mode === "final" && surveyDone && !gate.blocked && !hasBlockers;

  /* tier gates — UI mirrors of the backend enforcement, never the other way round */
  const isOwner = tier === "owner";
  const isFinalTier = tier === "final";
  const isSurvey = tier === "survey";
  const canFinal = isOwner || isFinalTier;
  const canSurveyToggle = isOwner || isFinalTier || isSurvey;
  const showBuild = isOwner || isFinalTier;   // price build + per-item dollar figures + weight detail
  const showPricing = !isSurvey;              // survey tier sees no pricing at all

  const flagged = ROOMS.filter((x) => x.risky && (dens[x.k] || 0) >= 2).map((x) => x.n);
  const overWeight = r.lbs > TRUCK_LBS * r.trucks * 0.92;
  const clear = () => { setDens({}); setCnt({}); setQty({}); setCustom([]); setAcc({}); setMat({}); setPack(0); setSurveyComplete(false); setMode("range"); setViewingSaved(null); setRefineFrom(null); setLabel(""); setCrewOverride(null); setHoursOverride(null); setVideo({ link: "", received: false, date: "" }); setMiles(""); setPickupState("NJ"); setDropoffState("NJ"); setPkg(""); setSanityCat(""); };

  const loadSavedList = () => listScopesApi().then(setSavedList).catch((e) => toast.error(apiErrorMessage(e)));

  const applyPkg = (k) => {
    if (pkg === k) { setPkg(""); setCrewOverride(null); setHoursOverride(null); return; }
    const def = PKGS.find((x) => x.k === k);
    setPkg(k);
    setCrewOverride(Number(P?.[def.crewKey]) || null);
    setHoursOverride(Number(P?.[def.hoursKey]) || null);
  };

  /* Quote pre-fill: seed the package (and job type) from the lead's home size, once. */
  const leadPrefilled = useRef(false);
  /* eslint-disable react-hooks/exhaustive-deps */
  useEffect(() => {
    if (!lead || !P || refineId || leadPrefilled.current) return;
    leadPrefilled.current = true;
    const size = f(lead, LF.homeSize);
    if (size === "Labor-only (no truck)") { setJobType("labor"); return; }
    const map = { "Studio/1BR": "studio", "2BR": "br2", "3BR": "br3", "4BR+": "br4" };
    if (map[size] && !pkg) applyPkg(map[size]);
  }, [lead, P]);
  /* eslint-enable react-hooks/exhaustive-deps */

  const applyInputs = (doc) => {
    const i = doc.inputs || {};
    const q = { ...(i.qty || {}) };
    Object.entries(LEGACY_ITEM_KEYS).forEach(([oldK, newK]) => {
      if (q[oldK]) { q[newK] = (q[newK] || 0) + q[oldK]; delete q[oldK]; }
    });
    setDens(i.dens || {}); setCnt(i.cnt || {}); setQty(q); setAcc(i.acc || {}); setMat(i.mat || {});
    setCustom(Array.isArray(i.custom) ? i.custom : []);   // scopes saved before custom items read as []
    setPack(i.pack || 0); setRate(i.rate || 2.1); setJobType(i.jobType || "truck");
    setCrewOverride(i.crewOverride ?? null); setHoursOverride(i.hoursOverride ?? null);
    setMiles(i.miles ? String(i.miles) : ""); setPickupState(i.pickupState || "NJ"); setDropoffState(i.dropoffState || "NJ");
    setPkg(i.pkg || "");
    const v = doc.video || {};
    setVideo({ link: v.link || "", received: !!v.received, date: v.received_date || "" });
    setSurveyComplete(!!doc.survey_complete);
  };

  const openSaved = (doc) => {
    applyInputs(doc);
    setMode(doc.inputs?.mode === "final" && doc.survey_complete ? "final" : "range");
    setViewingSaved(doc); setRefineFrom(null); setShowSaved(false); setLabel(doc.label || "");
  };

  const startRefine = (doc) => {
    applyInputs(doc);
    setMode("range");
    setRefineFrom(doc); setViewingSaved(null); setShowSaved(false); setLabel(doc.label || "");
  };

  const backToLive = () => {
    setViewingSaved(null);
    if (tier !== "survey") {
      getScopePricingValuesApi().then((vals) => setLivePricing(vals)).catch(() => {});
    }
    toast("Back to live pricing — current Settings values apply.");
  };

  const saveScope = async () => {
    setSaving(true);
    try {
      const doc = await saveScopeApi({
        lead_id: leadId,
        label: label.trim() || leadName || null,
        refined_from: refineFrom?._id || null,
        inputs: { dens, cnt, qty, custom, acc, mat, pack, rate, jobType, crewOverride, hoursOverride,
          miles: Number(miles) || 0, pickupState, dropoffState, pkg, mode: finalMode ? "final" : "range" },
        pricing: P,
        result: {
          cf: r.cf, lbs: r.lbs, trucks: r.trucks, crew: r.crew, crewRec: r.crewRec,
          onsiteHours: Math.round(r.onsite * 10) / 10,
          billMH: Math.round(r.billMH * 100) / 100, schedMH: Math.round(r.schedMH * 100) / 100,
          distFee: r.distBill, mileageExtra: r.mileage.extra,
          specialtyOnly: r.specialtyOnly, blockers: r.blockers,
          bandLo, bandHi,
          finalTotal: finalMode ? finalTotal : null,
          deposit: finalMode ? Math.round(deposit * 100) / 100 : null,
          mode: finalMode ? "final" : "range", jobType,
        },
        survey_complete: surveyComplete,
        video: { link: video.link, received: video.received, received_date: video.date },
      });
      setViewingSaved(doc);
      setRefineFrom(null);
      toast.success(refineFrom
        ? "Saved as a new version — the original scope is untouched."
        : "Scope saved with its pricing snapshot. Settings changes won't re-price it.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setSaving(false);
  };

  if (tier === "none") {
    return (
      <div data-testid="scope-no-access" className="surface p-8 text-center mt-6">
        <p className="font-display font-bold text-primary text-lg">No calculator access</p>
        <p className="text-sm text-faint mt-1">The owner hands out calculator access from the Crew page. Ask them if you need it.</p>
      </div>
    );
  }
  if (!P || tier === null) return <div className="text-sm text-faint p-6" data-testid="scope-loading">Loading pricing…</div>;

  const chip = (active) =>
    `flex-1 py-2 min-h-[44px] text-[11px] font-bold rounded transition-colors ${active ? "bg-accent text-accent-foreground" : "bg-surface-sunk text-faint hover:text-primary"}`;

  return (
    <div data-testid="scope-calculator-page" className="pb-16">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <PageTitle title="Job Scope Calculator"
          subtitle={leadId ? <>Scoping for lead: <strong className="text-primary">{leadName || leadId}</strong></>
            : isOwner ? "Owner tool — scope, range, and firm pricing."
            : isSurvey ? "Walk the home, scope every room, submit to the owner."
            : "Scope the move room by room."} />
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <Button data-testid="scope-saved-btn" variant="outline" size="sm" className="gap-1.5"
            onClick={() => { setShowSaved(!showSaved); if (!showSaved) loadSavedList(); }}>
            <FolderOpen className="w-3.5 h-3.5" /> Saved scopes
          </Button>
          <Button data-testid="scope-clear-btn" variant="outline" size="sm" className="gap-1.5" onClick={clear}>
            <RotateCcw className="w-3.5 h-3.5" /> Clear
          </Button>
        </div>
      </div>

      {gate.blocked && (
        <div data-testid="scope-out-of-state-block" className="mb-4 flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-[13px] text-primary">
          <Ban className="w-4 h-4 text-destructive mt-0.5 shrink-0" />
          <span>
            <strong className="text-destructive">We don't take this move — {gate.badStates.join(" / ")} is out of our service area.</strong>{" "}
            We move within {gate.allowed.join(", ")} only (no interstate authority). Politely decline — no quote, no referral, no "let me check."
          </span>
        </div>
      )}

      {access && (access.pickup || access.dropoff) && (
        <div data-testid="scope-lead-access" className="mb-4 flex flex-wrap gap-x-6 gap-y-1 rounded-lg border border-info/40 bg-info/10 px-4 py-2.5 text-[12.5px] text-primary">
          <span className="font-bold">Lead access:</span>
          {access.pickup && <span data-testid="scope-lead-access-pickup">Pickup — {access.pickup}</span>}
          {access.dropoff && <span data-testid="scope-lead-access-dropoff">Drop-off — {access.dropoff}</span>}
          <span className="basis-full text-[11px] text-faint">Set the stairs / elevator / carry inputs below to match.</span>
        </div>
      )}

      {refineFrom && (
        <div data-testid="scope-refine-banner" className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-accent/40 bg-accent-wash px-4 py-2.5 text-[12.5px] text-primary">
          <span>
            Refining <strong>{refineFrom.created_by}</strong>'s scope from {new Date(refineFrom.created_at).toLocaleDateString()}.
            Your edits save as a <strong>new version at today's pricing</strong> — the original is kept as-is.
          </span>
          <Button data-testid="scope-cancel-refine-btn" size="sm" variant="outline" className="gap-1 h-7 text-xs" onClick={clear}>
            <X className="w-3 h-3" /> Cancel refine
          </Button>
        </div>
      )}

      {viewingSaved && (
        <div data-testid="scope-snapshot-banner" className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-info/40 bg-info/10 px-4 py-2.5 text-[12.5px] text-primary">
          <span>
            Viewing a saved scope from <strong>{viewingSaved.created_by}</strong> ({new Date(viewingSaved.created_at).toLocaleDateString()}).
            Prices use its <strong>saved pricing snapshot</strong> — Settings changes don't touch it.
          </span>
          <Button data-testid="scope-refine-saved-btn" size="sm" variant="outline" className="gap-1 h-7 text-xs" onClick={() => startRefine(viewingSaved)}>
            <PencilRuler className="w-3 h-3" /> Refine this scope
          </Button>
          <Button data-testid="scope-back-live-btn" size="sm" variant="outline" className="gap-1 h-7 text-xs" onClick={backToLive}>
            <X className="w-3 h-3" /> Back to live pricing
          </Button>
        </div>
      )}

      {showSaved && (
        <div data-testid="scope-saved-list" className="surface p-4 mb-4">
          <Eyebrow>Saved scopes — newest first</Eyebrow>
          {savedList.length === 0 && <p className="text-sm text-faint">Nothing saved yet.</p>}
          <div className="space-y-1">
            {savedList.map((s) => (
              <div key={s._id} data-testid="scope-saved-row" className="w-full flex items-center justify-between gap-2 rounded-md px-2 py-1.5 hover:bg-surface-sunk">
                <button onClick={() => openSaved(s)} className="flex-1 min-w-0 text-left text-[13px]" data-testid="scope-saved-open-btn">
                  <span className="truncate text-primary font-semibold">
                    {s.label || "Untitled scope"}
                    <span className="text-faint font-normal ml-2">{s.created_by} · {new Date(s.created_at).toLocaleString()}{s.refined_from ? " · refined" : ""}</span>
                  </span>
                </button>
                <span className="tnum text-ink-2 text-[13px] shrink-0">
                  {s.result?.mode === "custom" ? "custom"
                    : s.result?.mode === "final" && s.result?.finalTotal ? money(s.result.finalTotal)
                    : s.result?.bandLo != null ? `${money(s.result.bandLo)}–${money(s.result.bandHi)}` : "—"}
                </span>
                <Button data-testid="scope-saved-refine-btn" size="sm" variant="outline" className="h-7 text-xs shrink-0" onClick={() => startRefine(s)}>
                  Refine
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Job type + distance + survey + mode controls */}
      <div className="surface p-4 mb-4 flex flex-wrap items-start gap-x-6 gap-y-3">
        <div>
          <Eyebrow className="mb-1">Job type</Eyebrow>
          <div className="flex gap-1.5">
            <button data-testid="scope-jobtype-truck" aria-pressed={jobType === "truck"} onClick={() => setJobType("truck")}
              className={`px-4 min-h-[44px] text-xs font-bold rounded ${jobType === "truck" ? "bg-accent text-accent-foreground" : "bg-surface-sunk text-faint"}`}>
              Truck move
            </button>
            <button data-testid="scope-jobtype-labor" aria-pressed={jobType === "labor"} onClick={() => setJobType("labor")}
              className={`px-4 min-h-[44px] text-xs font-bold rounded ${jobType === "labor" ? "bg-accent text-accent-foreground" : "bg-surface-sunk text-faint"}`}>
              Labor only
            </button>
          </div>
          {showBuild && (
          <p className="text-[10.5px] text-faint mt-1">Trip fee {jobType === "labor" ? moneyCents(P.tripFeeLabor) : moneyCents(P.tripFeeTruck)} (first {Number(P.mileageFreeMiles) || 20} mi included) · floor {jobType === "labor" ? money(P.floorLabor) : money(P.floorTruck)} · min {jobType === "labor" ? P.minHoursLabor : P.minHoursTruck} hrs</p>
          )}
        </div>

        <div>
          <Eyebrow className="mb-1">Quick start — package defaults</Eyebrow>
          <div className="flex gap-1.5 flex-wrap">
            {PKGS.map((pk) => (
              <button key={pk.k} data-testid={`scope-pkg-${pk.k}-btn`} aria-pressed={pkg === pk.k} onClick={() => applyPkg(pk.k)}
                className={`px-3 min-h-[44px] text-xs font-bold rounded ${pkg === pk.k ? "bg-accent text-accent-foreground" : "bg-surface-sunk text-faint"}`}>
                {pk.n}
              </button>
            ))}
          </div>
          <p className="text-[10.5px] text-faint mt-1">
            {pkg ? `Sets crew & hours to the ${PKGS.find((x) => x.k === pkg)?.n} package — tap again to clear.` : "Seeds crew & hours before you scope room by room."}
          </p>
        </div>

        <div>
          <Eyebrow className="mb-1">Distance & service area</Eyebrow>
          <div className="flex flex-wrap items-center gap-2">
            <Input data-testid="scope-miles-input" type="number" min="0" max="500" placeholder="Miles"
              value={miles} onChange={(e) => setMiles(e.target.value)} className="h-9 w-[84px] text-right tnum" />
            <span className="text-[11px] text-faint">mi one-way</span>
            <select data-testid="scope-pickup-state" aria-label="Pickup state" value={pickupState}
              onChange={(e) => setPickupState(e.target.value)}
              className="h-9 rounded-md border border-border bg-surface px-2 text-xs font-semibold text-primary">
              {STATE_OPTIONS.map((s) => <option key={s} value={s}>{s === pickupState ? `from ${s}` : s}</option>)}
            </select>
            <select data-testid="scope-dropoff-state" aria-label="Drop-off state" value={dropoffState}
              onChange={(e) => setDropoffState(e.target.value)}
              className="h-9 rounded-md border border-border bg-surface px-2 text-xs font-semibold text-primary">
              {STATE_OPTIONS.map((s) => <option key={s} value={s}>{s === dropoffState ? `to ${s}` : s}</option>)}
            </select>
          </div>
          <p data-testid="scope-mileage-note" className="text-[10.5px] mt-1 text-faint">
            {r.mileage.extra > 0
              ? `Mileage — ${r.mileage.extra} mi beyond the first ${r.mileage.free}${showBuild ? ` × ${moneyCents(P.mileageRatePerMile)}/mi · +${money(r.distBill)}` : ""}`
              : `First ${r.mileage.free} miles included in the trip fee`}
          </p>
        </div>

        <div>
          <Eyebrow className="mb-1">Pricing mode — derived</Eyebrow>
          <span data-testid="scope-mode-indicator"
            className={`inline-flex items-center px-3 min-h-[32px] rounded text-xs font-bold ${r.specialtyOnly ? "bg-info/15 text-info" : "bg-surface-sunk text-ink-2"}`}>
            {r.specialtyOnly ? "Specialty-only job" : "Household move"}
          </span>
          {r.specialtyOnly && (
            <p data-testid="scope-specialty-prompt" className="text-[10.5px] text-info mt-1 max-w-[200px] leading-snug">
              No rooms entered — pricing this as a specialty-only job.
            </p>
          )}
        </div>

        {canSurveyToggle && (
        <div>
          <Eyebrow className="mb-1">Survey</Eyebrow>
          <button data-testid="scope-survey-complete-toggle" aria-pressed={surveyComplete}
            onClick={() => setSurveyComplete(!surveyComplete)}
            className={`px-4 min-h-[44px] text-xs font-bold rounded ${surveyComplete ? "bg-success text-white" : "bg-surface-sunk text-faint"}`}>
            {surveyComplete ? "✓ Survey complete" : "Mark survey complete"}
          </button>
        </div>
        )}
        {canFinal && (
        <div>
          <Eyebrow className="mb-1">Output</Eyebrow>
          <div className="flex gap-1.5">
            <button data-testid="scope-mode-range" aria-pressed={!finalMode} onClick={() => setMode("range")}
              className={`px-4 min-h-[44px] text-xs font-bold rounded ${!finalMode ? "bg-accent text-accent-foreground" : "bg-surface-sunk text-faint"}`}>
              Range
            </button>
            <button data-testid="scope-mode-final" aria-pressed={finalMode} disabled={!surveyDone || gate.blocked}
              onClick={() => surveyDone && !gate.blocked && setMode("final")}
              title={surveyDone ? "" : "Locked until the survey is complete or a video survey is received"}
              className={`px-4 min-h-[44px] text-xs font-bold rounded disabled:opacity-40 disabled:cursor-not-allowed ${finalMode ? "bg-success text-white" : "bg-surface-sunk text-faint"}`}>
              Final {surveyDone && !gate.blocked ? "" : "🔒"}
            </button>
          </div>
        </div>
        )}
        <div className="basis-full sm:basis-auto sm:flex-1 min-w-[240px]">
          <Eyebrow className="mb-1">Video survey</Eyebrow>
          <div className="flex flex-wrap items-center gap-2">
            <Input data-testid="scope-video-link-input" placeholder="Video link (Drive, iCloud, YouTube…)"
              value={video.link} onChange={(e) => setVideo((s) => ({ ...s, link: e.target.value }))} className="h-9 w-full sm:w-60" />
            <label className="flex items-center gap-1.5 text-xs font-semibold text-primary cursor-pointer min-h-[44px]">
              <Checkbox data-testid="scope-video-received-checkbox" checked={video.received}
                onCheckedChange={(v) => setVideo((s) => ({ ...s, received: !!v, date: v && !s.date ? new Date().toISOString().slice(0, 10) : s.date }))} />
              Video received
            </label>
            {video.received && (
              <Input data-testid="scope-video-date-input" type="date" className="h-9 w-[150px]"
                value={video.date} onChange={(e) => setVideo((s) => ({ ...s, date: e.target.value }))} />
            )}
          </div>
          {video.received && <p className="text-[10.5px] text-success mt-1">A received video counts as a completed survey.</p>}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_376px] gap-4 items-start">
        {/* ================= SCOPE ================= */}
        <div className="grid gap-4">
          <div className="surface p-4">
            <Eyebrow>Rooms — tap a name to see what each tier includes</Eyebrow>
            {["Bedrooms", "Living areas", "High-variance spaces"].map((g) => (
              <div key={g} className="mt-3">
                <Eyebrow className={`mb-0.5 ${g[0] === "H" ? "text-warning" : ""}`}>{g}</Eyebrow>
                {ROOMS.filter((x) => x.g === g).map((rm) => {
                  const lvl = dens[rm.k] || 0;
                  return (
                    <div key={rm.k}>
                      <div className="grid grid-cols-1 sm:grid-cols-[1fr_168px] gap-2 items-center py-1.5 border-b border-border">
                        <div className="flex items-center gap-2 min-w-0">
                          <button className="text-[13.5px] font-semibold text-left text-primary hover:text-accent-ink min-h-[32px]"
                            onClick={() => setOpen(open === rm.k ? null : rm.k)} aria-expanded={open === rm.k}>{rm.n}</button>
                          {lvl > 0 && (
                            <span className="inline-flex items-center gap-1">
                              <Step v={cnt[rm.k] || 1} lbl={rm.n} max={6} set={(v) => setCnt({ ...cnt, [rm.k]: Math.max(1, v) })} />
                            </span>
                          )}
                          {lvl > 0 && <span className="tnum text-[11px] text-faint ml-auto pl-1.5">{rm.v[lvl - 1] * (cnt[rm.k] || 1)} cf</span>}
                        </div>
                        <div className="flex gap-1">
                          {TIERS.map((t, i) => (
                            <button key={i} className={chip(lvl === i)} aria-pressed={lvl === i}
                              onClick={() => setDens({ ...dens, [rm.k]: i })}>{t}</button>
                          ))}
                        </div>
                      </div>
                      {open === rm.k && (
                        <div className="bg-surface-sunk border border-border rounded px-3 py-2.5 my-1 text-xs leading-relaxed">
                          {rm.i.map((txt, i) => (
                            <div key={i} className={lvl === i + 1 ? "text-primary" : "text-faint"}>
                              <strong className={lvl === i + 1 ? "text-accent-ink" : ""}>{TIERS[i + 1]}</strong>
                              <span className="tnum text-[11px] ml-1.5">{rm.v[i]} cf</span> — {txt}
                            </div>
                          ))}
                          <div className="mt-1.5 pt-1.5 border-t border-border text-faint text-[11.5px]">
                            This list is the scope of work on the written estimate. Anything not on it is a change order.
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>

          <div className="surface p-4">
            <Eyebrow>Individual items — counted separately from rooms</Eyebrow>
            <p className="text-xs text-faint -mt-1 mb-2.5 leading-relaxed">
              These are priced on handling, not volume. A gun safe is 30 cu ft and 700 lbs — the cubic feet
              tell you nothing about how long it takes.
            </p>
            {["Appliances", "Heavy & awkward", "Fragile & oversized"].map((g) => (
              <div key={g} className="mt-3">
                <Eyebrow className="mb-0.5">{g}</Eyebrow>
                {ITEMS.filter((x) => x.g === g).map((it) => (
                  <div className="grid grid-cols-[1fr_110px] gap-2 items-center py-1.5 border-b border-border" key={it.k}>
                    <span className="text-[13.5px] font-semibold text-primary">{it.n}
                      <span className="tnum text-faint font-normal text-[11px] ml-2">
                        {it.cf}cf · {it.lbs}lb · +{it.mh}mh{showBuild && it.billKey ? ` · $${itemBill(it, P)}` : ""}
                      </span></span>
                    <Step v={qty[it.k] || 0} lbl={it.n} max={4} set={(v) => setQty({ ...qty, [it.k]: v })} />
                  </div>
                ))}
              </div>
            ))}
          </div>

          <div className="surface p-4" data-testid="scope-custom-items-card">
            <div className="flex items-center justify-between gap-2">
              <Eyebrow className="mb-0">Custom specialty items — not in the catalog</Eyebrow>
              <Button data-testid="scope-custom-add-btn" size="sm" variant="outline" className="gap-1 h-8 text-xs"
                onClick={() => setCustom([...custom, newCustomItem()])}>
                <Plus className="w-3.5 h-3.5" /> Add item
              </Button>
            </div>
            <p className="text-xs text-faint mt-1 leading-relaxed">
              Built-in fridges, wall ovens, hot tubs, gun safes — pick the weight band, never guess a number.
            </p>
            {custom.length === 0 && <p className="text-sm text-faint mt-2">Nothing custom on this job.</p>}
            {custom.map((c) => {
              const band = CUSTOM_BANDS.find((b) => b.k === c.band);
              const upd = (patch) => setCustom(custom.map((x) => (x.id === c.id ? { ...x, ...patch } : x)));
              return (
                <div key={c.id} data-testid="scope-custom-item-row" className="mt-3 rounded-lg border border-border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Input data-testid="scope-custom-name-input" placeholder={'Item (e.g. "Sub-Zero 42in built-in fridge")'}
                      value={c.name} onChange={(e) => upd({ name: e.target.value })} className="h-9 flex-1 min-w-[180px]" />
                    <select data-testid="scope-custom-band-select" aria-label="Weight band" value={c.band}
                      onChange={(e) => upd({ band: e.target.value })}
                      className="h-9 rounded-md border border-border bg-surface px-2 text-xs font-semibold text-primary">
                      {CUSTOM_BANDS.map((b) => <option key={b.k} value={b.k}>{b.n}</option>)}
                    </select>
                    <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">Qty
                      <Step v={Number(c.qty) || 1} lbl="custom items" max={6} set={(v) => upd({ qty: Math.max(1, v) })} />
                    </span>
                    <button data-testid="scope-custom-remove-btn" aria-label="Remove custom item" type="button"
                      onClick={() => setCustom(custom.filter((x) => x.id !== c.id))}
                      className="ml-auto inline-flex items-center justify-center min-h-[44px] min-w-[32px] text-faint hover:text-destructive">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                  {band?.blocked ? (
                    <p data-testid="scope-custom-800-note" className="text-[12px] text-destructive font-bold mt-2 leading-snug">
                      800 lb or more is beyond a standard crew. On-site assessment required — the calculator won't price it.
                    </p>
                  ) : (
                    <>
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mt-2">
                        <label className="flex items-center gap-1.5 text-xs font-semibold text-primary cursor-pointer min-h-[36px]">
                          <Checkbox data-testid="scope-custom-builtin" checked={!!c.builtIn} onCheckedChange={(v) => upd({ builtIn: !!v })} /> Built-in
                        </label>
                        <label className="flex items-center gap-1.5 text-xs font-semibold text-primary cursor-pointer min-h-[36px]">
                          <Checkbox data-testid="scope-custom-disconnect" checked={!!c.needsDisconnect} onCheckedChange={(v) => upd({ needsDisconnect: !!v })} /> Needs disconnect
                        </label>
                        <label className="flex items-center gap-1.5 text-xs font-semibold text-primary cursor-pointer min-h-[36px]">
                          <Checkbox data-testid="scope-custom-swap" checked={!!c.isSwap} onCheckedChange={(v) => upd({ isSwap: !!v })} /> Swap — old unit comes out
                        </label>
                        <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">
                          Width
                          <Input data-testid="scope-custom-width-input" type="number" min="0" max="120" placeholder="in"
                            value={c.widthIn || ""} onChange={(e) => upd({ widthIn: Number(e.target.value) || 0 })}
                            className="h-8 w-[64px] text-right tnum" /> in
                        </span>
                        <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">
                          Narrowest point on its path
                          <Input data-testid="scope-custom-path-input" type="number" min="0" max="120" placeholder="in"
                            value={c.pathNarrowestIn || ""} onChange={(e) => upd({ pathNarrowestIn: Number(e.target.value) || 0 })}
                            className="h-8 w-[64px] text-right tnum" /> in
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2">
                        <label className="text-xs font-semibold text-primary inline-flex items-center gap-1.5">
                          Fitting work
                          <select data-testid="scope-custom-fitwork-select" aria-label="Fitting work" value={c.fitWork || "none"}
                            onChange={(e) => upd({ fitWork: e.target.value })}
                            className="h-8 rounded-md border border-border bg-surface px-2 text-xs font-semibold text-primary">
                            {FIT_WORK_OPTIONS.map((o) => <option key={o.k} value={o.k}>{o.n}</option>)}
                          </select>
                        </label>
                        {(c.fitWork || "none") !== "none" && band && (
                          <span data-testid="scope-custom-fitwork-hours" className="tnum text-[11px] text-ink-2">
                            +{((c.fitWork === "removeOnly" || c.fitWork === "both" ? band.removeMh : 0)
                              + (c.fitWork === "placeOnly" || c.fitWork === "both" ? band.placeMh : 0)).toFixed(2)}mh each — billed as time, not a fee
                          </span>
                        )}
                      </div>
                      <p className="text-[10.5px] text-faint mt-1 leading-snug">
                        Ask directly. Customers often want a heavy item carried, not installed — and the two are priced differently.
                      </p>
                      {band && (
                        <p className="tnum text-[11px] text-faint mt-1.5">
                          {band.cf}cf · {band.lbs}lb · +{band.mh}mh each{showBuild ? ` · handling $${itemBill(band, P)} base` : ""}
                        </p>
                      )}
                      {c.needsDisconnect && (
                        <p data-testid="scope-custom-disconnect-note" className="text-[11px] text-warning font-semibold mt-1">
                          Confirm the customer disconnects before arrival, or refer out.
                        </p>
                      )}
                      <p className="text-[10.5px] text-faint mt-1 leading-snug">
                        Ask the customer to measure wall-to-wall at the narrowest point. A walkthrough video shows you
                        the turns; only a tape measure tells you if it fits.
                      </p>
                    </>
                  )}
                </div>
              );
            })}
          </div>

          <div className="surface p-4">
            <Eyebrow>Packing status</Eyebrow>
            <div className="flex flex-wrap gap-1.5 mb-4">
              {PACKING.map((p, i) => (
                <button key={i} aria-pressed={pack === i} onClick={() => setPack(i)}
                  className={`px-3 min-h-[44px] text-xs font-bold rounded ${pack === i ? "bg-accent text-accent-foreground" : "bg-surface-sunk text-faint"}`}>
                  {p.n} <span className="tnum">×{p.m.toFixed(2)}</span></button>
              ))}
            </div>

            <Eyebrow>Access conditions</Eyebrow>
            <p className="text-xs text-faint -mt-1 mb-2 leading-relaxed">
              Stairs, carries and elevators add man-hours that scale with load size — currently ×{r.sc.toFixed(2)} at {r.cf.toLocaleString()} cu ft. Billed fees are flat.
            </p>
            {ACCESS.map((a) => (
              <div className="grid grid-cols-[1fr_110px] gap-2 items-center py-1.5 border-b border-border" key={a.k}>
                <span className="text-[13.5px] font-semibold text-primary">{a.n}
                  <span className="tnum text-faint font-normal text-[11px] ml-2">
                    +{a.per}mh{showBuild && a.billKey ? ` · $${itemBill(a, P)}` : ""}{a.scale ? " ×vol" : ""}</span></span>
                {a.count
                  ? <Step v={acc[a.k] || 0} lbl={a.n} max={a.count} set={(v) => setAcc({ ...acc, [a.k]: v })} />
                  : <button className={chip(!!acc[a.k])} aria-pressed={!!acc[a.k]}
                      onClick={() => setAcc({ ...acc, [a.k]: acc[a.k] ? 0 : 1 })}>{acc[a.k] ? "YES" : "no"}</button>}
              </div>
            ))}

            <Eyebrow className="mt-4">Materials supplied</Eyebrow>
            {MATERIALS.map((m) => (
              <div className="grid grid-cols-[1fr_110px] gap-2 items-center py-1.5 border-b border-border" key={m.k}>
                <span className="text-[13.5px] font-semibold text-primary">{m.n}
                  {showBuild && <span className="tnum text-faint font-normal text-[11px] ml-2">${materialPrice(m, P)} ea</span>}</span>
                <Step v={mat[m.k] || 0} lbl={m.n} max={m.cap} set={(v) => setMat({ ...mat, [m.k]: v })} />
              </div>
            ))}

            {isOwner && (
            <div className="mt-4 pt-3 border-t border-border">
              <Eyebrow className="mb-1.5">Calibration — man-hours per 100 cu ft</Eyebrow>
              <div className="flex items-center gap-3">
                <input data-testid="scope-calibration-slider" type="range" min="1.6" max="2.8" step="0.05" value={rate}
                  onChange={(e) => setRate(parseFloat(e.target.value))}
                  className="flex-1 accent-[hsl(var(--accent))] min-h-[44px]" aria-label="Man-hours per 100 cubic feet" />
                <span className="tnum text-base font-semibold w-11 text-primary">{rate.toFixed(2)}</span>
              </div>
              <p className="text-[11.5px] text-faint mt-1.5 leading-snug">
                {Number(P.manHoursPer100CuFt).toFixed(2)} is your Settings default. Log actual man-hours ÷ surveyed cu ft on
                every job and move this to match reality after ten of them.
              </p>
            </div>
            )}
          </div>
        </div>

        {/* ================= OUTPUT ================= */}
        <div className="lg:sticky lg:top-4 grid gap-4">
          <div className="surface p-4">
            <div className="flex justify-between items-baseline">
              <Eyebrow className="mb-0">Load</Eyebrow>
              <div className="text-right">
                <span className="tnum text-2xl font-semibold text-primary">{r.cf.toLocaleString()}
                  <span className="text-[11px] text-faint font-normal"> cu ft</span></span>
                {showBuild && (
                <span className={`tnum text-[15px] font-semibold ml-2.5 ${overWeight ? "text-warning" : "text-faint"}`}>{r.lbs.toLocaleString()}
                  <span className="text-[11px] font-normal"> lb</span></span>
                )}
              </div>
            </div>

            <svg viewBox="0 0 340 96" className="w-full mt-2" role="img"
              aria-label={`${r.cf} cubic feet, ${r.lbs} pounds, ${r.trucks} trucks`}>
              {[0, 1].map((t) => {
                if (t === 1 && r.trucks < 2) return null;
                const y = t * 48;
                const rem = Math.max(0, r.cf - t * TRUCK_CF);
                const pct = Math.min(1, rem / TRUCK_CF);
                const fillCol = pct > 0.9 ? "hsl(var(--accent))" : pct > 0 ? "hsl(var(--success))" : "hsl(var(--surface-sunk))";
                return (
                  <g key={t}>
                    <path d={`M4 ${y + 20} h30 l10 12 v8 h-40 z`} style={{ fill: "hsl(var(--surface-sunk))" }} />
                    <circle cx="16" cy={y + 42} r="5" style={{ fill: "hsl(var(--border-strong))" }} />
                    <circle cx="62" cy={y + 42} r="5" style={{ fill: "hsl(var(--border-strong))" }} />
                    <circle cx="76" cy={y + 42} r="5" style={{ fill: "hsl(var(--border-strong))" }} />
                    <rect x="46" y={y + 6} width="240" height="32" rx="2" style={{ fill: "hsl(var(--muted))", stroke: "hsl(var(--border-strong))" }} />
                    <rect x="48" y={y + 8} width={236 * pct} height="28" style={{ fill: fillCol, opacity: 0.85 }} />
                    <text x="292" y={y + 27} fontSize="10" className="tnum" style={{ fill: "hsl(var(--faint))" }}>
                      {Math.round(pct * 100)}%</text>
                    <text x="52" y={y + 26} fontSize="10" fontWeight="700" className="tnum"
                      style={{ fill: pct > 0.15 ? "hsl(var(--surface))" : "hsl(var(--faint))" }}>TRUCK {t + 1}</text>
                  </g>
                );
              })}
            </svg>
            <div className="text-[11.5px] text-faint">
              26-ft box: ~{TRUCK_CF.toLocaleString()} usable cu ft{showBuild ? `, ~${TRUCK_LBS.toLocaleString()} lb payload. Dense loads hit the weight limit before the volume limit.` : "."}
            </div>
            {r.trucks > 1 && (
              <div data-testid="scope-trucks-banner" className="mt-2 rounded bg-accent-wash border border-accent/40 px-3 py-2 text-[12.5px] font-bold text-accent-ink leading-snug">
                {r.trucks} trucks required{showBuild && overWeight ? " — weight, not volume, is the binding limit" : ""}.
              </div>
            )}
          </div>

          {/* Crew & time — recommended values, overridable in every tier; the quote follows */}
          <div className="surface p-4" data-testid="scope-crew-time-card">
            <Eyebrow>Crew & time — recommended, override if you know better</Eyebrow>
            <div className="flex justify-between items-center py-1.5 border-b border-border">
              <span className="text-[12.5px] text-ink-2">
                Crew
                <span className="text-[10.5px] text-faint ml-1.5">recommended {r.crewRec}</span>
              </span>
              <span className="inline-flex items-center gap-2.5">
                <button type="button" data-testid="scope-crew-minus" aria-label="Fewer crew"
                  onClick={() => setCrewOverride(Math.max(1, (crewOverride || r.crewRec) - 1))}
                  className="relative w-[22px] h-[22px] rounded bg-surface-sunk text-ink-2 text-[13px] font-bold leading-none hover:text-primary before:content-[''] before:absolute before:-inset-[11px]">–</button>
                <span data-testid="scope-crew-value" className={`tnum text-[14px] w-[26px] text-center font-semibold ${crewOverride ? "text-accent-ink" : "text-primary"}`}>{r.crew}</span>
                <button type="button" data-testid="scope-crew-plus" aria-label="More crew"
                  onClick={() => setCrewOverride(Math.min(12, (crewOverride || r.crewRec) + 1))}
                  className="relative w-[22px] h-[22px] rounded bg-surface-sunk text-ink-2 text-[13px] font-bold leading-none hover:text-primary before:content-[''] before:absolute before:-inset-[11px]">+</button>
                {crewOverride != null && (
                  <button data-testid="scope-crew-reset" onClick={() => setCrewOverride(null)}
                    className="text-[10.5px] font-bold text-accent-ink hover:underline min-h-[44px]">reset</button>
                )}
              </span>
            </div>
            <div className="flex justify-between items-center py-1.5">
              <span className="text-[12.5px] text-ink-2">
                Hours on site
                <span className="text-[10.5px] text-faint ml-1.5">recommended {r.onsiteRec.toFixed(1)}</span>
              </span>
              <span className="inline-flex items-center gap-2">
                <Input data-testid="scope-hours-input" type="number" min="1" max="16" step="0.5"
                  value={hoursOverride ?? ""} placeholder={r.onsiteRec.toFixed(1)}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (v === "") { setHoursOverride(null); return; }
                    const n = Number(v);
                    if (!Number.isNaN(n)) setHoursOverride(Math.min(16, Math.max(0.5, n)));
                  }}
                  className={`h-9 w-[84px] text-right tnum ${hoursOverride ? "ring-2 ring-accent/70" : ""}`} />
                {hoursOverride != null && (
                  <button data-testid="scope-hours-reset" onClick={() => setHoursOverride(null)}
                    className="text-[10.5px] font-bold text-accent-ink hover:underline min-h-[44px]">reset</button>
                )}
              </span>
            </div>
            {r.hardFloorApplied && (
              <p data-testid="scope-hard-floor-note" className="text-[11px] text-warning font-semibold mt-1">
                {Number(P.hardFloorHours) || 6}-hour minimum applied — 3BR+ moves never bill under it.
              </p>
            )}
            {r.customCrewFloor >= 3 && (
              <p data-testid="scope-crew-floor-note" className="text-[11px] text-warning font-semibold mt-1">
                {r.customCrewFloor}-man minimum: heavy item{(acc.stairsO || 0) + (acc.stairsD || 0) > 0 ? " on stairs" : ""}.
                Fewer movers can't arrest that weight — this floor beats any override.
              </p>
            )}
            <p className="text-[10.5px] text-faint mt-1 leading-snug">
              {crewOverride != null || hoursOverride != null
                ? (showPricing ? "Using your numbers — the quote below follows them." : "Using your numbers.")
                : "Using the recommended crew and time for this scope."}
            </p>
          </div>

          {!showPricing ? (
          <div className="surface p-4" data-testid="scope-no-pricing-card">
            <Eyebrow className="text-info">Survey walkthrough — no pricing at this access level</Eyebrow>
            <p className="text-[12.5px] text-primary leading-relaxed">
              Walk every room and set its tier, count the individual items, and note the access conditions.
              When you've seen everything, press <strong>Mark survey complete</strong> and then
              <strong> Submit to owner</strong>. The owner prices it from your scope.
            </p>
          </div>
          ) : gate.blocked ? (
          <div className="surface p-4 border-destructive/40" data-testid="scope-state-refusal-card">
            <Eyebrow className="text-destructive">Out of service area — no quote</Eyebrow>
            <p className="text-[12.5px] text-primary leading-relaxed">
              This move touches {gate.badStates.join(" / ")}. We only move within {gate.allowed.join(", ")} —
              decline politely and move to the next lead. Nothing to price, nothing to save.
            </p>
          </div>
          ) : hasBlockers ? (
          <div className="surface p-4 border-destructive/40" data-testid="scope-blocker-card">
            <Eyebrow className="text-destructive">On-site assessment required — no quote</Eyebrow>
            {r.blockers.map((b, i) => (
              <p key={i} data-testid="scope-blocker-message" className="text-[12.5px] text-primary leading-relaxed mb-1.5">
                {b.message}
              </p>
            ))}
            <p className="text-xs text-faint leading-relaxed">
              Save the scope so nothing is lost — the number comes after someone lays eyes (and a tape measure) on it.
            </p>
          </div>
          ) : (
          <div className="surface p-4">
            <Eyebrow className={finalMode ? "text-success" : "text-accent-ink"}>
              {finalMode ? "Final quote — survey complete" : "Range — survey not complete · non-binding"}
            </Eyebrow>
            {finalMode ? (
              <>
                <div data-testid="scope-final-value" className="tnum text-[32px] font-semibold tracking-tight leading-tight text-primary">
                  {money(finalTotal)}
                </div>
                <div className="flex justify-between items-baseline mt-1">
                  <span className="text-[12.5px] text-ink-2">Deposit to book ({P.depositPercent}%)</span>
                  <span data-testid="scope-deposit-value" className="tnum text-[15px] font-semibold text-accent-ink">{moneyCents(deposit)}</span>
                </div>
                <p className="text-[11.5px] text-faint mt-1 leading-snug">One firm price. This is the number that goes on the written estimate.</p>
              </>
            ) : (
              <>
                <div data-testid="scope-band-value" className="tnum text-[32px] font-semibold tracking-tight leading-tight text-primary">
                  {money(bandLo)}<span className="text-faint font-normal">–</span>{money(bandHi)}
                </div>
                <p className="text-[11.5px] text-faint mt-1 leading-snug">
                  Spread {(spread * 100).toFixed(0)}% — derived by moving every high-variance space one tier either way.
                  Needs a survey before it can become a firm price.
                </p>
              </>
            )}

            <div className="mt-3">
              <Stat label="Crew" value={r.crew} />
              {showBuild && (
                <>
                  <Stat label="Block on the calendar" value={`${r.onsite.toFixed(1)} hrs`} accent />
                  <Stat label="Billable man-hours" value={r.billMH.toFixed(1)} />
                  <Stat label="Scheduling man-hours" value={r.schedMH.toFixed(1)} last />
                </>
              )}
            </div>

            {showBuild && (
            <>
            <Eyebrow className="mt-3.5">Price build</Eyebrow>
            <Stat label={`Labor · ${r.billMH.toFixed(1)} mh × ${moneyCents(P.manHourRate)}`} value={money(r.labor)} />
            <Stat label={`Trip fee (${jobType === "labor" ? "labor only" : "truck"}) × ${r.trucks}`} value={money(r.travel)} />
            {r.distBill > 0 && <Stat label={`Mileage — ${r.mileage.extra} mi beyond the first ${r.mileage.free} × ${moneyCents(P.mileageRatePerMile)}/mi`} value={money(r.distBill)} />}
            {r.accBill > 0 && <Stat label="Stairs / carries / stops" value={money(r.accBill)} />}
            {r.handlingBilled > 0 && <Stat label="Specialty handling" value={money(r.handlingBilled)} />}
            {r.handlingRaw > r.handlingBilled + 0.005 && (
              <p data-testid="scope-handling-cap-note" className="text-[10.5px] text-info leading-snug py-0.5">
                Handling capped at {Number(P.specialtyHandlingCapPct) || 30}% of labor on specialty-only jobs
                (uncapped it would be {money(r.handlingRaw)}).
              </p>
            )}
            {r.matBill > 0 && <Stat label="Materials" value={money(r.matBill)} />}
            <Stat label={`+ ${P.cushionPercent}% cushion`} value={money(r.cushioned - r.sub)} />
            {r.total > r.cushioned - 0.005 && r.priceFloor > r.cushioned && (
              <Stat label={`Price floor (${jobType === "labor" ? "labor only" : "truck"})`} value={money(r.priceFloor)} />
            )}
            <Stat label={`Rounded UP to next $${inc}`} value={money(finalMode ? finalTotal : bandHi)} last />
            </>
            )}

            {showBuild && r.onsite > 9 && (
              <div className="mt-2 rounded bg-destructive text-destructive-foreground px-3 py-2 text-[12.5px] font-bold leading-snug">
                {r.onsite.toFixed(1)}-hour day. Add crew or split it across two days — the last two hours
                are when damage claims happen.
              </div>
            )}
          </div>
          )}

          {isOwner && showPricing && !gate.blocked && !hasBlockers && r.specialtyOnly && (() => {
            const catKey = sanityCat || guessSanityCat(qty, custom);
            const cat = SANITY_BANDS.find((b) => b.k === catKey);
            const headline = finalMode ? finalTotal : bandHi;
            return (
              <div className="surface p-4" data-testid="scope-sanity-card">
                <Eyebrow className="mb-1.5">Market sanity check — owner only, never saved</Eyebrow>
                <select data-testid="scope-sanity-select" aria-label="Job category for sanity check" value={catKey}
                  onChange={(e) => setSanityCat(e.target.value)}
                  className="h-9 rounded-md border border-border bg-surface px-2 text-xs font-semibold text-primary">
                  {SANITY_BANDS.map((b) => <option key={b.k} value={b.k}>{b.n}</option>)}
                </select>
                {cat && headline > cat.hi ? (
                  <p data-testid="scope-sanity-warning" className="text-[12px] text-warning font-semibold mt-2 leading-snug">
                    {money(headline)} is above the typical range for this job type ({money(cat.lo)}–{money(cat.hi)}).
                    Confirm the scope justifies it before sending.
                  </p>
                ) : cat ? (
                  <p data-testid="scope-sanity-ok" className="text-[11px] text-faint mt-2">
                    Typical range {money(cat.lo)}–{money(cat.hi)} — you're at {money(headline)}.
                  </p>
                ) : null}
              </div>
            );
          })()}

          {!finalMode && flagged.length > 0 && (
            <div className="surface p-4 border-warning/50">
              <Eyebrow className="text-warning mb-1.5">Survey these before quoting</Eyebrow>
              <p className="text-[12.5px] leading-relaxed mb-2 text-primary">{flagged.join(" · ")}</p>
              <p className="text-xs text-faint leading-relaxed">
                <strong className="text-primary">Also confirm on site:</strong> what won't load — {NON_TRANSPORT}.
                A "packed" garage is often a third non-transportable. Deduct it before you sign the estimate.
              </p>
            </div>
          )}

          {!viewingSaved && (
          <div className="surface p-4">
            <div className="flex items-center gap-2 mb-2">
              <Input data-testid="scope-label-input" placeholder="Label (customer / address)" value={label}
                onChange={(e) => setLabel(e.target.value)} className="h-9 flex-1" />
              <Button data-testid="scope-save-btn" size="sm" className="gap-1.5 bg-accent hover:bg-accent-press min-h-[44px]"
                disabled={saving || (r.cf === 0 && !pkg) || gate.blocked} onClick={saveScope}>
                <Save className="w-3.5 h-3.5" /> {saving ? "Saving…" : isSurvey ? "Submit to owner" : refineFrom ? "Save as new version" : "Save scope"}
              </Button>
            </div>
            <p className="text-[11px] text-faint">
              {gate.blocked
                ? "Out-of-state moves can't be saved — we refuse the job on the call."
                : isSurvey
                ? "Submitting sends your walkthrough scope to the owner — they price it from there."
                : "Saving snapshots today's pricing values with the quote. Changing Settings later never re-prices a saved scope."}
            </p>
          </div>
          )}

          {isOwner && (
          <div className="surface p-4">
            <button data-testid="scope-margin-toggle" onClick={() => setOwnerBlock(!ownerBlock)}
              className="text-[11px] font-bold tracking-[.14em] uppercase text-faint hover:text-primary min-h-[44px]">
              {ownerBlock ? "▾" : "▸"} Margin — owner only
            </button>
            {ownerBlock && (() => {
              const crewCost = r.schedMH * 25.3, truckOp = 140 * r.trucks, matCost = r.matBill * 0.4;
              const cost = crewCost + truckOp + matCost + 25 * r.trucks;
              const worst = out.lo.total - (out.lo.schedMH * 25.3 + 140 * out.lo.trucks + 25 * out.lo.trucks);
              const mid = finalMode ? finalTotal : (bandLo + bandHi) / 2;
              return (
                <div className="mt-2" data-testid="scope-margin-block">
                  <Stat label={`Crew · ${r.schedMH.toFixed(1)} mh × $25.30`} value={money(crewCost)} />
                  <Stat label="Truck operating + materials" value={money(truckOp + matCost + 25 * r.trucks)} />
                  <div className="flex justify-between items-baseline py-1.5 text-[12.5px] border-b border-border">
                    <span className="font-bold text-primary">Gross at midpoint</span>
                    <span className={`tnum text-[15px] font-semibold ${(mid - cost) / (mid || 1) < 0.4 ? "text-destructive" : "text-success"}`}>
                      {money(mid - cost)} · {mid ? (((mid - cost) / mid) * 100).toFixed(0) : 0}%</span>
                  </div>
                  <Stat label="Gross if you quote low and it runs high" value={money(worst)} last />
                  <p className="text-[11.5px] text-faint mt-2 leading-snug">
                    Never send this block to a customer, a sales rep, or the crew.
                  </p>
                </div>
              );
            })()}
          </div>
          )}
        </div>
      </div>
    </div>
  );
}
