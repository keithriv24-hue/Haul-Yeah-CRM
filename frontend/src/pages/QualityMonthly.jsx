import React, { useEffect, useState, useCallback } from "react";
import { CalendarRange, RefreshCw, ArrowUp, ArrowDown, Minus, Scale, AlertOctagon, ClipboardCheck, IdCard } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InstructionBanner, PageTitle, EmptyState, LoadingRows } from "@/components/Bits";
import { qualityMonthlyApi, apiErrorMessage } from "@/lib/api";
import { fmtDate, stateTone, stateBorder, stateDot, metricValue } from "@/lib/quality";

const currentMonth = () => new Date().toISOString().slice(0, 7);
const monthLabel = (m) => {
  try {
    const [y, mo] = m.split("-");
    return new Date(Number(y), Number(mo) - 1, 1).toLocaleDateString("en-US", { month: "long", year: "numeric" });
  } catch {
    return m;
  }
};

const Movement = ({ m }) => {
  if (m.movement == null || m.prev_value == null)
    return <span className="inline-flex items-center gap-1 text-[11.5px] text-faint"><Minus className="h-3 w-3" /> no prior month</span>;
  const up = m.movement > 0;
  const flat = m.movement === 0;
  const Icon = flat ? Minus : up ? ArrowUp : ArrowDown;
  const suffix = m.unit === "hours" ? "h" : m.unit === "pct" ? "pts" : "";
  return (
    <span className={`inline-flex items-center gap-1 text-[11.5px] font-semibold ${flat ? "text-faint" : "text-ink-2"}`}>
      <Icon className="h-3 w-3" /> {up ? "+" : ""}{m.movement}{suffix} vs {metricValue({ ...m, value: m.prev_value })}
    </span>
  );
};

const MetricCard = ({ m, risk }) => (
  <div
    data-testid={`monthly-kpi-${m.key}`}
    className={`surface rounded-xl border ${risk ? "border-2" : ""} ${stateBorder(m.state)} p-4`}
  >
    <div className="flex items-center justify-between">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-faint">{m.label}{risk ? " · risk" : ""}</div>
      <span className={`h-2.5 w-2.5 rounded-full ${stateDot(m.state)}`} />
    </div>
    <div className={`mt-2 font-display text-[28px] font-extrabold leading-none ${stateTone(m.state)}`}>{metricValue(m)}</div>
    <div className="mt-1.5 text-[11.5px] text-faint">Target {m.target_display}</div>
    <div className="mt-1"><Movement m={m} /></div>
  </div>
);

const Section = ({ icon: Icon, title, count, children, testId }) => (
  <div data-testid={testId} className="surface rounded-xl border border-border p-4">
    <div className="mb-2 flex items-center gap-2">
      <Icon className="h-4 w-4 text-primary" />
      <span className="font-display text-[14px] font-bold text-primary">{title}</span>
      <span className="rounded-md bg-surface-sunk px-1.5 py-0.5 text-[11px] font-semibold text-ink-2">{count}</span>
    </div>
    {children}
  </div>
);

export default function QualityMonthly() {
  const [month, setMonth] = useState(currentMonth());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await qualityMonthlyApi(month));
    } catch (e) {
      setError(apiErrorMessage(e));
    }
    setLoading(false);
  }, [month]);

  useEffect(() => {
    load();
  }, [load]);

  const metrics = data?.metrics || [];
  const doc = data?.document_compliance;
  const openNcs = data?.open_nonconformances || [];
  const claims = data?.claims_near_deadline || [];
  const overdue = data?.overdue_audits || [];
  const expiring = data?.crew_docs_expiring || [];

  return (
    <div data-testid="quality-monthly-page">
      <PageTitle
        title="Monthly review"
        subtitle="The first-Monday agenda — six frozen numbers read against what's still open."
        action={
          <div className="flex items-end gap-2">
            <Input
              type="month"
              data-testid="monthly-month-input"
              value={month}
              max={currentMonth()}
              onChange={(e) => setMonth(e.target.value || currentMonth())}
              className="h-9 w-[160px]"
            />
            <Button data-testid="monthly-refresh-btn" variant="outline" onClick={load} className="gap-1.5">
              <RefreshCw className="h-4 w-4" /> Refresh
            </Button>
          </div>
        }
      />
      <InstructionBanner>
        Closed months read a frozen snapshot and never recalculate. The current month is live and not yet final.
      </InstructionBanner>

      {loading ? (
        <LoadingRows />
      ) : error ? (
        <EmptyState>{error}</EmptyState>
      ) : data?.no_snapshot ? (
        <div data-testid="monthly-no-snapshot" className="surface rounded-xl border border-border p-8 text-center">
          <CalendarRange className="mx-auto h-8 w-8 text-faint" />
          <div className="mt-3 font-display text-[16px] font-bold text-ink">No snapshot for {monthLabel(month)}</div>
          <p className="mx-auto mt-1 max-w-md text-[13px] text-faint">
            Monthly numbers freeze once, at month-end. This period was either before the feature shipped or hasn't been closed yet — and a back-filled number would be indistinguishable from a frozen one, so we show the gap instead.
          </p>
        </div>
      ) : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-display text-[17px] font-extrabold text-primary">{monthLabel(data.month)}</span>
            {data.is_current_month ? (
              <span data-testid="monthly-inprogress-badge" className="rounded-md bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-800">
                In progress — not yet final
              </span>
            ) : (
              <span data-testid="monthly-frozen-badge" className="rounded-md bg-emerald-100 px-2 py-0.5 text-[11px] font-bold text-emerald-700">
                Frozen{data.frozen_at ? ` ${fmtDate(data.frozen_at)}` : ""}
              </span>
            )}
            <span className="text-[12px] text-faint">{data.completed_jobs} completed job{data.completed_jobs === 1 ? "" : "s"}</span>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {metrics.map((m) => <MetricCard key={m.key} m={m} />)}
            {doc && <MetricCard m={doc} risk />}
          </div>

          <Section icon={AlertOctagon} title="Open nonconformances" count={openNcs.length} testId="monthly-open-ncs">
            {openNcs.length === 0 ? (
              <p className="text-[12.5px] text-faint">None open.</p>
            ) : (
              <div className="space-y-1.5">
                {openNcs.map((n) => (
                  <div key={n.id} data-testid="monthly-nc-row" className="flex flex-wrap items-center gap-2 border-b border-border/50 py-1 text-[12.5px] last:border-0">
                    <span className={`rounded px-1.5 py-0.5 text-[10.5px] font-bold ${n.severity === "Liability risk" || n.severity === "Regulatory" ? "bg-red-100 text-red-700" : "bg-surface-sunk text-ink-2"}`}>
                      {n.severity || "—"}
                    </span>
                    <span className="font-semibold text-ink">#{n.number ?? "—"} {n.type}</span>
                    <span className="text-faint">· {n.status}</span>
                    {n.what && <span className="text-ink-2 truncate">— {n.what}</span>}
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section icon={Scale} title="Claims near a deadline" count={claims.length} testId="monthly-claims">
            {claims.length === 0 ? (
              <p className="text-[12.5px] text-faint">No claims within 14 days.</p>
            ) : (
              <div className="space-y-1.5">
                {claims.map((c) => (
                  <div key={c.id} data-testid="monthly-claim-row" className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 py-1 text-[12.5px] last:border-0">
                    <span className="font-semibold text-ink">Claim #{c.claim_number ?? "—"} · {c.linked_job_name || "—"}</span>
                    <span className={stateTone(c.urgency?.state)}>
                      {c.urgency?.which === "form" ? "Form" : "Settlement"} due {fmtDate(c.urgency?.deadline)} ({c.urgency?.days}d)
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section icon={ClipboardCheck} title="Overdue audits" count={overdue.length} testId="monthly-overdue-audits">
            {overdue.length === 0 ? (
              <p className="text-[12.5px] text-faint">All caught up.</p>
            ) : (
              <div className="space-y-1.5">
                {overdue.map((a) => (
                  <div key={a.id} data-testid="monthly-audit-row" className="flex items-center justify-between gap-2 border-b border-border/50 py-1 text-[12.5px] last:border-0">
                    <span className="font-semibold text-ink truncate">{a.name}</span>
                    <span className="text-red-600 font-bold">{a.days_over}d over</span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section icon={IdCard} title="Crew docs expiring (60 days)" count={expiring.length} testId="monthly-expiring-docs">
            {expiring.length === 0 ? (
              <p className="text-[12.5px] text-faint">Nothing expiring soon.</p>
            ) : (
              <div className="space-y-1.5">
                {expiring.map((e) => (
                  <div key={e.user_id} data-testid="monthly-doc-row" className="flex items-center justify-between gap-2 border-b border-border/50 py-1 text-[12.5px] last:border-0">
                    <span className="font-semibold text-ink">{e.name}</span>
                    <span className={e.expired ? "text-red-600 font-bold" : "text-amber-600 font-semibold"}>
                      {e.expired ? "Expired" : `${e.days}d`} · {fmtDate(e.expires)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Section>
        </div>
      )}
    </div>
  );
}
