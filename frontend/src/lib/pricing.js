export const DEFAULT_RATES = {
  manHour: 65,
  cushionPercent: 10,
  travelTruck: 125,
  travelLabor: 75,
  mileageAllowance: 20,
  overageRate: 0.85,
  stairFlight: 85,
  packingRate: 65,
  depositPercent: 25,
  roundingIncrement: 50,
};

export function computeQuote(inputs, rates = DEFAULT_RATES, items = []) {
  const {
    crew = 0, hours = 0, minHours = 0, travel = "truck", miles = 0,
    flights = 0, packingHours = 0, itemQty = {},
  } = inputs;
  // hard hours floor (e.g. 6-hour minimum on 3BR+ jobs) applied in the math itself
  const effectiveHours = Math.max(hours, minHours || 0);
  const crewCharge = crew * effectiveHours * rates.manHour;
  const travelFee = travel === "labor" ? rates.travelLabor : rates.travelTruck;
  // first `mileageAllowance` miles are covered by the flat travel fee
  const overMiles = Math.max(0, miles - rates.mileageAllowance);
  const mileageOverage = overMiles * rates.overageRate;
  const stairs = flights * rates.stairFlight;
  const packing = packingHours * rates.packingRate;
  const itemLines = items
    .filter((it) => it.active !== false && (itemQty[it.id] || 0) > 0)
    .map((it) => ({ id: it.id, name: it.name, qty: itemQty[it.id], amount: itemQty[it.id] * it.price }));
  const itemsCharge = itemLines.reduce((s, l) => s + l.amount, 0);
  const subtotal = crewCharge + travelFee + mileageOverage + stairs + packing + itemsCharge;
  const cushion = subtotal * (rates.cushionPercent / 100);
  const inc = rates.roundingIncrement > 0 ? rates.roundingIncrement : 50;
  // cushion is folded into the top of the range — never shown as its own line
  const quoteLow = Math.ceil(subtotal / inc - 1e-9) * inc;
  const quoteHigh = Math.ceil((subtotal + cushion) / inc - 1e-9) * inc;
  const finalQuote = quoteHigh;
  const deposit = Math.round(finalQuote * rates.depositPercent) / 100;
  const balance = finalQuote - deposit;
  return {
    hours: effectiveHours, minHoursApplied: minHours > 0 && hours < minHours,
    crewCharge, travelFee, overMiles, mileageOverage, stairs, packing,
    itemLines, itemsCharge, subtotal, cushion, quoteLow, quoteHigh, finalQuote, deposit, balance,
  };
}

export const depositFromQuote = (quote, pct = 25) => Math.round((quote || 0) * pct) / 100;

export function invoiceLineItems(q) {
  const round2 = (n) => Math.round(n * 100) / 100;
  const labor = round2(q.crewCharge + q.mileageOverage + q.cushion + (q.finalQuote - q.subtotal - q.cushion));
  const lines = [{ name: "Local Moving Service — Crew & Truck", amount: labor }];
  if (q.travelFee > 0) lines.push({ name: "Travel & Trip Fee", amount: round2(q.travelFee) });
  if (q.stairs > 0) lines.push({ name: "Stair Carry", amount: round2(q.stairs) });
  if (q.packing > 0) lines.push({ name: "Packing Service", amount: round2(q.packing) });
  (q.itemLines || []).forEach((l) => lines.push({ name: l.qty > 1 ? `${l.name} × ${l.qty}` : l.name, amount: round2(l.amount) }));
  return lines.filter((l) => l.amount > 0);
}
