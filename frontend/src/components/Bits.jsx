import React, { useEffect, useState } from "react";
import { Info, Clock, Trash2, PhoneCall, ReceiptText, Search, X } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/components/AuthGate";
import { fmtMoney, minutesSince, ageLabel } from "@/lib/format";
import { STATUS_PILL } from "@/lib/fields";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

export const ConfirmDeleteButton = ({ what, onConfirm, testId, className = "" }) => (
  <AlertDialog>
    <AlertDialogTrigger asChild>
      <Button data-testid={testId} variant="outline" size="sm" className={`gap-1 text-xs text-red-600 border-red-200 hover:bg-red-50 hover:text-red-700 ${className}`}>
        <Trash2 className="w-3.5 h-3.5" /> Delete
      </Button>
    </AlertDialogTrigger>
    <AlertDialogContent data-testid="confirm-delete-dialog">
      <AlertDialogHeader>
        <AlertDialogTitle className="font-display">Delete {what}?</AlertDialogTitle>
        <AlertDialogDescription>This removes it from Airtable for good. You can't undo this.</AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel data-testid="confirm-delete-cancel">Keep it</AlertDialogCancel>
        <AlertDialogAction data-testid="confirm-delete-confirm" onClick={onConfirm} className="bg-red-600 hover:bg-red-700">
          Yes, delete
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
);

export const InstructionBanner = ({ children, testId = "instruction-banner" }) => (
  <div data-testid={testId} className="flex items-start gap-2 border border-[#1B2A4A]/15 bg-[#1B2A4A]/[0.04] text-[#1B2A4A] rounded-lg px-4 py-3 text-sm mb-6">
    <Info className="w-4 h-4 mt-0.5 shrink-0 text-[#E8743B]" />
    <span>{children}</span>
  </div>
);

export const Private = ({ children, block = false, className = "" }) => {
  const { privacy } = useApp();
  const { role } = useAuth();
  const masked = privacy && role !== "employee";
  const Tag = block ? "div" : "span";
  return <Tag className={`${masked ? "privacy-blur" : ""} ${className}`.trim()}>{children}</Tag>;
};

export const Money = ({ value, className = "" }) => (
  <Private className={className}>{fmtMoney(value)}</Private>
);

export const Pill = ({ value, className = "" }) => (
  <span className={`inline-flex items-center border rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_PILL[value] || "bg-slate-100 text-slate-600 border-slate-300"} ${className}`}>
    {value}
  </span>
);

export const AgeTimer = ({ createdTime }) => {
  const [, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), 15000);
    return () => clearInterval(t);
  }, []);
  const mins = minutesSince(createdTime);
  const late = mins > 5;
  return (
    <span
      data-testid="lead-age-timer"
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold ${
        late ? "bg-red-50 text-red-600 border-red-300 animate-pulse" : "bg-emerald-50 text-emerald-700 border-emerald-300"
      }`}
    >
      <Clock className="w-3.5 h-3.5" />
      waiting {ageLabel(mins)}
    </span>
  );
};

export const FollowUpBadge = ({ days }) => (
  <span
    data-testid="follow-up-badge"
    className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold bg-red-50 text-red-600 border-red-300"
  >
    <PhoneCall className="w-3.5 h-3.5" />
    quiet {days} days — call them back
  </span>
);

export const SQUARE_STATUS_LABEL = {
  PAID: "Paid",
  UNPAID: "Waiting on payment",
  SCHEDULED: "Scheduled",
  PARTIALLY_PAID: "Partly paid",
  PARTIALLY_REFUNDED: "Partly refunded",
  REFUNDED: "Refunded",
  CANCELED: "Canceled",
  FAILED: "Failed",
  DRAFT: "Draft",
};

const invoiceBadgeStyle = (status) => {
  if (status === "PAID") return "bg-emerald-50 text-emerald-700 border-emerald-300";
  if (["CANCELED", "FAILED", "REFUNDED", "PARTIALLY_REFUNDED"].includes(status)) return "bg-slate-100 text-slate-500 border-slate-300";
  return "bg-amber-50 text-amber-700 border-amber-300";
};

export const InvoiceBadge = ({ inv }) => (
  <a
    data-testid="invoice-status-badge"
    href={inv.public_url || undefined}
    target="_blank"
    rel="noreferrer"
    className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold ${invoiceBadgeStyle(inv.status)}`}
  >
    <ReceiptText className="w-3.5 h-3.5" />
    Invoice {inv.invoice_number ? `#${inv.invoice_number}` : ""} · {fmtMoney(inv.amount)} · {SQUARE_STATUS_LABEL[inv.status] || inv.status}
  </a>
);

export const PageTitle = ({ title, subtitle, action }) => (
  <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
    <div>
      <h1 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight text-[#1B2A4A]">{title}</h1>
      {subtitle && <p className="text-sm text-slate-500 mt-1">{subtitle}</p>}
    </div>
    {action}
  </div>
);

export const KpiCard = ({ label, value, sub, isPrivate = true, alert = false, testId }) => (
  <div
    data-testid={testId}
    className={`bg-white border rounded-lg p-4 flex flex-col gap-1 ${alert ? "border-red-400 ring-1 ring-red-300" : "border-slate-200"}`}
  >
    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</span>
    <span className={`font-display text-2xl font-extrabold ${alert ? "text-red-600" : "text-[#1B2A4A]"}`}>
      {isPrivate ? <Private>{value}</Private> : value}
    </span>
    {sub && <span className={`text-xs ${alert ? "text-red-500 font-semibold" : "text-slate-500"}`}>{sub}</span>}
  </div>
);

export const EmptyState = ({ children }) => (
  <div className="border border-dashed border-slate-300 rounded-lg p-8 text-center text-sm text-slate-500">{children}</div>
);

export const searchMatch = (q, ...vals) => {
  const needle = (q || "").trim().toLowerCase();
  if (!needle) return true;
  return vals.some((v) => String(v ?? "").toLowerCase().includes(needle));
};

export const SearchBar = ({ value, onChange, placeholder = "Search…", testId = "search-input", className = "" }) => (
  <div className={`relative w-full max-w-md ${className}`}>
    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
    <Input
      data-testid={testId}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="pl-9 pr-8 h-9 bg-white"
    />
    {value && (
      <button
        data-testid={`${testId}-clear`}
        onClick={() => onChange("")}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
        aria-label="Clear search"
      >
        <X className="w-4 h-4" />
      </button>
    )}
  </div>
);

export const LoadingRows = () => (
  <div className="space-y-3" data-testid="loading-rows">
    {[1, 2, 3].map((i) => (
      <div key={i} className="h-24 bg-slate-100 rounded-lg animate-pulse" />
    ))}
  </div>
);
