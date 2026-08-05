import { LF, PF, f } from "@/lib/fields";
import { fmtDate } from "@/lib/format";
import { getQuoteBreakdownApi } from "@/lib/api";

export async function bookLeadAsJob({ createRecord, updateRecord }, lead) {
  const name = f(lead, LF.name) || "No name";
  const quote = f(lead, LF.quote);
  const fields = {
    [PF.jobName]: `${name} — ${f(lead, LF.moveDate) ? fmtDate(f(lead, LF.moveDate)) : "date TBD"}`,
    [PF.status]: "Pending Deposit",
    [PF.lead]: [lead.id],
  };
  if (f(lead, LF.moveDate)) fields[PF.jobDate] = f(lead, LF.moveDate);
  if (quote) fields[PF.quote] = quote;
  if (f(lead, LF.from)) fields[PF.fromAddr] = f(lead, LF.from);
  if (f(lead, LF.to)) fields[PF.toAddr] = f(lead, LF.to);
  try {
    const { breakdown } = await getQuoteBreakdownApi(lead.id);
    if (breakdown?.crew) fields[PF.crewSize] = Number(breakdown.crew);
    if (breakdown?.hours) fields[PF.estHours] = Number(breakdown.hours);
  } catch {}
  await createRecord("projects", fields);
  await updateRecord("leads", lead.id, { [LF.status]: "Booked" });
}
