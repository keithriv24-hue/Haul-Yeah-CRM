export const mapsUrl = (addr) => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(addr || "")}`;

export const telUrl = (phone) => `tel:${(phone || "").replace(/[^\d+]/g, "")}`;

export const smsUrl = (phone) => `sms:${(phone || "").replace(/[^\d+]/g, "")}`;

export const fmtTime12 = (t) => {
  if (!t) return "";
  const [h, m] = t.split(":").map(Number);
  if (Number.isNaN(h)) return t;
  const ampm = h >= 12 ? "PM" : "AM";
  const hr = h % 12 || 12;
  return `${hr}:${String(m || 0).padStart(2, "0")} ${ampm}`;
};
