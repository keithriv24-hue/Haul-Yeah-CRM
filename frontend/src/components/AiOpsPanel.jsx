import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BrainCircuit, RefreshCw, AlertTriangle, Truck, DollarSign, Users, CalendarX2, Clock3, MessageSquareWarning } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { fmtMoney } from "@/lib/format";
import { opsBriefApi } from "@/lib/api";

const Chip = ({ icon: Icon, label, value, alert, to, testId }) => {
  const inner = (
    <span data-testid={testId} className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${alert ? "bg-red-500/15 border-red-400/40 text-red-200" : "bg-white/5 border-white/15 text-white/75"} ${to ? "hover:border-[#E8743B]" : ""}`}>
      <Icon className="w-3.5 h-3.5" /> {label}: <span className={alert ? "text-red-100 font-bold" : "text-white font-bold"}>{value}</span>
    </span>
  );
  return to ? <Link to={to}>{inner}</Link> : inner;
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
    <div data-testid="ai-ops-panel" className="bg-[#1B2A4A] rounded-lg p-5 mb-6 text-white">
      <div className="flex items-center gap-2 mb-3">
        <BrainCircuit className="w-5 h-5 text-[#E8743B]" />
        <h2 className="font-display font-bold text-lg flex-1">Ops brain</h2>
        {data?.generated_at && (
          <span className="text-[10px] text-white/40">
            {new Date(data.generated_at).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}
          </span>
        )}
        <button data-testid="ops-brief-refresh" disabled={busy} onClick={() => load(true)}
          className="inline-flex items-center gap-1 text-xs font-semibold text-white/60 hover:text-white transition-colors">
          <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      {f && (
        <div className="flex flex-wrap gap-2 mb-4">
          <Chip testId="ops-chip-jobs" icon={Truck} label="Jobs today" value={f.jobs_today.total} to="/dispatch" />
          <Chip testId="ops-chip-revenue" icon={DollarSign} label="Revenue today" value={fmtMoney(f.revenue_today)} />
          <Chip testId="ops-chip-crews" icon={Users} label="On the clock" value={f.crews_working.clocked_in.length}
            alert={f.crews_working.unscheduled_clock_ins.length > 0} />
          <Chip testId="ops-chip-behind" icon={Clock3} label="Behind / at risk" value={f.jobs_today.behind.length + f.late_job_risk.length}
            alert={f.jobs_today.behind.length + f.late_job_risk.length > 0} to="/dispatch" />
          <Chip testId="ops-chip-fleet" icon={AlertTriangle} label="Fleet flags" value={fleetFlags} alert={fleetFlags > 0} to="/fleet" />
          <Chip testId="ops-chip-outstanding" icon={DollarSign} label="Owed to you" value={fmtMoney(f.money.outstanding_balance_total)}
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

      {!data && !failed && <p className="text-sm text-white/50">Reading the board, the fleet, and the books…</p>}
      {lines.length > 0 ? (
        <div data-testid="ops-brief-text" className="space-y-1.5">
          {lines.map((l, i) => {
            const isDo = l.replace(/^-\s*/, "").startsWith("DO:");
            return (
              <p key={i} data-testid="ops-brief-line" className={`text-sm leading-snug ${isDo ? "text-[#E8743B] font-semibold" : "text-white/85"}`}>
                {l}
              </p>
            );
          })}
        </div>
      ) : data && (
        <p className="text-sm text-white/50">The brief is warming up — hit Refresh in a few seconds.</p>
      )}
      {f?.schedule_conflicts.length > 0 && (
        <div className="mt-3 space-y-1">
          {f.schedule_conflicts.map((c, i) => (
            <p key={i} data-testid="ops-conflict-line" className="text-xs text-amber-300 flex items-start gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {c}
            </p>
          ))}
        </div>
      )}
    </div>
  );
};
