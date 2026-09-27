import React, { useState, useCallback } from "react";
import { toast } from "sonner";
import { Cpu, Play, Pause, Lock, Unlock, Pencil, History, RotateCcw, Power, ChevronDown, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/Bits";
import { fmtDate } from "@/lib/quality";
import {
  optimizerRunApi, optimizerPauseApi, optimizerLockApi, optimizerManualSetApi,
  optimizerRollbackApi, optimizerActivateApi, optimizerHistoryApi, optimizerRunsApi, apiErrorMessage,
} from "@/lib/api";

const num = (v) => (v == null || Number.isNaN(Number(v)) ? "—" : Number(v));
const fmtHrs = (v) => (v == null ? "—" : Number(v).toFixed(2));

const STATUS = (f) => {
  if (f.locked) return { t: "Locked", cls: "bg-surface-sunk text-faint" };
  if (f.eligible === false || f.held_at_baseline) return { t: "Not enough data", cls: "bg-warning/10 text-warning" };
  if (f.changed) return { t: "Suggests a change", cls: "bg-accent/10 text-accent-ink" };
  return { t: "No change", cls: "bg-success/10 text-success" };
};

/* One reason-gated action dialog, optionally with a numeric value (manual set). */
const ActionDialog = ({ open, onOpenChange, title, description, withValue, valueLabel, bounds, initialValue, confirmLabel, onConfirm }) => {
  const [reason, setReason] = useState("");
  const [value, setValue] = useState(initialValue ?? "");
  const [busy, setBusy] = useState(false);
  React.useEffect(() => { if (open) { setReason(""); setValue(initialValue ?? ""); } }, [open, initialValue]);
  const submit = async () => {
    if (reason.trim().length < 5) { toast.error("Please enter a reason (5+ characters)."); return; }
    if (withValue && (value === "" || Number.isNaN(Number(value)))) { toast.error("Enter a valid value."); return; }
    setBusy(true);
    try { await onConfirm(reason.trim(), withValue ? Number(value) : undefined); onOpenChange(false); }
    catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy(false);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="optimizer-action-dialog">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        {withValue && (
          <div className="mb-2">
            <label className="text-[12px] font-semibold text-ink-2">{valueLabel}</label>
            <Input data-testid="optimizer-value-input" type="number" step="0.01"
              min={bounds?.[0]} max={bounds?.[1]} value={value}
              onChange={(e) => setValue(e.target.value)} className="mt-1" />
            {bounds && <p className="text-[10.5px] text-faint mt-0.5">Allowed range {bounds[0]}–{bounds[1]}.</p>}
          </div>
        )}
        <label className="text-[12px] font-semibold text-ink-2">Reason (recorded on the calibration version)</label>
        <Textarea data-testid="optimizer-reason-input" value={reason} onChange={(e) => setReason(e.target.value)}
          placeholder="Why are you making this change?" rows={3} className="mt-1" />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="optimizer-reason-confirm-btn" onClick={submit} disabled={busy}>
            {busy ? "Saving…" : (confirmLabel || "Confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const Chip = ({ children, cls }) => (
  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${cls}`}>{children}</span>
);

export default function OptimizerPanel({ data, isOwner, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState(null); // {kind, factor, ...}
  const [showHistory, setShowHistory] = useState(false);
  const [showRuns, setShowRuns] = useState(false);
  const [history, setHistory] = useState(null);
  const [runs, setRuns] = useState(null);

  const reload = onChanged;
  const active = data.activated && !data.paused;

  const run = async () => {
    setBusy(true);
    try {
      const res = await optimizerRunApi();
      const m = res.run?.mode;
      toast.success(m === "applied" ? `Applied ${res.run.applied_version}.`
        : m === "noop" ? "Ran — no eligible change to apply." : "Ran in shadow mode (no changes).");
      reload();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy(false);
  };

  const loadHistory = useCallback(async () => {
    setShowHistory((s) => !s);
    if (history == null) { try { setHistory(await optimizerHistoryApi()); } catch { setHistory([]); } }
  }, [history]);
  const loadRuns = useCallback(async () => {
    setShowRuns((s) => !s);
    if (runs == null) { try { setRuns(await optimizerRunsApi()); } catch { setRuns([]); } }
  }, [runs]);

  const doAction = async (fn, okMsg) => {
    try { await fn(); toast.success(okMsg); setHistory(null); setRuns(null); reload(); }
    catch (e) { toast.error(apiErrorMessage(e)); throw e; }
  };

  return (
    <div data-testid="optimizer-panel" className="surface p-4 rounded-lg">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-1">
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-accent-ink" />
          <h3 className="font-bold text-primary text-[14px]">Auto-optimizer</h3>
          <span data-testid="optimizer-status-badge" className={`text-[10px] font-bold px-2 py-0.5 rounded ${active ? "bg-success/10 text-success" : data.paused ? "bg-warning/10 text-warning" : "bg-surface-sunk text-faint"}`}>
            {active ? "Learning ON" : data.paused ? "Paused" : "Shadow only"}
          </span>
          <span className="text-[11px] text-faint">calibration {data.calibration_version}</span>
        </div>
        <div className="flex items-center gap-2">
          <Button data-testid="optimizer-run-btn" size="sm" variant="outline" className="gap-1.5" disabled={busy} onClick={run}>
            <Play className="w-3.5 h-3.5" /> Run now
          </Button>
          <Button data-testid="optimizer-pause-btn" size="sm" variant="outline" className="gap-1.5"
            onClick={() => setDialog({ kind: "pause" })}>
            {data.paused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
            {data.paused ? "Resume" : "Pause"}
          </Button>
          {isOwner && (
            <Button data-testid="optimizer-activate-btn" size="sm" className="gap-1.5"
              variant={data.activated ? "outline" : "default"} onClick={() => setDialog({ kind: "activate" })}>
              <Power className="w-3.5 h-3.5" /> {data.activated ? "Deactivate" : "Activate"}
            </Button>
          )}
        </div>
      </div>
      <p className="text-[11.5px] text-faint mb-3 flex items-start gap-1.5">
        <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {data.note}
      </p>

      {/* Per-factor table */}
      <div className="space-y-2">
        {data.factors.map((f) => {
          const st = STATUS(f);
          return (
            <div key={f.factor} data-testid={`optimizer-factor-${f.factor}`}
              className="rounded-lg border border-border p-2.5 flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-[12.5px] font-semibold text-primary">{f.label}</div>
                <div className="text-[11px] text-faint flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5">
                  <span>now <b className="text-ink-2 tnum">{num(f.current)}</b></span>
                  <span>baseline <span className="tnum">{num(f.baseline)}</span></span>
                  <span>suggested <span className="tnum">{f.candidate == null ? "—" : num(f.candidate)}</span></span>
                  <span>sample <span className="tnum">{f.sample ?? f.n_eff ?? 0}</span></span>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Chip cls={st.cls}>{st.t}</Chip>
                <Button data-testid={`optimizer-lock-${f.factor}-btn`} size="sm" variant="ghost" className="h-7 px-2 gap-1"
                  onClick={() => setDialog({ kind: "lock", factor: f.group, locked: !f.locked })}>
                  {f.locked ? <Unlock className="w-3.5 h-3.5" /> : <Lock className="w-3.5 h-3.5" />}
                  <span className="text-[11px]">{f.locked ? "Unlock" : "Lock"}</span>
                </Button>
                <Button data-testid={`optimizer-manual-${f.factor}-btn`} size="sm" variant="ghost" className="h-7 px-2 gap-1"
                  onClick={() => setDialog({ kind: "manual", factor: f.factor, label: f.label, bounds: f.bounds, current: f.current })}>
                  <Pencil className="w-3.5 h-3.5" /><span className="text-[11px]">Set</span>
                </Button>
              </div>
            </div>
          );
        })}
      </div>

      {/* History */}
      <div className="mt-3">
        <button data-testid="optimizer-history-toggle" onClick={loadHistory}
          className="flex items-center gap-1.5 text-[12px] font-semibold text-accent-ink">
          <History className="w-3.5 h-3.5" /> Calibration history ({data.history_count})
          <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showHistory ? "rotate-180" : ""}`} />
        </button>
        {showHistory && (
          <div className="mt-2 space-y-1.5">
            {(history || []).length === 0 ? <EmptyState>No calibration changes yet.</EmptyState> : (history || []).map((h) => (
              <div key={h.id} data-testid="optimizer-history-row" className="rounded border border-border/70 p-2 text-[11.5px] flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-semibold text-primary">
                    {h.version ? <span className="tnum">{h.version}</span> : null} <span className="uppercase text-[10px] text-faint">{h.type}</span>
                    {h.at && <span className="text-faint font-normal ml-1.5">{fmtDate(h.at)}</span>}
                  </div>
                  <div className="text-faint">{h.actor} · {h.reason || "—"}</div>
                  {Array.isArray(h.changes) && h.changes.length > 0 && (
                    <div className="text-ink-2 mt-0.5">
                      {h.changes.map((c, i) => (
                        <span key={i} className="mr-2">{c.factor}{c.key ? `·${c.key}` : ""} {c.before != null ? `${c.before}→${c.after}` : (c.restored_version || "")}</span>
                      ))}
                    </div>
                  )}
                </div>
                {h.version && (
                  <Button data-testid={`optimizer-rollback-${h.version}-btn`} size="sm" variant="ghost" className="h-7 px-2 gap-1 shrink-0"
                    onClick={() => setDialog({ kind: "rollback", version: h.version })}>
                    <RotateCcw className="w-3.5 h-3.5" /><span className="text-[11px]">Roll back</span>
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Run log */}
      <div className="mt-2">
        <button data-testid="optimizer-runs-toggle" onClick={loadRuns}
          className="flex items-center gap-1.5 text-[12px] font-semibold text-accent-ink">
          <Cpu className="w-3.5 h-3.5" /> Recent runs
          <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showRuns ? "rotate-180" : ""}`} />
        </button>
        {showRuns && (
          <div className="mt-2 space-y-1.5">
            {(runs || []).length === 0 ? <EmptyState>No optimizer runs recorded yet.</EmptyState> : (runs || []).map((r) => (
              <div key={r.id} data-testid="optimizer-run-row" className="rounded border border-border/70 p-2 text-[11.5px] flex items-center justify-between gap-2">
                <span className="text-ink-2">{r.at ? fmtDate(r.at) : "—"} · <b>{r.trigger}</b> · {r.usable_jobs} usable</span>
                <span className="flex items-center gap-2">
                  <Chip cls={r.mode === "applied" ? "bg-accent/10 text-accent-ink" : r.mode === "noop" ? "bg-surface-sunk text-faint" : "bg-warning/10 text-warning"}>{r.mode}</Chip>
                  {r.applied_version && <span className="tnum text-accent-ink font-semibold">{r.applied_version}</span>}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* dialogs */}
      <ActionDialog open={dialog?.kind === "pause"} onOpenChange={(o) => !o && setDialog(null)}
        title={data.paused ? "Resume the optimizer" : "Pause the optimizer"}
        description={data.paused ? "Nightly runs will apply eligible changes again." : "It keeps computing shadow suggestions but changes nothing until resumed."}
        confirmLabel={data.paused ? "Resume" : "Pause"}
        onConfirm={(reason) => doAction(() => optimizerPauseApi(!data.paused, reason), data.paused ? "Resumed." : "Paused.")} />

      <ActionDialog open={dialog?.kind === "activate"} onOpenChange={(o) => !o && setDialog(null)}
        title={data.activated ? "Deactivate automatic calibration" : "Activate automatic calibration"}
        description={data.activated ? "The nightly run will stop changing parameters." : "The nightly run will begin applying eligible, unlocked, gate-passing changes within their sample thresholds and bounds. You can pause or lock anything at any time."}
        confirmLabel={data.activated ? "Deactivate" : "Activate"}
        onConfirm={(reason) => doAction(() => optimizerActivateApi(!data.activated, reason), data.activated ? "Deactivated." : "Activated.")} />

      <ActionDialog open={dialog?.kind === "lock"} onOpenChange={(o) => !o && setDialog(null)}
        title={dialog?.locked ? "Lock this parameter" : "Unlock this parameter"}
        description={dialog?.locked ? "The optimizer will not change it until you unlock it." : "On unlock, the current value becomes the optimizer's new baseline."}
        confirmLabel={dialog?.locked ? "Lock" : "Unlock"}
        onConfirm={(reason) => doAction(() => optimizerLockApi(dialog.factor, dialog.locked, reason), "Saved.")} />

      <ActionDialog open={dialog?.kind === "manual"} onOpenChange={(o) => !o && setDialog(null)}
        title={`Set ${dialog?.label || "parameter"}`}
        description="This applies to NEW calculations only, locks the parameter, and records a new calibration version. Saved quotes keep their snapshot."
        withValue valueLabel="New value" bounds={dialog?.bounds} initialValue={dialog?.current}
        confirmLabel="Save value"
        onConfirm={(reason, value) => doAction(() => optimizerManualSetApi(dialog.factor, value, reason), "Value set.")} />

      <ActionDialog open={dialog?.kind === "rollback"} onOpenChange={(o) => !o && setDialog(null)}
        title={`Roll back to ${dialog?.version}`}
        description="Restores that version's parameter values as a new calibration version. History is preserved."
        confirmLabel="Roll back"
        onConfirm={(reason) => doAction(() => optimizerRollbackApi(dialog.version, reason), "Rolled back.")} />
    </div>
  );
}
