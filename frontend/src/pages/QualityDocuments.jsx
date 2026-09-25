import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, FileText, ExternalLink, Pencil } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, EmptyState, LoadingRows, SearchBar, searchMatch, ConfirmDeleteButton } from "@/components/Bits";
import { f } from "@/lib/fields";
import { QD, QD_STATUSES, fmtDate, daysUntil } from "@/lib/quality";

const blank = { [QD.name]: "", [QD.version]: "", [QD.owner]: "", [QD.effective]: "", [QD.review]: "", [QD.status]: "Current", [QD.drive]: "", [QD.notes]: "" };

const ReviewBadge = ({ value }) => {
  const d = daysUntil(value);
  if (d == null) return <span className="text-faint">—</span>;
  if (d < 0)
    return <span data-testid="doc-review-overdue" className="rounded-md bg-red-100 px-2 py-0.5 text-[11px] font-bold text-red-700">Overdue {fmtDate(value)}</span>;
  if (d <= 60)
    return <span data-testid="doc-review-soon" className="rounded-md bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-700">Due in {d}d</span>;
  return <span className="text-ink-2">{fmtDate(value)}</span>;
};

const DocForm = ({ open, onOpenChange, record }) => {
  const { createRecord, updateRecord } = useApp();
  const [form, setForm] = useState(blank);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(
        record
          ? {
              [QD.name]: f(record, QD.name) || "",
              [QD.version]: f(record, QD.version) || "",
              [QD.owner]: f(record, QD.owner) || "",
              [QD.effective]: f(record, QD.effective) || "",
              [QD.review]: f(record, QD.review) || "",
              [QD.status]: f(record, QD.status) || "Current",
              [QD.drive]: f(record, QD.drive) || "",
              [QD.notes]: f(record, QD.notes) || "",
            }
          : blank
      );
    }
  }, [open, record]);

  const set = (k) => (e) => setForm((s) => ({ ...s, [k]: e.target.value }));

  const save = async () => {
    if (!String(form[QD.name]).trim()) {
      toast.error("Give the document a name.");
      return;
    }
    setSaving(true);
    try {
      if (record) await updateRecord("quality_docs", record.id, form);
      else await createRecord("quality_docs", form);
      toast.success(record ? "Document updated." : "Document added.");
      onOpenChange(false);
    } catch {}
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="doc-form-modal" className="max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">{record ? "Edit document" : "Add a document"}</DialogTitle>
          <DialogDescription>Registers live in Google Drive — paste the link, no uploads here.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <Label>Name *</Label>
            <Input data-testid="doc-name-input" value={form[QD.name]} onChange={set(QD.name)} />
          </div>
          <div>
            <Label>Version</Label>
            <Input data-testid="doc-version-input" value={form[QD.version]} onChange={set(QD.version)} />
          </div>
          <div>
            <Label>Owner</Label>
            <Input data-testid="doc-owner-input" value={form[QD.owner]} onChange={set(QD.owner)} />
          </div>
          <div>
            <Label>Effective date</Label>
            <Input type="date" data-testid="doc-effective-input" value={form[QD.effective] || ""} onChange={set(QD.effective)} />
          </div>
          <div>
            <Label>Review date</Label>
            <Input type="date" data-testid="doc-review-input" value={form[QD.review] || ""} onChange={set(QD.review)} />
          </div>
          <div className="col-span-2">
            <Label>Status</Label>
            <Select value={form[QD.status]} onValueChange={(v) => setForm((s) => ({ ...s, [QD.status]: v }))}>
              <SelectTrigger data-testid="doc-status-select"><SelectValue /></SelectTrigger>
              <SelectContent>{QD_STATUSES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="col-span-2">
            <Label>Drive link</Label>
            <Input type="url" data-testid="doc-drive-input" placeholder="https://drive.google.com/…" value={form[QD.drive]} onChange={set(QD.drive)} />
          </div>
          <div className="col-span-2">
            <Label>Notes</Label>
            <Textarea data-testid="doc-notes-input" rows={2} value={form[QD.notes]} onChange={set(QD.notes)} />
          </div>
        </div>
        <Button data-testid="doc-save-btn" onClick={save} disabled={saving} className="w-full gap-2 bg-accent hover:bg-accent-press">
          <Plus className="w-4 h-4" /> {saving ? "Saving…" : record ? "Save changes" : "Add document"}
        </Button>
      </DialogContent>
    </Dialog>
  );
};

export default function QualityDocuments() {
  const { loadTable, records, tableState, deleteRecord } = useApp();
  const [query, setQuery] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  useEffect(() => {
    loadTable("quality_docs");
  }, [loadTable]);

  const all = records("quality_docs");
  const { loading, error } = tableState("quality_docs");
  const list = all
    .filter((r) => searchMatch(query, f(r, QD.name), f(r, QD.owner), f(r, QD.version), f(r, QD.status)))
    .sort((a, b) => (f(a, QD.name) || "").localeCompare(f(b, QD.name) || ""));

  return (
    <div data-testid="quality-documents-page">
      <PageTitle
        title="Document register"
        subtitle="Controlled documents and when they're next due for review."
        action={
          <Button data-testid="new-doc-btn" onClick={() => { setEditing(null); setModalOpen(true); }} className="gap-1.5 bg-accent hover:bg-accent-press">
            <Plus className="w-4 h-4" /> Add document
          </Button>
        }
      />
      <InstructionBanner>Every policy and form lives in Drive. Amber = review due within 60 days, red = overdue.</InstructionBanner>

      <div className="mb-4">
        <SearchBar value={query} onChange={setQuery} placeholder="Search name, owner, version…" testId="doc-search-input" />
      </div>

      {loading && !all.length ? (
        <LoadingRows />
      ) : error && !all.length ? (
        <EmptyState>{error}</EmptyState>
      ) : list.length === 0 ? (
        <EmptyState>No documents yet. Press "Add document".</EmptyState>
      ) : (
        <div className="space-y-2.5">
          {list.map((r) => (
            <div key={r.id} data-testid="doc-row" className="surface-interactive p-4 flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0 flex items-start gap-3">
                <FileText className="mt-0.5 w-5 h-5 shrink-0 text-primary" aria-hidden="true" />
                <div className="min-w-0">
                  <div className="font-display text-[15px] font-bold text-primary truncate">{f(r, QD.name) || "Untitled"}</div>
                  <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[12px] text-faint">
                    {f(r, QD.version) && <span>v{f(r, QD.version)}</span>}
                    {f(r, QD.owner) && <span>Owner: {f(r, QD.owner)}</span>}
                    {f(r, QD.effective) && <span>Effective {fmtDate(f(r, QD.effective))}</span>}
                  </div>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2.5">
                <div className="text-right">
                  <div className="text-[11px] text-faint">Review</div>
                  <ReviewBadge value={f(r, QD.review)} />
                </div>
                <span className="rounded-md bg-surface-sunk px-2 py-1 text-[11px] font-bold text-ink-2">{f(r, QD.status) || "—"}</span>
                {f(r, QD.drive) && (
                  <a
                    data-testid="doc-open-link"
                    href={f(r, QD.drive)}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-[12.5px] font-semibold text-primary hover:bg-surface-sunk"
                  >
                    <ExternalLink className="w-3.5 h-3.5" /> Open
                  </a>
                )}
                <button
                  data-testid="doc-edit-btn"
                  onClick={() => { setEditing(r); setModalOpen(true); }}
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-[12.5px] font-semibold text-ink-2 hover:bg-surface-sunk hover:text-primary"
                >
                  <Pencil className="w-3.5 h-3.5" /> Edit
                </button>
                <ConfirmDeleteButton
                  what="this document"
                  testId="doc-delete-btn"
                  onConfirm={() => deleteRecord("quality_docs", r.id).then(() => toast.success("Document removed.")).catch(() => {})}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      <DocForm open={modalOpen} onOpenChange={setModalOpen} record={editing} />
    </div>
  );
}
