import { LF, f } from "@/lib/fields";
import { fmtMoney, fmtMoneyCents } from "@/lib/format";

export const PREFILL_BY_SIZE = {
  "Studio/1BR": { crew: "3", hours: "3" },
  "2BR": { crew: "3", hours: "5.5" },
  "3BR": { crew: "4", hours: "6.5" },
  "4BR+": { crew: "4", hours: "8" },
};

export const CREW_GUIDE = [
  { size: "Studio/1BR", plan: "3 crew · 2.5–3.5 hours" },
  { size: "2BR", plan: "3 crew · 5–6.5 hours" },
  { size: "3BR+", plan: "4 crew · 6.5 hours (6-hour minimum)" },
  { size: "Partially packed", plan: "add 2–3 hours" },
];

export const QUOTE_COACH_LINE =
  "Say the final quote with confidence. The deposit holds their date — price is confirmed once access details check out.";

export const quoteSmsBody = (name, quote, deposit) => {
  const first = (name || "").trim().split(/\s+/)[0] || "there";
  return `Hi ${first}, it's Haul Yeah Moving! Your move quote is ${fmtMoney(quote)}. A ${fmtMoneyCents(deposit)} deposit locks in your date. Want me to hold it?`;
};

export function quoteSaveFields(lead, q, crew, hours, extra = {}) {
  const oldNotes = f(lead, LF.notes) || "";
  const parts = [`${crew} crew × ${hours} hrs = ${fmtMoneyCents(q.crewCharge)}`, `travel ${fmtMoneyCents(q.travelFee)}`];
  if (q.mileageOverage) parts.push(`miles over ${fmtMoneyCents(q.mileageOverage)}`);
  if (q.stairs) parts.push(`stairs ${fmtMoneyCents(q.stairs)}`);
  if (q.packing) parts.push(`packing ${fmtMoneyCents(q.packing)}`);
  (q.itemLines || []).forEach((l) => parts.push(`${l.name} ×${l.qty} ${fmtMoneyCents(l.amount)}`));
  if (extra.elevator) parts.push("elevator available");
  const range = q.quoteLow && q.quoteLow !== q.finalQuote
    ? `${fmtMoney(q.quoteLow)}–${fmtMoney(q.finalQuote)}` : fmtMoney(q.finalQuote);
  const line = `Quote ${new Date().toLocaleDateString("en-US")}: ${parts.join(" + ")} → quoted ${range}, deposit ${fmtMoneyCents(q.deposit)} (25% of high end).`;
  return {
    [LF.quote]: q.finalQuote,
    [LF.status]: "Quoted",
    [LF.notes]: oldNotes ? `${oldNotes}\n${line}` : line,
  };
}

// Structured lead columns written on save, mapped by Airtable field ID so column
// renames never break the write: Crew Size / Est Hours / Deposit Amount.
export const quoteStructuredFields = (q, crew) => ({
  fldz0UbjzI0MADcnh: Number(crew),      // Crew Size (number)
  fld74xIlr9zV9PZzA: Number(q.hours),   // Est Hours (number)
  fldqYyz9kkI0RDbdr: q.deposit,         // Deposit Amount (currency)
});
