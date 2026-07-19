import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, CheckCircle2, MessageSquare } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { InstructionBanner, PageTitle, Private, Money, KpiCard, EmptyState, LoadingRows, SearchBar, searchMatch } from "@/components/Bits";
import { IF, CF, LF, f, INVOICE_STATUSES, PAYMENT_METHODS, STATUS_PILL } from "@/lib/fields";
import { fmtDate, fmtMoney, todayISO, smsLink, payNudgeSmsBody } from "@/lib/format";

const blank = { number: "", customer: "", amount: "", status: "Draft", issueDate: todayISO(), dueDate: "", payMethod: "Square", notes: "" };
const num = (v) => Number(v) || 0;

export default function Invoices() {
  const { loadTable, records, tableState, updateRecord, createRecord } = useApp();
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    loadTable("invoices");
    loadTable("contacts");
    loadTable("leads");
  }, [loadTable]);

  const phoneForCustomer = (name) => {
    const norm = (s) => (s || "").trim().toLowerCase();
    const target = norm(name);
    if (!target) return null;
    const c = records("contacts").find((r) => norm(f(r, CF.name)) === target);
    if (c && f(c, CF.phone)) return f(c, CF.phone);
    const l = records("leads").find((r) => norm(f(r, LF.name)) === target);
    return (l && f(l, LF.phone)) || null;
  };

  const allInvoices = [...records("invoices")].sort((a, b) => (f(b, IF.issueDate) || "").localeCompare(f(a, IF.issueDate) || ""));
  const invoices = allInvoices.filter((i) => searchMatch(query, f(i, IF.number), f(i, IF.customer), f(i, IF.status), f(i, IF.payMethod)));
  const { loading, error } = tableState("invoices");

  const paid = allInvoices.filter((i) => f(i, IF.status) === "Paid").reduce((s, i) => s + num(f(i, IF.amount)), 0);
  const sent = allInvoices.filter((i) => f(i, IF.status) === "Sent").reduce((s, i) => s + num(f(i, IF.amount)), 0);
  const overdue = allInvoices.filter((i) => f(i, IF.status) === "Overdue").reduce((s, i) => s + num(f(i, IF.amount)), 0);

  const markPaid = (inv) => {
    updateRecord("invoices", inv.id, { [IF.status]: "Paid" })
      .then(() => toast.success("Marked paid. Money in!"))
      .catch(() => {});
  };

  const set = (k) => (e) => setForm((s) => ({ ...s, [k]: e.target.value }));

  const save = async () => {
    if (!form.customer.trim() || !form.amount) {
      toast.error("Add the customer and the amount first.");
      return;
    }
    setSaving(true);
    try {
      await createRecord("invoices", {
        [IF.number]: form.number,
        [IF.customer]: form.customer.trim(),
        [IF.amount]: Number(form.amount),
        [IF.status]: form.status,
        [IF.issueDate]: form.issueDate,
        [IF.dueDate]: form.dueDate,
        [IF.payMethod]: form.payMethod,
        [IF.notes]: form.notes,
      });
      toast.success("Invoice saved.");
      setForm(blank);
      setModalOpen(false);
    } catch {}
    setSaving(false);
  };

  return (
    <div data-testid="invoices-page">
      <PageTitle
        title="Invoices"
        subtitle="Bill it, send it, mark it paid."
        action={
          <Button data-testid="new-invoice-btn" onClick={() => setModalOpen(true)} className="gap-1.5 bg-[#E8743B] hover:bg-[#d4632e]">
            <Plus className="w-4 h-4" /> New invoice
          </Button>
        }
      />
      <InstructionBanner>Send bills and mark them paid the moment money lands. Overdue rows need a follow-up call.</InstructionBanner>

      <div className="grid grid-cols-3 gap-4 mb-6">
        <KpiCard testId="kpi-invoices-paid" label="Paid" value={fmtMoney(paid)} />
        <KpiCard testId="kpi-invoices-sent" label="Sent (waiting)" value={fmtMoney(sent)} />
        <KpiCard testId="kpi-invoices-overdue" label="Overdue" value={fmtMoney(overdue)} alert={overdue > 0} />
      </div>

      <div className="mb-4">
        <SearchBar value={query} onChange={setQuery} placeholder="Search invoice #, customer…" testId="invoices-search-input" />
      </div>

      {loading && !allInvoices.length ? (
        <LoadingRows />
      ) : error && !allInvoices.length ? (
        <EmptyState>{error}</EmptyState>
      ) : invoices.length === 0 ? (
        <EmptyState>{query ? "No invoices match that search." : 'No invoices yet. Press "+ New invoice".'}</EmptyState>
      ) : (
        <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Invoice #</TableHead>
                <TableHead>Customer</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden sm:table-cell">Issued</TableHead>
                <TableHead className="hidden sm:table-cell">Due</TableHead>
                <TableHead className="hidden md:table-cell">Method</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invoices.map((inv) => {
                const status = f(inv, IF.status) || "Draft";
                return (
                  <TableRow key={inv.id} data-testid="invoice-row">
                    <TableCell className="font-semibold">{f(inv, IF.number) || "—"}</TableCell>
                    <TableCell><Private>{f(inv, IF.customer) || "—"}</Private></TableCell>
                    <TableCell className="font-bold text-[#1B2A4A]"><Money value={f(inv, IF.amount)} /></TableCell>
                    <TableCell>
                      <Select value={status} onValueChange={(v) => updateRecord("invoices", inv.id, { [IF.status]: v }).catch(() => {})}>
                        <SelectTrigger data-testid="invoice-status-select" className={`w-[110px] h-8 text-xs font-semibold border ${STATUS_PILL[status] || ""}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>{INVOICE_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell text-xs text-slate-500">{fmtDate(f(inv, IF.issueDate))}</TableCell>
                    <TableCell className="hidden sm:table-cell text-xs text-slate-500">{fmtDate(f(inv, IF.dueDate))}</TableCell>
                    <TableCell className="hidden md:table-cell text-xs text-slate-500">{f(inv, IF.payMethod) || "—"}</TableCell>
                    <TableCell>
                      <div className="flex gap-1.5">
                        {status !== "Paid" && (
                          <Button data-testid="mark-paid-btn" size="sm" variant="outline" className="gap-1 text-xs text-emerald-700 border-emerald-300 hover:bg-emerald-50" onClick={() => markPaid(inv)}>
                            <CheckCircle2 className="w-3.5 h-3.5" /> Mark paid
                          </Button>
                        )}
                        {["Sent", "Overdue"].includes(status) && (() => {
                          const custPhone = phoneForCustomer(f(inv, IF.customer));
                          return (
                            <Button
                              data-testid="invoice-nudge-btn"
                              asChild
                              size="sm"
                              variant="outline"
                              className="gap-1 text-xs text-amber-700 border-amber-300 hover:bg-amber-50"
                              disabled={!custPhone}
                              title={custPhone ? "Text them a payment nudge" : "No phone found for this customer in Contacts or Leads"}
                            >
                              <a href={custPhone ? smsLink(custPhone, payNudgeSmsBody(f(inv, IF.customer), f(inv, IF.amount), null)) : undefined}>
                                <MessageSquare className="w-3.5 h-3.5" /> Text nudge
                              </a>
                            </Button>
                          );
                        })()}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent data-testid="new-invoice-modal" className="max-w-md">
          <DialogHeader>
            <DialogTitle className="font-display">New invoice</DialogTitle>
            <DialogDescription>Customer and amount are the must-haves.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Invoice #</Label>
              <Input data-testid="invoice-number-input" value={form.number} onChange={set("number")} placeholder="INV-014" />
            </div>
            <div>
              <Label>Customer *</Label>
              <Input data-testid="invoice-customer-input" value={form.customer} onChange={set("customer")} />
            </div>
            <div>
              <Label>Amount ($) *</Label>
              <Input data-testid="invoice-amount-input" type="number" min="0" value={form.amount} onChange={set("amount")} />
            </div>
            <div>
              <Label>Status</Label>
              <Select value={form.status} onValueChange={(v) => setForm((s) => ({ ...s, status: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{INVOICE_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Issue date</Label>
              <Input type="date" value={form.issueDate} onChange={set("issueDate")} />
            </div>
            <div>
              <Label>Due date</Label>
              <Input type="date" value={form.dueDate} onChange={set("dueDate")} />
            </div>
            <div className="col-span-2">
              <Label>Payment method</Label>
              <Select value={form.payMethod} onValueChange={(v) => setForm((s) => ({ ...s, payMethod: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{PAYMENT_METHODS.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <Button data-testid="invoice-save-btn" onClick={save} disabled={saving} className="w-full gap-2 bg-[#E8743B] hover:bg-[#d4632e]">
            <Plus className="w-4 h-4" /> {saving ? "Saving…" : "Save invoice"}
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
