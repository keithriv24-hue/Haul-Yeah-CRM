import React, { useMemo, useState } from "react";
import { Loader2, Save } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PF, PROJECT_STATUSES, TRUCKS } from "@/lib/fields";
import { jobMgmtUpdateApi, apiErrorMessage } from "@/lib/api";

const g = (fields, id) => fields?.[id];

// Logical field keys map 1:1 to the backend JOB_EDIT_FIELDS whitelist.
const initialFrom = (f) => ({
  status: g(f, PF.status) || "",
  move_date: (g(f, PF.jobDate) || "").slice(0, 10),
  crew_size: g(f, PF.crewSize) ?? "",
  est_hours: g(f, PF.estHours) ?? "",
  truck: g(f, PF.truck) || "",
  from_addr: g(f, PF.fromAddr) || "",
  to_addr: g(f, PF.toAddr) || "",
  quote: g(f, PF.quote) ?? "",
  final_revenue: g(f, PF.finalRevenue) ?? "",
});

export const JobEditDialog = ({ open, onOpenChange, projectId, fields, onSaved }) => {
  const base = useMemo(() => initialFrom(fields), [fields]);
  const [form, setForm] = useState(base);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  // Reset local state whenever the dialog re-opens with fresh data.
  React.useEffect(() => {
    if (open) { setForm(initialFrom(fields)); setNote(""); }
  }, [open, fields]);

  const set = (k, v) => setForm((s) => ({ ...s, [k]: v }));

  const changed = useMemo(() => {
    const out = {};
    Object.keys(base).forEach((k) => {
      const a = String(form[k] ?? "").trim();
      const b = String(base[k] ?? "").trim();
      if (a !== b) out[k] = form[k] === "" ? null : form[k];
    });
    return out;
  }, [form, base]);

  const nChanged = Object.keys(changed).length;

  const save = async () => {
    if (nChanged === 0) { toast.info("No changes to save."); return; }
    setSaving(true);
    try {
      const res = await jobMgmtUpdateApi(projectId, changed, note);
      toast.success(res.updated ? `Saved ${res.count} change${res.count === 1 ? "" : "s"}.` : "Nothing changed.");
      onSaved?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(apiErrorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="job-edit-dialog" className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit job record</DialogTitle>
          <DialogDescription>
            Changes write to the canonical job record and are permanently logged in the change history.
          </DialogDescription>
        </DialogHeader>

        <div className="grid sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label>Status</Label>
            <Select value={form.status} onValueChange={(v) => set("status", v)}>
              <SelectTrigger data-testid="job-edit-status"><SelectValue placeholder="Select" /></SelectTrigger>
              <SelectContent>{PROJECT_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Move date</Label>
            <Input data-testid="job-edit-move-date" type="date" value={form.move_date} onChange={(e) => set("move_date", e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Crew size</Label>
            <Input data-testid="job-edit-crew-size" type="number" min="0" value={form.crew_size} onChange={(e) => set("crew_size", e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Est. hours</Label>
            <Input data-testid="job-edit-est-hours" type="number" min="0" step="0.5" value={form.est_hours} onChange={(e) => set("est_hours", e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Truck</Label>
            <Select value={form.truck} onValueChange={(v) => set("truck", v)}>
              <SelectTrigger data-testid="job-edit-truck"><SelectValue placeholder="Select" /></SelectTrigger>
              <SelectContent>{TRUCKS.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label>From address</Label>
            <Input data-testid="job-edit-from" value={form.from_addr} onChange={(e) => set("from_addr", e.target.value)} />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label>To address</Label>
            <Input data-testid="job-edit-to" value={form.to_addr} onChange={(e) => set("to_addr", e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Quote ($)</Label>
            <Input data-testid="job-edit-quote" type="number" min="0" step="0.01" value={form.quote} onChange={(e) => set("quote", e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Final revenue ($)</Label>
            <Input data-testid="job-edit-final-revenue" type="number" min="0" step="0.01" value={form.final_revenue} onChange={(e) => set("final_revenue", e.target.value)} />
          </div>
        </div>

        <div className="space-y-1">
          <Label>Reason for change <span className="text-faint font-normal">(optional — saved to the log)</span></Label>
          <Textarea data-testid="job-edit-note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Corrected crew size after final headcount" />
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving} data-testid="job-edit-cancel">Cancel</Button>
          <Button onClick={save} disabled={saving || nChanged === 0} className="gap-1.5" data-testid="job-edit-save">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {nChanged > 0 ? `Save ${nChanged} change${nChanged === 1 ? "" : "s"}` : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
