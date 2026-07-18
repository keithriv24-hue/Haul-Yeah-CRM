import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Phone, Mail, Calculator, CreditCard, Truck, Plus, MapPin, CalendarDays, Home, Lightbulb } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, Private, Money, AgeTimer, EmptyState, LoadingRows } from "@/components/Bits";
import QuoteModal from "@/components/QuoteModal";
import DepositModal from "@/components/DepositModal";
import LeadModal from "@/components/LeadModal";
import { LF, PF, f, LEAD_STATUSES, STATUS_PILL, nextStepHint } from "@/lib/fields";
import { fmtDate, gmailCompose } from "@/lib/format";

const LeadCard = ({ lead, onQuote, onDeposit }) => {
  const { updateRecord, createRecord } = useApp();
  const [booking, setBooking] = useState(false);
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
      const fields = {
        [PF.jobName]: `${name} — ${f(lead, LF.moveDate) ? fmtDate(f(lead, LF.moveDate)) : "date TBD"}`,
        [PF.status]: "Pending Deposit",
        [PF.lead]: [lead.id],
      };
      if (f(lead, LF.moveDate)) fields[PF.jobDate] = f(lead, LF.moveDate);
      if (quote) fields[PF.quote] = quote;
      if (f(lead, LF.from)) fields[PF.fromAddr] = f(lead, LF.from);
      if (f(lead, LF.to)) fields[PF.toAddr] = f(lead, LF.to);
      await createRecord("projects", fields);
      await updateRecord("leads", lead.id, { [LF.status]: "Booked" });
      toast.success("Job created. Find it on the Projects page.");
    } catch {}
    setBooking(false);
  };

  return (
    <div data-testid="lead-card" className="bg-white border border-slate-200 rounded-lg p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Private className="font-display font-bold text-lg text-[#1B2A4A] truncate">{name}</Private>
            {isSample && <span className="text-[10px] font-bold uppercase tracking-wide bg-slate-100 text-slate-500 border border-slate-300 rounded-full px-2 py-0.5">Sample</span>}
          </div>
          <div className="text-xs text-slate-500 mt-0.5 space-x-2">
            {phone && <Private>{phone}</Private>}
            {email && <Private>{email}</Private>}
          </div>
        </div>
        {status === "New" && <AgeTimer createdTime={lead.createdTime} />}
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-600">
        <span className="flex items-center gap-1"><CalendarDays className="w-3.5 h-3.5 text-slate-400" /> {fmtDate(f(lead, LF.moveDate))}</span>
        <span className="flex items-center gap-1"><Home className="w-3.5 h-3.5 text-slate-400" /> {f(lead, LF.homeSize) || "Size TBD"}</span>
        <span className="col-span-2 flex items-center gap-1 min-w-0">
          <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <Private className="truncate">{f(lead, LF.from) || "?"} → {f(lead, LF.to) || "?"}</Private>
        </span>
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-slate-100 pt-2">
        <div className="text-sm">
          {quote ? (
            <div>
              <span className="font-bold text-[#1B2A4A]">Quoted: <Money value={quote} /></span>
              <span className={`ml-2 text-xs font-semibold ${depositPaid ? "text-emerald-600" : "text-amber-600"}`}>
                {depositPaid ? "Deposit paid" : "No deposit yet"}
              </span>
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

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-1.5">
        <Button data-testid="lead-call-btn" asChild variant="outline" size="sm" className="gap-1 text-xs" disabled={!phone}>
          <a href={phone ? `tel:${phone}` : undefined}><Phone className="w-3.5 h-3.5" /> Call</a>
        </Button>
        <Button data-testid="lead-email-btn" asChild variant="outline" size="sm" className="gap-1 text-xs">
          <a href={gmailCompose(email, "Your move with Haul Yeah Moving")} target="_blank" rel="noreferrer">
            <Mail className="w-3.5 h-3.5" /> Email
          </a>
        </Button>
        <Button data-testid="lead-quote-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => onQuote(lead)}>
          <Calculator className="w-3.5 h-3.5" /> Quote
        </Button>
        <Button data-testid="lead-deposit-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => onDeposit(lead)} disabled={!quote}>
          <CreditCard className="w-3.5 h-3.5" /> Deposit
        </Button>
        <Button
          data-testid="lead-book-btn"
          size="sm"
          className="gap-1 text-xs col-span-2 sm:col-span-1 bg-[#1B2A4A] hover:bg-[#26395f]"
          onClick={bookAsJob}
          disabled={booking || status === "Booked"}
        >
          <Truck className="w-3.5 h-3.5" /> {status === "Booked" ? "Booked" : booking ? "Booking…" : "Book as job"}
        </Button>
      </div>
    </div>
  );
};

export default function Leads() {
  const { loadTable, records, tableState } = useApp();
  const [filter, setFilter] = useState("All");
  const [quoteLead, setQuoteLead] = useState(null);
  const [depositLead, setDepositLead] = useState(null);
  const [newOpen, setNewOpen] = useState(false);

  useEffect(() => {
    loadTable("leads");
  }, [loadTable]);

  const all = [...records("leads")].sort((a, b) => (b.createdTime || "").localeCompare(a.createdTime || ""));
  const leads = filter === "All" ? all : all.filter((l) => f(l, LF.status) === filter);
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
        {["All", ...LEAD_STATUSES].map((s) => (
          <button
            key={s}
            data-testid={`lead-filter-${s.toLowerCase()}`}
            onClick={() => setFilter(s)}
            className={`shrink-0 rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-colors ${
              filter === s ? "bg-[#1B2A4A] text-white border-[#1B2A4A]" : "bg-white text-slate-600 border-slate-300 hover:border-[#1B2A4A]"
            }`}
          >
            {s} {s !== "All" && `(${all.filter((l) => f(l, LF.status) === s).length})`}
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
            <LeadCard key={l.id} lead={l} onQuote={setQuoteLead} onDeposit={setDepositLead} />
          ))}
        </div>
      )}

      {quoteLead && <QuoteModal lead={quoteLead} open={!!quoteLead} onOpenChange={(o) => !o && setQuoteLead(null)} />}
      {depositLead && <DepositModal lead={depositLead} open={!!depositLead} onOpenChange={(o) => !o && setDepositLead(null)} />}
      <LeadModal open={newOpen} onOpenChange={setNewOpen} />
    </div>
  );
}
