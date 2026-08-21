import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Save, RotateCcw, FolderOpen, X, PencilRuler } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { PageTitle } from "@/components/Bits";
import { apiErrorMessage, getScopeApi, getScopeAccessApi, getScopePricingValuesApi, listScopesApi, saveScopeApi } from "@/lib/api";

/* Haul Yeah Moving — Job Scope Calculator (v2 port)
   Scope arithmetic (ROOMS/ITEMS/PACKING/ACCESS/MATERIALS, volume/weight maths,
   crew sizing, billable-hour floor) is calibrated — DO NOT ALTER.
   Final pricing steps read from Settings → scope pricing (owner-only). */

const TIERS = ["—", "Light", "Avg", "Packed"];
const TRUCK_CF = 1500;      // usable cu ft, 26-ft box, blanket-wrapped
const TRUCK_LBS = 9000;     // safe payload; verify each door-jamb sticker

/* v = cu ft at Light/Avg/Packed · w = lbs per cu ft · i = what's included at each tier */
const ROOMS = [
  { g: "Bedrooms", k: "primary", n: "Primary bedroom", v: [180, 250, 340], w: 6, bed: true, i: [
    "Queen bed set, 1 dresser, 1 nightstand, ~4 boxes",
    "King/queen bed set, dresser, 2 nightstands, chest, TV, ~10 boxes",
    "Above + armoire or wardrobe, bench, full mirror, packed closet, 20+ boxes" ] },
  { g: "Bedrooms", k: "stdbed", n: "Standard bedroom", v: [130, 190, 260], w: 6, bed: true, i: [
    "Full/twin bed, small dresser, ~3 boxes",
    "Queen bed, dresser, nightstand, desk or chair, ~8 boxes",
    "Above + bookcase, TV, toy storage, packed closet, 15+ boxes" ] },
  { g: "Bedrooms", k: "smallbed", n: "Small bedroom / nursery", v: [90, 130, 180], w: 6, bed: true, i: [
    "Twin bed or crib, small dresser, ~2 boxes",
    "Bed, dresser, changing table or desk, ~6 boxes",
    "Bed, dresser, glider, shelving, 12+ boxes" ] },

  { g: "Living areas", k: "living", n: "Living room", v: [180, 275, 400], w: 6, i: [
    "Sofa, coffee table, TV + stand, ~4 boxes",
    "Sofa, loveseat or 2 chairs, coffee table, 2 end tables, TV + console, rug, ~10 boxes",
    "Sectional, recliners, wall unit or bookcases, large TV, rug, lamps, 20+ boxes" ] },
  { g: "Living areas", k: "family", n: "Family room / den", v: [220, 330, 480], w: 6, i: [
    "Sectional, TV, ~4 boxes",
    "Sectional, recliner, media console, TV, side tables, ~10 boxes",
    "Above + bar, bookcases, game table, 20+ boxes" ] },
  { g: "Living areas", k: "dining", n: "Dining room", v: [120, 200, 290], w: 8, i: [
    "Table + 4 chairs, ~3 boxes",
    "Table + 6 chairs, buffet or hutch, ~8 boxes china",
    "Table + 8 chairs, china cabinet, buffet, bar cart, 15+ boxes glass/china" ] },
  { g: "Living areas", k: "kitchen", n: "Kitchen", v: [90, 140, 220], w: 9, i: [
    "~6 boxes, microwave, small table",
    "Table + chairs, ~15 boxes, microwave, small appliances",
    "25+ boxes, island or cart, full pantry, small appliances — major appliances counted separately" ] },
  { g: "Living areas", k: "office", n: "Home office", v: [80, 130, 200], w: 10, i: [
    "Desk, chair, ~3 boxes",
    "Desk, chair, file cabinet, bookcase, monitors, ~8 boxes",
    "L-desk, 2 file cabinets, multiple bookcases, printer, 15+ boxes of books" ] },
  { g: "Living areas", k: "bath", n: "Bathroom", v: [15, 25, 40], w: 8, i: [
    "~1 box", "~2 boxes, small cabinet, hamper", "~4 boxes, storage cabinet, linens" ] },
  { g: "Living areas", k: "laundry", n: "Laundry room", v: [30, 60, 100], w: 7, i: [
    "Shelving, ~2 boxes",
    "Shelving, utility cart, ironing board, ~4 boxes",
    "Cabinets, drying racks, 8+ boxes — washer/dryer counted separately" ] },
  { g: "Living areas", k: "misc", n: "Hallways / linen closets", v: [30, 60, 110], w: 7, i: [
    "Console table, ~2 boxes", "Linens, coats, ~5 boxes, small shelving", "10+ boxes, storage cabinets, coat closet" ] },

  { g: "High-variance spaces", k: "basefin", n: "Basement — finished", v: [200, 350, 550], w: 7, risky: true, i: [
    "Sofa, TV, ~5 boxes",
    "Sofa, TV + stand, shelving, exercise piece, ~15 boxes",
    "Full second living room + storage shelving, 30+ boxes and bins" ] },
  { g: "High-variance spaces", k: "baseunfin", n: "Basement — unfinished", v: [150, 350, 700], w: 10, risky: true, i: [
    "One shelving unit, ~8 boxes, hand tools",
    "2–3 shelving units, workbench, tools, ~20 boxes and bins",
    "Wall-to-wall shelving, workbench, spare furniture, 40+ boxes and bins" ] },
  { g: "High-variance spaces", k: "attic", n: "Attic", v: [80, 200, 400], w: 6, risky: true, i: [
    "~6 boxes or bins",
    "~15 bins, holiday decor, luggage",
    "30+ bins, spare furniture, filled to the rafters" ] },
  { g: "High-variance spaces", k: "gar1", n: "Garage — 1 car", v: [150, 300, 500], w: 10, risky: true, i: [
    "Car still parks in it. Bikes, a few bins, hand tools",
    "No car fits, but you can walk to the back wall. Shelving, ~15 bins, mower, tools",
    "It's at the door. Full shelving, workbench, 30+ bins, mower, spare fridge" ] },
  { g: "High-variance spaces", k: "gar2", n: "Garage — 2 car", v: [300, 550, 900], w: 10, risky: true, i: [
    "Both cars still park. Perimeter shelving, bins, bikes",
    "One bay usable. Shelving on both walls, ~25 bins, mower, workbench",
    "No bays. Wall-to-wall, 50+ bins, workbench, spare appliances, seasonal" ] },
  { g: "High-variance spaces", k: "shed", n: "Shed", v: [60, 130, 240], w: 10, risky: true, i: [
    "Mower, a few tools", "Mower, shelving, yard tools, ~8 bins", "Packed — shelving, equipment, 15+ bins" ] },
  { g: "High-variance spaces", k: "patio", n: "Patio / deck", v: [60, 120, 220], w: 8, i: [
    "Bistro set, grill",
    "Patio set + 4–6 chairs, grill, umbrella, planters",
    "Sectional patio set, grill, fire pit, heater, 8+ planters, deck box" ] },
  { g: "High-variance spaces", k: "closet", n: "Walk-in closet overflow", v: [30, 60, 100], w: 5, i: [
    "~2 wardrobe boxes", "~4 wardrobe boxes, shoe storage", "8+ wardrobe boxes, shelving, seasonal" ] },
  { g: "High-variance spaces", k: "unit10", n: "Storage unit (10×10)", v: [400, 600, 800], w: 8, risky: true, i: [
    "Half full, walkway down the middle", "Two-thirds full, stacked chest height", "Full to the door, floor to ceiling" ] },
  { g: "High-variance spaces", k: "unit5", n: "Storage unit (5×10)", v: [200, 300, 400], w: 8, risky: true, i: [
    "Half full", "Two-thirds full", "Full to the door" ] },
];

/* Items priced by handling, not just volume. mh = added man-hours each. */
const ITEMS = [
  { g: "Appliances", k: "fridge", n: "Refrigerator", cf: 60, lbs: 300, mh: 0.75 },
  { g: "Appliances", k: "fridge2", n: "Fridge — French door / built-in", cf: 75, lbs: 400, mh: 1.25 },
  { g: "Appliances", k: "washer", n: "Washer", cf: 25, lbs: 200, mh: 0.5 },
  { g: "Appliances", k: "dryer", n: "Dryer", cf: 25, lbs: 150, mh: 0.5 },
  { g: "Appliances", k: "range", n: "Range / oven", cf: 30, lbs: 200, mh: 0.5 },
  { g: "Appliances", k: "freezer", n: "Chest freezer", cf: 35, lbs: 200, mh: 0.75 },

  { g: "Heavy & awkward", k: "upright", n: "Upright piano", cf: 60, lbs: 500, mh: 1.5, bill: 500 },
  { g: "Heavy & awkward", k: "grand", n: "Grand piano", cf: 100, lbs: 700, mh: 2.5, bill: 800 },
  { g: "Heavy & awkward", k: "safe", n: "Safe / gun safe", cf: 30, lbs: 700, mh: 1.25, bill: 400 },
  { g: "Heavy & awkward", k: "pool", n: "Pool table (slate)", cf: 90, lbs: 800, mh: 2.5, bill: 400 },
  { g: "Heavy & awkward", k: "gym", n: "Squat rack / home gym", cf: 70, lbs: 500, mh: 1.25 },
  { g: "Heavy & awkward", k: "tread", n: "Treadmill", cf: 40, lbs: 250, mh: 0.75 },
  { g: "Heavy & awkward", k: "plates", n: "Weight set / plates", cf: 20, lbs: 400, mh: 0.75 },
  { g: "Heavy & awkward", k: "mower", n: "Riding mower", cf: 60, lbs: 500, mh: 1.0 },
  { g: "Heavy & awkward", k: "moto", n: "Motorcycle / ATV", cf: 80, lbs: 450, mh: 1.5, bill: 300 },

  { g: "Fragile & oversized", k: "hutch", n: "China cabinet / hutch", cf: 60, lbs: 250, mh: 0.75 },
  { g: "Fragile & oversized", k: "tv", n: 'TV 70"+', cf: 25, lbs: 80, mh: 0.5 },
  { g: "Fragile & oversized", k: "marble", n: "Marble / glass table top", cf: 30, lbs: 300, mh: 0.75 },
  { g: "Fragile & oversized", k: "sleeper", n: "Sleeper sofa", cf: 90, lbs: 300, mh: 0.5 },
  { g: "Fragile & oversized", k: "tank", n: "Aquarium 50 gal+", cf: 25, lbs: 150, mh: 1.0 },
];

const PACKING = [
  { n: "Fully packed, furniture broken down", m: 1.0 },
  { n: "Mostly packed, a few loose items", m: 1.12 },
  { n: "Partially packed — closets or kitchen loose", m: 1.3 },
  { n: "Not packed", m: 1.6 },
];

/* Access adders scale with volume — one flight of stairs on 2,500 cu ft is not
   the same job as one flight on 800. Base is calibrated at 800 cu ft. */
const ACCESS = [
  { k: "stairsO", n: "Flights of stairs — origin", per: 1.5, bill: 85, count: 6, scale: true },
  { k: "stairsD", n: "Flights of stairs — destination", per: 1.5, bill: 85, count: 6, scale: true },
  { k: "elevO", n: "Shared building elevator", per: 2.0, scale: true },
  { k: "carryO", n: "Long carry >50 ft — origin", per: 1.5, scale: true },
  { k: "carryD", n: "Long carry >50 ft — destination", per: 1.5, scale: true },
  { k: "ladder", n: "Attic pull-down ladder only", per: 2.0 },
  { k: "tight", n: "Destination furnished / tight", per: 2.0, scale: true },
  { k: "noPark", n: "No truck parking — shuttle", per: 3.0, scale: true },
  { k: "disasm", n: "Pieces needing disassembly", per: 0.75, count: 12 },
  { k: "stops", n: "Extra stops (storage, 2nd address)", per: 1.0, bill: 125, count: 4 },
];

const MATERIALS = [
  { k: "mattress", n: "Mattress bags", price: 15, cap: 8 },
  { k: "wardrobe", n: "Wardrobe boxes", price: 12, cap: 20 },
  { k: "tvbox", n: "TV boxes", price: 25, cap: 6 },
];

const NON_TRANSPORT = "Propane tanks · gasoline & fuel cans · paint & solvents · aerosols · pool chemicals · fertilizer · ammunition · fire extinguishers · perishables · live plants";

/* survey tier gets no pricing values at all — engine runs with zeros, UI shows none */
const NO_PRICING = { manHourRate: 0, cushionPercent: 0, tripFeeTruck: 0, tripFeeLabor: 0,
  floorTruck: 0, floorLabor: 0, roundingIncrement: 25, depositPercent: 0, manHoursPer100CuFt: 2.1 };

const money = (n) => "$" + Math.round(n).toLocaleString();
const moneyCents = (n) => "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

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
  const [acc, setAcc] = useState({});
  const [mat, setMat] = useState({});
  const [pack, setPack] = useState(0);
  const [rate, setRate] = useState(2.1);
  const [jobType, setJobType] = useState("truck");
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

  const P = viewingSaved ? viewingSaved.pricing : livePricing;

  /* ---- engine — scope arithmetic UNCHANGED from the calibrated v2 file ---- */
  const price = (shift) => {
    let cf = 0, lbs = 0, itemMH = 0, beds = 0;
    ROOMS.forEach((r) => {
      let lvl = dens[r.k] || 0; if (!lvl) return;
      if (r.risky && shift) lvl = Math.min(3, Math.max(1, lvl + shift));
      const n = cnt[r.k] || 1;
      cf += r.v[lvl - 1] * n; lbs += r.v[lvl - 1] * n * r.w;
      if (r.bed) beds += n;
    });
    ITEMS.forEach((it) => {
      const n = qty[it.k] || 0; if (!n) return;
      cf += it.cf * n; lbs += it.lbs * n; itemMH += it.mh * n;
    });

    const trucks = Math.max(1, Math.ceil(cf / TRUCK_CF), Math.ceil(lbs / TRUCK_LBS));
    const sc = Math.max(1, cf / 800);          // volume scaling factor
    const volMH = (cf / 100) * rate * PACKING[pack].m;

    let accMH = 0, accBill = 0;
    ACCESS.forEach((a) => {
      const v = acc[a.k] || 0; if (!v) return;
      accMH += a.per * v * (a.scale ? sc : 1);
      if (a.bill) accBill += a.bill * v * (a.scale ? sc : 1);
    });
    let itemBill = 0;
    ITEMS.forEach((it) => { if (it.bill && qty[it.k]) itemBill += it.bill * qty[it.k]; });
    let matBill = 0;
    MATERIALS.forEach((m) => { matBill += (mat[m.k] || 0) * m.price; });

    let billMH = volMH + itemMH;
    const schedMH = billMH + accMH;

    let crewRec = schedMH < 12 ? 2 : schedMH < 24 ? 3 : 4;
    if (trucks >= 2) crewRec = 3 * trucks;
    const crew = crewOverride || crewRec;

    const hourFloor = beds >= 3 ? 6 : 3;
    billMH = Math.max(billMH, hourFloor * Math.min(crew, 4));
    const onsiteRec = schedMH / crew;
    let onsite = onsiteRec;
    if (hoursOverride) {
      billMH = hoursOverride * crew;   // explicit override — the owner's call beats the billable floor
      onsite = hoursOverride;
    }

    /* ---- final pricing steps — every value from Settings, exact spec order ---- */
    const manHourRate = P?.manHourRate ?? 0;
    const tripFee = jobType === "labor" ? (P?.tripFeeLabor ?? 0) : (P?.tripFeeTruck ?? 0);
    const priceFloor = jobType === "labor" ? (P?.floorLabor ?? 0) : (P?.floorTruck ?? 0);
    const labor = billMH * manHourRate;                                   // 2
    const travel = tripFee * trucks;                                      // 3
    const sub = labor + travel + accBill + itemBill + matBill;            // 4
    const cushioned = sub * (1 + (P?.cushionPercent ?? 0) / 100);         // 5
    const total = Math.max(cushioned, priceFloor);                        // 6 (rounding applied at output)

    return { cf, lbs, trucks, sc, volMH, itemMH, accMH, accBill, itemBill, matBill,
      billMH, schedMH, crew, crewRec, onsite, onsiteRec, labor, travel, sub, cushioned, total, beds, priceFloor };
  };

  /* eslint-disable react-hooks/exhaustive-deps */
  const r = useMemo(() => price(0), [dens, cnt, qty, acc, mat, pack, rate, jobType, crewOverride, hoursOverride, P]);
  const lo = useMemo(() => price(-1), [dens, cnt, qty, acc, mat, pack, rate, jobType, crewOverride, hoursOverride, P]);
  const hi = useMemo(() => price(+1), [dens, cnt, qty, acc, mat, pack, rate, jobType, crewOverride, hoursOverride, P]);
  /* eslint-enable react-hooks/exhaustive-deps */

  const inc = Math.max(1, P?.roundingIncrement ?? 25);
  const roundUp = (n) => Math.ceil(n / inc) * inc;                         // 7 — never down

  const bandLo = roundUp(Math.max(r.priceFloor, Math.min(lo.total, r.total) * 0.94));
  const bandHi = roundUp(Math.max(r.priceFloor, Math.max(hi.total, r.total) * 1.06));
  const spread = bandLo > 0 ? (bandHi - bandLo) / bandLo : 0;
  const finalTotal = roundUp(r.total);
  const deposit = finalTotal * ((P?.depositPercent ?? 0) / 100);           // 8

  const surveyDone = surveyComplete || video.received; // a received video counts as a completed survey

  useEffect(() => {
    if (!surveyDone && mode === "final") setMode("range");
  }, [surveyDone, mode]);

  const finalMode = mode === "final" && surveyDone;

  /* tier gates — UI mirrors of the backend enforcement, never the other way round */
  const isOwner = tier === "owner";
  const isFinalTier = tier === "final";
  const isSurvey = tier === "survey";
  const canFinal = isOwner || isFinalTier;
  const canSurveyToggle = isOwner || isFinalTier || isSurvey;
  const showBuild = isOwner || isFinalTier;   // price build + man-hour figures + weight detail
  const showPricing = !isSurvey;              // survey tier sees no pricing at all

  const flagged = ROOMS.filter((x) => x.risky && (dens[x.k] || 0) >= 2).map((x) => x.n);
  const overWeight = r.lbs > TRUCK_LBS * r.trucks * 0.92;
  const clear = () => { setDens({}); setCnt({}); setQty({}); setAcc({}); setMat({}); setPack(0); setSurveyComplete(false); setMode("range"); setViewingSaved(null); setRefineFrom(null); setLabel(""); setCrewOverride(null); setHoursOverride(null); setVideo({ link: "", received: false, date: "" }); };

  const loadSavedList = () => listScopesApi().then(setSavedList).catch((e) => toast.error(apiErrorMessage(e)));

  const applyInputs = (doc) => {
    const i = doc.inputs || {};
    setDens(i.dens || {}); setCnt(i.cnt || {}); setQty(i.qty || {}); setAcc(i.acc || {}); setMat(i.mat || {});
    setPack(i.pack || 0); setRate(i.rate || 2.1); setJobType(i.jobType || "truck");
    setCrewOverride(i.crewOverride ?? null); setHoursOverride(i.hoursOverride ?? null);
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
        inputs: { dens, cnt, qty, acc, mat, pack, rate, jobType, crewOverride, hoursOverride, mode: finalMode ? "final" : "range" },
        pricing: P,
        result: {
          cf: r.cf, lbs: r.lbs, trucks: r.trucks, crew: r.crew, crewRec: r.crewRec,
          onsiteHours: Math.round(r.onsite * 10) / 10,
          billMH: Math.round(r.billMH * 100) / 100, schedMH: Math.round(r.schedMH * 100) / 100,
          bandLo, bandHi, finalTotal: finalMode ? finalTotal : null,
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
                  {s.result?.mode === "final" && s.result?.finalTotal ? money(s.result.finalTotal)
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

      {/* Job type + survey + mode controls */}
      <div className="surface p-4 mb-4 flex flex-wrap items-center gap-x-6 gap-y-3">
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
          {showPricing && (
          <p className="text-[10.5px] text-faint mt-1">Sets the trip fee ({jobType === "labor" ? moneyCents(P.tripFeeLabor) : moneyCents(P.tripFeeTruck)}) and the price floor ({jobType === "labor" ? money(P.floorLabor) : money(P.floorTruck)}).</p>
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
            <button data-testid="scope-mode-final" aria-pressed={finalMode} disabled={!surveyDone}
              onClick={() => surveyDone && setMode("final")}
              title={surveyDone ? "" : "Locked until the survey is complete or a video survey is received"}
              className={`px-4 min-h-[44px] text-xs font-bold rounded disabled:opacity-40 disabled:cursor-not-allowed ${finalMode ? "bg-success text-white" : "bg-surface-sunk text-faint"}`}>
              Final {surveyDone ? "" : "🔒"}
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
                        {it.cf}cf · {it.lbs}lb · +{it.mh}mh{showPricing && it.bill ? ` · $${it.bill}` : ""}
                      </span></span>
                    <Step v={qty[it.k] || 0} lbl={it.n} max={4} set={(v) => setQty({ ...qty, [it.k]: v })} />
                  </div>
                ))}
              </div>
            ))}
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
              Stairs, carries and elevators scale with load size — currently ×{r.sc.toFixed(2)} at {r.cf.toLocaleString()} cu ft.
            </p>
            {ACCESS.map((a) => (
              <div className="grid grid-cols-[1fr_110px] gap-2 items-center py-1.5 border-b border-border" key={a.k}>
                <span className="text-[13.5px] font-semibold text-primary">{a.n}
                  <span className="tnum text-faint font-normal text-[11px] ml-2">
                    +{a.per}mh{showPricing && a.bill ? ` · $${a.bill}` : ""}{a.scale ? " ×vol" : ""}</span></span>
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
                  {showPricing && <span className="tnum text-faint font-normal text-[11px] ml-2">${m.price} ea</span>}</span>
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
            <p className="text-[10.5px] text-faint mt-1 leading-snug">
              {crewOverride != null || hoursOverride != null
                ? (showPricing ? "Using your numbers — the quote below follows them." : "Using your numbers.")
                : "Using the recommended crew and time for this scope."}
            </p>
          </div>

          {showPricing ? (
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
            {r.accBill > 0 && <Stat label="Stairs / stops" value={money(r.accBill)} />}
            {r.itemBill > 0 && <Stat label="Specialty handling" value={money(r.itemBill)} />}
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
          ) : (
          <div className="surface p-4" data-testid="scope-no-pricing-card">
            <Eyebrow className="text-info">Survey walkthrough — no pricing at this access level</Eyebrow>
            <p className="text-[12.5px] text-primary leading-relaxed">
              Walk every room and set its tier, count the individual items, and note the access conditions.
              When you've seen everything, press <strong>Mark survey complete</strong> and then
              <strong> Submit to owner</strong>. The owner prices it from your scope.
            </p>
          </div>
          )}

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
                disabled={saving || r.cf === 0} onClick={saveScope}>
                <Save className="w-3.5 h-3.5" /> {saving ? "Saving…" : isSurvey ? "Submit to owner" : refineFrom ? "Save as new version" : "Save scope"}
              </Button>
            </div>
            <p className="text-[11px] text-faint">
              {isSurvey
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
              const worst = lo.total - (lo.schedMH * 25.3 + 140 * lo.trucks + 25 * lo.trucks);
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
