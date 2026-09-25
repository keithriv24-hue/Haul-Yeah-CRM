import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil } from "lucide-react";import { useApp } from "@/context/AppContext";
import { useAuth } from "@/components/AuthGate";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, EmptyState, LoadingRows, SearchBar, searchMatch } from "@/components/Bits";
import { f } from "@/lib/fields";
import { NC, NC_TYPES, NC_SEVERITIES, NC_STATUSES, fmtDate } from "@/lib/quality";

const todayISO = () => new Date().toISOString().slice(0, 10);

const sevClass = (s) =>
  s === "Liability risk" || s === "Regulatory" ? "bg-red-100 text-red-700"
    : s === "Major" ? "bg-amber-100 text-amber-700"
    : "bg-surface-sunk text-ink-2";
const statusClass = (s) =>
  s === "Open" ? "bg-red-100 text-red-700"
    : s === "In progress" ? "bg-amber-100 text-amber-700"
    : s === "Verifying" ? "bg-blue-100 text-blue-700"
    : "bg-emerald-100 text-emerald-700";

const blank = {
  [NC.type]: "Complaint", [NC.severity]: "Minor", [NC.status]: "Open",
  [NC.what]: "", [NC.immediate]: "", [NC.root]: "", [NC.corrective]: "", [NC.verifyDate]: "",
};

const NcForm = ({ open, onOpenChange, record }) => {
  const { createRecord, updateRecord } = useApp();
  const { user } = useAuth();
  const [form, setForm] = useState(blank);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(
        record
          ? {
              [NC.type]: f(record, NC.type) || "Complaint",
              [NC.severity]: f(record, NC.severity) || "Minor",
              [NC.status]: f(record, NC.status) || "Open",
              [NC.what]: f(record, NC.what) || "",
              [NC.immediate]: f(record, NC.immediate) || "",
              [NC.root]: f(record, NC.root) || "",
              [NC.corrective]: f(record, NC.corrective) || "",
              [NC.verifyDate]: f(record, NC.verifyDate) || "",
            }
          : blank
      );
    }
  }, [open, record]);

  const set = (k) => (e) => setForm((s) => ({ ...s, [k]: e.target.value }));
  const setSel = (k) => (v) => setForm((s) => ({ ...s, [k]: v }));

  const save = async () => {
    if (!String(form[NC.what]).trim()) {
      toast.error("Describe what happened first.");
      return;
    }
    const closing = form[NC.status] === "Closed";
    if (closing && (!String(form[NC.root]).trim() || !String(form[NC.corrective]).trim())) {
      toast.error("Add a root cause and a corrective action before closing.");
      return;
    }
    setSaving(true);
    const fields = { ...form };
    if (!record) {
      fields[NC.raisedBy] = user?.name || "Quality";
      fields[NC.raisedDate] = todayISO();
    }
    if (closing) {
      fields[NC.closedBy] = user?.name || "Quality";
      fields[NC.closedDate] = todayISO();
    }
    try {
      if (record) await updateRecord("nonconformances", record.id, fields);
      else await createRecord("nonconformances", fields);
      toast.success(record ? "Nonconformance updated." : "Nonconformance raised.");
      onOpenChange(false);
    } catch {}
    setSaving(false);
  };

  const closing = form[NC.status] === "Closed";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="nc-form-modal" className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">{record ? "Nonconformance" : "Raise a nonconformance"}</DialogTitle>
          <DialogDescription>{record ? `NC #${f(record, NC.number) || "—"}` : "Log a problem so it gets worked and closed."}</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Type</Label>
            <Select value={form[NC.type]} onValueChange={setSel(NC.type)}>
              <SelectTrigger data-testid="nc-type-select"><SelectValue /></SelectTrigger>
              <SelectContent>{NC_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label>Severity</Label>
            <Select value={form[NC.severity]} onValueChange={setSel(NC.severity)}>
              <SelectTrigger data-testid="nc-severity-select"><SelectValue /></SelectTrigger>
              <SelectContent>{NC_SEVERITIES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="col-span-2">
            <Label>What happened *</Label>
            <Textarea data-testid="nc-what-input" rows={2} value={form[NC.what]} onChange={set(NC.what)} />
          </div>
          <div className="col-span-2">
            <Label>Immediate action</Label>
            <Textarea data-testid="nc-immediate-input" rows={2} value={form[NC.immediate]} onChange={set(NC.immediate)} />
          </div>
          <div className="col-span-2">
            <Label>Root cause {closing && <span className="text-red-600">*</span>}</Label>
            <Textarea data-testid="nc-root-input" rows={2} value={form[NC.root]} onChange={set(NC.root)} />
          </div>
          <div className="col-span-2">
            <Label>Corrective action {closing && <span className="text-red-600">*</span>}</Label>
            <Textarea data-testid="nc-corrective-input" rows={2} value={form[NC.corrective]} onChange={set(NC.corrective)} />
          </div>
          <div>
            <Label>Verify-by date</Label>
            <Input type="date" data-testid="nc-verify-date" value={form[NC.verifyDate] || ""} onChange={set(NC.verifyDate)} />
          </div>
          <div>
            <Label>Status</Label>
            <Select value={form[NC.status]} onValueChange={setSel(NC.status)}>
              <SelectTrigger data-testid="nc-status-select"><SelectValue /></SelectTrigger>
              <SelectContent>{NC_STATUSES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        </div>
        {closing && (
          <p className="text-[12px] text-faint" data-testid="nc-close-hint">Closing needs a root cause and a corrective action.</p>
        )}
        <Button data-testid="nc-save-btn" onClick={save} disabled={saving} className="w-full gap-2 bg-accent hover:bg-accent-press">
          <Plus className="w-4 h-4" /> {saving ? "Saving…" : record ? "Save changes" : "Raise nonconformance"}
        </Button>
      </DialogContent>
    </Dialog>
  );
};

export default function QualityProblems() {
  const { loadTable, records, tableState } = useApp();
  const [statusFilter, setStatusFilter] = useState("All");
  const [sevFilter, setSevFilter] = useState("All");
  const [query, setQuery] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  useEffect(() => {
    loadTable("nonconformances");
  }, [loadTable]);

  const all = records("nonconformances");
  const { loading, error } = tableState("nonconformances");
  const list = all
    .filter((r) => statusFilter === "All" || f(r, NC.status) === statusFilter)
    .filter((r) => sevFilter === "All" || f(r, NC.severity) === sevFilter)
    .filter((r) => searchMatch(query, f(r, NC.what), f(r, NC.type), f(r, NC.raisedBy), String(f(r, NC.number))))
    .sort((a, b) => (f(b, NC.raisedDate) || "").localeCompare(f(a, NC.raisedDate) || ""));

  return (
    <div data-testid="quality-problems-page">
      <PageTitle
        title="Nonconformances"
        subtitle="Problems, complaints, claims and audit findings."
        action={
          <Button data-testid="new-nc-btn" onClick={() => { setEditing(null); setModalOpen(true); }} className="gap-1.5 bg-accent hover:bg-accent-press">
            <Plus className="w-4 h-4" /> Raise one
          </Button>
        }
      />
      <InstructionBanner>Every problem gets logged, worked, and closed with a root cause. Nothing slips through.</InstructionBanner>

      <div className="mb-3">
        <SearchBar value={query} onChange={setQuery} placeholder="Search what happened, type, or NC #…" testId="nc-search-input" />
      </div>
      <div className="mb-4 flex flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <span className="text-[12px] font-semibold text-faint">Status</span>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger data-testid="nc-filter-status" className="h-9 w-[150px]"><SelectValue /></SelectTrigger>
            <SelectContent>{["All", ...NC_STATUSES].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[12px] font-semibold text-faint">Severity</span>
          <Select value={sevFilter} onValueChange={setSevFilter}>
            <SelectTrigger data-testid="nc-filter-severity" className="h-9 w-[150px]"><SelectValue /></SelectTrigger>
            <SelectContent>{["All", ...NC_SEVERITIES].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      </div>

      {loading && !all.length ? (
        <LoadingRows />
      ) : error && !all.length ? (
        <EmptyState>{error}</EmptyState>
      ) : list.length === 0 ? (
        <EmptyState>Nothing here. Press "Raise one" to log a problem.</EmptyState>
      ) : (
        <div className="space-y-2.5">
          {list.map((r) => (
            <button
              key={r.id}
              data-testid="nc-row"
              onClick={() => { setEditing(r); setModalOpen(true); }}
              className="press w-full text-left surface-interactive p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="tnum text-[12px] font-bold text-faint">NC #{f(r, NC.number) || "—"}</span>
                    <span className="rounded-md bg-primary/8 px-2 py-0.5 text-[11px] font-bold text-primary">{f(r, NC.type) || "—"}</span>
                  </div>
                  <div className="mt-1 font-display text-[15px] font-bold text-ink line-clamp-2">{f(r, NC.what) || "No detail"}</div>
                  <div className="mt-1 text-[12px] text-faint">Raised {fmtDate(f(r, NC.raisedDate))} by {f(r, NC.raisedBy) || "—"}</div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <span className={`rounded-md px-2 py-1 text-[11px] font-bold ${sevClass(f(r, NC.severity))}`}>{f(r, NC.severity) || "—"}</span>
                  <span className={`rounded-md px-2 py-1 text-[11px] font-bold ${statusClass(f(r, NC.status))}`}>{f(r, NC.status) || "—"}</span>
                  <Pencil className="w-3.5 h-3.5 text-faint" aria-hidden="true" />
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      <NcForm open={modalOpen} onOpenChange={setModalOpen} record={editing} />
    </div>
  );
}
