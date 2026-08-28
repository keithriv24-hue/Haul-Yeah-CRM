/* Regression anchors: three representative household scopes.
   Run BEFORE and AFTER engine changes — finalTotal & deposit must match to the cent. */
import { copyFileSync } from "fs";
copyFileSync(new URL("../src/lib/scopeEngine.js", import.meta.url), "/app/frontend/scripts/_engine.mjs");
const { scopeOutputs, computeScope } = await import("./_engine.mjs");

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
  hardFloorBedrooms: 3, hardFloorHours: 6,
  pkgStudioCrew: 2, pkgStudioHours: 3.5, pkg2brCrew: 3, pkg2brHours: 5.5,
  pkg3brCrew: 4, pkg3brHours: 6.5, pkg4brCrew: 4, pkg4brHours: 8,
  serviceStates: "NJ",
};

// Anchor A: 2BR truck move with an upright piano + stairs both ends, 28 mi
const A = {
  dens: { primary: 2, stdbed: 2, living: 2, kitchen: 2, bath: 1 },
  cnt: {}, qty: { upright: 1, washer: 1, dryer: 1 },
  acc: { stairsO: 1, stairsD: 1 }, mat: { mattress: 2 },
  pack: 1, rate: 2.1, jobType: "truck", miles: 28,
};
// Anchor B: 3BR packed household, garage, long carry, 12 mi (hard floor territory)
const B = {
  dens: { primary: 3, stdbed: 3, living: 3, dining: 2, kitchen: 3, gar1: 2 },
  cnt: { stdbed: 2 }, qty: { fridge: 1, safe2: 1, tv: 2 },
  acc: { carryO: 1, disasm: 2 }, mat: { wardrobe: 4, tvbox: 2 },
  pack: 2, rate: 2.1, jobType: "truck", miles: 12,
};
// Anchor C: studio labor-only with gym gear, 45 mi
const C = {
  dens: { smallbed: 1, living: 1 },
  cnt: {}, qty: { tread: 1, gym: 1, plates: 2 },
  acc: { elevO: 1 }, mat: {},
  pack: 0, rate: 2.1, jobType: "labor", miles: 45, pkg: "studio",
  crewOverride: 2, hoursOverride: 3.5,
};

const anchors = {};
for (const [name, inputs] of [["A", A], ["B", B], ["C", C]]) {
  const o = scopeOutputs(inputs, P);
  const r = computeScope(inputs, P, 0);
  anchors[name] = {
    finalTotal: o.finalTotal, deposit: o.deposit, bandLo: o.bandLo, bandHi: o.bandHi,
    sub: r.sub, itemBill: r.itemBill, crew: r.crew, billMH: r.billMH,
  };
}
console.log(JSON.stringify(anchors, null, 2));
