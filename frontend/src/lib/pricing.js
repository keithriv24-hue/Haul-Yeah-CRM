export const RATES = {
  manHour: 65,
  travelTruck: 125,
  travelLabor: 75,
  stairFlight: 85,
  pianoUpright: 500,
  pianoGrand: 800,
  driverHr: 28,
  helperHr: 24,
};

export function computeQuote({ crew, hours, travel, flights, piano }) {
  const base = (crew || 0) * (hours || 0) * RATES.manHour;
  const travelFee = travel === "labor" ? RATES.travelLabor : RATES.travelTruck;
  const stairs = (flights || 0) * RATES.stairFlight;
  const pianoFee = piano === "upright" ? RATES.pianoUpright : piano === "grand" ? RATES.pianoGrand : 0;
  const low = base + travelFee + stairs + pianoFee;
  const high = Math.round(low * 1.1);
  const deposit = Math.round(high * 0.25);
  return { base, travelFee, stairs, pianoFee, low, high, deposit };
}

export const depositFromQuote = (quoteHigh) => Math.round((quoteHigh || 0) * 0.25);

export const crewCost = (crew, hours) => {
  if (!crew || !hours) return 0;
  return (RATES.driverHr + Math.max(0, crew - 1) * RATES.helperHr) * hours;
};
