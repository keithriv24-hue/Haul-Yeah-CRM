import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { GitMerge, RefreshCw, PlayCircle, Link2, SkipForward, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageTitle, InstructionBanner, EmptyState, LoadingRows } from "@/components/Bits";
import {
  migrationStatusApi, migrationScanApi, migrationRunApi, migrationReviewApi,
  resolveMigrationItemApi,
} from "@/lib/api";
import { apiErrorMessage } from "@/lib/api";

const Count = ({ label, value, tone = "" }) => (
  <div className="rounded-lg border border-border bg-card px-3 py-2">
    <div className={`text-xl font-bold ${tone}`} data-testid={`mig-count-${label.replace(/\s+/g, "-").toLowerCase()}`}>{value ?? "—"}</div>
    <div className="text-xs text-faint">{label}</div>
  </div>
);

export default function MigrationReview() {
  const [status, setStatus] = useState(null);
  const [items, setItems] = useState(null);
  const [busy, setBusy] = useState("");
  const [picked, setPicked] = useState({}); // item_id -> project_record_id

  const load = async () => {
    try {
      const [s, its] = await Promise.all([migrationStatusApi(), migrationReviewApi()]);
      setStatus(s);
      setItems(its);
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  useEffect(() => { load(); }, []);

  const runScan = async () => {
    setBusy("scan");
    try { await migrationScanApi(); await load(); toast.success("Dry-run scan complete."); }
    catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy("");
  };

  const runBackfill = async () => {
    setBusy("run");
    try {
      const r = await migrationRunApi();
      await load();
      toast.success(`Backfill done — ${r.counts.deterministically_linked} linked, ${r.counts.ambiguous} need review.`);
    } catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy("");
  };

  const resolve = async (itemId, action) => {
    setBusy(itemId + action);
    try {
      await resolveMigrationItemApi(itemId, action, action === "link" ? picked[itemId] : undefined);
      await load();
      toast.success(action === "link" ? "Linked." : action === "skip" ? "Skipped." : "Marked resolved.");
    } catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy("");
  };

  const scan = status?.last_scan?.counts || status?.last_run?.counts || {};

  return (
    <div data-testid="migration-review-page" className="space-y-6">
      <PageTitle title="Migration Review" subtitle="Backfill the canonical job id (project_record_id) safely — deterministic matches link automatically, ambiguous ones wait here for you." />

      <InstructionBanner>
        <span className="inline-flex items-center gap-2"><GitMerge className="w-4 h-4" /> The scan is read-only.</span>{" "}
        A backfill links every job whose lead maps to exactly one Project. If a lead maps to
        more than one Project, it is never guessed — it lands in the review list below for you to pick the right one.
      </InstructionBanner>

      <div className="flex flex-wrap gap-2">
        <Button data-testid="mig-scan-btn" variant="outline" className="gap-2" onClick={runScan} disabled={!!busy}>
          <RefreshCw className={`w-4 h-4 ${busy === "scan" ? "animate-spin" : ""}`} /> Run dry-run scan
        </Button>
        <Button data-testid="mig-run-btn" className="gap-2 bg-primary hover:bg-[#26395f]" onClick={runBackfill} disabled={!!busy}>
          <PlayCircle className="w-4 h-4" /> Run backfill
        </Button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2" data-testid="mig-counts">
        <Count label="Scanned" value={scan.scanned} />
        <Count label="Already linked" value={scan.already_linked} />
        <Count label="Linked now" value={scan.deterministically_linked} tone="text-success" />
        <Count label="Ambiguous" value={scan.ambiguous} tone="text-warning" />
        <Count label="Skipped" value={scan.skipped} />
        <Count label="Failed" value={scan.failed} tone={scan.failed ? "text-destructive" : ""} />
      </div>

      <div>
        <h2 className="font-display text-lg font-bold text-primary mb-2">
          Needs your review {status?.pending_review ? `(${status.pending_review})` : ""}
        </h2>
        {items === null ? (
          <LoadingRows />
        ) : items.length === 0 ? (
          <EmptyState>
            <CheckCircle2 className="w-5 h-5 mx-auto mb-2 text-success" />
            Nothing to review — every job is either linked or waiting for a deposit. Run a backfill if you just deployed.
          </EmptyState>
        ) : (
          <div className="space-y-3">
            {items.map((it) => (
              <div key={it.item_id} data-testid="mig-review-item" className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="font-semibold text-primary">{it.label || it.ref_id}</div>
                  <div className="text-xs text-faint">{it.reason}</div>
                </div>
                <div className="mt-3 space-y-1.5">
                  {it.candidates.map((c) => (
                    <label key={c.project_record_id} className="flex items-center gap-2 text-sm cursor-pointer" data-testid="mig-candidate">
                      <input
                        type="radio"
                        name={`cand-${it.item_id}`}
                        value={c.project_record_id}
                        checked={picked[it.item_id] === c.project_record_id}
                        onChange={() => setPicked((p) => ({ ...p, [it.item_id]: c.project_record_id }))}
                        data-testid="mig-candidate-radio"
                      />
                      <span className="font-medium">{c.name || "(unnamed)"}</span>
                      <span className="text-faint">{c.date || "no date"} · {c.status || "—"}</span>
                    </label>
                  ))}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    data-testid="mig-link-btn"
                    size="sm"
                    className="gap-1 bg-primary hover:bg-[#26395f]"
                    disabled={!picked[it.item_id] || !!busy}
                    onClick={() => resolve(it.item_id, "link")}
                  >
                    <Link2 className="w-3.5 h-3.5" /> Link selected
                  </Button>
                  <Button data-testid="mig-skip-btn" size="sm" variant="outline" className="gap-1" disabled={!!busy} onClick={() => resolve(it.item_id, "skip")}>
                    <SkipForward className="w-3.5 h-3.5" /> Skip
                  </Button>
                  <Button data-testid="mig-resolved-btn" size="sm" variant="outline" className="gap-1" disabled={!!busy} onClick={() => resolve(it.item_id, "resolved")}>
                    <CheckCircle2 className="w-3.5 h-3.5" /> Mark resolved
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
