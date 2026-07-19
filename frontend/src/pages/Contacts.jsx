import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Phone, Mail, Plus, Building2, MapPin, Pencil, Search } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, Private, EmptyState, LoadingRows, ConfirmDeleteButton } from "@/components/Bits";
import { CF, f, CONTACT_TYPES } from "@/lib/fields";
import { gmailCompose, gmailSearch } from "@/lib/format";

const blank = { name: "", type: "Customer", company: "", phone: "", email: "", town: "", notes: "" };

const ContactForm = ({ open, onOpenChange, contact }) => {
  const { createRecord, updateRecord } = useApp();
  const [form, setForm] = useState(blank);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(
        contact
          ? {
              name: f(contact, CF.name) || "",
              type: f(contact, CF.type) || "Customer",
              company: f(contact, CF.company) || "",
              phone: f(contact, CF.phone) || "",
              email: f(contact, CF.email) || "",
              town: f(contact, CF.town) || "",
              notes: f(contact, CF.notes) || "",
            }
          : blank
      );
    }
  }, [open, contact]);

  const set = (k) => (e) => setForm((s) => ({ ...s, [k]: e.target.value }));

  const save = async () => {
    if (!form.name.trim()) {
      toast.error("Add a name first.");
      return;
    }
    setSaving(true);
    const fields = {
      [CF.name]: form.name.trim(),
      [CF.type]: form.type,
      [CF.company]: form.company,
      [CF.phone]: form.phone,
      [CF.email]: form.email,
      [CF.town]: form.town,
      [CF.notes]: form.notes,
    };
    try {
      if (contact) await updateRecord("contacts", contact.id, fields);
      else await createRecord("contacts", fields);
      toast.success(contact ? "Contact updated." : "Contact saved.");
      onOpenChange(false);
    } catch {}
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="contact-modal" className="max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display">{contact ? "Edit contact" : "New contact"}</DialogTitle>
          <DialogDescription>Who is this and how do you reach them?</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <Label>Name *</Label>
            <Input data-testid="contact-name-input" value={form.name} onChange={set("name")} />
          </div>
          <div>
            <Label>Type</Label>
            <Select value={form.type} onValueChange={(v) => setForm((s) => ({ ...s, type: v }))}>
              <SelectTrigger data-testid="contact-type-select"><SelectValue /></SelectTrigger>
              <SelectContent>{CONTACT_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label>Company</Label>
            <Input value={form.company} onChange={set("company")} />
          </div>
          <div>
            <Label>Phone</Label>
            <Input value={form.phone} onChange={set("phone")} />
          </div>
          <div>
            <Label>Email</Label>
            <Input type="email" value={form.email} onChange={set("email")} />
          </div>
          <div className="col-span-2">
            <Label>Town</Label>
            <Input value={form.town} onChange={set("town")} />
          </div>
          <div className="col-span-2">
            <Label>Notes</Label>
            <Textarea value={form.notes} onChange={set("notes")} rows={2} />
          </div>
        </div>
        <Button data-testid="contact-save-btn" onClick={save} disabled={saving} className="w-full gap-2 bg-[#E8743B] hover:bg-[#d4632e]">
          <Plus className="w-4 h-4" /> {saving ? "Saving…" : contact ? "Save changes" : "Save contact"}
        </Button>
      </DialogContent>
    </Dialog>
  );
};

export default function Contacts() {
  const { loadTable, records, tableState, deleteRecord } = useApp();
  const [filter, setFilter] = useState("All");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  useEffect(() => {
    loadTable("contacts");
  }, [loadTable]);

  const all = records("contacts");
  const contacts = filter === "All" ? all : all.filter((c) => f(c, CF.type) === filter);
  const { loading, error } = tableState("contacts");

  return (
    <div data-testid="contacts-page">
      <PageTitle
        title="Contacts"
        subtitle="Everyone you work with."
        action={
          <Button data-testid="new-contact-btn" onClick={() => { setEditing(null); setModalOpen(true); }} className="gap-1.5 bg-[#E8743B] hover:bg-[#d4632e]">
            <Plus className="w-4 h-4" /> New contact
          </Button>
        }
      />
      <InstructionBanner>Everyone you work with, in one place. Tap a card to call or email.</InstructionBanner>

      <div className="flex gap-2 overflow-x-auto no-scrollbar pb-1 mb-5">
        {["All", ...CONTACT_TYPES].map((t) => (
          <button
            key={t}
            data-testid={`contact-filter-${t.toLowerCase().replace(/\s+/g, "-")}`}
            onClick={() => setFilter(t)}
            className={`shrink-0 rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-colors ${
              filter === t ? "bg-[#1B2A4A] text-white border-[#1B2A4A]" : "bg-white text-slate-600 border-slate-300 hover:border-[#1B2A4A]"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {loading && !all.length ? (
        <LoadingRows />
      ) : error && !all.length ? (
        <EmptyState>{error}</EmptyState>
      ) : contacts.length === 0 ? (
        <EmptyState>No contacts here yet. Press "+ New contact".</EmptyState>
      ) : (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
          {contacts.map((c) => (
            <div key={c.id} data-testid="contact-card" className="bg-white border border-slate-200 rounded-lg p-4 flex flex-col gap-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <Private className="font-display font-bold text-lg text-[#1B2A4A] truncate">{f(c, CF.name) || "No name"}</Private>
                  <div className="text-xs text-slate-500 space-x-2">
                    {f(c, CF.phone) && <Private>{f(c, CF.phone)}</Private>}
                    {f(c, CF.email) && <Private>{f(c, CF.email)}</Private>}
                  </div>
                </div>
                <span className="shrink-0 text-[10px] font-bold uppercase tracking-wide bg-[#1B2A4A]/5 text-[#1B2A4A] border border-[#1B2A4A]/20 rounded-full px-2 py-1">
                  {f(c, CF.type) || "Contact"}
                </span>
              </div>
              <div className="text-xs text-slate-600 space-y-1">
                {f(c, CF.company) && <div className="flex items-center gap-1.5"><Building2 className="w-3.5 h-3.5 text-slate-400" /> {f(c, CF.company)}</div>}
                {f(c, CF.town) && <div className="flex items-center gap-1.5"><MapPin className="w-3.5 h-3.5 text-slate-400" /> {f(c, CF.town)}</div>}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-1.5 mt-1">
                <Button asChild variant="outline" size="sm" className="gap-1 text-xs" disabled={!f(c, CF.phone)} data-testid="contact-call-btn">
                  <a href={f(c, CF.phone) ? `tel:${f(c, CF.phone)}` : undefined}><Phone className="w-3.5 h-3.5" /> Call</a>
                </Button>
                <Button asChild variant="outline" size="sm" className="gap-1 text-xs" data-testid="contact-email-btn">
                  <a href={gmailCompose(f(c, CF.email))} target="_blank" rel="noreferrer"><Mail className="w-3.5 h-3.5" /> Email</a>
                </Button>
                <Button asChild variant="outline" size="sm" className="gap-1 text-xs" data-testid="contact-gmail-search-btn">
                  <a href={gmailSearch(f(c, CF.email) || f(c, CF.name))} target="_blank" rel="noreferrer"><Search className="w-3.5 h-3.5" /> Mail log</a>
                </Button>
                <Button variant="outline" size="sm" className="gap-1 text-xs" onClick={() => { setEditing(c); setModalOpen(true); }} data-testid="contact-edit-btn">
                  <Pencil className="w-3.5 h-3.5" /> Edit
                </Button>
                <ConfirmDeleteButton
                  what="this contact"
                  testId="contact-delete-btn"
                  onConfirm={() => deleteRecord("contacts", c.id).then(() => toast.success("Contact deleted.")).catch(() => {})}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      <ContactForm open={modalOpen} onOpenChange={setModalOpen} contact={editing} />
    </div>
  );
}
