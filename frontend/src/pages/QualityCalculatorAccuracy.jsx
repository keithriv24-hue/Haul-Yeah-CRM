import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Gauge, RefreshCw, TrendingUp, Layers, SlidersHorizontal, ClipboardList, FlaskConical, ArrowRight, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { InstructionBanner, PageTitle, EmptyState, LoadingRows } from "@/components/Bits";
import { qualityCalculatorAccuracyApi, optimizerStateApi, apiErrorMessage } from "@/lib/api";
import { money, fmtDate } from "@/lib/quality";
import OptimizerPanel from "@/components/quality/OptimizerPanel";

const ACCESS_LABELS = {
  stairsO: "Stairs — pickup", stairsD: "Stairs — drop-off", elevO: "Elevator",
  carryO: "Long carry — pickup", carryD: "Long carry — drop-off", ladder: "Attic ladder",
  tight: "Tight / furnished", noPark: "No parking / shuttle", disasm: "Disassembly", stops: "Extra stops",
};
const PACK_LABELS = ["Fully packed", "Mostly packed", "Partially packed", "Not packed"];
const PKG_LABELS = { studio: "Studio / 1BR", br2: "2BR", br3: "3BR", br4: "4BR+", none: "No package (rooms)" };
const CREW_LABELS = { "2": "2 movers", "3": "3 movers", "4": "4 movers", "5plus": "5+ movers" };
const REASON_LABELS = {
  incomplete_actuals: "Incomplete actuals", no_matched_quote: "No matched quote",
  model_outlier: "Large model miss", survey_miss_pending: "Survey miss to review",
  manually_excluded: "Manually excluded", final_total_missing: "Final billed missing",
};
const LABEL_TONE = { no_data: "text-faint bg-surface-sunk", insufficient: "text-warning bg-warning/10", limited: "text-accent-ink bg-accent/10", ok: "text-success bg-success/10" };
const LABEL_TEXT = { no_data: "No data", insufficient: "Insufficient", limited: "Limited data", ok: "Good sample" };

const signedMh = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v} mh`);
const pct = (v) => (v == null ? "—" : `${v}%`);

const CoverageChip = ({ label, sample, coverLabel, testId }) => (
  <div data-testid={testId} className="rounded-lg border border-border p-2.5 flex items-center justify-between gap-2">
    <span className="text-[12.5px] text-ink-2 min-w-0 truncate">{label}</span>
    <span className="flex items-center gap-1.5 shrink-0">
      <span className="tnum text-[12px] text-primary font-semibold">{sample}</span>
      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${LABEL_TONE[coverLabel] || LABEL_TONE.no_data}`}>{LABEL_TEXT[coverLabel] || "—"}</span>
    </span>
  </div>
);

const Metric = ({ label, value, sub, testId, tone = "text-primary" }) => (
  <div data-testid={testId} className="surface p-3 rounded-lg border border-border">
    <div className="text-[10.5px] uppercase tracking-wide text-faint font-bold">{label}</div>
    <div className={`mt-1 font-display text-[20px] font-extrabold ${tone}`}>{value}</div>
    {sub && <div className="text-[11px] text-faint mt-0.5">{sub}</div>}
  </div>
);

const Section = ({ icon: Icon, title, hint, children, testId }) => (
  <div data-testid={testId} className="surface p-4 rounded-lg">
    <div className="flex items-center gap-2 mb-1">
      <Icon className="w-4 h-4 text-accent-ink" />
      <h3 className="font-bold text-primary text-[14px]">{title}</h3>
    </div>
    {hint && <p className="text-[11.5px] text-faint mb-3">{hint}</p>}
    {children}
  </div>
);

export default function QualityCalculatorAccuracy() {
  const [data, setData] = useState(null);
  const [optState, setOptState] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    qualityCalculatorAccuracyApi()
      .then(setData)
      .catch((e) => toast.error(apiErrorMessage(e)))
      .finally(() => setLoading(false));
    optimizerStateApi().then(setOptState).catch(() => {});
  }, []);
  const reloadOptimizer = useCallback(() => {
    optimizerStateApi().then(setOptState).catch(() => {});
    qualityCalculatorAccuracyApi().then(setData).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading && !data) return <div className="mt-6"><LoadingRows rows={5} /></div>;
  if (!data) return null;

  const { summary, trends, coverage, review_queue: queue, current_parameters: cp, progress } = data;
  const isOwner = data.role === "owner";
  const wmh = summary.work_mh || {};
  const dollars = summary.dollars;   // owner only
  const biasTone = wmh.bias_direction === "over" ? "text-warning" : wmh.bias_direction === "under" ? "text-accent-ink" : "text-success";
  const learningOn = progress.stage7_enabled && !progress.paused;
  const stageBadge = learningOn ? { t: "Learning ON", cls: "bg-success/10 text-success" }
    : progress.paused ? { t: "Paused", cls: "bg-warning/10 text-warning" }
    : { t: "Shadow only", cls: "bg-surface-sunk text-faint" };

  return (
    <div data-testid="calc-accuracy-page" className="pb-16 space-y-4">
      <PageTitle
        title="Calculator Accuracy"
        subtitle="How accurate the estimator is against real completed jobs — and the guarded auto-optimizer that tunes it."
        action={<Button data-testid="calc-accuracy-refresh" variant="outline" size="sm" className="gap-1.5" onClick={load}><RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh</Button>}
      />

      <InstructionBanner testId="calc-accuracy-banner">
        This page <b>measures</b> estimating accuracy and runs the <b>guarded auto-optimizer</b>. The optimizer only
        learns non-monetary work-model parameters, moves within tight per-factor sample thresholds, movement caps,
        bounds and accuracy gates, and never re-prices a saved quote. It stays in <b>shadow</b> mode until the owner
        activates it — after that, eligible unlocked changes apply on the nightly run. Every change needs a reason and
        is versioned.
      </InstructionBanner>

      {/* Progress preview toward Stage 7 readiness */}
      <div data-testid="calc-accuracy-progress" className="surface p-4 rounded-lg">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <FlaskConical className="w-4 h-4 text-accent-ink" />
            <h3 className="font-bold text-primary text-[14px]">Optimizer readiness</h3>
            <span data-testid="calc-accuracy-stage7-badge" className={`text-[10px] font-bold px-2 py-0.5 rounded ${stageBadge.cls}`}>{stageBadge.t}</span>
          </div>
          <span className="tnum text-[12.5px] text-ink-2">{progress.usable_jobs} / {progress.readiness_target} usable jobs</span>
        </div>
        <div className="mt-2 h-2 rounded-full bg-surface-sunk overflow-hidden">
          <div className="h-full bg-accent transition-all" style={{ width: `${Math.min(100, Math.round((progress.usable_jobs / Math.max(1, progress.readiness_target)) * 100))}%` }} />
        </div>
        <p className="text-[11.5px] text-faint mt-2 flex items-start gap-1.5"><Info className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {progress.note}</p>
      </div>

      {/* Guarded auto-optimizer controls */}
      {optState && <OptimizerPanel data={optState} isOwner={isOwner} onChanged={reloadOptimizer} />}

      {/* Headline accuracy */}
      <Section icon={Gauge} title="Estimating accuracy" hint={`Man-hour model vs actual work hours across ${wmh.sample || 0} usable completed job(s).`} testId="calc-accuracy-summary">
        {wmh.sample === 0 ? (
          <EmptyState>No usable completed jobs yet. Accuracy appears once jobs finish with a matched quote and complete actuals.</EmptyState>
        ) : (
          <>
            {wmh.label !== "ok" && (
              <div data-testid="calc-accuracy-limited-note" className="mb-3 text-[11.5px] font-semibold text-warning bg-warning/10 rounded px-2.5 py-1.5 inline-block">
                Limited data ({wmh.sample} job{wmh.sample === 1 ? "" : "s"}) — read these as early signals, not conclusions.
              </div>
            )}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
              <Metric testId="calc-metric-bias" label="Hour bias" value={signedMh(wmh.mean_signed_error)} tone={biasTone}
                sub={wmh.bias_direction === "over" ? "tends to over-estimate" : wmh.bias_direction === "under" ? "tends to under-estimate" : "well balanced"} />
              <Metric testId="calc-metric-mae" label="Avg error (MAE)" value={wmh.mae == null ? "—" : `${wmh.mae} mh`} sub="lower is better" />
              <Metric testId="calc-metric-mape" label="Avg % off" value={pct(wmh.mean_abs_pct_error)} sub="of actual work hours" />
              <Metric testId="calc-metric-within" label="Within 15%" value={pct(wmh.within_15pct_rate)} sub={`within 1 mh: ${pct(wmh.within_1mh_rate)}`} />
            </div>
            {dollars && (
              <div data-testid="calc-accuracy-dollars" className="grid grid-cols-2 md:grid-cols-4 gap-2.5 mt-2.5">
                <Metric testId="calc-metric-dollar-var" label="Avg $ variance" value={dollars.mean_dollar_variance == null ? "—" : money(dollars.mean_dollar_variance)} sub={`billed − quoted · ${dollars.sample} job(s)`} />
                <Metric testId="calc-metric-inband" label="Landed in band" value={pct(dollars.in_band_rate)} sub={`${dollars.in_band_sample} job(s)`} />
              </div>
            )}
          </>
        )}
      </Section>

      {/* Trend */}
      {trends.length > 0 && (
        <Section icon={TrendingUp} title="Trend by month" hint="Model hour error over time (usable jobs)." testId="calc-accuracy-trends">
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="text-faint text-left border-b border-border">
                  <th className="py-1.5 font-semibold">Month</th>
                  <th className="py-1.5 font-semibold text-right">Jobs</th>
                  <th className="py-1.5 font-semibold text-right">Hour bias</th>
                  <th className="py-1.5 font-semibold text-right">Avg error</th>
                  {dollars && <th className="py-1.5 font-semibold text-right">Avg $ var</th>}
                </tr>
              </thead>
              <tbody>
                {trends.map((t) => (
                  <tr key={t.month} data-testid="calc-trend-row" className="border-b border-border/60">
                    <td className="py-1.5 text-primary font-semibold">{t.month}</td>
                    <td className="py-1.5 text-right tnum">{t.jobs}</td>
                    <td className="py-1.5 text-right tnum">{signedMh(t.mean_signed_error)}</td>
                    <td className="py-1.5 text-right tnum">{t.mae == null ? "—" : `${t.mae} mh`}</td>
                    {dollars && <td className="py-1.5 text-right tnum">{t.mean_dollar_variance == null ? "—" : money(t.mean_dollar_variance)}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {/* Sample coverage by factor */}
      <Section icon={Layers} title="Data coverage by factor" hint="How many usable jobs actually exercised each factor. No replacement values are proposed." testId="calc-accuracy-coverage">
        <div className="space-y-4">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-faint font-bold mb-1.5">Base volume rate</div>
            <div className="grid sm:grid-cols-2 gap-2">
              <CoverageChip testId="calc-cov-base" label="Overall (mh / 100 cu ft)" sample={coverage.base_rate.sample} coverLabel={coverage.base_rate.label} />
            </div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wide text-faint font-bold mb-1.5">Home size / package</div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {coverage.packages.map((c) => <CoverageChip key={c.key} testId={`calc-cov-pkg-${c.key}`} label={PKG_LABELS[c.key] || c.key} sample={c.sample} coverLabel={c.label} />)}
            </div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wide text-faint font-bold mb-1.5">Packing</div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2">
              {coverage.packing.map((c) => <CoverageChip key={c.tier} testId={`calc-cov-pack-${c.tier}`} label={PACK_LABELS[c.tier] || `Tier ${c.tier}`} sample={c.sample} coverLabel={c.label} />)}
            </div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wide text-faint font-bold mb-1.5">Access</div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {coverage.access.map((c) => <CoverageChip key={c.key} testId={`calc-cov-acc-${c.key}`} label={ACCESS_LABELS[c.key] || c.key} sample={c.sample} coverLabel={c.label} />)}
            </div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wide text-faint font-bold mb-1.5">Crew size &amp; specialty</div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {coverage.crew.map((c) => <CoverageChip key={c.key} testId={`calc-cov-crew-${c.key}`} label={CREW_LABELS[c.key] || c.key} sample={c.sample} coverLabel={c.label} />)}
              <CoverageChip testId="calc-cov-specialty" label="Specialty items" sample={coverage.specialty.sample} coverLabel={coverage.specialty.label} />
            </div>
          </div>
        </div>
      </Section>

      {/* Current parameters (read-only) */}
      <Section icon={SlidersHorizontal} title="Current estimating settings" hint="The values in use today. Tune them in the Auto-optimizer above — Set, Lock or Roll back, all reason-logged." testId="calc-accuracy-params">
        {cp.all_default && (
          <div data-testid="calc-params-default-note" className="mb-3 text-[11.5px] font-semibold text-ink-2 bg-surface-sunk rounded px-2.5 py-1.5 inline-block">
            All factors are on their baseline defaults (calibration {cp.calibration_version}). Nothing has been tuned.
          </div>
        )}
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2.5 text-[12.5px]">
          <div className="rounded-lg border border-border p-2.5"><div className="text-faint text-[11px]">Base rate</div><div className="tnum text-primary font-semibold">{cp.base_rate_mh_per_100cuft} mh / 100 cu ft</div></div>
          <div className="rounded-lg border border-border p-2.5"><div className="text-faint text-[11px]">Item multiplier</div><div className="tnum text-primary font-semibold">×{cp.item_multiplier}</div></div>
          <div className="rounded-lg border border-border p-2.5"><div className="text-faint text-[11px]">Package hours</div><div className="tnum text-primary font-semibold">{Object.entries(cp.package_hours || {}).map(([k, v]) => `${PKG_LABELS[k] || k}: ${v}h`).join(" · ")}</div></div>
          <div className="rounded-lg border border-border p-2.5"><div className="text-faint text-[11px]">Packing multipliers</div><div className="tnum text-primary font-semibold">{(cp.packing_multipliers || []).map((v, i) => `${i}:×${v}`).join("  ")}</div></div>
          <div className="rounded-lg border border-border p-2.5 sm:col-span-2"><div className="text-faint text-[11px]">Access man-hours</div><div className="tnum text-primary font-semibold text-[11.5px]">{Object.entries(cp.access_per_mh || {}).map(([k, v]) => `${ACCESS_LABELS[k] || k}: ${v}`).join(" · ")}</div></div>
          <div className="rounded-lg border border-border p-2.5"><div className="text-faint text-[11px]">Crew efficiency</div><div className="tnum text-primary font-semibold">{Object.entries(cp.crew_efficiency || {}).map(([k, v]) => `${k}:×${v}`).join(" ")}</div></div>
          <div className="rounded-lg border border-border p-2.5 sm:col-span-2"><div className="text-faint text-[11px]">Scheduling</div><div className="tnum text-primary font-semibold">target {cp.scheduling?.targetHoursOnSite}h · max {cp.scheduling?.maxHoursOnSite}h/day · max {cp.scheduling?.maxCrewPerDay} crew</div></div>
        </div>
      </Section>

      {/* Review queue */}
      <Section icon={ClipboardList} title={`Needs review (${queue.length})`} hint="Jobs the estimator can't learn from cleanly yet. Open the job's Outcome tab to fix a fact, decide a survey miss, or exclude it." testId="calc-accuracy-queue">
        {queue.length === 0 ? (
          <EmptyState>Nothing to review — all measured jobs have clean, matched data.</EmptyState>
        ) : (
          <div className="space-y-2">
            {queue.map((r) => (
              <div key={r.job_key} data-testid="calc-queue-row" className="rounded-lg border border-border p-3 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-[13px] font-semibold text-primary truncate">{r.job_name}</div>
                  <div className="text-[11px] text-faint">{r.job_date ? fmtDate(r.job_date) : "No date"}</div>
                  <div className="flex flex-wrap gap-1.5 mt-1.5">
                    {r.reasons.map((rs) => (
                      <span key={rs} className="text-[10.5px] font-bold px-1.5 py-0.5 rounded bg-warning/10 text-warning">{REASON_LABELS[rs] || rs}</span>
                    ))}
                    {r.excluded && <span className="text-[10.5px] font-bold px-1.5 py-0.5 rounded bg-surface-sunk text-faint">Excluded</span>}
                  </div>
                </div>
                {r.linkable ? (
                  <Link to={`/projects/${r.project_id}?tab=outcome`} data-testid="calc-queue-open-btn"
                    className="shrink-0 inline-flex items-center gap-1 text-[12px] font-semibold text-accent-ink hover:underline">
                    Outcome <ArrowRight className="w-3.5 h-3.5" />
                  </Link>
                ) : (
                  <span className="shrink-0 text-[11px] text-faint">No project link</span>
                )}
              </div>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}
