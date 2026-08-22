export const LF = {
  name: "fldsBIJdaasQ9fh9a",
  phone: "fldQMF5LKSd0yI8Bs",
  email: "fldi6lWGr530XQ4YE",
  moveDate: "fldWUAHyvTippkVGd",
  from: "fldHysDcz9GAos0zD",
  to: "fldIKwCb5ZqAP1fEh",
  homeSize: "fldbcSKdb3iBeyUQO",
  specialty: "fld5ey4eIbIqHQSxe",
  contactMethod: "fldO6I8G31dI0eF5E",
  notes: "fldSLeTIb2RHpRohW",
  status: "fldplIOmtbERJFG6X",
  quote: "fldI5HufBfW35A1fD",
  depositPaid: "fld7BsZG5A6S1oh7Z",
  source: "fldNQ7kAAIcVQbysk",
  created: "fldKJdaOCpnECKpyU",
};

export const CF = {
  name: "fldObstefaoowAs1W",
  type: "flda7oRb5lSunnujV",
  company: "fldQDeXAT8Y4bpw0R",
  phone: "fldJluIWPpltVglRG",
  email: "fldZnttwNCfnt7vV3",
  town: "fldcJLjvjhLCImPST",
  notes: "fldSQPnALXbqnmlse",
};

export const PF = {
  jobName: "fldcuvCepinGbQbK8",
  status: "fldMZV9A6p0SJyuM5",
  jobDate: "fldVBgzlG9gUCq5OB",
  crewSize: "fldkeeMYBMooCqi7p",
  estHours: "fldhVlH3Cu66W5EYo",
  truck: "fldhQpzJrqDE6tPAg",
  quote: "fldkRQlJvhnUhWoR3",
  depositCollected: "fldpqyinP1L9vZ2UP",
  finalRevenue: "fldvOyVAK9ywo2DNA",
  fromAddr: "fldDf4w5prPb89Q4y",
  toAddr: "fldnFH0mMdyQ84hTV",
  lead: "fldiN7fny2dKI2r2V",
  notes: "fldtmYFaWLi5l6LpP",
};

export const TF = {
  task: "fldm3n4ZdjUF00dBF",
  status: "fldIpdRVz51aQaNZh",
  priority: "fldiPws9HxQnALJ8Z",
  category: "fld6X2EBphlGCrx1Q",
  dueDate: "fldWW4F0P9mxL9iqT",
  project: "fldZOyIIosMzoUq3u",
  notes: "fld4QHQzukkteQjy0",
};

export const BF = {
  title: "fldKzcIH5j4ZMZQrj",
  status: "fldu92VQBEbkeGhtQ",
  category: "fld8XYGs1ikbr8uAs",
  publishDate: "fldiBTxU2Bvp3MmpY",
  slug: "fldmwKkQyQYKhzXaK",
  body: "fldab1yOqSyGmDe2R",
};

export const IF = {
  number: "fldGmJw84bqKSSnAU",
  customer: "fldVXyWVhz6387TuN",
  amount: "fldTh5uHleHVWFBDV",
  status: "fldWwAcWFcH79Yw7H",
  issueDate: "flddqwJe0N3099J5V",
  dueDate: "flducZBby35qCR9Uq",
  payMethod: "fldYQ4Ivpi5Ux4dsA",
  project: "fldwngVwfBc8I1yeA",
  notes: "fldFdMDLKazZhL4uC",
};

export const SF = {
  name: "flde8mD2kzYs0qKp5",
  category: "fldPwzkia81IIksX2",
  monthlyCost: "fldIVJAp07djwe4kS",
  billingCycle: "fldmNLDvFBARMCf4b",
  nextRenewal: "fldKgBLY0JTv9geJO",
  status: "flduZOwx1cexVJ3LT",
  notes: "fldfq3MwJ37cKf8gC",
};

export const f = (record, fieldId) => record?.fields?.[fieldId];

export const KNOWN_LEAD_FIELD_IDS = new Set(Object.values(LF));

export const formatExtraValue = (v) => {
  if (Array.isArray(v)) return v.map((x) => (typeof x === "object" ? x?.name || x?.url || "" : x)).filter(Boolean).join(", ");
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "object" && v !== null) return v.name || v.url || "";
  return String(v);
};

/* --- Tally form access fields (2026-06) — "Pickup access" / "Drop-off access" are
   first-class; the old floor/stairs/elevator questions are dead and stay hidden. --- */
const normFieldName = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

export const LEGACY_LEAD_FIELD_NAMES = new Set([
  "floor", "new building floor", "stairs at destination", "stairs at new destination",
  "elevator", "elevator at new location",
]);
export const isLegacyLeadField = (name) => LEGACY_LEAD_FIELD_NAMES.has(normFieldName(name));

export const findAccessFieldIds = (schemaFields) => {
  const out = { pickup: null, dropoff: null };
  (schemaFields || []).forEach((fd) => {
    const n = normFieldName(fd.name);
    if (n === "pickup access" || n === "pick up access") out.pickup = fd.id;
    else if (n === "drop off access" || n === "dropoff access") out.dropoff = fd.id;
  });
  return out;
};

export const leadAccess = (lead, schemaFields) => {
  const ids = findAccessFieldIds(schemaFields);
  const val = (id) => {
    if (!id) return "";
    const v = f(lead, id);
    return v == null ? "" : formatExtraValue(v);
  };
  return { pickup: val(ids.pickup), dropoff: val(ids.dropoff), ids };
};

export const LEAD_STATUSES = ["New", "Contacted", "Warm", "Hot", "Quoted", "Booked", "Lost", "Cold"];
export const HOME_SIZES = ["Studio/1BR", "2BR", "3BR", "4BR+", "Labor-only (no truck)"];
export const LEAD_SOURCES = ["Meta Ad", "Google Business Profile", "Referral", "Repeat Customer", "Walk-in/Other", "Website — Direct"];
export const SPECIALTY_ITEMS = ["Piano", "Safe/vault", "Gym equipment", "Antiques/art", "Large sectional", "None"];
export const CONTACT_METHODS = ["Text", "Call", "Email"];
export const CONTACT_TYPES = ["Customer", "Realtor Partner", "Property Manager", "Storage Facility", "Vendor", "Crew"];
export const PROJECT_STATUSES = ["Pending Deposit", "Scheduled", "In Progress", "Completed", "Cancelled"];
export const TRUCKS = ["Truck 1", "Truck 2", "Truck 3", "Truck 4", "Truck 5", "Labor only"];
export const TASK_STATUSES = ["Backlog", "To Do", "In Progress", "Done"];
export const TASK_PRIORITIES = ["High", "Medium", "Low"];
export const TASK_CATEGORIES = ["Sales", "Ops", "Compliance", "Marketing", "Finance"];
export const BLOG_STATUSES = ["Idea", "Draft", "In Review", "Published"];
export const INVOICE_STATUSES = ["Draft", "Sent", "Paid", "Overdue"];
export const PAYMENT_METHODS = ["Square", "Cash", "Check", "Zelle"];
export const SUB_CATEGORIES = ["Software", "Insurance", "Phone", "Marketing", "Fuel & Fleet", "Other"];
export const SUB_STATUSES = ["Active", "Cancel Pending", "Cancelled"];

export const LEAD_STATUS_COLORS = {
  New: "#E8743B",
  Contacted: "#4A78A8",
  Warm: "#B9781F",
  Hot: "#C0392B",
  Booked: "#0E6B46",
  Quoted: "#1B2A4A",
  Lost: "#A8ADB6",
  Cold: "#C9CDD3",
};

export const STATUS_PILL = {
  New: "bg-accent/12 text-accent-ink",
  Contacted: "bg-info/12 text-info",
  Warm: "bg-warning/12 text-warning",
  Hot: "bg-destructive/12 text-destructive",
  Quoted: "bg-primary/10 text-primary",
  Booked: "bg-success/12 text-success",
  Lost: "bg-surface-sunk text-faint",
  Cold: "bg-surface-sunk text-faint",
  "Pending Deposit": "bg-warning/12 text-warning",
  Scheduled: "bg-info/12 text-info",
  "In Progress": "bg-primary/10 text-primary",
  Completed: "bg-success/12 text-success",
  Cancelled: "bg-surface-sunk text-faint",
  Draft: "bg-surface-sunk text-ink-2",
  Sent: "bg-info/12 text-info",
  Paid: "bg-success/12 text-success",
  Overdue: "bg-destructive/12 text-destructive",
  Idea: "bg-surface-sunk text-ink-2",
  "In Review": "bg-warning/12 text-warning",
  Published: "bg-success/12 text-success",
  Active: "bg-success/12 text-success",
  "Cancel Pending": "bg-warning/12 text-warning",
  High: "bg-destructive/12 text-destructive",
  Medium: "bg-warning/12 text-warning",
  Low: "bg-surface-sunk text-ink-2",
};

export const lastTouch = (lead) => {
  const notes = f(lead, LF.notes) || "";
  let latest = lead?.createdTime ? new Date(lead.createdTime) : null;
  const re = /(\d{1,2})\/(\d{1,2})\/(\d{4})/g;
  let m;
  while ((m = re.exec(notes))) {
    const d = new Date(+m[3], +m[1] - 1, +m[2]);
    if (!Number.isNaN(d.getTime()) && (!latest || d > latest)) latest = d;
  }
  return latest;
};

export const quietDays = (lead) => {
  const t = lastTouch(lead);
  return t ? Math.floor((Date.now() - t.getTime()) / 86400000) : 0;
};

export const needsFollowUp = (lead) =>
  f(lead, LF.status) === "Quoted" && !f(lead, LF.depositPaid) && quietDays(lead) >= 2;

export const nextStepHint = (lead) => {
  const status = f(lead, LF.status);
  const hasDeposit = !!f(lead, LF.depositPaid);
  if (status === "New") return "Call or text now — the clock is running.";
  if (["Contacted", "Warm", "Hot"].includes(status)) return "Use Quote to price the job.";
  if (status === "Quoted" && !hasDeposit && needsFollowUp(lead)) return "They've gone quiet — call them back today.";
  if (status === "Quoted" && !hasDeposit) return "Send the deposit link to lock the date.";
  if (status === "Quoted" && hasDeposit) return "Book it as a job.";
  if (status === "Booked") return "Manage it in Projects.";
  return "No action needed.";
};
