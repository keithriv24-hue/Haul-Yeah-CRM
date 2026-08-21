import { fmtMoney, fmtMoneyCents } from "@/lib/format";

export const quoteSmsBody = (name, quote, deposit) => {
  const first = (name || "").trim().split(/\s+/)[0] || "there";
  return `Hi ${first}, it's Haul Yeah Moving! Your move quote is ${fmtMoney(quote)}. A ${fmtMoneyCents(deposit)} deposit locks in your date. Want me to hold it?`;
};
