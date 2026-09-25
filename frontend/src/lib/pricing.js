/* Fallback pricing config shape — mirrors backend DEFAULT_RATES (/api/settings/rates).
   Only used before the owner's live values load; the calculators always price
   from server values (live or saved snapshot), never from this object. */
export const DEFAULT_RATES = {
  manHourRate: 65, cushionPercent: 10, depositPercent: 25,
  roundingIncrement: 25, manHoursPer100CuFt: 2.1,
  tripFeeTruck: 125, tripFeeLabor: 75,
  floorTruck: 650, floorLabor: 375,
  minHoursTruck: 3, minHoursLabor: 2,
  mileageFreeMiles: 20, mileageRatePerMile: 8.0,
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

export const depositFromQuote = (quote, pct = 25) => Math.round((quote || 0) * pct) / 100;
