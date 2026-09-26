import React, { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Scale, Plus, RefreshCw, Lock, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, EmptyState, LoadingRows } from "@/components/Bits";
import {
  qualityClaimsApi, qualityCreateClaimApi, qualityUpdateClaimApi, listRecords, apiErrorMessage,
} from "@/lib/api";
import { f, PF } from "@/lib/fields";
import { money, fmtDate, stateTone } from "@/lib/quality";

const urgencyLabel = (u) => {
  if (!u || u.days == null) return null;
  const w = u.which === "form" ? "Form" : "Settlement";
  if (u.days < 0) return `${w} ${-u.days}d overdue`;
  return `${w} due in ${u.days}d`;
};

const StatusBadge = ({ status }) => {
  const terminal = ["Settled", "Denied", "Withdrawn"].includes(status);
  return (
    <span className={`rounded-md px-2 py-0.5 text-[11px] font-bold ${terminal ? "bg-surface-sunk text-faint" : "bg-primary/10 text-primary"}`}>
      {status}
    </span>
  );
};

const ClaimForm = ({ open, onOpenChange, claim, meta, projects, onSaved }) => {
  const editing = !!claim;
  const canSettle = meta?.can_settle;
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm({
      linked_job: claim?.linked_job_id || "",
      notice_received_date: claim?.notice_received_date || "",
      protection_option: claim?.protection_option || "",
      amount_claimed: claim?.amount_claimed != null ? String(claim.amount_claimed) : "",
      amount_settled: claim?.amount_settled != null ? String(claim.amount_settled) : "",
      status: claim?.status || "Notice received",
      form_sent_date: claim?.form_sent_date || "",
      completed_claim_received_date: claim?.completed_claim_received_date || "",
      extension_agreed: !!claim?.extension_agreed,
      notes: claim?.notes || "",
    });
  }, [open, claim]);

  const set = (k) => (e) => setForm((s) => ({ ...s, [k]: e.target.value }));
  const setV = (k) => (v) => setForm((s) => ({ ...s, [k]: v }));

  const statuses = (meta?.statuses || []).filter((s) => canSettle || s !== "Settled");

  const buildInputs = () => {
    const inp = {};
    if (form.linked_job) inp.linked_job = form.linked_job;
    if (form.notice_received_date) inp.notice_received_date = form.notice_received_date;
    if (form.protection_option) inp.protection_option = form.protection_option;
    if (form.amount_claimed !== "") inp.amount_claimed = Number(form.amount_claimed);
    if (form.status) inp.status = form.status;
    if (form.form_sent_date) inp.form_sent_date = form.form_sent_date;
    if (form.completed_claim_received_date) inp.completed_claim_received_date = form.completed_claim_received_date;
    inp.extension_agreed = !!form.extension_agreed;
    if (form.notes) inp.notes = form.notes;
    if (canSettle && form.amount_settled !== "") inp.amount_settled = Number(form.amount_settled);
    return inp;
  };

  const save = async () => {
    if (!editing && !form.notice_received_date) {
      toast.error("Notice received date is required — the 7-day form clock starts there.");
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await qualityUpdateClaimApi(claim.id, buildInputs());
        toast.success("Claim updated.");
      } else {
        await qualityCreateClaimApi(buildInputs());
        toast.success("Claim opened — a Liability-risk nonconformance was created automatically.");
      }
      onOpenChange(false);
      onSaved && onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="claim-form-modal" className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">{editing ? `Claim #${claim.claim_number ?? ""}` : "Open a claim"}</DialogTitle>
          <DialogDescription>
            {editing ? claim.linked_job_name || "Claim record" : "Opening a claim starts the 7-day form clock and files a Liability-risk nonconformance."}
          </DialogDescription>
        </DialogHeader>

        {editing && (
          <div className="grid grid-cols-2 gap-2 rounded-lg bg-surface-sunk p-3 text-[12.5px]" data-testid="claim-readonly">
            <div><span className="text-faint">Form due</span><div className="font-bold text-ink">{fmtDate(claim.form_due)}</div></div>
            <div><span className="text-faint">Settlement due</span><div className="font-bold text-ink">{fmtDate(claim.settlement_due)}</div></div>
            <div className="col-span-2 flex items-center gap-1 text-[11px] text-faint">
              <Lock className="h-3 w-3" /> Both due dates are calculated by Airtable — read-only.
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <Label>Linked job</Label>
            <Select value={form.linked_job || ""} onValueChange={setV("linked_job")}>
              <SelectTrigger data-testid="claim-job-select"><SelectValue placeholder="Choose a job…" /></SelectTrigger>
              <SelectContent>
                {projects.length === 0 && <SelectItem value="__none" disabled>No jobs loaded</SelectItem>}
                {projects.map((pr) => (
                  <SelectItem key={pr.id} value={pr.id}>{f(pr, PF.jobName) || "Untitled job"}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Notice received *</Label>
            <Input type="date" data-testid="claim-notice-date" value={form.notice_received_date || ""} onChange={set("notice_received_date")} />
          </div>
          <div>
            <Label>Protection option</Label>
            <Select value={form.protection_option || ""} onValueChange={setV("protection_option")}>
              <SelectTrigger data-testid="claim-protection-select"><SelectValue placeholder="Choose…" /></SelectTrigger>
              <SelectContent>{(meta?.protection_options || []).map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label>Form sent</Label>
            <Input type="date" data-testid="claim-form-sent-date" value={form.form_sent_date || ""} onChange={set("form_sent_date")} />
          </div>
          <div>
            <Label>Completed claim received</Label>
            <Input type="date" data-testid="claim-completed-date" value={form.completed_claim_received_date || ""} onChange={set("completed_claim_received_date")} />
          </div>
          <div>
            <Label>Amount claimed</Label>
            <Input type="number" data-testid="claim-amount-claimed" value={form.amount_claimed || ""} onChange={set("amount_claimed")} />
          </div>
          <div>
            <Label className="flex items-center gap-1">Amount settled {!canSettle && <Lock className="h-3 w-3 text-faint" />}</Label>
            <Input
              type="number"
              data-testid="claim-amount-settled"
              value={form.amount_settled || ""}
              onChange={set("amount_settled")}
              disabled={!canSettle}
              placeholder={canSettle ? "" : "Owner only"}
            />
          </div>
          <div className="col-span-2 flex items-center gap-2 pt-1">
            <Checkbox
              id="claim-ext"
              data-testid="claim-extension-checkbox"
              checked={!!form.extension_agreed}
              onCheckedChange={(v) => setForm((s) => ({ ...s, extension_agreed: !!v }))}
            />
            <Label htmlFor="claim-ext" className="text-[13px] font-normal">
              Extension agreed <span className="text-faint">(the +30 days is applied by Airtable's settlement-due formula — not here)</span>
            </Label>
          </div>
          <div className="col-span-2">
            <Label>Status</Label>
            <Select value={form.status || ""} onValueChange={setV("status")}>
              <SelectTrigger data-testid="claim-status-select"><SelectValue /></SelectTrigger>
              <SelectContent>{statuses.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
            </Select>
            {!canSettle && (
              <p className="mt-1 flex items-center gap-1 text-[11.5px] text-faint">
                <Lock className="h-3 w-3" /> Only the owner can mark a claim Settled or record a settlement amount.
              </p>
            )}
          </div>
          <div className="col-span-2">
            <Label>Notes</Label>
            <Textarea data-testid="claim-notes" rows={2} value={form.notes || ""} onChange={set("notes")} />
          </div>
        </div>

        <Button data-testid="claim-save-btn" onClick={save} disabled={saving} className="w-full gap-2 bg-accent hover:bg-accent-press">
          <Scale className="h-4 w-4" /> {saving ? "Saving…" : editing ? "Save claim" : "Open claim"}
        </Button>
      </DialogContent>
    </Dialog>
  );
};

export default function QualityClaims() {
  const [data, setData] = useState(null);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [active, setActive] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await qualityClaimsApi());
    } catch (e) {
      setError(apiErrorMessage(e));
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    listRecords("projects")
      .then((recs) => setProjects((recs || []).filter((r) => f(r, PF.status) === "Completed")))
      .catch(() => setProjects([]));
  }, []);

  const rows = data?.rows || [];
  const openNew = () => { setActive(null); setFormOpen(true); };
  const openEdit = (c) => { setActive(c); setFormOpen(true); };

  return (
    <div data-testid="quality-claims-page">
      <PageTitle
        title="Claims"
        subtitle="Nearest deadline first — a form due in two days outranks a claim opened this morning."
        action={
          <div className="flex gap-2">
            <Button data-testid="claims-refresh-btn" variant="outline" onClick={load} className="gap-1.5">
              <RefreshCw className="h-4 w-4" /> Refresh
            </Button>
            <Button data-testid="claim-new-btn" onClick={openNew} className="gap-1.5 bg-accent hover:bg-accent-press">
              <Plus className="h-4 w-4" /> New claim
            </Button>
          </div>
        }
      />
      <InstructionBanner>
        Statutory deadlines: the 7-day form clock, then the settlement clock. Red is overdue or within days. Form due and Settlement due come straight from Airtable — never edited here.
      </InstructionBanner>

      {loading ? (
        <LoadingRows />
      ) : error ? (
        <EmptyState>{error}</EmptyState>
      ) : rows.length === 0 ? (
        <EmptyState>No claims on record. That's the goal.</EmptyState>
      ) : (
        <div className="space-y-2.5">
          {rows.map((c) => {
            const u = c.urgency || {};
            const ul = urgencyLabel(u);
            return (
              <button
                key={c.id}
                data-testid="claim-row"
                onClick={() => openEdit(c)}
                className={`press w-full text-left surface-interactive p-4 flex flex-wrap items-center justify-between gap-3 ${
                  u.state === "red" ? "border-red-300 bg-red-50/60" : u.state === "amber" ? "border-amber-300" : ""
                }`}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-display text-[16px] font-extrabold text-primary">Claim #{c.claim_number ?? "—"}</span>
                    <StatusBadge status={c.status} />
                    {c.extension_agreed && <span className="rounded bg-surface-sunk px-1.5 py-0.5 text-[10px] font-semibold text-ink-2">+30d ext</span>}
                  </div>
                  <div className="mt-0.5 text-[12.5px] text-faint truncate">
                    {c.linked_job_name || "No job linked"} · claimed {money(c.amount_claimed)}
                    {c.amount_settled != null ? ` · settled ${money(c.amount_settled)}` : ""}
                  </div>
                </div>
                <div className="flex items-center gap-4 shrink-0">
                  {ul ? (
                    <div className="text-right">
                      <div className="text-[11px] text-faint">Deadline</div>
                      <div className={`text-[13px] font-bold ${stateTone(u.state)}`}>{fmtDate(u.deadline)}</div>
                    </div>
                  ) : (
                    <span className="text-[12px] text-faint">No active clock</span>
                  )}
                  {ul && (
                    <span
                      data-testid="claim-urgency-tag"
                      className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-bold text-white ${
                        u.state === "red" ? "bg-red-600" : u.state === "amber" ? "bg-amber-500" : "bg-emerald-500"
                      }`}
                    >
                      <Clock className="h-3 w-3" /> {ul}
                    </span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}

      <ClaimForm
        open={formOpen}
        onOpenChange={(v) => { setFormOpen(v); if (!v) setActive(null); }}
        claim={active}
        meta={data}
        projects={projects}
        onSaved={load}
      />
    </div>
  );
}
