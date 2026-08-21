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
import { InstructionBanner, PageTitle, Private, EmptyState, LoadingRows, ConfirmDeleteButton, SearchBar, searchMatch } from "@/components/Bits";
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
        <Button data-testid="contact-save-btn" onClick={save} disabled={saving} className="w-full gap-2 bg-accent hover:bg-accent-press">
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
  const [query, setQuery] = useState("");

  useEffect(() => {
    loadTable("contacts");
  }, [loadTable]);

  const all = records("contacts");
  const byType = filter === "All" ? all : all.filter((c) => f(c, CF.type) === filter);
  const contacts = byType.filter((c) => searchMatch(query, f(c, CF.name), f(c, CF.phone), f(c, CF.email), f(c, CF.company), f(c, CF.town), f(c, CF.notes)));
  const { loading, error } = tableState("contacts");

  return (
    <div data-testid="contacts-page">
      <PageTitle
        title="Contacts"
        subtitle="Everyone you work with."
        action={
          <Button data-testid="new-contact-btn" onClick={() => { setEditing(null); setModalOpen(true); }} className="gap-1.5 bg-accent hover:bg-accent-press">
            <Plus className="w-4 h-4" /> New contact
          </Button>
        }
      />
      <InstructionBanner>Everyone you work with, in one place. Tap a card to call or email.</InstructionBanner>

      <div className="mb-4">
        <SearchBar value={query} onChange={setQuery} placeholder="Search name, phone, email, or company…" testId="contacts-search-input" />
      </div>

      <div className="flex gap-2 overflow-x-auto no-scrollbar pb-1 mb-5">
        {["All", ...CONTACT_TYPES].map((t) => (
          <button
            key={t}
            data-testid={`contact-filter-${t.toLowerCase().replace(/\s+/g, "-")}`}
            onClick={() => setFilter(t)}
            className={`press shrink-0 rounded-lg px-3 py-2 text-[12.5px] font-semibold transition-colors duration-[160ms] ${
              filter === t ? "bg-primary text-white" : "bg-surface-sunk text-ink-2 hover:bg-muted hover:text-ink"
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
        <div className="grid items-stretch gap-4 md:grid-cols-2 xl:grid-cols-3">
          {contacts.map((c) => (
            <div key={c.id} data-testid="contact-card" className="surface-interactive p-4 flex flex-col gap-2.5">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <Private className="block truncate font-display text-[18px] font-extrabold leading-tight text-primary">{f(c, CF.name) || "No name"}</Private>
                  <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[12.5px] text-faint">
                    {f(c, CF.phone) && <Private className="tnum">{f(c, CF.phone)}</Private>}
                    {f(c, CF.email) && <Private className="truncate">{f(c, CF.email)}</Private>}
                  </div>
                </div>
                <span className="shrink-0 rounded-md bg-primary/8 px-2 py-1 text-[10.5px] font-bold uppercase tracking-[0.08em] text-primary">
                  {f(c, CF.type) || "Contact"}
                </span>
              </div>
              {(f(c, CF.company) || f(c, CF.town)) && (
                <div className="flex flex-wrap gap-x-3 gap-y-1 text-[12.5px] text-ink-2">
                  {f(c, CF.company) && <span className="inline-flex items-center gap-1.5"><Building2 className="w-3.5 h-3.5 text-faint" aria-hidden="true" /> {f(c, CF.company)}</span>}
                  {f(c, CF.town) && <span className="inline-flex items-center gap-1.5"><MapPin className="w-3.5 h-3.5 text-faint" aria-hidden="true" /> {f(c, CF.town)}</span>}
                </div>
              )}
              <div className="mt-auto space-y-2 pt-1">
                <div className="grid grid-cols-2 gap-2">
                  <Button asChild variant="accent" className="gap-1.5" disabled={!f(c, CF.phone)} data-testid="contact-call-btn">
                    <a href={f(c, CF.phone) ? `tel:${f(c, CF.phone)}` : undefined}><Phone className="w-4 h-4" /> Call</a>
                  </Button>
                  <Button asChild variant="outline" className="gap-1.5" data-testid="contact-email-btn">
                    <a href={gmailCompose(f(c, CF.email))} target="_blank" rel="noreferrer"><Mail className="w-4 h-4" /> Email</a>
                  </Button>
                </div>
                <div className="-mx-1 flex flex-wrap items-center gap-x-0.5 gap-y-1">
                  <a
                    data-testid="contact-gmail-search-btn"
                    href={gmailSearch(f(c, CF.email) || f(c, CF.name))}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[12.5px] font-semibold text-ink-2 transition-colors hover:bg-surface-sunk hover:text-primary"
                  >
                    <Search className="w-3.5 h-3.5" aria-hidden="true" /> Mail log
                  </a>
                  <button
                    data-testid="contact-edit-btn"
                    onClick={() => { setEditing(c); setModalOpen(true); }}
                    className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[12.5px] font-semibold text-ink-2 transition-colors hover:bg-surface-sunk hover:text-primary"
                  >
                    <Pencil className="w-3.5 h-3.5" aria-hidden="true" /> Edit
                  </button>
                  <ConfirmDeleteButton
                    what="this contact"
                    testId="contact-delete-btn"
                    className="ml-auto"
                    onConfirm={() => deleteRecord("contacts", c.id).then(() => toast.success("Contact deleted.")).catch(() => {})}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <ContactForm open={modalOpen} onOpenChange={setModalOpen} contact={editing} />
    </div>
  );
}
