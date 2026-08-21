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
      <Button
        data-testid={testId}
        variant="ghost"
        size="sm"
        className={`gap-1.5 text-destructive hover:bg-destructive/10 hover:text-destructive ${className}`}
      >
        <Trash2 className="w-3.5 h-3.5" /> Delete
      </Button>
    </AlertDialogTrigger>
    <AlertDialogContent data-testid="confirm-delete-dialog">
      <AlertDialogHeader>
        <AlertDialogTitle className="font-display text-xl">Delete {what}?</AlertDialogTitle>
        <AlertDialogDescription>This removes it from Airtable for good. You can't undo this.</AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel data-testid="confirm-delete-cancel">Keep it</AlertDialogCancel>
        <AlertDialogAction
          data-testid="confirm-delete-confirm"
          onClick={onConfirm}
          className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
        >
          Yes, delete
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
);

/** One quiet line telling you what this screen is for. Never a coloured box. */
export const InstructionBanner = ({ children, testId = "instruction-banner" }) => (
  <p data-testid={testId} className="flex items-start gap-2 text-[13.5px] leading-relaxed text-ink-2 mb-5">
    <Info className="w-4 h-4 mt-0.5 shrink-0 text-faint" aria-hidden="true" />
    <span>{children}</span>
  </p>
);

export const Private = ({ children, block = false, className = "" }) => {
  const { privacy } = useApp();
  const { role } = useAuth();
  const masked = privacy && role !== "employee";
  const Tag = block ? "div" : "span";
  return <Tag className={`${masked ? "privacy-blur" : ""} ${className}`.trim()}>{children}</Tag>;
};

export const Money = ({ value, className = "" }) => (
  <Private className={`tnum ${className}`.trim()}>{fmtMoney(value)}</Private>
);

export const Pill = ({ value, className = "" }) => (
  <span
    className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11.5px] font-semibold leading-5 ${
      STATUS_PILL[value] || "bg-surface-sunk text-ink-2"
    } ${className}`}
  >
    {value}
  </span>
);

/** Live wait timer. Goes red past five minutes — that is the whole point of it. */
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
      className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-bold tnum ${
        late ? "bg-destructive/10 text-destructive" : "bg-success/10 text-success"
      }`}
    >
      <Clock className={`w-3.5 h-3.5 ${late ? "animate-tick" : ""}`} aria-hidden="true" />
      waiting {ageLabel(mins)}
    </span>
  );
};

export const FollowUpBadge = ({ days }) => (
  <span
    data-testid="follow-up-badge"
    className="inline-flex items-center gap-1.5 rounded-md bg-destructive/10 px-2 py-1 text-xs font-bold text-destructive"
  >
    <PhoneCall className="w-3.5 h-3.5" aria-hidden="true" />
    quiet {days} {days === 1 ? "day" : "days"} — call back
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
  if (status === "PAID") return "bg-success/10 text-success";
  if (["CANCELED", "FAILED", "REFUNDED", "PARTIALLY_REFUNDED"].includes(status)) return "bg-surface-sunk text-faint";
  return "bg-warning/10 text-warning";
};

export const InvoiceBadge = ({ inv }) => (
  <a
    data-testid="invoice-status-badge"
    href={inv.public_url || undefined}
    target="_blank"
    rel="noreferrer"
    className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-bold tnum transition-colors hover:brightness-95 ${invoiceBadgeStyle(inv.status)}`}
  >
    <ReceiptText className="w-3.5 h-3.5" aria-hidden="true" />
    Invoice {inv.invoice_number ? `#${inv.invoice_number}` : ""} · {fmtMoney(inv.amount)} · {SQUARE_STATUS_LABEL[inv.status] || inv.status}
  </a>
);

/**
 * Page header. Deliberately small — the nav already told you where you are,
 * so the headline's job is to hold the live count and the primary action,
 * not to fill the top third of a phone.
 */
export const PageTitle = ({ title, subtitle, action, meta }) => (
  <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3 mb-4">
    <div className="min-w-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="font-display text-[22px] sm:text-[26px] font-extrabold text-primary leading-tight">{title}</h1>
        {meta && <span className="text-[13px] font-semibold text-faint tnum">{meta}</span>}
      </div>
      {subtitle && <p className="text-[13.5px] text-ink-2 mt-1 max-w-prose">{subtitle}</p>}
    </div>
    {action && <div className="flex items-center gap-2 shrink-0">{action}</div>}
  </div>
);

/** A labelled section rule. Used instead of another card wrapper. */
export const SectionTitle = ({ children, action, className = "" }) => (
  <div className={`flex items-baseline justify-between gap-3 mb-3 ${className}`}>
    <h2 className="label-eyebrow">{children}</h2>
    {action}
  </div>
);

/**
 * The number component. Owner screens live or die on these, so the figure is
 * large, tabular, and sits on its own line with nothing overlapping it.
 */
export const Figure = ({ label, value, sub, size = "md", tone = "default", isPrivate = false, testId }) => {
  const sizes = {
    sm: "text-[22px]",
    md: "text-[28px] sm:text-[26px]",
    lg: "text-[36px] sm:text-[32px]",
  };
  const tones = {
    default: "text-primary",
    alert: "text-destructive",
    good: "text-success",
    warn: "text-warning",
  };
  return (
    <div data-testid={testId} className="min-w-0">
      <span className="label-eyebrow block">{label}</span>
      <span className={`font-display font-extrabold block mt-1.5 leading-none ${sizes[size]} ${tones[tone]}`}>
        {isPrivate ? <Private>{value}</Private> : value}
      </span>
      {sub && <span className="block text-[12.5px] text-faint mt-1.5 leading-snug">{sub}</span>}
    </div>
  );
};

/**
 * Kept under its original name so every existing page keeps working, but it is
 * now a Figure on a surface. `alert` turns the number red and marks the edge —
 * it no longer wraps the whole card in a red box.
 */
export const KpiCard = ({ label, value, sub, isPrivate = true, alert = false, testId }) => (
  <div
    data-testid={testId}
    className={`surface relative overflow-hidden p-4 h-full ${alert ? "border-destructive/35" : ""}`}
  >
    {alert && <span aria-hidden="true" className="absolute left-0 inset-y-0 w-1 bg-destructive" />}
    <Figure label={label} value={value} sub={sub} isPrivate={isPrivate} tone={alert ? "alert" : "default"} />
  </div>
);

export const EmptyState = ({ children }) => (
  <div className="rounded-xl border border-dashed border-border-strong bg-surface/60 px-6 py-8 text-center text-[13.5px] text-faint">
    {children}
  </div>
);

export const searchMatch = (q, ...vals) => {
  const needle = (q || "").trim().toLowerCase();
  if (!needle) return true;
  return vals.some((v) => String(v ?? "").toLowerCase().includes(needle));
};

export const SearchBar = ({ value, onChange, placeholder = "Search…", testId = "search-input", className = "" }) => (
  <div className={`relative w-full max-w-md ${className}`}>
    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-faint pointer-events-none" aria-hidden="true" />
    <Input
      data-testid={testId}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="pl-9 pr-9"
    />
    {value && (
      <button
        data-testid={`${testId}-clear`}
        onClick={() => onChange("")}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-faint transition-colors hover:bg-surface-sunk hover:text-ink"
        aria-label="Clear search"
      >
        <X className="w-4 h-4" />
      </button>
    )}
  </div>
);

export const LoadingRows = ({ rows = 3 }) => (
  <div className="space-y-3" data-testid="loading-rows">
    {Array.from({ length: rows }).map((_, i) => (
      <div key={i} className="relative h-24 overflow-hidden rounded-xl bg-surface-sunk">
        <span className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/70 to-transparent" />
      </div>
    ))}
  </div>
);
