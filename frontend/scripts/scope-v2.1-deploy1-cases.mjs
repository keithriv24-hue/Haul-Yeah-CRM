/* Scope Calculator v2.1 — Deploy 1 (P0) acceptance cases.
   Runs the real engine file. Regression R1–R5 must stay green; N-cases prove the P0 fixes.
   Live rate per extra mile is 6.00 (owner set it; the seed default now matches). */
import { copyFileSync } from "fs";
copyFileSync(new URL("../src/lib/scopeEngine.js", import.meta.url), "/app/frontend/scripts/_engine_v21.mjs");
const E = await import("./_engine_v21.mjs");
const { computeScope, scopeOutputs, mileageInfo, stateGate } = E;

const P = {
  manHourRate: 65, cushionPercent: 10, depositPercent: 25,
  roundingIncrement: 25, manHoursPer100CuFt: 2.1,
  tripFeeTruck: 125, tripFeeLabor: 75, floorTruck: 650, floorLabor: 375,
  minHoursTruck: 3, minHoursLabor: 2,
  mileageFreeMiles: 20, mileageRatePerMile: 6.0,
  stairFlightFee: 85, longCarryFee: 100, disassemblyFee: 100, extraStopFee: 125,
  surchargeUprightPiano: 500, surchargeGrandPiano: 800, surchargePoolTable: 600,
  surchargeSafeT1: 200, surchargeSafeT2: 500, surchargeSafeT3: 800,
  surchargeGymT1: 150, surchargeGymT2: 300, surchargeMotorcycle: 300,
  materialMattressBag: 15, materialWardrobeBox: 12, materialTvBox: 25,
  surchargeCustomB1: 75, surchargeCustomB2: 150, surchargeCustomB3: 250, surchargeCustomB4: 400,
  customBuiltInMultiplier: 1.25, customDisconnectMultiplier: 1.15,
  customSwapFactor: 0.6, specialtyHandlingCapPct: 30,
  hardFloorBedrooms: 3, hardFloorHours: 6,
  maxCrewPerDay: 12, targetHoursOnSite: 8, maxHoursOnSite: 10,
  pkgStudioCrew: 2, pkgStudioHours: 3.5, pkg2brCrew: 3, pkg2brHours: 5.5,
  pkg3brCrew: 4, pkg3brHours: 6.5, pkg4brCrew: 4, pkg4brHours: 8,
  serviceStates: "NJ",
};

const results = [];
const check = (test, expected, actual, pass) => results.push({ test, expected, actual, pass: !!pass });
const near = (a, b, eps = 0.05) => Math.abs(a - b) < eps;

// ---------- REGRESSION (must stay green) ----------
// R1 — 1BR truck, 3 flights pickup, 8 mi
{
  const inp = { dens: { primary: 2, living: 2, kitchen: 2, bath: 1 }, acc: { stairsO: 3 }, jobType: "truck", miles: 8 };
  const o = scopeOutputs(inp, P); const r = o.r;
  check("R1 crew 3", 3, r.crew, r.crew === 3);
  check("R1 billMH 14.3", 14.3, +r.billMH.toFixed(1), near(r.billMH, 14.28));
  check("R1 labor $928", 928, Math.round(r.labor), Math.round(r.labor) === 928);
  check("R1 trip $125 ×1", 125, r.travel, r.travel === 125 && r.billableTrips === 1);
  check("R1 access $255", 255, r.accBill, r.accBill === 255);
  check("R1 FINAL $1,450", 1450, o.finalTotal, o.finalTotal === 1450);
  check("R1 deposit 362.50", 362.5, o.deposit, o.deposit === 362.5);
  check("R1 no blocker", 0, r.blockers.length, r.blockers.length === 0);
}
// R2 — Sub-Zero built-in swap, labor-only, 1 flight each end
{
  const inp = { dens: {}, qty: {}, acc: { stairsO: 1, stairsD: 1 }, jobType: "labor", miles: 1,
    custom: [{ id: "1", band: "w500_799", builtIn: true, isSwap: true, fitWork: "none", widthIn: 42, pathNarrowestIn: 46, qty: 1 }] };
  const o = scopeOutputs(inp, P); const r = o.r;
  check("R2 crew 4", 4, r.crew, r.crew === 4);
  check("R2 billMH 8.0", 8, +r.billMH.toFixed(2), near(r.billMH, 8));
  check("R2 labor $520", 520, Math.round(r.labor), Math.round(r.labor) === 520);
  check("R2 handling raw $800", 800, r.handlingRaw, r.handlingRaw === 800);
  check("R2 handling billed $156", 156, Math.round(r.handlingBilled), Math.round(r.handlingBilled) === 156);
  check("R2 FINAL $1,025", 1025, o.finalTotal, o.finalTotal === 1025);
  check("R2 deposit 256.25", 256.25, o.deposit, o.deposit === 256.25);
}
// R3 — R2 with fitting = both
{
  const inp = { dens: {}, qty: {}, acc: { stairsO: 1, stairsD: 1 }, jobType: "labor", miles: 1,
    custom: [{ id: "1", band: "w500_799", builtIn: true, isSwap: true, fitWork: "both", widthIn: 42, pathNarrowestIn: 46, qty: 1 }] };
  const o = scopeOutputs(inp, P); const r = o.r;
  check("R3 billMH 11.5", 11.5, +r.billMH.toFixed(2), near(r.billMH, 11.52));
  check("R3 labor $749", 749, Math.round(r.labor), Math.round(r.labor) === 749);
  check("R3 handling raw still $800", 800, r.handlingRaw, r.handlingRaw === 800);
  check("R3 handling billed $225", 225, Math.round(r.handlingBilled), Math.round(r.handlingBilled) === 225);
  check("R3 FINAL $1,350", 1350, o.finalTotal, o.finalTotal === 1350);
}
// R4 — gun safe 900 lb, blocker fires, savable, no price
{
  const r = computeScope({ dens: {}, qty: {}, jobType: "truck", miles: 10, acc: { stairsO: 1 },
    custom: [{ id: "h", name: "Gun safe", band: "w800plus", qty: 1 }] }, P, 0);
  check("R4 800+ blocker fires", "weight_800_plus", (r.blockers[0] || {}).code, r.blockers.some((b) => b.code === "weight_800_plus"));
  check("R4 no cubic feet from blocked item (reads empty)", 0, r.cf, r.cf === 0);
  check("R4 no dollars leaked", 0, r.customBill, r.customBill === 0);
}
// R5 — out-of-state drop-off blocks the job
{
  const g = stateGate("NJ", "NY", P);
  check("R5 NY drop-off blocked", true, g.blocked, g.blocked === true);
  check("R5 names NY", "NY", (g.badStates || []).join(","), g.badStates.includes("NY"));
}

// ---------- NEW BEHAVIOR (P0 fixes) ----------
// N1 (P0-1) — 3BR + upright piano, truck, 12 mi: crew 4 not 6, handling one $500 line
{
  const inp = { dens: { primary: 2, stdbed: 2, smallbed: 2, living: 2, dining: 2, kitchen: 2, bath: 2 },
    cnt: { stdbed: 2 }, qty: { upright: 1 }, acc: { stairsO: 1, stairsD: 1 }, jobType: "truck", miles: 12 };
  const r = computeScope(inp, P, 0);
  check("N1 cf 1460", 1460, r.cf, r.cf === 1460);
  check("N1 crew 4 (NOT 6 — no 3×trucks)", 4, r.crew, r.crew === 4);
  check("N1 billMH 32.2", 32.2, +r.billMH.toFixed(1), near(r.billMH, 32.16));
  check("N1 labor $2,090", 2090, Math.round(r.labor), Math.round(r.labor) === 2090);
  check("N1 handling one uncapped $500 line", 500, r.handlingBilled, r.handlingBilled === 500 && r.specialtyOnly === false);
  check("N1 displayTrucks 2 (weight)", 2, r.displayTrucks, r.displayTrucks === 2);
}
// N2 (P0-1 + P0-2) — large labor-only POD: no trucks, one trip fee, crew escalates, price crew-independent
{
  const inp = { dens: { gar2: 3, baseunfin: 3, basefin: 3, unit10: 3, living: 3, family: 3 }, jobType: "labor", miles: 0 };
  const o = scopeOutputs(inp, P); const r = o.r;
  check("N2 cf ~3830", 3830, r.cf, r.cf === 3830);
  check("N2 displayTrucks 0 (no truck banner)", 0, r.displayTrucks, r.displayTrucks === 0);
  check("N2 billableTrips 1 → trip $75 (NOT ×N)", 75, r.travel, r.travel === 75 && r.billableTrips === 1);
  check("N2 crew escalated ~10", 10, r.crew, r.crew === 10 && r.dayLengthEscalated === true);
  check("N2 onsite ≤ maxHoursOnSite", true, r.onsite <= 10, r.onsite <= 10);
  check("N2 FINAL $5,850", 5850, o.finalTotal, o.finalTotal === 5850);
  check("N2 deposit 1462.50", 1462.5, o.deposit, o.deposit === 1462.5);
  const forced = scopeOutputs({ ...inp, crewOverride: 4 }, P);
  check("N2 total crew-independent (crew 4 == escalated)", 5850, forced.finalTotal, forced.finalTotal === 5850);
}
// N3 (P0-3) — one treadmill 300–499 lb, labor-only, 3BR package selected, NO rooms: package ignored ENTIRELY
{
  const inp = { dens: {}, qty: {}, jobType: "labor", miles: 2, pkg: "br3", crewOverride: 4, hoursOverride: 6.5,
    custom: [{ id: "t", name: "Treadmill", band: "w300_499", qty: 1 }] };
  const o = scopeOutputs(inp, P); const r = o.r;
  check("N3 specialtyOnly + droppedPkg", true, `${r.specialtyOnly}/${r.droppedPkg}`, r.specialtyOnly && r.droppedPkg);
  check("N3 crew 3 (band floor, NOT package 4)", 3, r.crew, r.crew === 3);
  check("N3 billMH 6.0 (3 × 2-hr labor min)", 6, +r.billMH.toFixed(2), near(r.billMH, 6));
  check("N3 labor $390", 390, Math.round(r.labor), Math.round(r.labor) === 390);
  check("N3 handling raw $250 → billed $117 (30% cap)", "250/117", `${r.handlingRaw}/${Math.round(r.handlingBilled)}`, r.handlingRaw === 250 && Math.round(r.handlingBilled) === 117);
  check("N3 trip $75 ×1, no truck", "75/0", `${r.travel}/${r.displayTrucks}`, r.travel === 75 && r.displayTrucks === 0);
  check("N3 FINAL $650 (NOT $850, NOT $2,075)", 650, o.finalTotal, o.finalTotal === 650);
  check("N3 deposit 162.50", 162.5, o.deposit, o.deposit === 162.5);
}
// N5 (P0-5) — 3BR no piano, truck, 150 mi: mileage line 130 × $6.00, crew 4
{
  const inp = { dens: { primary: 2, stdbed: 2, smallbed: 2, living: 2, dining: 2, kitchen: 2, bath: 2 },
    cnt: { stdbed: 2 }, jobType: "truck", miles: 150 };
  const r = computeScope(inp, P, 0);
  const mi = mileageInfo(150, P);
  check("N5 cf 1400", 1400, r.cf, r.cf === 1400);
  check("N5 crew 4 (NOT 6)", 4, r.crew, r.crew === 4);
  check("N5 billMH 29.4", 29.4, +r.billMH.toFixed(1), near(r.billMH, 29.4));
  check("N5 mileage extra 130 mi", 130, mi.extra, mi.extra === 130);
  check("N5 mileage line $780 (130 × $6.00)", 780, mi.fee, mi.fee === 780);
}

// ---------- report ----------
const failed = results.filter((x) => !x.pass);
console.log("| test | expected | actual | pass |");
console.log("|---|---|---|---|");
for (const x of results) console.log(`| ${x.test} | ${x.expected} | ${x.actual} | ${x.pass ? "PASS" : "FAIL"} |`);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
if (failed.length) { console.error("FAILURES:", failed); process.exit(1); }
