// Quality & Compliance module — Airtable field IDs + select options.
// Reference fields by these IDs. NEVER write AUTONUMBER / FORMULA fields
// (NC number, Audit number, Audit due).

export const QD = {
  name: "fld3W18nU4Io2ZZNV",
  version: "fldiDIwr9JW8hPCzD",
  effective: "fldT6Y875tNiquvuX",
  owner: "fldLjP5CWmyqnZ9Mz",
  review: "fldJpv1V4gzYMFeDY",
  status: "fldvFny72rpqL8Gq7",
  drive: "fldCZuors8kOtxo4Z",
  notes: "fldX9QV8g2HjF5tnQ",
};
export const QD_STATUSES = ["Current", "Superseded", "Pending"];

export const NC = {
  number: "fldrmgtcxlPwNdzkw", // AUTONUMBER — read only
  raisedBy: "fldEImK9opqEgqUlS",
  raisedDate: "fld0CIIBJ4ONEPB7K",
  type: "fldJcoMjr8CWfpw89",
  severity: "fldZjx6p4spGnJkiV",
  what: "fldzMOMAv7N762lzo",
  immediate: "fldjUQA70Llyko0pY",
  root: "fldI1z8PvBXwLwECr",
  corrective: "fldMayZQl7txWLmrZ",
  verifyDate: "fldLIfdho83ko7VCw",
  status: "fldHMZHQBqbI0KOTe",
  closedBy: "fldtabcHA42ln02nr",
  closedDate: "fldefdFzqGo7xz153",
  linkedJob: "fldenMuCifGb9sc5n",
};
export const NC_TYPES = ["Complaint", "Damage", "Claim", "Gate override", "Audit finding", "Low review", "Quote variance"];
export const NC_SEVERITIES = ["Liability risk", "Regulatory", "Major", "Minor"];
export const NC_STATUSES = ["Open", "In progress", "Verifying", "Closed"];

export const JA = {
  number: "fldsa0PZkrqe8029F", // AUTONUMBER — read only
  completedDate: "fldcTXzOnPN4UynoG",
  auditDue: "fldQVm8CyjurFAgyJ", // FORMULA — read only
  auditor: "fldYOjPbBIkx5Lf9Z",
  bol: "fldYXIYUXAmisK4SD",
  quotedTotal: "fldcRVrYi4RvI1f8g",
  finalTotal: "fldopn48enx6Xkg1f",
  varianceExplained: "fldHbvmW6KUNQuyuw",
  estHours: "fldmTWweMfFkFdAod",
  actualHours: "fldq7VZ4bHyiRpk1W",
  gates: "fldlFQ0Ovpe8CYRPs",
  result: "fldc6beKUsF8nHdWO",
  findings: "fldUp6XjCp9kLl00e",
  signedBol: "fld8Hu5BuK7oI6dE1",
  linkedNc: "fldJZDkUMcLRDnx3r",
  linkedJob: "fldYjt6xsNHq2U2Qn",
};
export const JA_BOL_ITEMS = [
  "License number", "Origin address", "Destination address", "Times", "Rates",
  "Hours", "Accessorials", "Final total", "Customer signature", "Driver signature",
];
export const JA_RESULTS = ["Pass", "Pass with findings", "Fail"];
export const JA_GATES = ["All green", "Override recorded", "Failed gate, no override"];
// NOTE: first option has an EM DASH (U+2014), not a hyphen. Copy byte-for-byte.
export const JA_VARIANCE = ["Yes — customer agreed", "No", "No variance"];

export const money = (v) =>
  v == null || v === "" ? "—" : `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
export const hrs = (v) => (v == null || v === "" ? "—" : `${Number(v).toFixed(2)}h`);
export const fmtDate = (v) => {
  if (!v) return "—";
  try {
    return new Date(String(v).length <= 10 ? `${v}T00:00:00` : v).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return String(v);
  }
};
export const daysUntil = (v) => {
  if (!v) return null;
  try {
    const d = new Date(`${String(v).slice(0, 10)}T00:00:00`);
    return Math.round((d - new Date(new Date().toDateString())) / 86400000);
  } catch {
    return null;
  }
};

// KPI state → styling. Backend states: "green" | "amber" | "red" | null.
export const stateTone = (s) =>
  s === "green" ? "text-emerald-700" : s === "amber" ? "text-amber-600" : s === "red" ? "text-red-600" : "text-faint";
export const stateBorder = (s) =>
  s === "green" ? "border-emerald-300" : s === "amber" ? "border-amber-300" : s === "red" ? "border-red-300" : "border-border";
export const stateDot = (s) =>
  s === "green" ? "bg-emerald-500" : s === "amber" ? "bg-amber-500" : s === "red" ? "bg-red-500" : "bg-muted";
export const metricValue = (m) => {
  if (!m || m.value == null) return "—";
  if (m.unit === "hours") return `${m.value > 0 ? "+" : ""}${m.value}h`;
  if (m.unit === "rate") return `${m.value}`;
  return `${m.value}%`;
};
