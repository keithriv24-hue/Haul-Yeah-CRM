import React, { useState } from "react";
import { toast } from "sonner";
import { UserPlus } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useApp } from "@/context/AppContext";
import { LF, HOME_SIZES, CONTACT_METHODS, SPECIALTY_ITEMS, LEAD_SOURCES } from "@/lib/fields";

const blank = { name: "", phone: "", email: "", moveDate: "", from: "", to: "", homeSize: "", notes: "", source: "" };

export default function LeadModal({ open, onOpenChange }) {
  const { createRecord } = useApp();
  const [form, setForm] = useState(blank);
  const [methods, setMethods] = useState([]);
  const [specialty, setSpecialty] = useState([]);
  const [saving, setSaving] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const toggle = (list, setList, v) => setList(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  const save = async () => {
    if (!form.name.trim()) {
      toast.error("Add the person's name first.");
      return;
    }
    setSaving(true);
    try {
      await createRecord("leads", {
        [LF.name]: form.name.trim(),
        [LF.phone]: form.phone,
        [LF.email]: form.email,
        [LF.moveDate]: form.moveDate,
        [LF.from]: form.from,
        [LF.to]: form.to,
        [LF.homeSize]: form.homeSize,
        [LF.contactMethod]: methods.length ? methods : undefined,
        [LF.specialty]: specialty.length ? specialty : undefined,
        [LF.notes]: form.notes,
        [LF.source]: form.source,
        [LF.status]: "New",
      });
      toast.success("Lead saved. The clock starts now — call them fast!");
      setForm(blank);
      setMethods([]);
      setSpecialty([]);
      onOpenChange(false);
    } catch {}
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="new-lead-modal" className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <UserPlus className="w-5 h-5 text-[#E8743B]" /> New lead
          </DialogTitle>
          <DialogDescription>Fill in what you know. Name is the only must-have.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <Label>Name *</Label>
            <Input data-testid="lead-name-input" value={form.name} onChange={set("name")} placeholder="Jane Smith" />
          </div>
          <div>
            <Label>Phone</Label>
            <Input data-testid="lead-phone-input" value={form.phone} onChange={set("phone")} placeholder="(973) 555-0100" />
          </div>
          <div>
            <Label>Email</Label>
            <Input data-testid="lead-email-input" type="email" value={form.email} onChange={set("email")} placeholder="jane@email.com" />
          </div>
          <div>
            <Label>Move date</Label>
            <Input data-testid="lead-movedate-input" type="date" value={form.moveDate} onChange={set("moveDate")} />
          </div>
          <div>
            <Label>Home size</Label>
            <Select value={form.homeSize} onValueChange={(v) => setForm((f) => ({ ...f, homeSize: v }))}>
              <SelectTrigger data-testid="lead-homesize-select"><SelectValue placeholder="Pick one" /></SelectTrigger>
              <SelectContent>
                {HOME_SIZES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Moving from</Label>
            <Input data-testid="lead-from-input" value={form.from} onChange={set("from")} placeholder="Montclair, NJ" />
          </div>
          <div>
            <Label>Moving to</Label>
            <Input data-testid="lead-to-input" value={form.to} onChange={set("to")} placeholder="Edison, NJ" />
          </div>
          <div className="col-span-2">
            <Label>Best way to reach them</Label>
            <div className="flex gap-4 mt-1.5">
              {CONTACT_METHODS.map((m) => (
                <label key={m} className="flex items-center gap-1.5 text-sm">
                  <Checkbox checked={methods.includes(m)} onCheckedChange={() => toggle(methods, setMethods, m)} /> {m}
                </label>
              ))}
            </div>
          </div>
          <div className="col-span-2">
            <Label>Special items</Label>
            <div className="flex flex-wrap gap-3 mt-1.5">
              {SPECIALTY_ITEMS.map((m) => (
                <label key={m} className="flex items-center gap-1.5 text-sm">
                  <Checkbox checked={specialty.includes(m)} onCheckedChange={() => toggle(specialty, setSpecialty, m)} /> {m}
                </label>
              ))}
            </div>
          </div>
          <div>
            <Label>Where did they find us?</Label>
            <Select value={form.source} onValueChange={(v) => setForm((f) => ({ ...f, source: v }))}>
              <SelectTrigger data-testid="lead-source-select"><SelectValue placeholder="Pick the source" /></SelectTrigger>
              <SelectContent>
                {LEAD_SOURCES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="col-span-2">
            <Label>Notes</Label>
            <Textarea data-testid="lead-notes-input" value={form.notes} onChange={set("notes")} rows={2} />
          </div>
        </div>
        <Button data-testid="lead-save-btn" onClick={save} disabled={saving} className="w-full gap-2 bg-[#E8743B] hover:bg-[#d4632e]">
          <UserPlus className="w-4 h-4" /> {saving ? "Saving…" : "Save lead"}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
