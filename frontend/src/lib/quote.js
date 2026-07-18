import { LF, f } from "@/lib/fields";
import { fmtMoney } from "@/lib/format";

export const PREFILL_BY_SIZE = {
  "Studio/1BR": { crew: "2", hours: "3.5" },
  "2BR": { crew: "3", hours: "5" },
  "3BR": { crew: "4", hours: "6.5" },
  "4BR+": { crew: "4", hours: "8" },
};

export const QUOTE_COACH_LINE =
  "Quote this as a range by phone — final price confirmed after access details are verified. Never promise the low number.";

export function quoteSaveFields(lead, q, crew, hours) {
  const oldNotes = f(lead, LF.notes) || "";
  const parts = [`${crew} crew × ${hours} hrs = ${fmtMoney(q.base)}`, `travel ${fmtMoney(q.travelFee)}`];
  if (q.stairs) parts.push(`stairs ${fmtMoney(q.stairs)}`);
  if (q.pianoFee) parts.push(`piano ${fmtMoney(q.pianoFee)}`);
  const line = `Quote ${new Date().toLocaleDateString("en-US")}: ${parts.join(" + ")} → range ${fmtMoney(q.low)}–${fmtMoney(q.high)}, deposit ${fmtMoney(q.deposit)}.`;
  return {
    [LF.quote]: q.high,
    [LF.status]: "Quoted",
    [LF.notes]: oldNotes ? `${oldNotes}\n${line}` : line,
  };
}
