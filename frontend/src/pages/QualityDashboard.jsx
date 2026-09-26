import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  ShieldCheck, AlertTriangle, RefreshCw, ChevronDown, ChevronRight,
  Star, Clock, CheckCircle2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { InstructionBanner, PageTitle, EmptyState, LoadingRows } from "@/components/Bits";
import { qualityDashboardApi, qualityReviewsApi, qualitySetGoogleReviewApi, apiErrorMessage } from "@/lib/api";
import { fmtDate, daysUntil, stateTone, stateBorder, stateDot, metricValue } from "@/lib/quality";

const KpiTile = ({ m }) => (
  <div data-testid={`kpi-${m.key}`} className={`surface rounded-xl border ${stateBorder(m.state)} p-4`}>
    <div className="flex items-center justify-between">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-faint">{m.label}</div>
      <span className={`h-2.5 w-2.5 rounded-full ${stateDot(m.state)}`} />
    </div>
    <div className={`mt-2 font-display text-[30px] font-extrabold leading-none ${stateTone(m.state)}`}>
      {metricValue(m)}
    </div>
    <div className="mt-1.5 flex items-center justify-between text-[11.5px] text-faint">
      <span>Target {m.target_display}</span>
      {m.denominator != null && m.unit === "pct" && (
        <span className="tnum">{m.numerator} / {m.denominator}</span>
      )}
    </div>
    {m.key === "quote_variance" && (
      <Link
        to="/quality/quote-accuracy"
        data-testid="kpi-quote-accuracy-link"
        className="press mt-2 inline-block text-[11.5px] font-semibold text-accent hover:underline"
      >
        Open quote accuracy →
      </Link>
    )}
  </div>
);

const RiskCard = ({ m }) => {
  const good = m.value === 100;
  return (
    <div
      data-testid={`kpi-${m.key}`}
      className={`rounded-xl border-2 p-5 ${good ? "border-emerald-400 bg-emerald-50/50" : "border-red-400 bg-red-50/50"}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-ink-2">
            <ShieldCheck className="h-3.5 w-3.5" /> Risk measure · document compliance
          </div>
          <div className={`mt-1 font-display text-[34px] font-extrabold leading-none ${good ? "text-emerald-700" : "text-red-600"}`}>
            {metricValue(m)}
          </div>
          <div className="mt-1 text-[12px] text-ink-2">
            {m.numerator} of {m.denominator} completed jobs pass all 11 legal gates with no override.
          </div>
        </div>
        <div className="text-right">
          <div className="text-[11px] uppercase tracking-wide text-faint">Target</div>
          <div className="font-display text-[15px] font-bold text-ink">{m.target_display}</div>
          <div className="mt-1 text-[11px] text-faint max-w-[190px]">
            Exempt gate = pass · override = fail. This one has no partial credit.
          </div>
        </div>
      </div>
    </div>
  );
};

const NeedRow = ({ testId, tone, children }) => (
  <div
    data-testid={testId}
    className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-[13px] ${
      tone === "red" ? "border-red-300 bg-red-50 text-red-800" : "border-amber-300 bg-amber-50 text-amber-900"
    }`}
  >
    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
    <div className="min-w-0">{children}</div>
  </div>
);

const ReviewStateChip = ({ row }) => {
  if (row.state === "received")
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-emerald-100 px-2 py-0.5 text-[11px] font-bold text-emerald-700">
        <CheckCircle2 className="h-3 w-3" /> Review in
      </span>
    );
  if (row.state === "waiting") {
    const wd = daysUntil(row.review_requested_at);
    const waited = wd == null ? null : Math.max(0, -wd);
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-surface-sunk px-2 py-0.5 text-[11px] font-semibold text-ink-2">
        <Clock className="h-3 w-3" /> Asked{waited != null ? ` · ${waited}d` : ""}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-surface-sunk px-2 py-0.5 text-[11px] font-semibold text-faint">
      No ask sent
    </span>
  );
};

const ReviewCapture = () => {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await qualityReviewsApi());
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (open && !data) load();
  }, [open, data, load]);

  const toggle = async (row) => {
    setSaving(row.id);
    try {
      const next = !row.google_review_received;
      await qualitySetGoogleReviewApi(row.id, next);
      setData((d) => ({
        ...d,
        rows: d.rows.map((r) =>
          r.id === row.id
            ? { ...r, google_review_received: next, state: next ? "received" : (r.review_requested_at ? "waiting" : "none"), flag: next ? null : r.flag }
            : r
        ),
      }));
      toast.success(next ? "Marked review received." : "Cleared.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setSaving(null);
  };

  const rows = data?.rows || [];
  const toChase = data?.to_chase ?? 0;

  return (
    <div data-testid="review-capture" className="surface rounded-xl border border-border">
      <button
        data-testid="review-capture-toggle"
        onClick={() => setOpen((o) => !o)}
        className="press flex w-full items-center justify-between gap-2 p-4 text-left"
      >
        <div className="flex items-center gap-2">
          {open ? <ChevronDown className="h-4 w-4 text-faint" /> : <ChevronRight className="h-4 w-4 text-faint" />}
          <Star className="h-4 w-4 text-accent" />
          <span className="font-display text-[15px] font-bold text-primary">Review chase</span>
        </div>
        {toChase > 0 && (
          <span data-testid="review-chase-count" className="rounded-md bg-accent px-2 py-0.5 text-[11px] font-bold text-white">
            {toChase} to text
          </span>
        )}
      </button>
      {open && (
        <div className="border-t border-border p-3">
          <p className="mb-2 text-[12px] text-faint">
            This month's completed jobs, oldest first. Text at day 2, again at day 6, then leave it alone.
          </p>
          {loading ? (
            <LoadingRows rows={2} />
          ) : rows.length === 0 ? (
            <EmptyState>No completed jobs this month yet.</EmptyState>
          ) : (
            <div className="space-y-1.5">
              {rows.map((r) => (
                <div
                  key={r.id}
                  data-testid="review-row"
                  className={`flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border px-3 py-2 ${
                    r.flag === "day6" ? "border-red-300 bg-red-50/60" : r.flag === "day2" ? "border-amber-300 bg-amber-50/60" : "border-border"
                  }`}
                >
                  <div className="min-w-[140px] flex-1">
                    <div className="font-semibold text-[13.5px] text-ink truncate">{r.name}</div>
                    <div className="text-[11.5px] text-faint">
                      {fmtDate(r.move_date)} · {r.days_since == null ? "—" : `${r.days_since}d since`}
                    </div>
                  </div>
                  <ReviewStateChip row={r} />
                  {r.flag === "day2" && (
                    <span data-testid="review-flag-day2" className="rounded-md bg-amber-500 px-2 py-0.5 text-[10.5px] font-bold uppercase text-white">
                      Text now · day 2
                    </span>
                  )}
                  {r.flag === "day6" && (
                    <span data-testid="review-flag-day6" className="rounded-md bg-red-600 px-2 py-0.5 text-[10.5px] font-bold uppercase text-white">
                      2nd text · day 6
                    </span>
                  )}
                  <Button
                    data-testid={`review-toggle-${r.id}`}
                    size="sm"
                    variant={r.google_review_received ? "outline" : "default"}
                    disabled={saving === r.id}
                    onClick={() => toggle(r)}
                    className={`h-7 gap-1 text-[12px] ${r.google_review_received ? "" : "bg-accent hover:bg-accent-press"}`}
                  >
                    {r.google_review_received ? "Undo" : "Got review"}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default function QualityDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await qualityDashboardApi());
    } catch (e) {
      setError(apiErrorMessage(e));
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const metrics = data?.metrics || [];
  const doc = data?.document_compliance;
  const nyn = data?.needs_you_now || { claims: [], overdue_audits: [], liability_ncs: [], count: 0 };

  return (
    <div data-testid="quality-dashboard-page">
      <PageTitle
        title="Quality dashboard"
        subtitle="Today — this month's numbers, live."
        action={
          <Button data-testid="dashboard-refresh-btn" variant="outline" onClick={load} className="gap-1.5">
            <RefreshCw className="h-4 w-4" /> Refresh
          </Button>
        }
      />
      <InstructionBanner>
        The live picture for the month in progress. The strip up top is what needs you now; the six numbers are where you stand.
      </InstructionBanner>

      {loading ? (
        <LoadingRows />
      ) : error ? (
        <EmptyState>{error}</EmptyState>
      ) : (
        <div className="space-y-5">
          {/* Needs you now */}
          <div data-testid="needs-you-now" className="surface rounded-xl border border-border p-4">
            <div className="mb-2 flex items-center gap-2">
              <span className="font-display text-[15px] font-bold text-primary">Needs you now</span>
              {nyn.count > 0 && (
                <span data-testid="needs-count" className="rounded-md bg-red-600 px-2 py-0.5 text-[11px] font-bold text-white">
                  {nyn.count}
                </span>
              )}
            </div>
            {nyn.count === 0 ? (
              <div data-testid="needs-clear" className="flex items-center gap-2 text-[13px] text-emerald-700">
                <CheckCircle2 className="h-4 w-4" /> Nothing needs you right now — you're clear.
              </div>
            ) : (
              <div className="space-y-1.5">
                {nyn.claims.map((c) => (
                  <NeedRow key={c.id} testId="need-claim" tone={c.state === "red" ? "red" : "amber"}>
                    <span className="font-semibold">Claim #{c.claim_number ?? "—"}</span>
                    {c.job ? ` · ${c.job}` : ""} — {c.which === "form" ? "form" : "settlement"} due {fmtDate(c.deadline)}
                    {c.days != null && (
                      <b> ({c.days < 0 ? `${-c.days}d overdue` : `${c.days}d left`})</b>
                    )}
                  </NeedRow>
                ))}
                {nyn.overdue_audits.map((a) => (
                  <NeedRow key={a.id} testId="need-audit" tone="red">
                    <span className="font-semibold">Audit overdue</span> · {a.name} — {a.days_over}d past its 7-day window
                  </NeedRow>
                ))}
                {nyn.liability_ncs.map((n) => (
                  <NeedRow key={n.id} testId="need-liability-nc" tone="red">
                    <span className="font-semibold">Liability-risk NC #{n.number ?? "—"}</span> · {n.type} — {n.status}
                    {n.what ? ` — ${n.what}` : ""}
                  </NeedRow>
                ))}
              </div>
            )}
          </div>

          {/* Five KPIs */}
          <div data-testid="kpi-grid" className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {metrics.map((m) => <KpiTile key={m.key} m={m} />)}
          </div>

          {/* Document compliance — separate risk measure */}
          {doc && <RiskCard m={doc} />}

          {/* Review chase */}
          <ReviewCapture />
        </div>
      )}
    </div>
  );
}
