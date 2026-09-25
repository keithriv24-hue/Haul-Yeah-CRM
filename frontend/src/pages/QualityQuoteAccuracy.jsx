import React, { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Gauge, ChevronDown, ChevronRight, MessageSquarePlus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, EmptyState, LoadingRows } from "@/components/Bits";
import { qualityQuoteAccuracyApi, qualityFeedbackListApi, qualityFeedbackCreateApi, getQuoteBreakdownApi, apiErrorMessage } from "@/lib/api";
import { money, hrs, fmtDate } from "@/lib/quality";

const prettyKey = (k) =>
  k.replace(/([A-Z])/g, " $1").replace(/^./, (c) => c.toUpperCase()).trim();
const MONEYISH = /(quote|total|fee|deposit|subtotal|band|dist|mileage|stairs|carry|stop|materials|rate)/i;
const isMoney = (k, v) => typeof v === "number" && MONEYISH.test(k);

const Metric = ({ label, value, testId, tone = "" }) => (
  <div data-testid={testId} className="surface p-3 rounded-lg border border-border">
    <div className="text-[11px] uppercase tracking-wide text-faint">{label}</div>
    <div className={`mt-1 font-display text-[20px] font-extrabold ${tone || "text-primary"}`}>{value}</div>
  </div>
);

const FeedbackForm = ({ row, onDone }) => {
  const [off, setOff] = useState("");
  const [todo, setTodo] = useState("");
  const [saving, setSaving] = useState(false);
  const submit = async () => {
    if (!off.trim()) {
      toast.error("Say what was off first.");
      return;
    }
    setSaving(true);
    try {
      await qualityFeedbackCreateApi({
        job_id: row.id,
        job_name: row.name,
        rep_user_id: row.quoted_by_id || null,
        rep_name: row.quoted_by || null,
        what_was_off: off.trim(),
        what_to_do: todo.trim(),
      });
      toast.success(row.quoted_by_id ? `Feedback sent to ${row.quoted_by}.` : "Feedback logged.");
      setOff("");
      setTodo("");
      onDone && onDone();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setSaving(false);
  };
  return (
    <div className="rounded-lg border border-border bg-surface-sunk p-3">
      <div className="text-[12px] font-bold text-ink-2 mb-2">Give feedback to {row.quoted_by || "the rep"}</div>
      <div className="space-y-2">
        <div>
          <Label className="text-[12px]">What was off</Label>
          <Textarea data-testid="feedback-off-input" rows={2} value={off} onChange={(e) => setOff(e.target.value)} />
        </div>
        <div>
          <Label className="text-[12px]">What to do differently</Label>
          <Textarea data-testid="feedback-todo-input" rows={2} value={todo} onChange={(e) => setTodo(e.target.value)} />
        </div>
        <Button data-testid="feedback-submit-btn" onClick={submit} disabled={saving} className="gap-1.5 bg-accent hover:bg-accent-press">
          <MessageSquarePlus className="w-4 h-4" /> {saving ? "Saving…" : "Send feedback"}
        </Button>
      </div>
    </div>
  );
};

const Breakdown = ({ leadId }) => {
  const [data, setData] = useState(null);
  const [state, setState] = useState("loading");
  useEffect(() => {
    let live = true;
    if (!leadId) {
      setState("none");
      return;
    }
    getQuoteBreakdownApi(leadId)
      .then((d) => {
        if (!live) return;
        setData(d.breakdown);
        setState(d.breakdown ? "ok" : "none");
      })
      .catch(() => live && setState("error"));
    return () => {
      live = false;
    };
  }, [leadId]);
  if (state === "loading") return <div className="text-[12.5px] text-faint">Loading quote…</div>;
  if (state !== "ok" || !data) return <div className="text-[12.5px] text-faint">No stored quote breakdown for this job.</div>;
  const entries = Object.entries(data).filter(([, v]) => typeof v !== "object");
  return (
    <dl data-testid="quote-breakdown" className="grid grid-cols-2 gap-x-4 gap-y-1 text-[12.5px]">
      {entries.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-2 border-b border-border/60 py-0.5">
          <dt className="text-faint truncate">{prettyKey(k)}</dt>
          <dd className="font-semibold text-ink tnum">{isMoney(k, v) ? money(v) : String(v)}</dd>
        </div>
      ))}
    </dl>
  );
};

const hoursTone = (flag) => (flag === "red" ? "text-red-600" : flag === "amber" ? "text-amber-600" : "text-ink");

export default function QualityQuoteAccuracy() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [rep, setRep] = useState("all");
  const [expanded, setExpanded] = useState(null);
  const [feedback, setFeedback] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (from) params.from = from;
      if (to) params.to = to;
      if (rep !== "all") params.rep = rep;
      const d = await qualityQuoteAccuracyApi(params);
      setData(d);
    } catch (e) {
      setError(apiErrorMessage(e));
    }
    setLoading(false);
  }, [from, to, rep]);

  const loadFeedback = useCallback(async () => {
    try {
      setFeedback(await qualityFeedbackListApi());
    } catch {}
  }, []);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    loadFeedback();
  }, [loadFeedback]);

  const rows = data?.rows || [];
  const summary = data?.summary || {};
  const reps = data?.reps || [];

  return (
    <div data-testid="quality-quote-accuracy-page">
      <PageTitle
        title="Quote accuracy"
        subtitle="Quoted vs. what actually happened — hours and dollars."
        action={
          <Button data-testid="qa-refresh-btn" variant="outline" onClick={load} className="gap-1.5">
            <RefreshCw className="w-4 h-4" /> Refresh
          </Button>
        }
      />
      <InstructionBanner>How close the quote was to reality. Amber = off by more than 0.5h, red = off by more than 1h or over the on-site cap.</InstructionBanner>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div>
          <Label className="text-[12px]">From</Label>
          <Input type="date" data-testid="qa-from-input" value={from} onChange={(e) => setFrom(e.target.value)} className="h-9 w-[150px]" />
        </div>
        <div>
          <Label className="text-[12px]">To</Label>
          <Input type="date" data-testid="qa-to-input" value={to} onChange={(e) => setTo(e.target.value)} className="h-9 w-[150px]" />
        </div>
        <div>
          <Label className="text-[12px]">Rep</Label>
          <Select value={rep} onValueChange={setRep}>
            <SelectTrigger data-testid="qa-rep-select" className="h-9 w-[170px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All reps</SelectItem>
              {reps.map((r) => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      {loading ? (
        <LoadingRows />
      ) : error ? (
        <EmptyState>{error}</EmptyState>
      ) : (
        <>
          <div className="mb-4 grid grid-cols-3 gap-3">
            <Metric testId="qa-jobs-metric" label="Jobs" value={summary.jobs ?? 0} />
            <Metric
              testId="qa-hours-metric"
              label="Mean hours variance"
              value={summary.mean_hours_variance == null ? "—" : `${summary.mean_hours_variance > 0 ? "+" : ""}${summary.mean_hours_variance}h`}
            />
            <Metric
              testId="qa-dollar-metric"
              label="Mean dollar variance"
              value={summary.mean_dollar_variance == null ? "—" : money(summary.mean_dollar_variance)}
            />
          </div>

          {(summary.per_rep || []).length > 0 && (
            <div data-testid="qa-per-rep" className="mb-5 surface p-3 rounded-lg border border-border">
              <div className="text-[12px] font-bold text-ink-2 mb-2">Per rep</div>
              <div className="space-y-1">
                {summary.per_rep.map((r) => (
                  <div key={r.rep} className="flex flex-wrap items-center justify-between gap-2 text-[12.5px] border-b border-border/50 py-1 last:border-0">
                    <span className="font-semibold text-ink">{r.rep}</span>
                    <span className="text-faint">
                      {r.jobs} job{r.jobs !== 1 ? "s" : ""} · hours {r.mean_hours_variance == null ? "—" : `${r.mean_hours_variance > 0 ? "+" : ""}${r.mean_hours_variance}h`} · ${" "}
                      {r.mean_dollar_variance == null ? "—" : money(r.mean_dollar_variance)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {rows.length === 0 ? (
            <EmptyState>No completed jobs in this range yet.</EmptyState>
          ) : (
            <div className="space-y-2">
              {rows.map((r) => {
                const open = expanded === r.id;
                return (
                  <div key={r.id} data-testid="qa-row" className={`surface-interactive ${r.over_max_hours ? "border-red-300" : ""}`}>
                    <button
                      onClick={() => setExpanded(open ? null : r.id)}
                      data-testid="qa-row-toggle"
                      className="press w-full text-left p-3.5 flex flex-wrap items-center gap-x-4 gap-y-1.5"
                    >
                      {open ? <ChevronDown className="w-4 h-4 text-faint shrink-0" /> : <ChevronRight className="w-4 h-4 text-faint shrink-0" />}
                      <div className="min-w-[160px] flex-1">
                        <div className="font-display text-[15px] font-bold text-primary truncate">{r.name}</div>
                        <div className="text-[12px] text-faint">{fmtDate(r.move_date)} · {r.quoted_by || "—"}</div>
                      </div>
                      <div className="text-right w-[110px]">
                        <div className="text-[11px] text-faint">Quoted / final</div>
                        <div className="tnum text-[13px] font-semibold text-ink">{money(r.quoted_total)} / {money(r.final_total)}</div>
                      </div>
                      <div className="text-right w-[90px]">
                        <div className="text-[11px] text-faint">$ variance</div>
                        <div className="tnum text-[13px] font-semibold text-ink">{r.dollar_variance == null ? "—" : money(r.dollar_variance)}</div>
                      </div>
                      <div className="text-right w-[110px]">
                        <div className="text-[11px] text-faint">Est / actual</div>
                        <div className="tnum text-[13px] font-semibold text-ink">{hrs(r.estimated_hours)} / {hrs(r.actual_hours)}</div>
                      </div>
                      <div className="text-right w-[90px]">
                        <div className="text-[11px] text-faint">Hrs var</div>
                        <div className={`tnum text-[13px] font-bold ${hoursTone(r.hours_flag)}`}>
                          {r.hours_variance == null ? "—" : `${r.hours_variance > 0 ? "+" : ""}${r.hours_variance}h`}
                        </div>
                      </div>
                      {r.over_max_hours && (
                        <span data-testid="qa-over-max-tag" className="rounded-md bg-red-600 px-2 py-1 text-[10.5px] font-bold uppercase text-white">
                          Over cap
                        </span>
                      )}
                    </button>
                    {open && (
                      <div data-testid="qa-row-detail" className="border-t border-border p-4 grid gap-4 md:grid-cols-2">
                        <div>
                          <div className="text-[12px] font-bold text-ink-2 mb-2 flex items-center gap-1.5"><Gauge className="w-4 h-4" /> The quote</div>
                          <Breakdown leadId={r.lead_id} />
                        </div>
                        <div className="space-y-3">
                          <div>
                            <div className="text-[12px] font-bold text-ink-2 mb-2">What actually happened</div>
                            <div className="grid grid-cols-2 gap-2 text-[12.5px]">
                              <div className="rounded-lg bg-surface-sunk p-2"><div className="text-faint text-[11px]">Final total</div><div className="tnum font-bold text-ink">{money(r.final_total)}</div></div>
                              <div className="rounded-lg bg-surface-sunk p-2"><div className="text-faint text-[11px]">Actual hours</div><div className={`tnum font-bold ${hoursTone(r.hours_flag)}`}>{hrs(r.actual_hours)}</div></div>
                              <div className="rounded-lg bg-surface-sunk p-2"><div className="text-faint text-[11px]">Surveyor</div><div className="font-semibold text-ink truncate">{r.surveyor || "—"}</div></div>
                              <div className="rounded-lg bg-surface-sunk p-2"><div className="text-faint text-[11px]">Variance explained</div><div className="font-semibold text-ink truncate">{r.variance_explained || "—"}</div></div>
                            </div>
                          </div>
                          <FeedbackForm row={r} onDone={loadFeedback} />
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          <div className="mt-6">
            <div className="text-[13px] font-bold text-ink-2 mb-2">Feedback log</div>
            {feedback.length === 0 ? (
              <EmptyState>No feedback logged yet.</EmptyState>
            ) : (
              <div className="space-y-2" data-testid="feedback-log">
                {feedback.map((fb) => (
                  <div key={fb.nc_id || fb.date + fb.what_was_off} data-testid="feedback-log-row" className="surface p-3 rounded-lg border border-border">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-[12px] text-faint">
                      <span className="font-semibold text-ink">{fb.job_name || "A job"}{fb.rep_name ? ` → ${fb.rep_name}` : ""}</span>
                      <span>{fmtDate(fb.date)}</span>
                    </div>
                    <div className="mt-1 text-[13px] text-ink"><span className="font-semibold">Off:</span> {fb.what_was_off}</div>
                    {fb.what_to_do && <div className="text-[13px] text-ink-2"><span className="font-semibold">Do:</span> {fb.what_to_do}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
