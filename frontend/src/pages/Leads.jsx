import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Phone, Mail, Calculator, CreditCard, Truck, Plus, MapPin, CalendarDays, CalendarPlus, Home, Lightbulb, Package, StickyNote, Search, MessageSquare, ChevronRight, FileText, Undo2, BellRing } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/components/AuthGate";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, Private, Money, AgeTimer, EmptyState, LoadingRows, ConfirmDeleteButton, FollowUpBadge, InvoiceBadge, SearchBar, searchMatch } from "@/components/Bits";
import QuotePdfModal from "@/components/QuotePdfModal";
import DepositModal from "@/components/DepositModal";
import LeadModal from "@/components/LeadModal";
import SquareInvoiceModal from "@/components/SquareInvoiceModal";
import { LF, f, LEAD_STATUSES, nextStepHint, KNOWN_LEAD_FIELD_IDS, formatExtraValue, needsFollowUp, quietDays } from "@/lib/fields";
import { fmtDate, gmailCompose, gmailSearch, calendarTemplate, smsLink, winBackSmsBody, payNudgeSmsBody } from "@/lib/format";
import { quoteSmsBody } from "@/lib/quote";
import { depositFromQuote } from "@/lib/pricing";
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
            <StickyNote className="w-5 h-5 text-accent-ink" /> Add note for {f(lead, LF.name) || "lead"}
          </DialogTitle>
          <DialogDescription>Write what happened. It saves to the lead's notes.</DialogDescription>
        </DialogHeader>
        <div>
          <Label>Note</Label>
          <Textarea data-testid="add-note-input" rows={3} value={text} onChange={(e) => setText(e.target.value)} />
        </div>
        <Button data-testid="add-note-save-btn" onClick={save} disabled={saving || !text.trim()} className="w-full gap-2 bg-accent hover:bg-accent-press">
          <StickyNote className="w-4 h-4" /> {saving ? "Saving…" : "Save note"}
        </Button>
      </DialogContent>
    </Dialog>
  );
};

/**
 * One lead. The card follows a strict action ladder:
 *   1 accent band  — the single next thing to do, taken from nextStepHint()
 *   3 outline      — the other things you reach for on most calls
 *   n text links   — everything else, still one tap away, visually quiet
 * Nothing is hidden from the DOM; it is ranked, not buried.
 */
const LeadCard = ({ lead, onQuote, onDeposit, onNote, onInvoice, onPdf }) => {
  const { updateRecord, createRecord, deleteRecord, schemas, invoicesForLead, rates } = useApp();
  const { role } = useAuth();
  const isSales = role === "sales";
  const isOwner = role === "owner";
  const [booking, setBooking] = useState(false);
  const [showExtras, setShowExtras] = useState(false);
  const latestInvoice = isOwner ? invoicesForLead(lead.id)[0] : null;
  const unpaidInvoice = latestInvoice && ["UNPAID", "PARTIALLY_PAID", "SCHEDULED"].includes(latestInvoice.status) ? latestInvoice : null;

  const extras = (schemas.leads || [])
    .filter((fd) => !KNOWN_LEAD_FIELD_IDS.has(fd.id))
    .map((fd) => ({ ...fd, display: formatExtraValue(f(lead, fd.id)) }))
    .filter((x) => f(lead, x.id) !== undefined && f(lead, x.id) !== null && x.display !== "");
  const status = f(lead, LF.status) || "New";
  const name = f(lead, LF.name) || "No name";
  const firstName = String(name).split(" ")[0];
  const phone = f(lead, LF.phone);
  const email = f(lead, LF.email);
  const quote = f(lead, LF.quote);
  const depositPaid = !!f(lead, LF.depositPaid);
  const isSample = f(lead, LF.source) === "Sample Data";
  const specialty = (f(lead, LF.specialty) || []).filter((x) => x && x !== "None");

  const setStatus = (v) => updateRecord("leads", lead.id, { [LF.status]: v }).catch(() => {});

  const bookAsJob = async () => {
    setBooking(true);
    try {
      await bookLeadAsJob({ createRecord, updateRecord }, lead);
      toast.success("Job created. Find it on the Projects page.");
    } catch {}
    setBooking(false);
  };

  const stampNote = (line) => {
    const old = f(lead, LF.notes) || "";
    updateRecord("leads", lead.id, { [LF.notes]: old ? `${old}\n${line}` : line }).catch(() => {});
  };

  const callHref = phone ? `tel:${phone}` : undefined;
  const textQuoteHref =
    phone && quote ? smsLink(phone, quoteSmsBody(name, quote, depositFromQuote(quote, rates.depositPercent))) : undefined;

  /* The loudest button on the card mirrors nextStepHint(), so the sentence and
     the button never disagree about what to do next. */
  const primary = (() => {
    if (status === "Booked" && !isSales) {
      return { key: "book", node: (
        <Button data-testid="lead-book-btn" size="band" variant="outline" disabled className="gap-2">
          <Truck className="w-4 h-4" /> Booked — manage in Projects
        </Button>
      )};
    }
    if (status === "Quoted" && quote && depositPaid && !isSales) {
      return { key: "book", node: (
        <Button data-testid="lead-book-btn" size="band" variant="accent" onClick={bookAsJob} disabled={booking} className="gap-2">
          <Truck className="w-4 h-4" /> {booking ? "Booking…" : "Book as job"}
        </Button>
      )};
    }
    if (status === "Quoted" && quote && !depositPaid && !isSales) {
      return { key: "deposit", node: (
        <Button data-testid="lead-deposit-btn" size="band" variant="accent" onClick={() => onDeposit(lead)} className="gap-2">
          <CreditCard className="w-4 h-4" /> Send deposit link
        </Button>
      )};
    }
    if (["Contacted", "Warm", "Hot"].includes(status) && !quote) {
      return { key: "quote", node: (
        <Button data-testid="lead-quote-btn" size="band" variant="accent" onClick={() => onQuote(lead)} className="gap-2">
          <Calculator className="w-4 h-4" /> Price this move
        </Button>
      )};
    }
    return { key: "call", node: (
      <Button data-testid="lead-call-btn" asChild size="band" variant="accent" disabled={!phone} className="gap-2">
        <a href={callHref}>
          <Phone className="w-4 h-4" /> {phone ? `Call ${firstName}` : "No phone number"}
        </a>
      </Button>
    )};
  })();

  /* Secondary row — rendered unless that action is already the primary. */
  const secondary = [
    primary.key !== "call" && (
      <Button key="call" data-testid="lead-call-btn" asChild variant="outline" size="sm" className="gap-1.5" disabled={!phone}>
        <a href={callHref}><Phone className="w-3.5 h-3.5" /> Call</a>
      </Button>
    ),
    primary.key !== "quote" && (
      <Button key="quote" data-testid="lead-quote-btn" variant="outline" size="sm" className="gap-1.5" onClick={() => onQuote(lead)}>
        <Calculator className="w-3.5 h-3.5" /> Quote
      </Button>
    ),
    <Button key="text" data-testid="lead-text-quote-btn" asChild variant="outline" size="sm" className="gap-1.5" disabled={!textQuoteHref}>
      <a href={textQuoteHref}><MessageSquare className="w-3.5 h-3.5" /> Text quote</a>
    </Button>,
    <Button key="email" data-testid="lead-email-btn" asChild variant="outline" size="sm" className="gap-1.5">
      <a href={gmailCompose(email, "Your move with Haul Yeah Moving")} target="_blank" rel="noreferrer">
        <Mail className="w-3.5 h-3.5" /> Email
      </a>
    </Button>,
  ].filter(Boolean).slice(0, 3);

  const linkCls = "inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[12.5px] font-semibold text-ink-2 transition-colors hover:bg-surface-sunk hover:text-primary";

  return (
    <div data-testid="lead-card" className="surface-interactive flex flex-col gap-3 p-4">
      {/* --- identity ------------------------------------------------- */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <Link to={`/leads/${lead.id}`} data-testid="lead-open-link" className="group flex items-center gap-0.5 min-w-0">
              <Private className="font-display font-extrabold text-[19px] leading-tight text-primary truncate group-hover:underline decoration-2 underline-offset-2">{name}</Private>
              <ChevronRight className="w-4 h-4 text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-accent-ink shrink-0" />
            </Link>
            {isSample && (
              <span className="rounded bg-surface-sunk px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-faint">Sample</span>
            )}
          </div>
          {(phone || email) && (
            <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[12.5px] text-faint">
              {phone && <Private className="tnum">{phone}</Private>}
              {email && <Private className="truncate">{email}</Private>}
            </div>
          )}
        </div>
        <div className="flex flex-col items-end gap-1.5 shrink-0">
          {status === "New" && <AgeTimer createdTime={lead.createdTime} />}
          {needsFollowUp(lead) && <FollowUpBadge days={quietDays(lead)} />}
        </div>
      </div>

      {/* --- the move ------------------------------------------------- */}
      <div className="rounded-lg bg-surface-sunk px-3 py-2.5">
        <Private className="flex items-center gap-1.5 text-[14px] font-semibold text-ink">
          <MapPin className="w-4 h-4 text-faint shrink-0" aria-hidden="true" />
          <span className="truncate">{f(lead, LF.from) || "?"} → {f(lead, LF.to) || "?"}</span>
        </Private>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-ink-2">
          <span className="inline-flex items-center gap-1"><CalendarDays className="w-3.5 h-3.5 text-faint" aria-hidden="true" /> {fmtDate(f(lead, LF.moveDate))}</span>
          <span className="inline-flex items-center gap-1"><Home className="w-3.5 h-3.5 text-faint" aria-hidden="true" /> {f(lead, LF.homeSize) || "Size TBD"}</span>
          {specialty.length > 0 && (
            <span className="inline-flex items-center gap-1 min-w-0">
              <Package className="w-3.5 h-3.5 text-faint shrink-0" aria-hidden="true" />
              <span className="truncate">{specialty.join(", ")}</span>
            </span>
          )}
        </div>
      </div>

      {/* --- money + status ------------------------------------------- */}
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          {quote ? (
            <>
              <span className="font-display text-[17px] font-extrabold text-primary"><Money value={quote} /></span>
              {!isSales && (
                <span className={`ml-2 text-[12px] font-semibold ${depositPaid ? "text-success" : "text-warning"}`}>
                  {depositPaid ? "deposit paid" : "no deposit yet"}
                </span>
              )}
              <span className="block text-[11px] text-faint">Final price confirmed by phone.</span>
            </>
          ) : (
            <span className="text-[13px] text-faint">No quote yet</span>
          )}
        </div>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger data-testid="lead-status-select" className="w-[118px] h-9 text-[12.5px] font-semibold shrink-0">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LEAD_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {latestInvoice && <InvoiceBadge inv={latestInvoice} />}

      {/* --- what to do next ------------------------------------------ */}
      <p className="flex items-start gap-1.5 text-[13px] text-ink-2">
        <Lightbulb className="w-3.5 h-3.5 mt-0.5 shrink-0 text-faint" aria-hidden="true" />
        <span data-testid="lead-next-step">{nextStepHint(lead)}</span>
      </p>

      {/* --- action ladder -------------------------------------------- */}
      <div className="space-y-2">
        {primary.node}
        <div className="grid grid-cols-3 gap-1.5">{secondary}</div>
      </div>

      {/* --- quiet actions -------------------------------------------- */}
      <div className="flex flex-wrap items-center gap-x-0.5 gap-y-1 border-t border-border pt-2 -mx-1">
        <a data-testid="lead-gmail-search-btn" href={gmailSearch(email || name)} target="_blank" rel="noreferrer" className={linkCls}>
          <Search className="w-3.5 h-3.5" aria-hidden="true" /> Mail log
        </a>
        <a
          data-testid="lead-calendar-btn"
          href={calendarTemplate(
            `Move: ${name}`,
            f(lead, LF.moveDate),
            `Lead: ${name}\nEmail: ${email || "—"}\nPhone: ${phone || "—"}\nFrom: ${f(lead, LF.from) || "?"} → ${f(lead, LF.to) || "?"}`,
            email
          )}
          target="_blank"
          rel="noreferrer"
          className={linkCls}
        >
          <CalendarPlus className="w-3.5 h-3.5" aria-hidden="true" /> Calendar
        </a>
        <button data-testid="lead-note-btn" onClick={() => onNote(lead)} className={linkCls}>
          <StickyNote className="w-3.5 h-3.5" aria-hidden="true" /> Add note
        </button>
        {!!quote && ["Quoted", "Booked"].includes(status) && (
          <button data-testid="lead-pdf-btn" onClick={() => onPdf(lead)} className={linkCls}>
            <FileText className="w-3.5 h-3.5" aria-hidden="true" /> Quote PDF
          </button>
        )}
        {["Lost", "Cold"].includes(status) && phone && (
          <a
            data-testid="lead-winback-btn"
            href={smsLink(phone, winBackSmsBody(name))}
            onClick={() => stampNote(`Win-back text sent ${new Date().toLocaleDateString("en-US")}.`)}
            className={linkCls}
          >
            <Undo2 className="w-3.5 h-3.5" aria-hidden="true" /> Win back
          </a>
        )}
        {unpaidInvoice && phone && (
          <a
            data-testid="lead-nudge-btn"
            href={smsLink(phone, payNudgeSmsBody(name, unpaidInvoice.amount, unpaidInvoice.public_url))}
            onClick={() => stampNote(`Payment nudge text sent ${new Date().toLocaleDateString("en-US")}.`)}
            className={`${linkCls} text-warning hover:text-warning`}
          >
            <BellRing className="w-3.5 h-3.5" aria-hidden="true" /> Nudge pay
          </a>
        )}
        {!isSales && (
          <>
            {primary.key !== "deposit" && (
              <button data-testid="lead-deposit-btn" onClick={() => onDeposit(lead)} disabled={!quote} className={`${linkCls} disabled:opacity-40`}>
                <CreditCard className="w-3.5 h-3.5" aria-hidden="true" /> Deposit
              </button>
            )}
            <button data-testid="lead-square-invoice-btn" onClick={() => onInvoice(lead)} className={linkCls}>
              <FileText className="w-3.5 h-3.5" aria-hidden="true" /> Invoice
            </button>
            {primary.key !== "book" && (
              <button data-testid="lead-book-btn" onClick={bookAsJob} disabled={booking} className={linkCls}>
                <Truck className="w-3.5 h-3.5" aria-hidden="true" /> {booking ? "Booking…" : "Book as job"}
              </button>
            )}
          </>
        )}
        {isOwner && (
          <ConfirmDeleteButton
            what="this lead"
            testId="lead-delete-btn"
            className="ml-auto"
            onConfirm={() => deleteRecord("leads", lead.id).then(() => toast.success("Lead deleted.")).catch(() => {})}
          />
        )}
      </div>

      {/* --- notes and raw fields, folded away by default -------------- */}
      {f(lead, LF.notes) && (
        <p data-testid="lead-notes-preview" className="border-t border-border pt-2 text-[12.5px] leading-relaxed text-faint line-clamp-3 whitespace-pre-wrap">
          {f(lead, LF.notes)}
        </p>
      )}

      {extras.length > 0 && (
        <div className="border-t border-border pt-2">
          <button
            data-testid="lead-extra-toggle"
            onClick={() => setShowExtras((v) => !v)}
            className="text-[12px] font-semibold text-faint transition-colors hover:text-primary"
            aria-expanded={showExtras}
          >
            {showExtras ? "Hide" : "Show"} {extras.length} tracking {extras.length === 1 ? "field" : "fields"}
          </button>
          {showExtras && (
            <div data-testid="lead-extra-fields" className="mt-2 space-y-1 text-[12px] text-ink-2 animate-fade-up">
              {extras.map((x) => (
                <div key={x.id} className="flex gap-1.5">
                  <span className="shrink-0 font-semibold text-faint">{x.name}:</span>
                  <Private className="min-w-0 break-all">{x.display}</Private>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default function Leads() {
  const { loadTable, loadSchema, records, tableState, loadSquareInvoices } = useApp();
  const { role } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const filter = searchParams.get("filter") || "All";
  const setFilter = (v) => setSearchParams(v === "All" ? {} : { filter: v });
  const navigate = useNavigate();
  const openScope = (l) => navigate(`/scope-calculator?lead=${l.id}&name=${encodeURIComponent(f(l, LF.name) || "")}`);
  const [pdfLead, setPdfLead] = useState(null);
  const [depositLead, setDepositLead] = useState(null);
  const [noteLead, setNoteLead] = useState(null);
  const [invoiceLead, setInvoiceLead] = useState(null);
  const [newOpen, setNewOpen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    loadTable("leads");
    loadSchema("leads");
    if (role === "owner") loadSquareInvoices();
  }, [loadTable, loadSchema, loadSquareInvoices, role]);

  const all = [...records("leads")].sort((a, b) => (b.createdTime || "").localeCompare(a.createdTime || ""));
  const callbackCount = all.filter(needsFollowUp).length;
  const byFilter = filter === "All" ? all : filter === "Call back" ? all.filter(needsFollowUp) : all.filter((l) => f(l, LF.status) === filter);
  const leads = byFilter.filter((l) => searchMatch(query, f(l, LF.name), f(l, LF.phone), f(l, LF.email), f(l, LF.from), f(l, LF.to), f(l, LF.notes)));
  const { loading, error } = tableState("leads");

  return (
    <div data-testid="leads-page">
      <PageTitle
        title="Leads"
        subtitle="Speed wins jobs. Call New leads in under 5 minutes."
        action={
          <Button data-testid="new-lead-btn" onClick={() => setNewOpen(true)} variant="accent" className="gap-1.5">
            <Plus className="w-4 h-4" /> New lead
          </Button>
        }
      />
      <InstructionBanner>Call New leads fast — under 5 minutes wins the job. Use the buttons on each card to call, quote, and book.</InstructionBanner>

      <div className="mb-4">
        <SearchBar value={query} onChange={setQuery} placeholder="Search name, phone, email, or address…" testId="leads-search-input" />
      </div>

      <div className="flex gap-2 overflow-x-auto no-scrollbar pb-1 mb-5">
        {["All", "Call back", ...LEAD_STATUSES].map((s) => (
          <button
            key={s}
            data-testid={`lead-filter-${s.toLowerCase().replace(/\s+/g, "-")}`}
            onClick={() => setFilter(s)}
            className={`press shrink-0 rounded-lg px-3 py-2 text-[12.5px] font-semibold transition-colors duration-[160ms] ${
              filter === s
                ? "bg-primary text-white"
                : s === "Call back" && callbackCount > 0
                ? "bg-destructive/10 text-destructive hover:bg-destructive/15"
                : "bg-surface-sunk text-ink-2 hover:bg-muted hover:text-ink"
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
        <EmptyState>{query ? "No leads match that search." : 'No leads here. Press "+ New lead" to add one.'}</EmptyState>
      ) : (
        <div className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3">
          {leads.map((l) => (
            <LeadCard key={l.id} lead={l} onQuote={openScope} onDeposit={setDepositLead} onNote={setNoteLead} onInvoice={setInvoiceLead} onPdf={setPdfLead} />
          ))}
        </div>
      )}

      {pdfLead && <QuotePdfModal key={pdfLead.id} lead={pdfLead} open={!!pdfLead} onOpenChange={(o) => !o && setPdfLead(null)} />}
      {depositLead && <DepositModal lead={depositLead} open={!!depositLead} onOpenChange={(o) => !o && setDepositLead(null)} />}
      {noteLead && <AddNoteDialog lead={noteLead} open={!!noteLead} onOpenChange={(o) => !o && setNoteLead(null)} />}
      {invoiceLead && <SquareInvoiceModal lead={invoiceLead} open={!!invoiceLead} onOpenChange={(o) => !o && setInvoiceLead(null)} />}
      <LeadModal open={newOpen} onOpenChange={setNewOpen} />
    </div>
  );
}
