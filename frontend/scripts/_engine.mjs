/* Haul Yeah Moving — Scope engine (Pricing Spec v2.0)
   Scope arithmetic (rooms/items volume & weight, crew sizing) is calibrated.
   EVERY dollar figure comes from the pricing config P (backend /api/settings/rates)
   — nothing monetary is hardcoded here. Pure JS, no imports, node-testable. */

export const TIERS = ["—", "Light", "Avg", "Packed"];
export const TRUCK_CF = 1500;      // usable cu ft, 26-ft box, blanket-wrapped
export const TRUCK_LBS = 9000;     // safe payload; verify each door-jamb sticker

/* v = cu ft at Light/Avg/Packed · w = lbs per cu ft · i = what's included at each tier */
export const ROOMS = [
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

/* Items priced by handling, not just volume. mh = added man-hours each.
   billKey = specialty surcharge key in the pricing config (spec v2.0). */
export const ITEMS = [
  { g: "Appliances", k: "fridge", n: "Refrigerator", cf: 60, lbs: 300, mh: 0.75 },
  { g: "Appliances", k: "fridge2", n: "Fridge — French door / built-in", cf: 75, lbs: 400, mh: 1.25 },
  { g: "Appliances", k: "washer", n: "Washer", cf: 25, lbs: 200, mh: 0.5 },
  { g: "Appliances", k: "dryer", n: "Dryer", cf: 25, lbs: 150, mh: 0.5 },
  { g: "Appliances", k: "range", n: "Range / oven", cf: 30, lbs: 200, mh: 0.5 },
  { g: "Appliances", k: "freezer", n: "Chest freezer", cf: 35, lbs: 200, mh: 0.75 },

  { g: "Heavy & awkward", k: "upright", n: "Upright piano", cf: 60, lbs: 500, mh: 1.5, billKey: "surchargeUprightPiano" },
  { g: "Heavy & awkward", k: "grand", n: "Grand piano", cf: 100, lbs: 700, mh: 2.5, billKey: "surchargeGrandPiano" },
  { g: "Heavy & awkward", k: "safe1", n: "Safe — under 300 lb", cf: 25, lbs: 250, mh: 1.0, billKey: "surchargeSafeT1" },
  { g: "Heavy & awkward", k: "safe2", n: "Safe — 300–700 lb", cf: 30, lbs: 500, mh: 1.25, billKey: "surchargeSafeT2" },
  { g: "Heavy & awkward", k: "safe3", n: "Safe — over 700 lb", cf: 35, lbs: 800, mh: 1.5, billKey: "surchargeSafeT3" },
  { g: "Heavy & awkward", k: "pool", n: "Pool table (slate)", cf: 90, lbs: 800, mh: 2.5, billKey: "surchargePoolTable" },
  { g: "Heavy & awkward", k: "tread", n: "Treadmill / single machine", cf: 40, lbs: 250, mh: 0.75, billKey: "surchargeGymT1" },
  { g: "Heavy & awkward", k: "gym", n: "Squat rack / multi-station gym", cf: 70, lbs: 500, mh: 1.25, billKey: "surchargeGymT2" },
  { g: "Heavy & awkward", k: "plates", n: "Weight set / plates (billed in hours)", cf: 20, lbs: 400, mh: 0.75 },
  { g: "Heavy & awkward", k: "mower", n: "Riding mower", cf: 60, lbs: 500, mh: 1.0 },
  { g: "Heavy & awkward", k: "moto", n: "Motorcycle / ATV", cf: 80, lbs: 450, mh: 1.5, billKey: "surchargeMotorcycle" },

  { g: "Fragile & oversized", k: "hutch", n: "China cabinet / hutch", cf: 60, lbs: 250, mh: 0.75 },
  { g: "Fragile & oversized", k: "tv", n: 'TV 70"+', cf: 25, lbs: 80, mh: 0.5 },
  { g: "Fragile & oversized", k: "marble", n: "Marble / glass table top", cf: 30, lbs: 300, mh: 0.75 },
  { g: "Fragile & oversized", k: "sleeper", n: "Sleeper sofa", cf: 90, lbs: 300, mh: 0.5 },
  { g: "Fragile & oversized", k: "tank", n: "Aquarium 50 gal+", cf: 25, lbs: 150, mh: 1.0 },
];

/* scopes saved before v2.0 used a single flat-priced safe (700 lb class) */
export const LEGACY_ITEM_KEYS = { safe: "safe2" };

/* Custom specialty items — weight is BANDED, never a free number: a free number
   means the operator guesses differently every time and every quote becomes a
   negotiation with himself. Handling dollars come from the pricing config. */
export const CUSTOM_BANDS = [
  { k: "under150", n: "Under 150 lb", billKey: "surchargeCustomB1", cf: 20, lbs: 120, mh: 0.5, crewFloor: 2, crewFloorStairs: 2 },
  { k: "w150_299", n: "150–299 lb", billKey: "surchargeCustomB2", cf: 30, lbs: 220, mh: 0.75, crewFloor: 3, crewFloorStairs: 3 },
  { k: "w300_499", n: "300–499 lb", billKey: "surchargeCustomB3", cf: 45, lbs: 400, mh: 1.0, crewFloor: 3, crewFloorStairs: 4 },
  { k: "w500_799", n: "500–799 lb", billKey: "surchargeCustomB4", cf: 60, lbs: 650, mh: 1.25, crewFloor: 4, crewFloorStairs: 4 },
  { k: "w800plus", n: "800 lb or more", blocked: true },
];

export const PACKING = [
  { n: "Fully packed, furniture broken down", m: 1.0 },
  { n: "Mostly packed, a few loose items", m: 1.12 },
  { n: "Partially packed — closets or kitchen loose", m: 1.3 },
  { n: "Not packed", m: 1.6 },
];

/* Access man-hours scale with volume (base calibrated at 800 cu ft).
   Billed dollars are FLAT per unit per spec v2.0 — never volume-scaled. */
export const ACCESS = [
  { k: "stairsO", n: "Flights of stairs — pickup", per: 1.5, billKey: "stairFlightFee", count: 6, scale: true },
  { k: "stairsD", n: "Flights of stairs — drop-off", per: 1.5, billKey: "stairFlightFee", count: 6, scale: true },
  { k: "elevO", n: "Shared building elevator", per: 2.0, scale: true },
  { k: "carryO", n: "Long carry >50 ft — pickup", per: 1.5, billKey: "longCarryFee", scale: true },
  { k: "carryD", n: "Long carry >50 ft — drop-off", per: 1.5, billKey: "longCarryFee", scale: true },
  { k: "ladder", n: "Attic pull-down ladder only", per: 2.0 },
  { k: "tight", n: "Destination furnished / tight", per: 2.0, scale: true },
  { k: "noPark", n: "No truck parking — shuttle", per: 3.0, scale: true },
  { k: "disasm", n: "Major pieces needing disassembly", per: 0.75, billKey: "disassemblyFee", count: 12 },
  { k: "stops", n: "Extra stops (storage, 2nd address)", per: 1.0, billKey: "extraStopFee", count: 4 },
];

export const MATERIALS = [
  { k: "mattress", n: "Mattress bags", priceKey: "materialMattressBag", cap: 8 },
  { k: "wardrobe", n: "Wardrobe boxes", priceKey: "materialWardrobeBox", cap: 20 },
  { k: "tvbox", n: "TV boxes", priceKey: "materialTvBox", cap: 6 },
];

export const NON_TRANSPORT = "Propane tanks · gasoline & fuel cans · paint & solvents · aerosols · pool chemicals · fertilizer · ammunition · fire extinguishers · perishables · live plants";

/* Package defaults (crew / hours) — quick-start presets per home size */
export const PKGS = [
  { k: "studio", n: "Studio/1BR", crewKey: "pkgStudioCrew", hoursKey: "pkgStudioHours", beds: 1 },
  { k: "br2", n: "2BR", crewKey: "pkg2brCrew", hoursKey: "pkg2brHours", beds: 2 },
  { k: "br3", n: "3BR", crewKey: "pkg3brCrew", hoursKey: "pkg3brHours", beds: 3 },
  { k: "br4", n: "4BR+", crewKey: "pkg4brCrew", hoursKey: "pkg4brHours", beds: 4 },
];

export const STATE_OPTIONS = ["NJ", "NY", "PA", "DE", "CT", "Other"];

/* survey tier gets no pricing values at all — engine runs with zeros, UI shows none.
   Non-monetary calibration/rule values stay so crew & hours still work. */
export const NO_PRICING = {
  manHourRate: 0, cushionPercent: 0, depositPercent: 0, roundingIncrement: 25, manHoursPer100CuFt: 2.1,
  tripFeeTruck: 0, tripFeeLabor: 0, floorTruck: 0, floorLabor: 0, minHoursTruck: 3, minHoursLabor: 2,
  mileageFreeMiles: 20, mileageRatePerMile: 0,
  stairFlightFee: 0, longCarryFee: 0, disassemblyFee: 0, extraStopFee: 0,
  surchargeUprightPiano: 0, surchargeGrandPiano: 0, surchargePoolTable: 0,
  surchargeSafeT1: 0, surchargeSafeT2: 0, surchargeSafeT3: 0,
  surchargeGymT1: 0, surchargeGymT2: 0, surchargeMotorcycle: 0,
  materialMattressBag: 0, materialWardrobeBox: 0, materialTvBox: 0,
  surchargeCustomB1: 0, surchargeCustomB2: 0, surchargeCustomB3: 0, surchargeCustomB4: 0,
  customBuiltInMultiplier: 0, customDisconnectMultiplier: 0, customSwapFactor: 0, specialtyHandlingCapPct: 0,
  hardFloorBedrooms: 3, hardFloorHours: 6,
  pkgStudioCrew: 2, pkgStudioHours: 3.5, pkg2brCrew: 3, pkg2brHours: 5.5,
  pkg3brCrew: 4, pkg3brHours: 6.5, pkg4brCrew: 4, pkg4brHours: 8,
  serviceStates: "NJ",
};

const num = (v, d = 0) => (Number.isFinite(Number(v)) ? Number(v) : d);

export const itemBill = (def, P) => (def.billKey ? num(P?.[def.billKey]) : 0);
export const materialPrice = (def, P) => num(P?.[def.priceKey]);

export const roundUpTo = (n, inc) => Math.ceil(n / Math.max(1, inc) - 1e-9) * Math.max(1, inc);

/* Mileage — one-way miles. The first `mileageFreeMiles` ride free in the trip fee;
   every mile after that bills at `mileageRatePerMile`. */
export function mileageInfo(miles, P) {
  const m = Math.max(0, num(miles));
  const free = num(P?.mileageFreeMiles, 20);
  const rate = num(P?.mileageRatePerMile);
  const extra = Math.max(0, Math.round((m - free) * 10) / 10);
  const fee = Math.round(extra * rate * 100) / 100;
  return { miles: m, free, rate, extra, fee,
    label: extra > 0 ? `${extra} mi beyond the first ${free}` : `first ${free} mi included` };
}

/* Out-of-state guard — we quote NJ-to-NJ only. Any other state = refuse. */
export function stateGate(pickupState, dropoffState, P) {
  const allowed = String(P?.serviceStates ?? "NJ").split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
  const bad = [...new Set([pickupState, dropoffState]
    .filter((s) => s && !allowed.includes(String(s).toUpperCase()))
    .map((s) => String(s).toUpperCase()))];
  return { blocked: bad.length > 0, badStates: bad, allowed };
}

/* ---- the engine — scope arithmetic calibrated, pricing per spec v2.0 ---- */
export function computeScope(inputs, P, shift = 0) {
  const { dens = {}, cnt = {}, qty = {}, acc = {}, mat = {}, pack = 0, rate = 2.1,
    jobType = "truck", crewOverride = null, hoursOverride = null, miles = 0, pkg = "" } = inputs || {};
  const custom = Array.isArray(inputs?.custom) ? inputs.custom : []; // scopes saved before custom items read as []

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

  /* Custom specialty items — feed the SAME cf/lbs/mh totals so trucks, volume
     scaling and the lo/hi band keep working untouched. */
  const hasStairs = (acc.stairsO || 0) + (acc.stairsD || 0) > 0;
  const blockers = [];
  let customBillTotal = 0, customCrewFloor = 0;
  custom.forEach((c) => {
    const band = CUSTOM_BANDS.find((b) => b.k === c?.band);
    if (!band) return;
    const label = String(c.name || "").trim() || "Custom item";
    const n = Math.max(1, Math.round(num(c.qty, 1)) || 1);
    if (band.blocked) {
      blockers.push({ code: "weight_800_plus",
        message: `"${label}" is 800 lb or more. An on-site assessment is required before quoting.` });
      return;
    }
    if (num(c.widthIn) > 0 && num(c.pathNarrowestIn) > 0 && num(c.widthIn) + 2 > num(c.pathNarrowestIn)) {
      blockers.push({ code: "clearance",
        message: `"${label}" is wider than the narrowest point on its path. An on-site assessment is required before quoting.` });
    }
    const units = c.isSwap ? 2 : 1;              // a swap carries the old unit out too — full cf/lbs/mh
    cf += band.cf * n * units; lbs += band.lbs * n * units; itemMH += band.mh * n * units;
    let per = num(P?.[band.billKey]);
    if (c.builtIn) per *= num(P?.customBuiltInMultiplier, 1);
    if (c.needsDisconnect) per *= num(P?.customDisconnectMultiplier, 1);
    let handling = per * n;
    if (c.isSwap) handling += per * num(P?.customSwapFactor, 0) * n;  // 2nd unit: same setup, real marginal risk
    customBillTotal += handling;
    customCrewFloor = Math.max(customCrewFloor, hasStairs ? band.crewFloorStairs : band.crewFloor);
  });
  /* Specialty-only is DERIVED, never a toggle — a household move always has a room set,
     so this can never fire on one. */
  const specialtyOnly = ROOMS.every((rm) => !dens[rm.k])
    && (ITEMS.some((it) => (qty[it.k] || 0) > 0) || custom.some((c) => CUSTOM_BANDS.some((b) => b.k === c?.band)));

  const pkgDef = PKGS.find((x) => x.k === pkg);
  const bedsEff = Math.max(beds, pkgDef ? pkgDef.beds : 0);

  const trucks = Math.max(1, Math.ceil(cf / TRUCK_CF), Math.ceil(lbs / TRUCK_LBS));
  const sc = Math.max(1, cf / 800);          // volume scaling factor (man-hours only)
  const volMH = (cf / 100) * rate * PACKING[pack].m;

  let accMH = 0, accBill = 0;
  ACCESS.forEach((a) => {
    const v = acc[a.k] || 0; if (!v) return;
    accMH += a.per * v * (a.scale ? sc : 1);
    accBill += itemBill(a, P) * v;           // flat dollars per flight / carry / piece / stop
  });
  let itemBillTotal = 0;
  ITEMS.forEach((it) => { if (it.billKey && qty[it.k]) itemBillTotal += itemBill(it, P) * qty[it.k]; });
  let matBill = 0;
  MATERIALS.forEach((m) => { matBill += (mat[m.k] || 0) * materialPrice(m, P); });

  let billMH = volMH + itemMH;
  const schedMH = billMH + accMH;

  const hardBeds = num(P?.hardFloorBedrooms, 3);
  const hardHours = num(P?.hardFloorHours, 6);

  let crewRec = schedMH < 12 ? 2 : schedMH < 24 ? 3 : 4;
  if (trucks >= 2) crewRec = 3 * trucks;
  if (bedsEff >= hardBeds) crewRec = Math.max(crewRec, 4);                       // 3BR+ runs with 4 crew
  else if (bedsEff >= 2 && crewRec === 3 && schedMH / 3 > hardHours) crewRec = 4; // 2–3BR running long → 4th mover
  if (customCrewFloor) crewRec = Math.max(crewRec, customCrewFloor);             // heavy-item safety floor
  const crew = Math.max(crewOverride || crewRec, customCrewFloor);               // override can't go below it

  const minHours = jobType === "labor" ? num(P?.minHoursLabor, 2) : num(P?.minHoursTruck, 3);
  const hourFloor = bedsEff >= hardBeds ? Math.max(hardHours, minHours) : minHours;
  billMH = Math.max(billMH, hourFloor * Math.min(crew, 4));
  const onsiteRec = schedMH / crew;
  let onsite = onsiteRec;
  if (hoursOverride) {
    billMH = hoursOverride * crew;
    onsite = hoursOverride;
    if (bedsEff >= hardBeds) billMH = Math.max(billMH, hardHours * Math.min(crew, 4)); // HARD 6-hr floor — override can't go below
  }
  const floorMH = hourFloor * Math.min(crew, 4);
  const hardFloorApplied = bedsEff >= hardBeds && Math.abs(billMH - hardHours * Math.min(crew, 4)) < 1e-9
    && (hoursOverride ? hoursOverride * crew < billMH : volMH + itemMH < billMH);

  /* ---- final pricing steps — every value from the pricing config, exact spec order ---- */
  const manHourRate = num(P?.manHourRate);
  const tripFee = jobType === "labor" ? num(P?.tripFeeLabor) : num(P?.tripFeeTruck);
  const priceFloor = jobType === "labor" ? num(P?.floorLabor) : num(P?.floorTruck);
  const mileage = mileageInfo(miles, P);
  const distBill = mileage.fee;
  const labor = billMH * manHourRate;                                             // 1 flat man-hour rate
  const travel = tripFee * trucks;                                                // 2 trip fee
  const handlingRaw = itemBillTotal + customBillTotal;
  const handlingBilled = specialtyOnly                                            // cap only ever binds specialty-only:
    ? Math.min(handlingRaw, labor * (num(P?.specialtyHandlingCapPct, 30) / 100))  //   household stays bit-identical
    : handlingRaw;
  const sub = labor + travel + distBill + accBill + handlingBilled + matBill;     // 3 subtotal
  const cushioned = sub * (1 + num(P?.cushionPercent) / 100);                     // 4 cushion (never itemized)
  const total = Math.max(cushioned, priceFloor);                                  // 5 price floor (round-up at output)

  return { cf, lbs, trucks, sc, volMH, itemMH, accMH, accBill, itemBill: itemBillTotal, matBill, distBill, mileage,
    customBill: customBillTotal, handlingRaw, handlingBilled, specialtyOnly, blockers, customCrewFloor,
    billMH, schedMH, crew, crewRec, onsite, onsiteRec, labor, travel, sub, cushioned, total,
    beds, bedsEff, priceFloor, floorMH, hardFloorApplied };
}

export function scopeOutputs(inputs, P) {
  const r = computeScope(inputs, P, 0);
  const lo = computeScope(inputs, P, -1);
  const hi = computeScope(inputs, P, +1);
  const inc = Math.max(1, num(P?.roundingIncrement, 25));
  const roundUp = (n) => roundUpTo(n, inc);                                       // 6 — round UP, never down
  const bandLo = roundUp(Math.max(r.priceFloor, Math.min(lo.total, r.total) * 0.94));
  const bandHi = roundUp(Math.max(r.priceFloor, Math.max(hi.total, r.total) * 1.06));
  const spread = bandLo > 0 ? (bandHi - bandLo) / bandLo : 0;
  const finalTotal = roundUp(r.total);
  const deposit = Math.round(finalTotal * num(P?.depositPercent)) / 100;          // 7 deposit
  return { r, lo, hi, inc, bandLo, bandHi, spread, finalTotal, deposit };
}
