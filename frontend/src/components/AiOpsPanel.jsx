import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BrainCircuit, RefreshCw, AlertTriangle, Truck, DollarSign, Users, CalendarX2, Clock3, MessageSquareWarning } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { fmtMoney } from "@/lib/format";
import { opsBriefApi } from "@/lib/api";

/**
 * A gauge, not a pill. The owner reads this panel at arm's length, so the
 * number is the biggest thing in the cell and the label sits above it.
 */
const Chip = ({ icon: Icon, label, value, alert, to, testId }) => {
  const inner = (
    <span
      data-testid={testId}
      className={`flex h-full flex-col justify-between gap-1.5 rounded-lg px-3 py-2.5 transition-colors duration-[160ms] ${
        alert ? "bg-white/[0.07] ring-1 ring-inset ring-destructive/50" : "bg-white/[0.06]"
      } ${to ? "hover:bg-white/[0.12]" : ""}`}
    >
      <span className="flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-[0.1em] text-white/50">
        <Icon className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
        <span className="truncate">{label}</span>
      </span>
      <span className={`font-display text-[22px] font-extrabold leading-none tnum ${alert ? "text-accent" : "text-white"}`}>
        {value}
      </span>
    </span>
  );
  return to ? <Link to={to} className="block h-full press">{inner}</Link> : inner;
};

export const AiOpsPanel = () => {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const load = (refresh) => {
    setBusy(true);
    opsBriefApi(refresh)
      .then((d) => { setData(d); setFailed(false); })
      .catch(() => setFailed(true))
      .finally(() => setBusy(false));
  };
  useEffect(() => load(false), []);

  if (failed && !data) return null;
  const f = data?.facts;
  const lines = (data?.brief || "").split("\n").map((l) => l.trim()).filter(Boolean);
  const fleetFlags = f ? f.fleet.needs_attention.length + f.fleet.in_shop.length + f.fleet.maintenance_due.length + f.fleet.document_warnings.length : 0;

  return (
    <div data-testid="ai-ops-panel" className="rounded-xl bg-primary p-4 sm:p-5 mb-6 text-white">
      <div className="flex items-center gap-2 mb-4">
        <BrainCircuit className="w-[18px] h-[18px] text-accent shrink-0" aria-hidden="true" />
        <h2 className="font-display text-[17px] font-extrabold flex-1">Ops brain</h2>
        {data?.generated_at && (
          <span className="text-[11px] text-white/55 tnum">
            {new Date(data.generated_at).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}
          </span>
        )}
        <button data-testid="ops-brief-refresh" disabled={busy} onClick={() => load(true)}
          className="press inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[12px] font-semibold text-white/60 transition-colors hover:bg-white/10 hover:text-white disabled:opacity-50">
          <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} aria-hidden="true" /> Refresh
        </button>
      </div>

      {f && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7 gap-2 mb-4">
          <Chip testId="ops-chip-jobs" icon={Truck} label="Jobs today" value={f.jobs_today.total} to="/dispatch" />
          <Chip testId="ops-chip-revenue" icon={DollarSign} label="Revenue today" value={fmtMoney(f.revenue_today)} />
          <Chip testId="ops-chip-crews" icon={Users} label="On the clock" value={f.crews_working.clocked_in.length}
            alert={f.crews_working.unscheduled_clock_ins.length > 0} />
          <Chip testId="ops-chip-behind" icon={Clock3} label="Behind / at risk" value={f.jobs_today.behind.length + f.late_job_risk.length}
            alert={f.jobs_today.behind.length + f.late_job_risk.length > 0} to="/dispatch" />
          <Chip testId="ops-chip-fleet" icon={AlertTriangle} label="Fleet flags" value={fleetFlags} alert={fleetFlags > 0} to="/fleet" />
          <Chip testId="ops-chip-outstanding" icon={DollarSign} label="Owed to us" value={fmtMoney(f.money.outstanding_balance_total)}
            alert={f.money.outstanding_balance_total > 0} to="/jobs" />
          <Chip testId="ops-chip-conflicts" icon={CalendarX2} label="Conflicts" value={f.schedule_conflicts.length}
            alert={f.schedule_conflicts.length > 0} to="/dispatch" />
          {f.overtime_warnings.length > 0 && (
            <Chip testId="ops-chip-overtime" icon={Clock3} label="Overtime" value={f.overtime_warnings.length} alert />
          )}
          {f.customer_issues.length > 0 && (
            <Chip testId="ops-chip-issues" icon={MessageSquareWarning} label="Customer issues" value={f.customer_issues.length} alert />
          )}
        </div>
      )}

      {!data && !failed && <p className="text-[13.5px] text-white/65">Reading the board, the fleet, and the books…</p>}
      {lines.length > 0 ? (
        <div data-testid="ops-brief-text" className="space-y-2 border-t border-white/10 pt-3.5">
          {lines.map((l, i) => {
            const clean = l.replace(/^-\s*/, "");
            const isDo = clean.startsWith("DO:");
            return (
              <p
                key={i}
                data-testid="ops-brief-line"
                className={`flex items-start gap-2 text-[13.5px] leading-relaxed ${isDo ? "font-semibold text-white" : "text-white/75"}`}
              >
                {isDo && (
                  <span className="mt-[3px] shrink-0 rounded bg-accent px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-accent-foreground">
                    Do
                  </span>
                )}
                <span>{isDo ? clean.replace(/^DO:\s*/, "") : clean}</span>
              </p>
            );
          })}
        </div>
      ) : data && (
        <p className="text-[13.5px] text-white/65">The brief is warming up — hit Refresh in a few seconds.</p>
      )}
      {f?.schedule_conflicts.length > 0 && (
        <div className="mt-3 space-y-1">
          {f.schedule_conflicts.map((c, i) => (
            <p key={i} data-testid="ops-conflict-line" className="flex items-start gap-1.5 text-[12.5px] text-accent">
              <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" aria-hidden="true" /> {c}
            </p>
          ))}
        </div>
      )}
    </div>
  );
};
