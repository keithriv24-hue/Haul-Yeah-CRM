import React from "react";
import { Badge } from "@/components/ui/badge";
import { ClipboardList, ShieldAlert, ShieldCheck, MessageSquareWarning, Clock } from "lucide-react";
import { fmtDate } from "@/lib/format";

const POSITION_CHIP = {
  Driver: "bg-primary/10 text-primary border-primary/25",
  Helper: "bg-accent/10 text-accent-ink border-accent/25",
};

const FLAG_TONE = {
  open: "bg-warning/10 border-warning/30 text-warning",
  unverified: "bg-info/10 border-info/30 text-info",
  disputed: "bg-primary/10 border-primary/25 text-primary",
  resolved: "bg-surface-sunk border-border text-faint",
};

const FLAG_STATUS_WORD = {
  open: "Needs review",
  unverified: "Unverified",
  disputed: "Disputed",
  resolved: "Resolved",
};

const HoursCell = ({ hours, estimated }) => {
  if (hours === null || hours === undefined) {
    return <span data-testid="work-record-hours-pending" className="text-faint italic">Hours not recorded</span>;
  }
  if (estimated) {
    return (
      <span data-testid="work-record-hours-estimated" className="inline-flex items-center gap-1 text-ink-2">
        ~{hours.toFixed(1)}h
        <Badge variant="outline" className="text-[9px] bg-info/10 text-info border-info/30">estimate · not payroll</Badge>
      </span>
    );
  }
  return (
    <span data-testid="work-record-hours-actual" className="inline-flex items-center gap-1 font-semibold text-primary">
      {hours.toFixed(1)}h
      <Badge variant="outline" className="text-[9px] bg-success/10 text-success border-success/30">confirmed</Badge>
    </span>
  );
};

// Team HQ "Work record" — dated job history + Crew Lead documentation + reliability flags.
// Backend only sends `records` for self or owner, so this simply renders what it receives.
export const WorkRecord = ({ records, isSelf }) => {
  if (!records) return null;
  const { jobs = [], documentation = {}, flags = [] } = records;
  const who = isSelf ? "you were" : "they were";

  return (
    <div className="space-y-4" data-testid="work-record-section">
      <div className="surface p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-display font-bold text-lg text-primary flex items-center gap-2">
            <ClipboardList className="w-4 h-4 text-accent-ink" /> Work record
          </h2>
          {documentation.as_lead_total > 0 && (
            <Badge data-testid="work-record-doc-summary" variant="outline" className="text-[10px] bg-primary/10 text-primary border-primary/25">
              Crew Lead docs: {documentation.fully_documented}/{documentation.as_lead_total} fully documented
            </Badge>
          )}
        </div>
        {jobs.length === 0 ? (
          <p className="text-sm text-faint" data-testid="work-record-empty">No jobs on the record yet.</p>
        ) : (
          <div className="space-y-2">
            {jobs.map((j) => (
              <div key={j.assignment_id} data-testid="work-record-job" className="rounded-md border border-border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-faint font-mono">{fmtDate(j.job_date)}</span>
                  <span className="font-semibold text-primary flex-1 min-w-[140px]">{j.job_name}</span>
                  {j.position && (
                    <Badge variant="outline" className={`text-[9px] ${POSITION_CHIP[j.position] || "bg-surface-sunk text-ink-2 border-border"}`}>
                      {j.position}
                    </Badge>
                  )}
                  <Badge variant="outline" className="text-[9px] bg-surface-sunk text-ink-2 border-border">{j.exec_status}</Badge>
                </div>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1.5 text-xs">
                  <span className="inline-flex items-center gap-1"><Clock className="w-3 h-3 text-faint" /> <HoursCell hours={j.hours} estimated={j.hours_estimated} /></span>
                  {j.was_lead && (
                    <span data-testid="work-record-lead-docs" className="inline-flex items-center gap-1 text-faint">
                      <ClipboardList className="w-3 h-3 text-accent-ink" />
                      Crew Lead documentation: <strong className="text-ink-2">{j.taps_done}/{j.taps_total} steps</strong>
                      {j.taps_done >= j.taps_total && j.taps_total > 0 && (
                        <Badge variant="outline" className="text-[9px] bg-success/10 text-success border-success/30">complete</Badge>
                      )}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        <p className="text-[11px] text-faint mt-3">
          Estimated hours are labeled and are never approved payroll time. Only {isSelf ? "you" : "they"} and the owner can see this record.
        </p>
      </div>

      <div className="surface p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-display font-bold text-lg text-primary flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-warning" /> Timekeeping history
          </h2>
          <div className="flex items-center gap-1.5">
            {records.flags_open > 0 && (
              <Badge data-testid="work-record-flags-open" variant="outline" className="text-[10px] bg-warning/10 text-warning border-warning/30">{records.flags_open} to review</Badge>
            )}
            {records.flags_resolved > 0 && (
              <Badge data-testid="work-record-flags-resolved" variant="outline" className="text-[10px] bg-surface-sunk text-faint border-border">{records.flags_resolved} resolved</Badge>
            )}
          </div>
        </div>
        {flags.length === 0 ? (
          <p className="text-sm text-faint inline-flex items-center gap-1.5" data-testid="work-record-flags-empty">
            <ShieldCheck className="w-4 h-4 text-success" /> No timekeeping flags on record — clean sheet.
          </p>
        ) : (
          <div className="space-y-2">
            {flags.map((f) => (
              <div key={f.id} data-testid="work-record-flag" className="rounded-md border border-border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline" className={`text-[9px] ${FLAG_TONE[f.status] || FLAG_TONE.open}`}>{f.label}</Badge>
                  <Badge variant="outline" className="text-[9px] bg-surface-sunk text-ink-2 border-border">{FLAG_STATUS_WORD[f.status] || f.status}</Badge>
                  <span className="text-[10px] text-faint font-mono ml-auto">{fmtDate((f.job_date || f.created_at || "").slice(0, 10))}</span>
                </div>
                <p className="text-[13px] text-ink-2 mt-1">{f.detail}</p>
                <p className="text-[11px] text-faint">{f.job_name}</p>
                {f.dispute_reason && (
                  <p className="text-[12px] text-primary mt-1 italic">{who} disputed: {f.dispute_reason}</p>
                )}
                {f.status === "resolved" && f.resolve_reason && (
                  <p data-testid="work-record-resolve-reason" className="text-[12px] text-faint mt-1 inline-flex items-start gap-1">
                    <MessageSquareWarning className="w-3.5 h-3.5 text-success shrink-0 mt-0.5" />
                    Owner resolved{f.resolved_by ? ` (${f.resolved_by})` : ""}: {f.resolve_reason}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
