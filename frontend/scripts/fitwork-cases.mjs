/* Fit-work reference cases (Section 6) — run before and after the change. */
import { copyFileSync } from "fs";
copyFileSync(new URL("../src/lib/scopeEngine.js", import.meta.url), "/app/frontend/scripts/_engine.mjs");
const { computeScope, scopeOutputs } = await import("./_engine.mjs");

const P = {
  manHourRate: 65, cushionPercent: 10, depositPercent: 25,
  roundingIncrement: 25, manHoursPer100CuFt: 2.1,
  tripFeeTruck: 125, tripFeeLabor: 75, floorTruck: 650, floorLabor: 375,
  minHoursTruck: 3, minHoursLabor: 2,
  mileageFreeMiles: 20, mileageRatePerMile: 0.85,
  stairFlightFee: 85, longCarryFee: 100, disassemblyFee: 100, extraStopFee: 125,
  surchargeCustomB1: 75, surchargeCustomB2: 150, surchargeCustomB3: 250, surchargeCustomB4: 400,
  customBuiltInMultiplier: 1.25, customDisconnectMultiplier: 1.15,
  customSwapFactor: 0.6, specialtyHandlingCapPct: 30,
  hardFloorBedrooms: 3, hardFloorHours: 6,
  serviceStates: "NJ",
};

const mk = (fitWork) => ({
  dens: {}, cnt: {}, qty: {}, acc: { stairsO: 1, stairsD: 1 }, mat: {}, pack: 0, rate: 2.1,
  jobType: "labor", miles: 0,
  custom: [
    { id: "1", name: "Built-in fridge (swap)", band: "w500_799", qty: 1, builtIn: true, needsDisconnect: false, widthIn: 42, pathNarrowestIn: 48, isSwap: true, fitWork },
    { id: "2", name: "Built-in fridge", band: "w500_799", qty: 1, builtIn: true, needsDisconnect: false, widthIn: 42, pathNarrowestIn: 48, isSwap: false, fitWork },
  ],
});

for (const [label, inputs] of [["Case A (fitWork none)", mk("none")], ["Case B (fitWork both)", mk("both")]]) {
  const r = computeScope(inputs, P, 0);
  const o = scopeOutputs(inputs, P);
  console.log(label, JSON.stringify({
    itemMH: +r.itemMH.toFixed(2), fitMH: r.fitMH !== undefined ? +r.fitMH.toFixed(2) : "n/a (pre-change)",
    schedMH: +r.schedMH.toFixed(2), billMH: +r.billMH.toFixed(2), crew: r.crew,
    onsite: +r.onsite.toFixed(2), labor: +r.labor.toFixed(2),
    handlingRaw: +r.handlingRaw.toFixed(2), handlingBilled: +r.handlingBilled.toFixed(2),
    capExact: Math.abs(r.handlingBilled - r.labor * 0.3) < 0.01,
    bandLo: o.bandLo, bandHi: o.bandHi, finalTotal: o.finalTotal, deposit: o.deposit,
  }, null, 1));
}
