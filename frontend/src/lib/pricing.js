export const DEFAULT_RATES = {
  manHour: 65,
  travelTruck: 125,
  travelLabor: 75,
  stairFlight: 85,
  pianoUpright: 500,
  pianoGrand: 800,
};

export function computeQuote({ crew, hours, travel, flights, piano }, rates = DEFAULT_RATES) {
  const base = (crew || 0) * (hours || 0) * rates.manHour;
  const travelFee = travel === "labor" ? rates.travelLabor : rates.travelTruck;
  const stairs = (flights || 0) * rates.stairFlight;
  const pianoFee = piano === "upright" ? rates.pianoUpright : piano === "grand" ? rates.pianoGrand : 0;
  const round50 = (n) => Math.round(n / 50) * 50;
  const low = round50(base + travelFee + stairs + pianoFee);
  const high = round50((base + travelFee + stairs + pianoFee) * 1.1);
  const deposit = Math.round(high * 0.25);
  return { base, travelFee, stairs, pianoFee, low, high, deposit };
}

export const depositFromQuote = (quoteHigh) => Math.round((quoteHigh || 0) * 0.25);
