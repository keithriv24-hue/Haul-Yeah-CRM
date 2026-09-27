import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  RefreshCw, TriangleAlert, CircleCheck, CircleHelp, History, ShieldQuestion, Ban, ScrollText,
  Pencil, Crosshair, ClipboardList,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  jobOutcomeApi, jobOutcomeHistoryApi, excludeOutcomeApi, surveyMissDecisionApi,
  correctOutcomeApi, repointOutcomeScopeApi, outcomeCandidateScopesApi, apiErrorMessage,
} from "@/lib/api";

const DQ_TONE = {
  complete: "bg-success/10 text-success border-success/30",
  incomplete: "bg-warning/10 text-warning border-warning/30",
  unmatched: "bg-destructive/10 text-destructive border-destructive/30",
};
const DQ_LABEL = { complete: "Complete", incomplete: "Incomplete for learning", unmatched: "Unmatched" };
const SRC_LABEL = { taps: "from Crew Lead taps", gps: "from GPS (lower confidence)", clock_only: "clock only — no on-site window", estimated: "estimated from miles" };

// The four correctable facts. final_total is owner-only (Quality never sees revenue).
const CORRECT_FIELDS = [
  { key: "final_total", label: "Final billed amount", ownerOnly: true, kind: "money",
    help: "What the customer actually paid in total. Owner only — never a Square deposit or the original quote." },
  { key: "actual_mileage", label: "Actual miles driven (observed)", kind: "number",
    help: "Real miles driven that day. This is NOT the quoted route estimate." },
  { key: "quoted_crew", label: "Quoted crew — estimate restated", kind: "number",
    help: "Restates the crew estimate after the fact for accuracy tracking. The original quote and amount stay untouched." },
  { key: "as_found_note", label: "As-found note", kind: "text",
    help: "Free-text note about how the job was actually found. Does not change the structured scope selections." },
];

const h = (v) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(2)}h`);
const money = (v) => (v === null || v === undefined ? "—" : `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`);
const when = (iso) => (iso ? String(iso).slice(0, 16).replace("T", " ") : "—");

const Row = ({ label, quoted, actual, testId }) => (
  <div data-testid={testId} className="grid grid-cols-3 gap-2 py-1.5 border-b border-border last:border-0 text-sm">
    <span className="text-faint">{label}</span>
    <span className="text-right font-mono text-ink-2">{quoted}</span>
    <span className="text-right font-mono font-semibold text-primary">{actual}</span>
  </div>
);

export const JobOutcomePanel = ({ jobKey, role = "owner", initial = null }) => {
  const [o, setO] = useState(initial);
  const [loading, setLoading] = useState(!initial);
  const [busy, setBusy] = useState(false);
  const [histOpen, setHistOpen] = useState(false);
  const [history, setHistory] = useState([]);
  const [exclOpen, setExclOpen] = useState(false);
  const [exclReason, setExclReason] = useState("");
  // correction dialog
  const [corrOpen, setCorrOpen] = useState(false);
  const [corrField, setCorrField] = useState("");
  const [corrValue, setCorrValue] = useState("");
  const [corrReason, setCorrReason] = useState("");
  // repoint dialog
  const [rpOpen, setRpOpen] = useState(false);
  const [rpScopes, setRpScopes] = useState(null);
  const [rpPick, setRpPick] = useState("");
  const [rpReason, setRpReason] = useState("");

  const isOwner = role === "owner";
  const fields = CORRECT_FIELDS.filter((fld) => !fld.ownerOnly || isOwner);

  const load = useCallback((rebuild = false) => {
    setLoading(true);
    jobOutcomeApi(jobKey, rebuild)
      .then((d) => setO(d))
      .catch((e) => toast.error(apiErrorMessage(e)))
      .finally(() => setLoading(false));
  }, [jobKey]);

  useEffect(() => { if (!initial) load(false); }, [load, initial]);

  const refreshHistory = useCallback(async () => {
    if (!histOpen) return;
    try { setHistory(await jobOutcomeHistoryApi(jobKey)); } catch { /* history is best-effort */ }
  }, [histOpen, jobKey]);

  if (loading && !o) return <p className="text-sm text-faint py-6 text-center" data-testid="outcome-loading">Building the outcome…</p>;
  if (!o) return <p className="text-sm text-faint py-6 text-center">No outcome yet.</p>;

  const q = o.quote || {};
  const a = o.actuals || {};
  const err = o.errors || {};
  const ft = o.final_total || {};
  const excluded = o.exclusion?.excluded;
  const missFlags = o.survey_miss?.flags || [];
  const decisions = o.survey_miss?.decisions || {};
  const corrections = o.corrections || [];
  const corrMap = o.corrections_map || {};

  const openHistory = async () => {
    setHistOpen(true);
    try { setHistory(await jobOutcomeHistoryApi(jobKey)); } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const decideMiss = async (key, decision) => {
    setBusy(true);
    try { setO(await surveyMissDecisionApi(jobKey, key, decision)); toast.success(`Marked ${decision}.`); refreshHistory(); }
    catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy(false);
  };

  const submitExclude = async () => {
    if (exclReason.trim().length < 5) { toast.error("Add a reason (5+ characters)."); return; }
    setBusy(true);
    try { setO(await excludeOutcomeApi(jobKey, !excluded, exclReason.trim())); setExclOpen(false); setExclReason(""); toast.success("Saved."); refreshHistory(); }
    catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy(false);
  };

  const currentValueFor = (key) => {
    if (key === "final_total") return ft.redacted ? "hidden" : money(ft.value);
    if (key === "actual_mileage") return corrMap.actual_mileage != null ? `${corrMap.actual_mileage} mi` : "not recorded";
    if (key === "quoted_crew") return q.crew_rec != null ? String(q.crew_rec) : "—";
    if (key === "as_found_note") return corrMap.as_found_note || "—";
    return "—";
  };

  const submitCorrection = async () => {
    const fld = fields.find((x) => x.key === corrField);
    if (!fld) { toast.error("Pick a field to correct."); return; }
    if (corrReason.trim().length < 5) { toast.error("Add a reason (5+ characters)."); return; }
    let value = corrValue;
    if (fld.kind === "money" || fld.kind === "number") {
      if (String(corrValue).trim() === "" || Number.isNaN(Number(corrValue))) { toast.error("Enter a number."); return; }
      value = Number(corrValue);
    } else if (!String(corrValue).trim()) { toast.error("Enter a value."); return; }
    setBusy(true);
    try {
      const res = await correctOutcomeApi(jobKey, corrField, value, corrReason.trim());
      setO(res);
      setCorrOpen(false); setCorrField(""); setCorrValue(""); setCorrReason("");
      toast.success("Correction saved — recorded as a new version.");
      refreshHistory();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy(false);
  };

  const openRepoint = async () => {
    setRpOpen(true); setRpScopes(null); setRpPick(""); setRpReason("");
    try {
      const res = await outcomeCandidateScopesApi(jobKey);
      setRpScopes(res.scopes || []);
    } catch (e) { toast.error(apiErrorMessage(e)); setRpScopes([]); }
  };

  const submitRepoint = async () => {
    if (!rpPick) { toast.error("Pick a saved quote."); return; }
    if (rpReason.trim().length < 5) { toast.error("Add a reason (5+ characters)."); return; }
    setBusy(true);
    try {
      setO(await repointOutcomeScopeApi(jobKey, rpPick, rpReason.trim()));
      setRpOpen(false);
      toast.success("Re-pointed to the selected quote.");
      refreshHistory();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy(false);
  };

  return (
    <div data-testid="job-outcome-panel" className="space-y-4 mt-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge data-testid="outcome-data-quality" variant="outline" className={`text-[10px] gap-1 ${DQ_TONE[o.data_quality] || DQ_TONE.unmatched}`}>
          {o.data_quality === "complete" ? <CircleCheck className="w-3 h-3" /> : <TriangleAlert className="w-3 h-3" />}
          {DQ_LABEL[o.data_quality] || o.data_quality}
        </Badge>
        {o.learning_eligible
          ? <Badge variant="outline" className="text-[10px] bg-success/10 text-success border-success/30">Learning-eligible</Badge>
          : <Badge variant="outline" className="text-[10px] bg-surface-sunk text-faint border-border">Not used for learning</Badge>}
        <Badge data-testid="outcome-version" variant="outline" className="text-[10px] bg-surface-sunk text-ink-2 border-border">v{o.version}</Badge>
        <span className="ml-auto flex items-center gap-1.5">
          <Button data-testid="outcome-history-btn" size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={openHistory}>
            <History className="w-3.5 h-3.5" /> History
          </Button>
          <Button data-testid="outcome-rebuild-btn" size="sm" variant="outline" className="h-7 text-xs gap-1" disabled={busy} onClick={() => load(true)}>
            <RefreshCw className="w-3.5 h-3.5" /> Rebuild
          </Button>
        </span>
      </div>

      {excluded && (
        <div data-testid="outcome-excluded-note" className="rounded-md border border-warning/30 bg-warning/5 p-2.5 text-xs text-warning flex items-start gap-1.5">
          <Ban className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          <span>Excluded from learning{o.exclusion?.reasons?.length ? ` — ${o.exclusion.reasons.join(", ")}` : ""}.
            {o.exclusion?.reason ? ` Note: ${o.exclusion.reason}` : ""}</span>
        </div>
      )}

      <div className="surface p-3">
        <div className="grid grid-cols-3 gap-2 text-[10px] font-bold uppercase tracking-wide text-faint pb-1.5 border-b border-border-strong">
          <span>Measure</span><span className="text-right">Quoted</span><span className="text-right">Actual</span>
        </div>
        <Row testId="outcome-row-schedmh" label="Model man-hours" quoted={h(q.sched_mh)} actual={h(a.work_man_hours)} />
        <Row testId="outcome-row-onsite" label="On-site man-hours" quoted="—" actual={h(a.actual_man_hours)} />
        <Row testId="outcome-row-onsitehrs" label="On-site hours (elapsed)" quoted="—" actual={h(a.on_site_hours)} />
        <Row testId="outcome-row-crew" label="Crew" quoted={q.crew_rec ?? "—"} actual={a.actual_crew_count ?? "—"} />
        <Row testId="outcome-row-amount" label="Amount / final billed" quoted={money(q.finalTotal ?? q.amount)} actual={ft.redacted ? "hidden" : money(ft.value)} />
      </div>

      <div className="flex flex-wrap gap-1.5 text-[10px]">
        <Badge data-testid="outcome-window-source" variant="outline" className="bg-surface-sunk text-ink-2 border-border">
          Window: {SRC_LABEL[a.window_source] || a.window_source || "—"}
        </Badge>
        {a.drive_source && <Badge variant="outline" className="bg-surface-sunk text-ink-2 border-border">Drive: {SRC_LABEL[a.drive_source] || a.drive_source}</Badge>}
        <Badge variant="outline" className="bg-surface-sunk text-ink-2 border-border">Total day: {h(a.total_day_hours)} (incl. travel)</Badge>
        <Badge variant="outline" className="bg-surface-sunk text-ink-2 border-border">Quote match: {o.quote_match?.rule || "—"}</Badge>
      </div>

      {a.incomplete_reasons?.length > 0 && (
        <p data-testid="outcome-incomplete-note" className="text-xs text-warning flex items-start gap-1.5">
          <CircleHelp className="w-3.5 h-3.5 mt-0.5 shrink-0" /> Missing for a defensible outcome: {a.incomplete_reasons.join(", ")}.
        </p>
      )}
      {ft.source === "missing" && (
        <p data-testid="outcome-final-missing" className="text-xs text-faint">Final billed amount not recorded yet{ft.note === "airtable_unavailable" ? " (needs the production Airtable connection)" : ""}.{isOwner ? " Use “Correct a fact” to enter it." : ""}</p>
      )}

      {err.available && (
        <div className="surface p-3 text-xs space-y-1" data-testid="outcome-errors">
          <p className="font-bold text-faint uppercase tracking-wide text-[10px] mb-1">Estimating accuracy (this job)</p>
          {err.model_work_mh_error !== undefined && (
            <p>Model vs actual work hours: <strong className={err.model_work_mh_error < 0 ? "text-destructive" : "text-primary"}>
              {err.model_work_mh_error > 0 ? "+" : ""}{err.model_work_mh_error}h</strong> {err.model_work_mh_error < 0 ? "(under-estimated)" : "(over-estimated)"}</p>
          )}
          {err.dollar_variance !== undefined && <p>Dollar variance (final − quote): <strong>{money(err.dollar_variance)}</strong></p>}
          {err.in_band !== undefined && <p>Final landed {err.in_band ? "inside" : "outside"} the quoted range.</p>}
        </div>
      )}

      {missFlags.length > 0 && (
        <div className="surface p-3 space-y-2" data-testid="outcome-survey-misses">
          <p className="font-bold text-faint uppercase tracking-wide text-[10px] flex items-center gap-1"><ShieldQuestion className="w-3.5 h-3.5" /> Possible survey misses</p>
          {missFlags.map((m) => {
            const d = decisions[m.key];
            return (
              <div key={m.key} data-testid={`survey-miss-${m.key}`} className="rounded-md border border-border p-2 text-xs">
                <p className="text-ink-2">{m.detail}</p>
                {d ? (
                  <p className="text-[11px] text-faint mt-1 italic">{d.decision === "confirmed" ? "Confirmed" : "Dismissed"} by {d.by}</p>
                ) : (
                  <div className="flex gap-1.5 mt-1.5">
                    <Button data-testid={`survey-miss-confirm-${m.key}`} size="sm" variant="outline" className="h-6 text-[11px]" disabled={busy} onClick={() => decideMiss(m.key, "confirmed")}>Confirm miss</Button>
                    <Button data-testid={`survey-miss-dismiss-${m.key}`} size="sm" variant="outline" className="h-6 text-[11px]" disabled={busy} onClick={() => decideMiss(m.key, "dismissed")}>Dismiss</Button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {corrections.length > 0 && (
        <div className="surface p-3 space-y-1.5" data-testid="outcome-corrections-log">
          <p className="font-bold text-faint uppercase tracking-wide text-[10px] flex items-center gap-1"><ClipboardList className="w-3.5 h-3.5" /> Corrections log</p>
          {corrections.map((c, i) => (
            <div key={i} data-testid="outcome-correction-row" className="text-xs border-b border-border last:border-0 pb-1.5 last:pb-0">
              <p className="text-ink-2"><strong>{c.field}</strong>: <span className="line-through text-faint">{c.before ?? "—"}</span> → <span className="font-medium text-primary">{String(c.value)}</span></p>
              <p className="text-[11px] text-faint italic">{c.reason} · {c.by} · {when(c.at)}</p>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-1.5">
        <Button data-testid="outcome-correct-btn" size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => { setCorrField(fields[0]?.key || ""); setCorrValue(""); setCorrReason(""); setCorrOpen(true); }}>
          <Pencil className="w-3.5 h-3.5" /> Correct a fact
        </Button>
        <Button data-testid="outcome-repoint-btn" size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={openRepoint}>
          <Crosshair className="w-3.5 h-3.5" /> Re-point quote
        </Button>
        <Button data-testid="outcome-exclude-btn" size="sm" variant="ghost" className="h-7 text-xs text-faint gap-1" onClick={() => { setExclReason(""); setExclOpen(true); }}>
          <Ban className="w-3.5 h-3.5" /> {excluded ? "Re-include in learning" : "Exclude from learning"}
        </Button>
      </div>

      {/* HISTORY */}
      <Dialog open={histOpen} onOpenChange={setHistOpen}>
        <DialogContent data-testid="outcome-history-dialog" className="max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><ScrollText className="w-4 h-4" /> Outcome history</DialogTitle>
            <DialogDescription>Every material change is an immutable version — nothing is overwritten.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            {history.length === 0 ? <p className="text-sm text-faint">No versions yet.</p> : history.map((v) => (
              <div key={v.version} data-testid={`outcome-version-${v.version}`} className="rounded-md border border-border p-2.5 text-xs">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px] bg-primary/10 text-primary border-primary/25">v{v.version}</Badge>
                  <span className="text-faint">{v.source}{v.actor ? ` · ${v.actor}` : ""}</span>
                  <span className="text-faint ml-auto">{when(v.at)}</span>
                </div>
                {v.reason && <p className="text-ink-2 mt-1 italic">{v.reason}</p>}
                {v.changed_fields && Object.keys(v.changed_fields).length > 0 && (
                  <p className="text-faint mt-1">Changed: {Object.keys(v.changed_fields).join(", ")}</p>
                )}
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      {/* EXCLUDE */}
      <Dialog open={exclOpen} onOpenChange={setExclOpen}>
        <DialogContent data-testid="outcome-exclude-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">{excluded ? "Re-include this job" : "Exclude this job from learning"}</DialogTitle>
            <DialogDescription>This only affects whether the job feeds later learning. It never changes pricing, pay, or the record itself.</DialogDescription>
          </DialogHeader>
          <Textarea data-testid="outcome-exclude-reason" value={exclReason} onChange={(e) => setExclReason(e.target.value)} placeholder="Why? (e.g. one-off charity move — not representative)" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setExclOpen(false)}>Cancel</Button>
            <Button data-testid="outcome-exclude-submit" disabled={busy} onClick={submitExclude} className="bg-primary hover:bg-[#152238]">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* CORRECT A FACT */}
      <Dialog open={corrOpen} onOpenChange={setCorrOpen}>
        <DialogContent data-testid="outcome-correct-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">Correct a fact</DialogTitle>
            <DialogDescription>Supplement or fix a fact with a required reason. The original value is preserved and a new version is recorded — nothing is overwritten in place.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Field</Label>
              <Select value={corrField} onValueChange={(v) => { setCorrField(v); setCorrValue(""); }}>
                <SelectTrigger data-testid="outcome-correct-field" className="mt-1"><SelectValue placeholder="Choose a field" /></SelectTrigger>
                <SelectContent>
                  {fields.map((fld) => (
                    <SelectItem key={fld.key} value={fld.key} data-testid={`outcome-correct-field-${fld.key}`}>{fld.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {corrField && (
              <>
                <p className="text-[11px] text-faint">{fields.find((x) => x.key === corrField)?.help}</p>
                <div className="rounded-md bg-surface-sunk border border-border p-2 text-xs">
                  <span className="text-faint">Current: </span><span className="font-mono text-ink-2" data-testid="outcome-correct-current">{currentValueFor(corrField)}</span>
                </div>
                <div>
                  <Label className="text-xs">Proposed value</Label>
                  {corrField === "as_found_note" ? (
                    <Textarea data-testid="outcome-correct-value" className="mt-1" value={corrValue} onChange={(e) => setCorrValue(e.target.value)} placeholder="What was actually found on site…" />
                  ) : (
                    <Input data-testid="outcome-correct-value" className="mt-1" type="number" inputMode="decimal" value={corrValue} onChange={(e) => setCorrValue(e.target.value)}
                      placeholder={corrField === "final_total" ? "e.g. 2150" : corrField === "actual_mileage" ? "observed miles" : "crew count"} />
                  )}
                </div>
                <div>
                  <Label className="text-xs">Reason (required)</Label>
                  <Textarea data-testid="outcome-correct-reason" className="mt-1" value={corrReason} onChange={(e) => setCorrReason(e.target.value)} placeholder="Why this correction? (5+ characters)" />
                </div>
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCorrOpen(false)}>Cancel</Button>
            <Button data-testid="outcome-correct-submit" disabled={busy || !corrField} onClick={submitCorrection} className="bg-primary hover:bg-[#152238]">Save correction</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* RE-POINT QUOTE */}
      <Dialog open={rpOpen} onOpenChange={setRpOpen}>
        <DialogContent data-testid="outcome-repoint-dialog" className="max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">Re-point the quote</DialogTitle>
            <DialogDescription>Choose which saved quote this job is measured against. The original quote-time snapshots stay in history — this only changes what the outcome compares to going forward.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            {rpScopes === null && <p className="text-sm text-faint">Loading saved quotes…</p>}
            {rpScopes && rpScopes.length === 0 && <p className="text-sm text-faint" data-testid="outcome-repoint-empty">No saved quotes are linked to this job's lead.</p>}
            {rpScopes && rpScopes.map((s) => (
              <button
                type="button"
                key={s.id}
                data-testid={`outcome-repoint-scope-${s.id}`}
                onClick={() => setRpPick(s.id)}
                className={`w-full text-left rounded-md border p-2.5 text-xs transition-colors ${rpPick === s.id ? "border-primary bg-primary/5" : "border-border hover:border-border-strong"}`}
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-primary">{s.label || (s.mode ? `${s.mode} quote` : "Saved quote")}</span>
                  {s.is_active && <Badge variant="outline" className="text-[10px] bg-success/10 text-success border-success/30">current</Badge>}
                  {s.amount != null && <span className="ml-auto font-mono text-ink-2">{money(s.amount)}</span>}
                </div>
                <p className="text-faint mt-0.5">{s.created_by || "—"} · {when(s.created_at)} · crew {s.crew_rec ?? "—"}{s.survey_complete ? " · survey ✓" : ""}</p>
              </button>
            ))}
            <div>
              <Label className="text-xs">Reason (required)</Label>
              <Textarea data-testid="outcome-repoint-reason" className="mt-1" value={rpReason} onChange={(e) => setRpReason(e.target.value)} placeholder="Why re-point to this quote? (5+ characters)" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRpOpen(false)}>Cancel</Button>
            <Button data-testid="outcome-repoint-submit" disabled={busy || !rpPick} onClick={submitRepoint} className="bg-primary hover:bg-[#152238]">Re-point</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
