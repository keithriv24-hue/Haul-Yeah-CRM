import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Phone, Mail, Calculator, CreditCard, Truck, Plus, MapPin, CalendarDays, CalendarPlus, Home, Lightbulb, Package, StickyNote, Search, MessageSquare, ChevronRight } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/components/AuthGate";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, Private, Money, AgeTimer, EmptyState, LoadingRows, ConfirmDeleteButton, FollowUpBadge } from "@/components/Bits";
import QuoteModal from "@/components/QuoteModal";
import DepositModal from "@/components/DepositModal";
import LeadModal from "@/components/LeadModal";
import { LF, f, LEAD_STATUSES, STATUS_PILL, nextStepHint, KNOWN_LEAD_FIELD_IDS, formatExtraValue, needsFollowUp, quietDays } from "@/lib/fields";
import { fmtDate, gmailCompose, gmailSearch, calendarTemplate, smsLink } from "@/lib/format";
import { quoteSmsBody } from "@/lib/quote";
import { lowFromHigh, depositFromQuote } from "@/lib/pricing";
import { bookLeadAsJob } from "@/lib/leadActions";

export const AddNoteDialog = ({ lead, open, onOpenChange }) => {
  const { updateRecord } = useApp();
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const save = async () => {
    if (!text.trim()) return;
    setSaving(true);
    const oldNotes = f(lead, LF.notes) || "";
    const line = `Note ${new Date().toLocaleDateString("en-US")}: ${text.trim()}`;
    try {
      await updateRecord("leads", lead.id, { [LF.notes]: oldNotes ? `${oldNotes}\n${line}` : line });
      toast.success("Note added.");
      setText("");
      onOpenChange(false);
    } catch {}
    setSaving(false);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="add-note-modal" className="max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <StickyNote className="w-5 h-5 text-[#E8743B]" /> Add note for {f(lead, LF.name) || "lead"}
          </DialogTitle>
          <DialogDescription>Write what happened. It saves to the lead's notes.</DialogDescription>
        </DialogHeader>
        <div>
          <Label>Note</Label>
          <Textarea data-testid="add-note-input" rows={3} value={text} onChange={(e) => setText(e.target.value)} />
        </div>
        <Button data-testid="add-note-save-btn" onClick={save} disabled={saving || !text.trim()} className="w-full gap-2 bg-[#E8743B] hover:bg-[#d4632e]">
          <StickyNote className="w-4 h-4" /> {saving ? "Saving…" : "Save note"}
        </Button>
      </DialogContent>
    </Dialog>
  );
};

const LeadCard = ({ lead, onQuote, onDeposit, onNote }) => {
  const { updateRecord, createRecord, deleteRecord, schemas } = useApp();
  const { role } = useAuth();
  const isSales = role === "sales";
  const isOwner = role === "owner";
  const [booking, setBooking] = useState(false);

  const extras = (schemas.leads || [])
    .filter((fd) => !KNOWN_LEAD_FIELD_IDS.has(fd.id))
    .map((fd) => ({ ...fd, display: formatExtraValue(f(lead, fd.id)) }))
    .filter((x) => f(lead, x.id) !== undefined && f(lead, x.id) !== null && x.display !== "");
  const status = f(lead, LF.status) || "New";
  const name = f(lead, LF.name) || "No name";
  const phone = f(lead, LF.phone);
  const email = f(lead, LF.email);
  const quote = f(lead, LF.quote);
  const depositPaid = !!f(lead, LF.depositPaid);
  const isSample = f(lead, LF.source) === "Sample Data";

  const setStatus = (v) => updateRecord("leads", lead.id, { [LF.status]: v }).catch(() => {});

  const bookAsJob = async () => {
    setBooking(true);
    try {
      await bookLeadAsJob({ createRecord, updateRecord }, lead);
      toast.success("Job created. Find it on the Projects page.");
    } catch {}
    setBooking(false);
  };

  return (
    <div data-testid="lead-card" className="bg-white border border-slate-200 rounded-lg p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Link to={`/leads/${lead.id}`} data-testid="lead-open-link" className="group flex items-center gap-0.5 min-w-0">
              <Private className="font-display font-bold text-lg text-[#1B2A4A] truncate group-hover:underline">{name}</Private>
              <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-[#E8743B] shrink-0" />
            </Link>
            {isSample && <span className="text-[10px] font-bold uppercase tracking-wide bg-slate-100 text-slate-500 border border-slate-300 rounded-full px-2 py-0.5">Sample</span>}
          </div>
          <div className="text-xs text-slate-500 mt-0.5 space-x-2">
            {phone && <Private>{phone}</Private>}
            {email && <Private>{email}</Private>}
          </div>
        </div>
        {status === "New" && <AgeTimer createdTime={lead.createdTime} />}
        {needsFollowUp(lead) && <FollowUpBadge days={quietDays(lead)} />}
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-600">
        <span className="flex items-center gap-1"><CalendarDays className="w-3.5 h-3.5 text-slate-400" /> {fmtDate(f(lead, LF.moveDate))}</span>
        <span className="flex items-center gap-1"><Home className="w-3.5 h-3.5 text-slate-400" /> {f(lead, LF.homeSize) || "Size TBD"}</span>
        <span className="col-span-2 flex items-center gap-1 min-w-0">
          <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <Private className="truncate">{f(lead, LF.from) || "?"} → {f(lead, LF.to) || "?"}</Private>
        </span>
        {(f(lead, LF.specialty) || []).length > 0 && (
          <span className="col-span-2 flex items-center gap-1 min-w-0">
            <Package className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            <span className="truncate">{(f(lead, LF.specialty) || []).join(", ")}</span>
          </span>
        )}
      </div>

      {extras.length > 0 && (
        <div data-testid="lead-extra-fields" className="space-y-1 text-xs text-slate-600 border-t border-slate-100 pt-2">
          {extras.map((x) => (
            <div key={x.id} className="flex gap-1.5">
              <span className="font-semibold text-slate-500 shrink-0">{x.name}:</span>
              <Private className="min-w-0 break-words">{x.display}</Private>
            </div>
          ))}
        </div>
      )}

      {f(lead, LF.notes) && (
        <p data-testid="lead-notes-preview" className="text-xs text-slate-500 line-clamp-2 whitespace-pre-wrap border-t border-slate-100 pt-2">
          {f(lead, LF.notes)}
        </p>
      )}

      <div className="flex items-center justify-between gap-2 border-t border-slate-100 pt-2">
        <div className="text-sm">
          {quote ? (
            <div>
              <span className="font-bold text-[#1B2A4A]">Quoted: <Money value={quote} /></span>
              {!isSales && (
                <span className={`ml-2 text-xs font-semibold ${depositPaid ? "text-emerald-600" : "text-amber-600"}`}>
                  {depositPaid ? "Deposit paid" : "No deposit yet"}
                </span>
              )}
              <div className="text-[10px] text-slate-400">Final price confirmed by phone.</div>
            </div>
          ) : (
            <span className="text-xs text-slate-400">No quote yet</span>
          )}
        </div>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger data-testid="lead-status-select" className={`w-[120px] h-8 text-xs font-semibold border ${STATUS_PILL[status] || ""}`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LEAD_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-start gap-1.5 text-xs text-[#1B2A4A] bg-[#E8743B]/10 border border-[#E8743B]/25 rounded-md px-2.5 py-1.5">
        <Lightbulb className="w-3.5 h-3.5 text-[#E8743B] mt-0.5 shrink-0" />
        <span data-testid="lead-next-step">{nextStepHint(lead)}</span>
      </div>

      <div className={`grid grid-cols-2 gap-1.5 ${isSales ? "sm:grid-cols-4" : "sm:grid-cols-5"}`}>
        <Button data-testid="lead-call-btn" asChild variant="outline" size="sm" className="gap-1 text-xs" disabled={!phone}>
          <a href={phone ? `tel:${phone}` : undefined}><Phone className="w-3.5 h-3.5" /> Call</a>
        </Button>
        <Button data-testid="lead-email-btn" asChild variant="outline" size="sm" className="gap-1 text-xs">
          <a href={gmailCompose(email, "Your move with Haul Yeah Moving")} target="_blank" rel="noreferrer">
            <Mail className="w-3.5 h-3.5" /> Email
          </a>
        </Button>
        <Button data-testid="lead-gmail-search-btn" asChild variant="outline" size="sm" className="gap-1 text-xs">
          <a href={gmailSearch(email || name)} target="_blank" rel="noreferrer">
            <Search className="w-3.5 h-3.5" /> Mail log
          </a>
        </Button>
        <Button data-testid="lead-calendar-btn" asChild variant="outline" size="sm" className="gap-1 text-xs">
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
        <Button data-testid="lead-quote-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => onQuote(lead)}>
          <Calculator className="w-3.5 h-3.5" /> Quote
        </Button>
        <Button data-testid="lead-text-quote-btn" asChild variant="outline" size="sm" className="gap-1 text-xs" disabled={!phone || !quote}>
          <a href={phone && quote ? smsLink(phone, quoteSmsBody(name, lowFromHigh(quote), quote, depositFromQuote(quote))) : undefined}>
            <MessageSquare className="w-3.5 h-3.5" /> Text quote
          </a>
        </Button>
        <Button data-testid="lead-note-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => onNote(lead)}>
          <StickyNote className="w-3.5 h-3.5" /> Add note
        </Button>
        {!isSales && (
          <>
            <Button data-testid="lead-deposit-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => onDeposit(lead)} disabled={!quote}>
              <CreditCard className="w-3.5 h-3.5" /> Deposit
            </Button>
            <Button
              data-testid="lead-book-btn"
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
            what={`this lead`}
            testId="lead-delete-btn"
            onConfirm={() => deleteRecord("leads", lead.id).then(() => toast.success("Lead deleted.")).catch(() => {})}
          />
        )}
      </div>
    </div>
  );
};

export default function Leads() {
  const { loadTable, loadSchema, records, tableState } = useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const filter = searchParams.get("filter") || "All";
  const setFilter = (v) => setSearchParams(v === "All" ? {} : { filter: v });
  const [quoteLead, setQuoteLead] = useState(null);
  const [depositLead, setDepositLead] = useState(null);
  const [noteLead, setNoteLead] = useState(null);
  const [newOpen, setNewOpen] = useState(false);

  useEffect(() => {
    loadTable("leads");
    loadSchema("leads");
  }, [loadTable, loadSchema]);

  const all = [...records("leads")].sort((a, b) => (b.createdTime || "").localeCompare(a.createdTime || ""));
  const callbackCount = all.filter(needsFollowUp).length;
  const leads = filter === "All" ? all : filter === "Call back" ? all.filter(needsFollowUp) : all.filter((l) => f(l, LF.status) === filter);
  const { loading, error } = tableState("leads");

  return (
    <div data-testid="leads-page">
      <PageTitle
        title="Leads"
        subtitle="Speed wins jobs. Call New leads in under 5 minutes."
        action={
          <Button data-testid="new-lead-btn" onClick={() => setNewOpen(true)} className="gap-1.5 bg-[#E8743B] hover:bg-[#d4632e]">
            <Plus className="w-4 h-4" /> New lead
          </Button>
        }
      />
      <InstructionBanner>Call New leads fast — under 5 minutes wins the job. Use the buttons on each card to call, quote, and book.</InstructionBanner>

      <div className="flex gap-2 overflow-x-auto no-scrollbar pb-1 mb-5">
        {["All", "Call back", ...LEAD_STATUSES].map((s) => (
          <button
            key={s}
            data-testid={`lead-filter-${s.toLowerCase().replace(/\s+/g, "-")}`}
            onClick={() => setFilter(s)}
            className={`shrink-0 rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-colors ${
              filter === s
                ? s === "Call back"
                  ? "bg-red-600 text-white border-red-600"
                  : "bg-[#1B2A4A] text-white border-[#1B2A4A]"
                : s === "Call back" && callbackCount > 0
                ? "bg-red-50 text-red-600 border-red-300 hover:border-red-500"
                : "bg-white text-slate-600 border-slate-300 hover:border-[#1B2A4A]"
            }`}
          >
            {s} {s === "Call back" ? `(${callbackCount})` : s !== "All" && `(${all.filter((l) => f(l, LF.status) === s).length})`}
          </button>
        ))}
      </div>

      {loading && !all.length ? (
        <LoadingRows />
      ) : error && !all.length ? (
        <EmptyState>{error}</EmptyState>
      ) : leads.length === 0 ? (
        <EmptyState>No leads here. Press "+ New lead" to add one.</EmptyState>
      ) : (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
          {leads.map((l) => (
            <LeadCard key={l.id} lead={l} onQuote={setQuoteLead} onDeposit={setDepositLead} onNote={setNoteLead} />
          ))}
        </div>
      )}

      {quoteLead && <QuoteModal key={quoteLead.id} lead={quoteLead} open={!!quoteLead} onOpenChange={(o) => !o && setQuoteLead(null)} />}
      {depositLead && <DepositModal lead={depositLead} open={!!depositLead} onOpenChange={(o) => !o && setDepositLead(null)} />}
      {noteLead && <AddNoteDialog lead={noteLead} open={!!noteLead} onOpenChange={(o) => !o && setNoteLead(null)} />}
      <LeadModal open={newOpen} onOpenChange={setNewOpen} />
    </div>
  );
}
