export const fmtMoney = (n) => {
  const num = Number(n);
  if (n === null || n === undefined || n === "" || Number.isNaN(num)) return "—";
  return num.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
};

export const fmtDate = (d) => {
  if (!d) return "—";
  const iso = d.length === 10 ? `${d}T12:00:00` : d;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return d;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};

export const todayISO = () => new Date().toISOString().slice(0, 10);

export const isOverdue = (d) => !!d && d.slice(0, 10) < todayISO();

export const daysUntil = (d) => {
  if (!d) return null;
  const target = new Date(`${d.slice(0, 10)}T12:00:00`);
  return Math.round((target.getTime() - Date.now()) / 86400000);
};

export const minutesSince = (iso) => Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000));

export const ageLabel = (mins) => {
  if (mins < 60) return `${mins} min`;
  if (mins < 1440) return `${Math.floor(mins / 60)} hr ${mins % 60} min`;
  return `${Math.floor(mins / 1440)} days`;
};

export const SENDER_EMAIL = "contact@haulyeahmoves.com";

export const gmailCompose = (to, subject = "", body = "") =>
  `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(to || "")}&su=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}&authuser=${encodeURIComponent(SENDER_EMAIL)}`;

export const gmailSearch = (query) => `https://mail.google.com/mail/u/${SENDER_EMAIL}/#search/${encodeURIComponent(query || "")}`;

export const smsLink = (phone, body) => `sms:${(phone || "").replace(/[^+\d]/g, "")}?&body=${encodeURIComponent(body)}`;

export const reviewSmsBody = (name, link) => {
  const first = (name || "").trim().split(/\s+/)[0] || "there";
  return `Hi ${first}, thanks for moving with Haul Yeah Moving! If we did a good job, a quick Google review would mean a lot to our small crew.${link ? ` Here's the link: ${link}` : ""} Thank you!`;
};

export const winBackSmsBody = (name) => {
  const first = (name || "").trim().split(/\s+/)[0] || "there";
  return `Hi ${first}, it's Haul Yeah Moving! We quoted your move a while back — still need a hand? Weekend slots are filling up and we're happy to refresh your quote. Text back and we'll grab you a date.`;
};

export const payNudgeSmsBody = (name, amount, url) => {
  const first = (name || "").trim().split(/\s+/)[0] || "there";
  return `Hi ${first}, friendly nudge from Haul Yeah Moving — your invoice for ${fmtMoney(amount)} is still open.${url ? ` Pay here: ${url}` : ""} Thanks so much!`;
};

export const calendarTemplate = (title, dateISO, details = "", guestEmail = "") => {
  const d = (dateISO || todayISO()).replace(/-/g, "");
  let url = `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(title)}&dates=${d}/${d}&details=${encodeURIComponent(details)}`;
  if (guestEmail) url += `&add=${encodeURIComponent(guestEmail)}`;
  return url;
};
