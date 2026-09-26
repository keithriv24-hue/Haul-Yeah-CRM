import React, { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { ClipboardCheck, AlertTriangle, RefreshCw, Star, CheckCircle2 } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/components/AuthGate";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, EmptyState, LoadingRows } from "@/components/Bits";
import { qualityAuditQueueApi, qualitySetGoogleReviewApi, apiErrorMessage } from "@/lib/api";
import { JA, JA_BOL_ITEMS, JA_RESULTS, JA_GATES, JA_VARIANCE, fmtDate, money } from "@/lib/quality";

const todayISO = () => new Date().toISOString().slice(0, 10);

const AuditForm = ({ open, onOpenChange, project, onSaved }) => {
  const { createRecord } = useApp();
  const { user } = useAuth();
  const [form, setForm] = useState({});
  const [bol, setBol] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open && project) {
      setForm({
        completedDate: project.move_date || todayISO(),
        auditor: user?.name || "",
        quotedTotal: project.quoted_total != null ? String(project.quoted_total) : "",
        finalTotal: "",
        varianceExplained: "",
        estHours: "",
        actualHours: "",
        gates: "",
        result: "",
        findings: "",
        signedBol: "",
      });
      setBol([]);
    }
  }, [open, project, user]);

  const set = (k) => (e) => setForm((s) => ({ ...s, [k]: e.target.value }));
  const setSel = (k) => (v) => setForm((s) => ({ ...s, [k]: v }));
  const toggleBol = (item) => setBol((b) => (b.includes(item) ? b.filter((x) => x !== item) : [...b, item]));

  const save = async () => {
    if (!form.result) {
      toast.error("Pick an audit result first.");
      return;
    }
    setSaving(true);
    const fields = { [JA.linkedJob]: [project.id] };
    if (form.completedDate) fields[JA.completedDate] = form.completedDate;
    if (form.auditor) fields[JA.auditor] = form.auditor;
    if (bol.length) fields[JA.bol] = bol;
    if (form.quotedTotal !== "") fields[JA.quotedTotal] = Number(form.quotedTotal);
    if (form.finalTotal !== "") fields[JA.finalTotal] = Number(form.finalTotal);
    if (form.varianceExplained) fields[JA.varianceExplained] = form.varianceExplained;
    if (form.estHours !== "") fields[JA.estHours] = Number(form.estHours);
    if (form.actualHours !== "") fields[JA.actualHours] = Number(form.actualHours);
    if (form.gates) fields[JA.gates] = form.gates;
    fields[JA.result] = form.result;
    if (form.findings) fields[JA.findings] = form.findings;
    if (form.signedBol) fields[JA.signedBol] = form.signedBol;
    try {
      await createRecord("job_audits", fields);
      const flagged = form.result === "Fail" || form.result === "Pass with findings";
      toast.success(flagged ? "Audit saved — a nonconformance was opened automatically." : "Audit saved.");
      onOpenChange(false);
      onSaved && onSaved();
    } catch {}
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="audit-form-modal" className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">7-day job audit</DialogTitle>
          <DialogDescription className="truncate">{project?.name}</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Completed date</Label>
            <Input type="date" data-testid="audit-completed-date" value={form.completedDate || ""} onChange={set("completedDate")} />
          </div>
          <div>
            <Label>Auditor</Label>
            <Input data-testid="audit-auditor" value={form.auditor || ""} onChange={set("auditor")} />
          </div>
          <div className="col-span-2">
            <Label>BOL complete</Label>
            <div className="flex flex-wrap gap-1.5 mt-1" data-testid="audit-bol-chips">
              {JA_BOL_ITEMS.map((item) => (
                <button
                  key={item}
                  type="button"
                  data-testid={`audit-bol-${item.toLowerCase().replace(/\s+/g, "-")}`}
                  onClick={() => toggleBol(item)}
                  className={`press rounded-md px-2.5 py-1.5 text-[12px] font-semibold transition-colors ${
                    bol.includes(item) ? "bg-primary text-white" : "bg-surface-sunk text-ink-2 hover:bg-muted"
                  }`}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
          <div>
            <Label>Quoted total</Label>
            <Input type="number" data-testid="audit-quoted-total" value={form.quotedTotal || ""} onChange={set("quotedTotal")} />
          </div>
          <div>
            <Label>Final total</Label>
            <Input type="number" data-testid="audit-final-total" value={form.finalTotal || ""} onChange={set("finalTotal")} />
          </div>
          <div>
            <Label>Estimated hours</Label>
            <Input type="number" step="0.25" data-testid="audit-est-hours" value={form.estHours || ""} onChange={set("estHours")} />
          </div>
          <div>
            <Label>Actual hours</Label>
            <Input type="number" step="0.25" data-testid="audit-actual-hours" value={form.actualHours || ""} onChange={set("actualHours")} />
          </div>
          <div className="col-span-2">
            <Label>Variance explained</Label>
            <Select value={form.varianceExplained || ""} onValueChange={setSel("varianceExplained")}>
              <SelectTrigger data-testid="audit-variance-select"><SelectValue placeholder="Choose…" /></SelectTrigger>
              <SelectContent>{JA_VARIANCE.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="col-span-2">
            <Label>Gates green or override recorded</Label>
            <Select value={form.gates || ""} onValueChange={setSel("gates")}>
              <SelectTrigger data-testid="audit-gates-select"><SelectValue placeholder="Choose…" /></SelectTrigger>
              <SelectContent>{JA_GATES.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="col-span-2">
            <Label>Result *</Label>
            <Select value={form.result || ""} onValueChange={setSel("result")}>
              <SelectTrigger data-testid="audit-result-select"><SelectValue placeholder="Pass / Pass with findings / Fail" /></SelectTrigger>
              <SelectContent>{JA_RESULTS.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
            </Select>
            {(form.result === "Fail" || form.result === "Pass with findings") && (
              <p className="mt-1 text-[12px] text-accent" data-testid="audit-nc-note">
                This opens a nonconformance (Type "Audit finding") automatically.
              </p>
            )}
          </div>
          <div className="col-span-2">
            <Label>Findings</Label>
            <Textarea data-testid="audit-findings" rows={2} value={form.findings || ""} onChange={set("findings")} />
          </div>
          <div className="col-span-2">
            <Label>Signed BOL Drive link</Label>
            <Input type="url" data-testid="audit-signed-bol" placeholder="https://drive.google.com/…" value={form.signedBol || ""} onChange={set("signedBol")} />
          </div>
        </div>
        <Button data-testid="audit-save-btn" onClick={save} disabled={saving} className="w-full gap-2 bg-accent hover:bg-accent-press">
          <ClipboardCheck className="w-4 h-4" /> {saving ? "Saving…" : "Save audit"}
        </Button>
      </DialogContent>
    </Dialog>
  );
};

export default function QualityAudits() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [active, setActive] = useState(null);
  const [savingReview, setSavingReview] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await qualityAuditQueueApi();
      setRows(data.rows || []);
    } catch (e) {
      setError(apiErrorMessage(e));
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggleReview = async (row) => {
    setSavingReview(row.id);
    try {
      const next = !row.google_review_received;
      await qualitySetGoogleReviewApi(row.id, next);
      setRows((rs) => rs.map((r) => (r.id === row.id ? { ...r, google_review_received: next } : r)));
      toast.success(next ? "Google review marked received." : "Cleared.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setSavingReview(null);
  };

  const overdue = rows.filter((r) => r.past_due).length;

  return (
    <div data-testid="quality-audits-page">
      <PageTitle
        title="Job audits"
        subtitle="Every completed move gets a within-7-days audit."
        action={
          <Button data-testid="audit-refresh-btn" variant="outline" onClick={load} className="gap-1.5">
            <RefreshCw className="w-4 h-4" /> Refresh
          </Button>
        }
      />
      <InstructionBanner>
        These completed jobs still need an audit. Anything past its 7-day due date is red — clear those first.
      </InstructionBanner>

      {overdue > 0 && (
        <div data-testid="audit-overdue-banner" className="mb-4 flex items-center gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-[13px] font-semibold text-red-700">
          <AlertTriangle className="w-4 h-4" /> {overdue} audit{overdue > 1 ? "s" : ""} past due
        </div>
      )}

      {loading ? (
        <LoadingRows />
      ) : error ? (
        <EmptyState>{error}</EmptyState>
      ) : rows.length === 0 ? (
        <EmptyState>Queue clear — every completed job has been audited.</EmptyState>
      ) : (
        <div className="space-y-2.5">
          {rows.map((r) => (
            <div
              key={r.id}
              data-testid="audit-queue-row"
              className={`surface-interactive p-4 flex flex-wrap items-center justify-between gap-3 ${
                r.past_due ? "border-red-300 bg-red-50/60" : ""
              }`}
            >
              <button
                data-testid="audit-open-btn"
                onClick={() => setActive(r)}
                className="press min-w-0 flex-1 text-left"
              >
                <div className="font-display text-[16px] font-extrabold text-primary truncate">{r.name}</div>
                <div className="mt-0.5 text-[12.5px] text-faint">
                  Move {fmtDate(r.move_date)} · {r.quoted_total != null ? `quoted ${money(r.quoted_total)}` : "no quote on file"}
                </div>
              </button>
              <div className="flex items-center gap-4 shrink-0">
                <button
                  type="button"
                  data-testid={`audit-review-toggle-${r.id}`}
                  onClick={() => toggleReview(r)}
                  disabled={savingReview === r.id}
                  title="Google review received"
                  className={`press inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] font-bold transition-colors ${
                    r.google_review_received
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-surface-sunk text-ink-2 hover:bg-muted"
                  }`}
                >
                  {r.google_review_received ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Star className="h-3.5 w-3.5" />}
                  {r.google_review_received ? "Review in" : "Review?"}
                </button>
                <div className="text-right">
                  <div className="text-[12px] text-faint">Days since</div>
                  <div className="tnum font-bold text-ink">{r.days_since == null ? "—" : r.days_since}</div>
                </div>
                <div className="text-right">
                  <div className="text-[12px] text-faint">Audit due</div>
                  <div className={`tnum font-bold ${r.past_due ? "text-red-600" : "text-ink"}`}>{fmtDate(r.audit_due)}</div>
                </div>
                {r.past_due && (
                  <span data-testid="audit-past-due-tag" className="rounded-md bg-red-600 px-2 py-1 text-[10.5px] font-bold uppercase tracking-wide text-white">
                    Past due
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <AuditForm open={!!active} onOpenChange={(v) => !v && setActive(null)} project={active} onSaved={load} />
    </div>
  );
}
