import React, { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import {
  Phone, Mail, Calculator, CreditCard, Truck, MapPin, CalendarDays, CalendarPlus, Home, Lightbulb,
  Package, StickyNote, Search, MessageSquare, ArrowLeft, History, Pencil, Save, X, FileText, Undo2, BellRing,
} from "lucide-react";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/components/AuthGate";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, Private, Money, AgeTimer, EmptyState, LoadingRows, ConfirmDeleteButton, FollowUpBadge, InvoiceBadge } from "@/components/Bits";
import QuoteModal from "@/components/QuoteModal";
import DepositModal from "@/components/DepositModal";
import SquareInvoiceModal from "@/components/SquareInvoiceModal";
import { AddNoteDialog } from "@/pages/Leads";
import { LF, f, LEAD_STATUSES, STATUS_PILL, nextStepHint, KNOWN_LEAD_FIELD_IDS, formatExtraValue, needsFollowUp, quietDays, HOME_SIZES } from "@/lib/fields";
import { fmtDate, gmailCompose, gmailSearch, calendarTemplate, smsLink, winBackSmsBody, payNudgeSmsBody } from "@/lib/format";
import { quoteSmsBody } from "@/lib/quote";
import { depositFromQuote } from "@/lib/pricing";
import { bookLeadAsJob } from "@/lib/leadActions";

const InfoRow = ({ icon: Icon, label, children, isPrivate = true }) => (
  <div className="flex items-start gap-2 text-sm">
    <Icon className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
    <span className="text-slate-500 shrink-0">{label}:</span>
    {isPrivate ? <Private className="min-w-0 break-words font-medium text-[#1B2A4A]">{children}</Private> : <span className="min-w-0 break-words font-medium text-[#1B2A4A]">{children}</span>}
  </div>
);

export default function LeadDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { loadTable, loadSchema, records, tableState, updateRecord, createRecord, deleteRecord, schemas, invoicesForLead, loadSquareInvoices, rates } = useApp();
  const { role } = useAuth();
  const isSales = role === "sales";
  const isOwner = role === "owner";
  const [quoteOpen, setQuoteOpen] = useState(false);
  const [depositOpen, setDepositOpen] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);
  const [invoiceOpen, setInvoiceOpen] = useState(false);
  const [booking, setBooking] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [savingEdit, setSavingEdit] = useState(false);

  useEffect(() => {
    loadTable("leads");
    loadSchema("leads");
    if (isOwner) loadSquareInvoices();
  }, [loadTable, loadSchema, loadSquareInvoices, isOwner]);

  const lead = records("leads").find((r) => r.id === id);
  const { loading } = tableState("leads");

  if (!lead) {
    return (
      <div data-testid="lead-detail-page">
        <Button asChild variant="outline" size="sm" className="gap-1.5 mb-4" data-testid="lead-detail-back-btn">
          <Link to="/leads"><ArrowLeft className="w-4 h-4" /> Back to Leads</Link>
        </Button>
        {loading ? <LoadingRows /> : <EmptyState>This lead is gone or the link is wrong. Go back to Leads.</EmptyState>}
      </div>
    );
  }

  const name = f(lead, LF.name) || "No name";
  const phone = f(lead, LF.phone);
  const email = f(lead, LF.email);
  const quote = f(lead, LF.quote);
  const status = f(lead, LF.status) || "New";
  const depositPaid = !!f(lead, LF.depositPaid);
  const latestInvoice = isOwner ? invoicesForLead(lead.id)[0] : null;
  const unpaidInvoice = latestInvoice && ["UNPAID", "PARTIALLY_PAID", "SCHEDULED"].includes(latestInvoice.status) ? latestInvoice : null;

  const stampNote = (line) => {
    const old = f(lead, LF.notes) || "";
    updateRecord("leads", lead.id, { [LF.notes]: old ? `${old}\n${line}` : line }).catch(() => {});
  };

  const extras = (schemas.leads || [])
    .filter((fd) => !KNOWN_LEAD_FIELD_IDS.has(fd.id))
    .map((fd) => ({ ...fd, display: formatExtraValue(f(lead, fd.id)) }))
    .filter((x) => f(lead, x.id) !== undefined && f(lead, x.id) !== null && x.display !== "");

  const noteEntries = (f(lead, LF.notes) || "").split("\n").map((s) => s.trim()).filter(Boolean).reverse();

  const setStatus = (v) => updateRecord("leads", lead.id, { [LF.status]: v }).catch(() => {});

  const startEdit = () => {
    setForm({
      name: f(lead, LF.name) || "",
      phone: f(lead, LF.phone) || "",
      email: f(lead, LF.email) || "",
      moveDate: (f(lead, LF.moveDate) || "").slice(0, 10),
      homeSize: f(lead, LF.homeSize) || "",
      from: f(lead, LF.from) || "",
      to: f(lead, LF.to) || "",
    });
    setEditing(true);
  };

  const setF = (k) => (e) => setForm((s) => ({ ...s, [k]: e.target.value }));

  const saveEdit = async () => {
    if (!form.name.trim()) {
      toast.error("The lead needs a name.");
      return;
    }
    setSavingEdit(true);
    const fields = {
      [LF.name]: form.name.trim(),
      [LF.phone]: form.phone,
      [LF.email]: form.email,
      [LF.from]: form.from,
      [LF.to]: form.to,
    };
    if (form.moveDate) fields[LF.moveDate] = form.moveDate;
    if (form.homeSize) fields[LF.homeSize] = form.homeSize;
    try {
      await updateRecord("leads", lead.id, fields);
      toast.success("Lead updated.");
      setEditing(false);
    } catch {}
    setSavingEdit(false);
  };

  const bookAsJob = async () => {
    setBooking(true);
    try {
      await bookLeadAsJob({ createRecord, updateRecord }, lead);
      toast.success("Job created. Find it on the Projects page.");
    } catch {}
    setBooking(false);
  };

  return (
    <div data-testid="lead-detail-page">
      <Button asChild variant="outline" size="sm" className="gap-1.5 mb-4" data-testid="lead-detail-back-btn">
        <Link to="/leads"><ArrowLeft className="w-4 h-4" /> Back to Leads</Link>
      </Button>

      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <Private className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight text-[#1B2A4A]" data-testid="lead-detail-name">{name}</Private>
            {status === "New" && <AgeTimer createdTime={lead.createdTime} />}
            {needsFollowUp(lead) && <FollowUpBadge days={quietDays(lead)} />}
          </div>
          <div className="text-sm text-slate-500 mt-1 space-x-3">
            {phone && <Private>{phone}</Private>}
            {email && <Private>{email}</Private>}
          </div>
        </div>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger data-testid="lead-detail-status-select" className={`w-[140px] h-9 text-sm font-semibold border ${STATUS_PILL[status] || ""}`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LEAD_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      <InstructionBanner testId="lead-detail-hint">{nextStepHint(lead)}</InstructionBanner>

      <div className="grid lg:grid-cols-2 gap-4 items-start">
        <div className="space-y-4">
          <div className="bg-white border border-slate-200 rounded-lg p-5 space-y-3" data-testid="lead-detail-info">
            <div className="flex items-center justify-between">
              <h2 className="font-display font-bold text-[#1B2A4A]">Move details</h2>
              {!editing && (
                <Button data-testid="lead-detail-edit-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={startEdit}>
                  <Pencil className="w-3.5 h-3.5" /> Edit
                </Button>
              )}
            </div>
            {editing ? (
              <div className="grid grid-cols-2 gap-3" data-testid="lead-detail-edit-form">
                <div className="col-span-2">
                  <Label>Name *</Label>
                  <Input data-testid="lead-edit-name-input" value={form.name} onChange={setF("name")} />
                </div>
                <div>
                  <Label>Phone</Label>
                  <Input data-testid="lead-edit-phone-input" value={form.phone} onChange={setF("phone")} />
                </div>
                <div>
                  <Label>Email</Label>
                  <Input data-testid="lead-edit-email-input" type="email" value={form.email} onChange={setF("email")} />
                </div>
                <div>
                  <Label>Move date</Label>
                  <Input data-testid="lead-edit-date-input" type="date" value={form.moveDate} onChange={setF("moveDate")} />
                </div>
                <div>
                  <Label>Home size</Label>
                  <Select value={form.homeSize} onValueChange={(v) => setForm((s) => ({ ...s, homeSize: v }))}>
                    <SelectTrigger data-testid="lead-edit-size-select"><SelectValue placeholder="Pick size" /></SelectTrigger>
                    <SelectContent>{HOME_SIZES.map((h) => <SelectItem key={h} value={h}>{h}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="col-span-2">
                  <Label>Moving from</Label>
                  <Input data-testid="lead-edit-from-input" value={form.from} onChange={setF("from")} />
                </div>
                <div className="col-span-2">
                  <Label>Moving to</Label>
                  <Input data-testid="lead-edit-to-input" value={form.to} onChange={setF("to")} />
                </div>
                <div className="col-span-2 flex gap-2">
                  <Button data-testid="lead-edit-save-btn" onClick={saveEdit} disabled={savingEdit} className="flex-1 gap-1.5 bg-[#E8743B] hover:bg-[#d4632e]">
                    <Save className="w-4 h-4" /> {savingEdit ? "Saving…" : "Save changes"}
                  </Button>
                  <Button data-testid="lead-edit-cancel-btn" variant="outline" onClick={() => setEditing(false)} className="gap-1.5">
                    <X className="w-4 h-4" /> Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <InfoRow icon={CalendarDays} label="Move date" isPrivate={false}>{fmtDate(f(lead, LF.moveDate))}</InfoRow>
                <InfoRow icon={Home} label="Home size" isPrivate={false}>{f(lead, LF.homeSize) || "Size TBD"}</InfoRow>
                <InfoRow icon={MapPin} label="Route">{f(lead, LF.from) || "?"} → {f(lead, LF.to) || "?"}</InfoRow>
                {(f(lead, LF.specialty) || []).length > 0 && (
                  <InfoRow icon={Package} label="Specialty" isPrivate={false}>{(f(lead, LF.specialty) || []).join(", ")}</InfoRow>
                )}
                {f(lead, LF.contactMethod) && <InfoRow icon={Phone} label="Prefers" isPrivate={false}>{f(lead, LF.contactMethod)}</InfoRow>}
                {f(lead, LF.source) && <InfoRow icon={Lightbulb} label="Source" isPrivate={false}>{f(lead, LF.source)}</InfoRow>}
                {extras.map((x) => (
                  <InfoRow key={x.id} icon={Lightbulb} label={x.name}>{x.display}</InfoRow>
                ))}
              </>
            )}
          </div>

          <div className="bg-white border border-slate-200 rounded-lg p-5" data-testid="lead-detail-quote">
            <h2 className="font-display font-bold text-[#1B2A4A] mb-2">Quote</h2>
            {quote ? (
              <div>
                <span className="font-bold text-[#1B2A4A] text-lg">Quoted: <Money value={quote} /></span>
                {!isSales && (
                  <span className={`ml-2 text-sm font-semibold ${depositPaid ? "text-emerald-600" : "text-amber-600"}`}>
                    {depositPaid ? "Deposit paid" : "No deposit yet"}
                  </span>
                )}
                <div className="text-xs text-slate-400 mt-1">Final price confirmed by phone.</div>
              </div>
            ) : (
              <span className="text-sm text-slate-400">No quote yet. Press Quote below to price this move.</span>
            )}
            {isOwner && invoicesForLead(lead.id).length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-3" data-testid="lead-detail-invoices">
                {invoicesForLead(lead.id).map((inv) => (
                  <InvoiceBadge key={inv.invoice_id} inv={inv} />
                ))}
              </div>
            )}
          </div>

          <div className="bg-white border border-slate-200 rounded-lg p-5" data-testid="lead-detail-actions">
            <h2 className="font-display font-bold text-[#1B2A4A] mb-3">Actions</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
              <Button data-testid="lead-detail-call-btn" asChild variant="outline" size="sm" className="gap-1 text-xs" disabled={!phone}>
                <a href={phone ? `tel:${phone}` : undefined}><Phone className="w-3.5 h-3.5" /> Call</a>
              </Button>
              <Button data-testid="lead-detail-email-btn" asChild variant="outline" size="sm" className="gap-1 text-xs">
                <a href={gmailCompose(email, "Your move with Haul Yeah Moving")} target="_blank" rel="noreferrer"><Mail className="w-3.5 h-3.5" /> Email</a>
              </Button>
              <Button data-testid="lead-detail-gmail-search-btn" asChild variant="outline" size="sm" className="gap-1 text-xs">
                <a href={gmailSearch(email || name)} target="_blank" rel="noreferrer"><Search className="w-3.5 h-3.5" /> Mail log</a>
              </Button>
              <Button data-testid="lead-detail-calendar-btn" asChild variant="outline" size="sm" className="gap-1 text-xs">
                <a
                  href={calendarTemplate(
                    `Move: ${name}`,
                    f(lead, LF.moveDate),
                    `Lead: ${name}\nEmail: ${email || "—"}\nPhone: ${phone || "—"}\nFrom: ${f(lead, LF.from) || "?"} → ${f(lead, LF.to) || "?"}`,
                    email
                  )}
                  target="_blank"
                  rel="noreferrer"
                >
                  <CalendarPlus className="w-3.5 h-3.5" /> Calendar
                </a>
              </Button>
              <Button data-testid="lead-detail-quote-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => setQuoteOpen(true)}>
                <Calculator className="w-3.5 h-3.5" /> Quote
              </Button>
              <Button data-testid="lead-detail-text-quote-btn" asChild variant="outline" size="sm" className="gap-1 text-xs" disabled={!phone || !quote}>
                <a href={phone && quote ? smsLink(phone, quoteSmsBody(name, quote, depositFromQuote(quote, rates.depositPercent))) : undefined}>
                  <MessageSquare className="w-3.5 h-3.5" /> Text quote
                </a>
              </Button>
              <Button data-testid="lead-detail-note-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => setNoteOpen(true)}>
                <StickyNote className="w-3.5 h-3.5" /> Add note
              </Button>
              {["Lost", "Cold"].includes(status) && (
                <Button data-testid="lead-detail-winback-btn" asChild variant="outline" size="sm" className="gap-1 text-xs border-sky-300 text-sky-700 hover:bg-sky-50 hover:text-sky-800" disabled={!phone}>
                  <a
                    href={phone ? smsLink(phone, winBackSmsBody(name)) : undefined}
                    onClick={() => stampNote(`Win-back text sent ${new Date().toLocaleDateString("en-US")}.`)}
                  >
                    <Undo2 className="w-3.5 h-3.5" /> Win back
                  </a>
                </Button>
              )}
              {unpaidInvoice && (
                <Button data-testid="lead-detail-nudge-btn" asChild variant="outline" size="sm" className="gap-1 text-xs border-amber-300 text-amber-700 hover:bg-amber-50 hover:text-amber-800" disabled={!phone}>
                  <a
                    href={phone ? smsLink(phone, payNudgeSmsBody(name, unpaidInvoice.amount, unpaidInvoice.public_url)) : undefined}
                    onClick={() => stampNote(`Payment nudge text sent ${new Date().toLocaleDateString("en-US")}.`)}
                  >
                    <BellRing className="w-3.5 h-3.5" /> Nudge pay
                  </a>
                </Button>
              )}
              {!isSales && (
                <>
                  <Button data-testid="lead-detail-deposit-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => setDepositOpen(true)} disabled={!quote}>
                    <CreditCard className="w-3.5 h-3.5" /> Deposit
                  </Button>
                  <Button data-testid="lead-detail-square-invoice-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => setInvoiceOpen(true)}>
                    <FileText className="w-3.5 h-3.5" /> Invoice
                  </Button>
                  <Button
                    data-testid="lead-detail-book-btn"
                    size="sm"
                    className="gap-1 text-xs bg-[#1B2A4A] hover:bg-[#26395f]"
                    onClick={bookAsJob}
                    disabled={booking || status === "Booked"}
                  >
                    <Truck className="w-3.5 h-3.5" /> {status === "Booked" ? "Booked" : booking ? "Booking…" : "Book as job"}
                  </Button>
                </>
              )}
              {isOwner && (
                <ConfirmDeleteButton
                  what="this lead"
                  testId="lead-detail-delete-btn"
                  onConfirm={() =>
                    deleteRecord("leads", lead.id)
                      .then(() => { toast.success("Lead deleted."); navigate("/leads"); })
                      .catch(() => {})
                  }
                />
              )}
            </div>
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-lg p-5" data-testid="lead-detail-notes">
          <h2 className="font-display font-bold text-[#1B2A4A] mb-3 flex items-center gap-2">
            <History className="w-4 h-4 text-[#E8743B]" /> Notes history
          </h2>
          {noteEntries.length === 0 ? (
            <EmptyState>No notes yet. Press "Add note" after every call or text.</EmptyState>
          ) : (
            <div className="space-y-2">
              {noteEntries.map((line, i) => (
                <div key={i} data-testid="lead-note-entry" className="flex items-start gap-2 text-sm border border-slate-100 bg-slate-50/70 rounded-md px-3 py-2">
                  <StickyNote className="w-3.5 h-3.5 text-slate-400 mt-0.5 shrink-0" />
                  <Private className="min-w-0 break-words whitespace-pre-wrap">{line}</Private>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {quoteOpen && <QuoteModal key={lead.id} lead={lead} open={quoteOpen} onOpenChange={setQuoteOpen} />}
      {depositOpen && <DepositModal lead={lead} open={depositOpen} onOpenChange={setDepositOpen} />}
      {noteOpen && <AddNoteDialog lead={lead} open={noteOpen} onOpenChange={setNoteOpen} />}
      {invoiceOpen && <SquareInvoiceModal lead={lead} open={invoiceOpen} onOpenChange={setInvoiceOpen} />}
    </div>
  );
}
