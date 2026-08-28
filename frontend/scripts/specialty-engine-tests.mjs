/* Specialty Item Engine — acceptance tests T1–T8, T10.
   Runs the real engine file. T1 compares against anchors_before.json captured on main. */
import { copyFileSync, readFileSync } from "fs";
copyFileSync(new URL("../src/lib/scopeEngine.js", import.meta.url), "/app/frontend/scripts/_engine.mjs");
const E = await import("./_engine.mjs");
const { computeScope, scopeOutputs, NO_PRICING, CUSTOM_BANDS } = E;

const P = {
  manHourRate: 65, cushionPercent: 10, depositPercent: 25,
  roundingIncrement: 25, manHoursPer100CuFt: 2.1,
  tripFeeTruck: 125, tripFeeLabor: 75, floorTruck: 650, floorLabor: 375,
  minHoursTruck: 3, minHoursLabor: 2,
  mileageFreeMiles: 20, mileageRatePerMile: 0.85,
  stairFlightFee: 85, longCarryFee: 100, disassemblyFee: 100, extraStopFee: 125,
  surchargeUprightPiano: 500, surchargeGrandPiano: 800, surchargePoolTable: 600,
  surchargeSafeT1: 200, surchargeSafeT2: 500, surchargeSafeT3: 800,
  surchargeGymT1: 150, surchargeGymT2: 300, surchargeMotorcycle: 300,
  materialMattressBag: 15, materialWardrobeBox: 12, materialTvBox: 25,
  surchargeCustomB1: 75, surchargeCustomB2: 150, surchargeCustomB3: 250, surchargeCustomB4: 400,
  customBuiltInMultiplier: 1.25, customDisconnectMultiplier: 1.15,
  customSwapFactor: 0.6, specialtyHandlingCapPct: 30,
  hardFloorBedrooms: 3, hardFloorHours: 6,
  pkgStudioCrew: 2, pkgStudioHours: 3.5, pkg2brCrew: 3, pkg2brHours: 5.5,
  pkg3brCrew: 4, pkg3brHours: 6.5, pkg4brCrew: 4, pkg4brHours: 8,
  serviceStates: "NJ",
};

const HOUSEHOLD = {
  A: { dens: { primary: 2, stdbed: 2, living: 2, kitchen: 2, bath: 1 }, cnt: {}, qty: { upright: 1, washer: 1, dryer: 1 },
       acc: { stairsO: 1, stairsD: 1 }, mat: { mattress: 2 }, pack: 1, rate: 2.1, jobType: "truck", miles: 28 },
  B: { dens: { primary: 3, stdbed: 3, living: 3, dining: 2, kitchen: 3, gar1: 2 }, cnt: { stdbed: 2 },
       qty: { fridge: 1, safe2: 1, tv: 2 }, acc: { carryO: 1, disasm: 2 }, mat: { wardrobe: 4, tvbox: 2 },
       pack: 2, rate: 2.1, jobType: "truck", miles: 12 },
  C: { dens: { smallbed: 1, living: 1 }, cnt: {}, qty: { tread: 1, gym: 1, plates: 2 }, acc: { elevO: 1 }, mat: {},
       pack: 0, rate: 2.1, jobType: "labor", miles: 45, pkg: "studio", crewOverride: 2, hoursOverride: 3.5 },
};

const results = [];
const check = (test, expected, actual, pass) => results.push({ test, expected, actual, pass: !!pass });

// ---- T1: household regression against pre-change anchors (must run first)
const before = JSON.parse(readFileSync("/app/frontend/scripts/anchors_before.json", "utf8"));
for (const k of ["A", "B", "C"]) {
  const o = scopeOutputs(HOUSEHOLD[k], P);
  check(`T1 anchor ${k} finalTotal`, before[k].finalTotal, o.finalTotal, o.finalTotal === before[k].finalTotal);
  check(`T1 anchor ${k} deposit`, before[k].deposit, o.deposit, o.deposit === before[k].deposit);
  check(`T1 anchor ${k} band`, `${before[k].bandLo}-${before[k].bandHi}`, `${o.bandLo}-${o.bandHi}`,
        o.bandLo === before[k].bandLo && o.bandHi === before[k].bandHi);
}

// ---- T2: cap is a no-op whenever specialtyOnly === false
{
  const withCustom = { ...HOUSEHOLD.A, custom: [{ id: "x", name: "Gun safe", band: "w300_499", qty: 1, builtIn: true, needsDisconnect: false, widthIn: 30, pathNarrowestIn: 36, isSwap: false }] };
  const r = computeScope(withCustom, P, 0);
  check("T2 household specialtyOnly=false", false, r.specialtyOnly, r.specialtyOnly === false);
  check("T2 handlingBilled===handlingRaw", r.handlingRaw, r.handlingBilled, r.handlingBilled === r.handlingRaw);
  const plain = computeScope(HOUSEHOLD.A, P, 0);
  check("T2 plain household billed===raw===itemBill", plain.itemBill, plain.handlingBilled,
        plain.handlingBilled === plain.handlingRaw && plain.handlingRaw === plain.itemBill);
}

// ---- T3: cap binds on the Sub-Zero specialty-only job
const subZero = {
  dens: {}, cnt: {}, qty: {}, acc: { stairsO: 1, stairsD: 1 }, mat: {}, pack: 0, rate: 2.1,
  jobType: "labor", miles: 0,
  custom: [
    { id: "1", name: "Sub-Zero 42in built-in fridge (upstairs unit)", band: "w500_799", qty: 1, builtIn: true, needsDisconnect: false, widthIn: 42, pathNarrowestIn: 48, isSwap: true },
    { id: "2", name: "Sub-Zero 42in built-in fridge (downstairs unit)", band: "w500_799", qty: 1, builtIn: true, needsDisconnect: false, widthIn: 42, pathNarrowestIn: 48, isSwap: true },
  ],
};
{
  const r = computeScope(subZero, P, 0);
  const cap = r.labor * 0.30;
  check("T3 specialtyOnly", true, r.specialtyOnly, r.specialtyOnly === true);
  check("T3 handlingRaw > handlingBilled", "raw>billed", `${r.handlingRaw} > ${r.handlingBilled}`, r.handlingRaw > r.handlingBilled);
  check("T3 handlingBilled === labor*0.30", cap.toFixed(2), r.handlingBilled.toFixed(2), Math.abs(r.handlingBilled - cap) < 0.01);
  const o = scopeOutputs(subZero, P);
  check("T3 quote is sane (< $2150 hand-quote)", "< 2150", `${o.bandLo}-${o.bandHi}`, o.bandHi < 2150);
}

// ---- T4: no specialty-only combination can exceed labor*30%
{
  let violations = 0, tried = 0;
  const bands = ["under150", "w150_299", "w300_499", "w500_799"];
  for (const band of bands)
    for (const builtIn of [false, true])
      for (const needsDisconnect of [false, true])
        for (const isSwap of [false, true])
          for (const qtyN of [1, 3, 6])
            for (const jobType of ["labor", "truck"])
              for (const stairs of [0, 3]) {
                tried++;
                const r = computeScope({ dens: {}, qty: {}, acc: { stairsO: stairs }, jobType,
                  custom: [{ id: "t", band, qty: qtyN, builtIn, needsDisconnect, isSwap, widthIn: 0, pathNarrowestIn: 0 }] }, P, 0);
                if (!r.specialtyOnly) violations++;
                if (r.handlingBilled - r.labor * 0.30 > 1e-9) violations++;
              }
  check("T4 cap never exceeded across sweep", "0 violations", `${violations} violations / ${tried} combos`, violations === 0);
}

// ---- T5: clearance blocks (42in item through a 34in path)
{
  const r = computeScope({ dens: {}, qty: {}, acc: {},
    custom: [{ id: "c", name: "Sub-Zero 42in", band: "w500_799", qty: 1, builtIn: true, needsDisconnect: false, widthIn: 42, pathNarrowestIn: 34, isSwap: false }] }, P, 0);
  check("T5 clearance blocker present", "clearance", (r.blockers[0] || {}).code, r.blockers.some((b) => b.code === "clearance"));
  // boundary: width+2 must fit — 42 through 44 passes, 42 through 43 blocks
  const ok = computeScope({ dens: {}, qty: {}, custom: [{ id: "c", band: "w500_799", qty: 1, widthIn: 42, pathNarrowestIn: 44 }] }, P, 0);
  const tight = computeScope({ dens: {}, qty: {}, custom: [{ id: "c", band: "w500_799", qty: 1, widthIn: 42, pathNarrowestIn: 43 }] }, P, 0);
  check("T5 44in path clears a 42in item", 0, ok.blockers.length, ok.blockers.length === 0);
  check("T5 43in path blocks a 42in item", 1, tight.blockers.length, tight.blockers.length === 1);
}

// ---- T6: 800+ hard block
{
  const r = computeScope({ dens: {}, qty: {},
    custom: [{ id: "h", name: "Commercial safe", band: "w800plus", qty: 1 }] }, P, 0);
  check("T6 w800plus blocker", "weight_800_plus", (r.blockers[0] || {}).code, r.blockers.some((b) => b.code === "weight_800_plus"));
  check("T6 blocked item adds no dollars", 0, r.customBill, r.customBill === 0);
}

// ---- T7: crew floor beats the override
{
  const r = computeScope({ dens: {}, qty: {}, acc: { stairsO: 1 }, crewOverride: 2,
    custom: [{ id: "s", name: "Gun safe", band: "w300_499", qty: 1 }] }, P, 0);
  check("T7 crew floor holds vs override 2", 4, r.crew, r.crew === 4);
  const noStairs = computeScope({ dens: {}, qty: {}, acc: {}, crewOverride: 2,
    custom: [{ id: "s", band: "w300_499", qty: 1 }] }, P, 0);
  check("T7 same item no stairs floors at 3", 3, noStairs.crew, noStairs.crew === 3);
}

// ---- T8: survey tier (NO_PRICING) leaks zero dollars from custom items
{
  const r = computeScope(subZero, NO_PRICING, 0);
  const dollars = { customBill: r.customBill, handlingRaw: r.handlingRaw, handlingBilled: r.handlingBilled,
                    labor: r.labor, travel: r.travel, accBill: r.accBill, sub: r.sub, total: r.total, distBill: r.distBill };
  const leak = Object.entries(dollars).filter(([, v]) => v !== 0);
  check("T8 NO_PRICING → all $0", "all 0", JSON.stringify(dollars), leak.length === 0);
  check("T8 non-monetary still works (crew)", 4, r.crew, r.crew === 4);
}

// ---- T10: pre-custom saved scopes deserialize and price identically
{
  const legacy = { ...HOUSEHOLD.B };            // no `custom` key at all
  delete legacy.custom;
  const o = scopeOutputs(legacy, P);
  const r = computeScope(legacy, P, 0);
  check("T10 no-custom scope prices as before", before.B.finalTotal, o.finalTotal, o.finalTotal === before.B.finalTotal);
  check("T10 custom reads as [] (customBill 0)", 0, r.customBill, r.customBill === 0 && r.handlingRaw === r.itemBill);
}

// ---- FIT-WORK follow-up: install/uninstall separated from handling ----
{
  const B4 = CUSTOM_BANDS.find((b) => b.k === "w500_799");
  const mkCase = (fitWork) => ({
    dens: {}, cnt: {}, qty: {}, acc: { stairsO: 1, stairsD: 1 }, mat: {}, pack: 0, rate: 2.1,
    jobType: "labor", miles: 0,
    custom: [
      { id: "1", name: "Built-in fridge (swap)", band: "w500_799", qty: 1, builtIn: true, needsDisconnect: false, widthIn: 42, pathNarrowestIn: 48, isSwap: true, fitWork },
      { id: "2", name: "Built-in fridge", band: "w500_799", qty: 1, builtIn: true, needsDisconnect: false, widthIn: 42, pathNarrowestIn: 48, isSwap: false, fitWork },
    ],
  });
  const rA = computeScope(mkCase("none"), P, 0);
  const rB = computeScope(mkCase("both"), P, 0);

  // F1 backward compat: no fitWork key at all → reads as "none", fitMH 0
  const legacyItem = computeScope({ dens: {}, qty: {},
    custom: [{ id: "l", band: "w300_499", qty: 2, isSwap: false }] }, P, 0);
  check("F1 missing fitWork key → fitMH 0", 0, legacyItem.fitMH, legacyItem.fitMH === 0);
  check("F1 itemMH = band.mh only", 1.5 * 2, legacyItem.itemMH, legacyItem.itemMH === 1.5 * 2);

  // F2 fitWork "none" is a no-op: itemMH === mh × qty × units exactly
  check("F2 caseA itemMH = 2.0×(2+1)", 6, rA.itemMH, rA.itemMH === 6 && rA.fitMH === 0);

  // F3 swap doubles fitting work: (removeMh + placeMh) × 2 on the swap item
  const swapBoth = computeScope({ dens: {}, qty: {},
    custom: [{ id: "s", band: "w500_799", qty: 1, isSwap: true, fitWork: "both" }] }, P, 0);
  check("F3 swap+both fitMH = (1.0+1.5)×2", 5, swapBoth.fitMH, swapBoth.fitMH === (B4.removeMh + B4.placeMh) * 2);

  // F4 cap still exact on both reference cases
  check("F4 caseA cap = labor×0.30", (rA.labor * 0.3).toFixed(2), rA.handlingBilled.toFixed(2), Math.abs(rA.handlingBilled - rA.labor * 0.3) < 0.01);
  check("F4 caseB cap = labor×0.30", (rB.labor * 0.3).toFixed(2), rB.handlingBilled.toFixed(2), Math.abs(rB.handlingBilled - rB.labor * 0.3) < 0.01);

  // F5 crew floor holds on both, produced by customCrewFloor
  check("F5 crew 4 via floor (A)", "crew 4 / floor 4", `crew ${rA.crew} / floor ${rA.customCrewFloor}`, rA.crew === 4 && rA.customCrewFloor === 4);
  check("F5 crew 4 via floor (B)", "crew 4 / floor 4", `crew ${rB.crew} / floor ${rB.customCrewFloor}`, rB.crew === 4 && rB.customCrewFloor === 4);

  // F6 no new dollars: fitting work moves TIME only
  check("F6 handlingRaw identical A vs B", rA.handlingRaw, rB.handlingRaw, rA.handlingRaw === rB.handlingRaw);
  // fit total = swap item (1.0+1.5)×2 units + plain item (1.0+1.5)×1 = 7.5mh
  check("F6 caseB adds hours (7.5mh fit)", rA.itemMH + 7.5, rB.itemMH, rB.itemMH === rA.itemMH + 7.5 && rB.fitMH === 7.5);

  // F7 survey tier: dollars 0, fitMh still computes (non-monetary calibration)
  const rSurvey = computeScope(mkCase("both"), NO_PRICING, 0);
  check("F7 NO_PRICING $0 but fitMH computes", "fitMH 7.5, $0", `fitMH ${rSurvey.fitMH}, $${rSurvey.sub}`,
        rSurvey.fitMH === 7.5 && rSurvey.sub === 0 && rSurvey.customBill === 0 && rSurvey.handlingBilled === 0);
  check("F7 caseB onsite > caseA onsite", "B > A", `${rB.onsite.toFixed(2)} > ${rA.onsite.toFixed(2)}`, rB.onsite > rA.onsite);
}

// ---- report
const failed = results.filter((x) => !x.pass);
console.log("| test | expected | actual | pass |");
console.log("|---|---|---|---|");
for (const x of results) console.log(`| ${x.test} | ${x.expected} | ${x.actual} | ${x.pass ? "PASS" : "FAIL"} |`);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
if (failed.length) { console.error("FAILURES:", failed); process.exit(1); }
