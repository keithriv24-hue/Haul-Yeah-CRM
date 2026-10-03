import React, { useMemo, useState } from "react";
import { toast } from "sonner";
import { Search, UserPlus, Loader2, Check } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useApp } from "@/context/AppContext";
import { LF, f } from "@/lib/fields";
import { fmtDate } from "@/lib/format";
import { apiErrorMessage } from "@/lib/api";

// Search + create + select a lead. Used on direct calculator open and the "Who is this quote for?" prompt.
export const ScopeLeadPicker = ({ open, onOpenChange, onPick, title = "Who is this quote for?" }) => {
  const { records, loadTable, createRecord } = useApp();
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: "", phone: "", email: "", from: "", to: "", moveDate: "" });

  React.useEffect(() => { if (open) loadTable("leads"); }, [open, loadTable]);

  const matches = useMemo(() => {
    const term = q.trim().toLowerCase();
    const rows = (records("leads") || []).filter((l) => f(l, LF.status) !== "Lost");
    if (!term) return rows.slice(0, 8);
    return rows.filter((l) => {
      const hay = [LF.name, LF.phone, LF.email, LF.from, LF.to, LF.moveDate]
        .map((id) => String(f(l, id) || "").toLowerCase()).join(" ");
      return hay.includes(term);
    }).slice(0, 20);
  }, [records, q]);

  const create = async () => {
    if (form.name.trim().length < 2) { toast.error("Add a name for the new lead."); return; }
    setBusy(true);
    try {
      const fields = { [LF.name]: form.name.trim(), [LF.status]: "Contacted" };
      if (form.phone.trim()) fields[LF.phone] = form.phone.trim();
      if (form.email.trim()) fields[LF.email] = form.email.trim();
      if (form.from.trim()) fields[LF.from] = form.from.trim();
      if (form.to.trim()) fields[LF.to] = form.to.trim();
      if (form.moveDate) fields[LF.moveDate] = form.moveDate;
      const rec = await createRecord("leads", fields);
      toast.success("Lead created.");
      onPick(rec.id, form.name.trim());
      onOpenChange(false);
    } catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="scope-lead-picker" className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>Attach this quote to the right customer. Search an existing lead or create a new one.</DialogDescription>
        </DialogHeader>

        {!creating ? (
          <div className="space-y-3">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
              <Input data-testid="scope-lead-search" autoFocus value={q} onChange={(e) => setQ(e.target.value)}
                placeholder="Search name, phone, email, date or address" className="pl-9" />
            </div>
            <div className="space-y-1 max-h-[46vh] overflow-y-auto">
              {matches.length === 0 && <p className="text-sm text-faint px-1 py-3">No matching leads. Create one below.</p>}
              {matches.map((l) => (
                <button key={l.id} data-testid="scope-lead-option" onClick={() => { onPick(l.id, f(l, LF.name) || ""); onOpenChange(false); }}
                  className="w-full text-left rounded-lg border border-border hover:border-accent hover:bg-surface-sunk px-3 py-2 transition-colors">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-primary truncate">{f(l, LF.name) || "No name"}</span>
                    <span className="text-[11px] text-faint shrink-0">{f(l, LF.status) || "New"}</span>
                  </div>
                  <div className="text-xs text-faint truncate">
                    {[f(l, LF.phone), f(l, LF.moveDate) ? fmtDate(f(l, LF.moveDate)) : null, f(l, LF.from)].filter(Boolean).join(" · ") || "—"}
                  </div>
                </button>
              ))}
            </div>
            <Button data-testid="scope-lead-create-toggle" variant="outline" className="w-full gap-1.5" onClick={() => setCreating(true)}>
              <UserPlus className="w-4 h-4" /> Create a new lead
            </Button>
          </div>
        ) : (
          <div className="space-y-2.5">
            <div><Label>Name *</Label><Input data-testid="scope-new-lead-name" value={form.name} onChange={(e) => setForm((s) => ({ ...s, name: e.target.value }))} /></div>
            <div className="grid grid-cols-2 gap-2">
              <div><Label>Phone</Label><Input data-testid="scope-new-lead-phone" value={form.phone} onChange={(e) => setForm((s) => ({ ...s, phone: e.target.value }))} /></div>
              <div><Label>Move date</Label><Input data-testid="scope-new-lead-date" type="date" value={form.moveDate} onChange={(e) => setForm((s) => ({ ...s, moveDate: e.target.value }))} /></div>
            </div>
            <div><Label>Email</Label><Input data-testid="scope-new-lead-email" value={form.email} onChange={(e) => setForm((s) => ({ ...s, email: e.target.value }))} /></div>
            <div><Label>From</Label><Input data-testid="scope-new-lead-from" value={form.from} onChange={(e) => setForm((s) => ({ ...s, from: e.target.value }))} /></div>
            <div><Label>To</Label><Input data-testid="scope-new-lead-to" value={form.to} onChange={(e) => setForm((s) => ({ ...s, to: e.target.value }))} /></div>
            <div className="flex gap-2 pt-1">
              <Button variant="outline" className="flex-1" onClick={() => setCreating(false)} disabled={busy}>Back to search</Button>
              <Button data-testid="scope-new-lead-save" className="flex-1 gap-1.5 bg-accent hover:bg-accent-press" onClick={create} disabled={busy}>
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Create & select
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};
