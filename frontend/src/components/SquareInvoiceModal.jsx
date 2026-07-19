import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { FileText, Send, ExternalLink, CheckCircle2, AlertTriangle } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Private, Money } from "@/components/Bits";
import { LF, f } from "@/lib/fields";
import { fmtMoney } from "@/lib/format";
import { depositFromQuote } from "@/lib/pricing";
import { getSquareStatusApi, sendSquareInvoiceApi, apiErrorMessage } from "@/lib/api";

export default function SquareInvoiceModal({ lead, open, onOpenChange }) {
  const { updateRecord, loadSquareInvoices, rates } = useApp();
  const quote = f(lead, LF.quote);
  const name = f(lead, LF.name) || "Customer";
  const email = f(lead, LF.email) || "";
  const phone = f(lead, LF.phone) || "";
  const deposit = depositFromQuote(quote, rates.depositPercent);

  const [choice, setChoice] = useState(quote ? "deposit" : "custom");
  const [custom, setCustom] = useState("");
  const [square, setSquare] = useState(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (open) {
      setResult(null);
      setChoice(quote ? "deposit" : "custom");
      setCustom("");
      getSquareStatusApi().then(setSquare).catch(() => setSquare({ configured: false }));
    }
  }, [open, quote]);

  const amount = choice === "deposit" ? deposit : choice === "full" ? Number(quote) || 0 : Number(custom) || 0;
  const label = choice === "deposit" ? `${rates.depositPercent}% deposit` : choice === "full" ? "full quote" : "custom amount";
  const canSend = amount > 0 && !!email && square?.configured;

  const send = async () => {
    setConfirmOpen(false);
    setSending(true);
    try {
      const res = await sendSquareInvoiceApi({
        name,
        email,
        phone,
        amount,
        description: `Haul Yeah Moving — ${label} for ${name}'s move`,
        lead_id: lead.id,
      });
      setResult(res);
      loadSquareInvoices();
      toast.success(`Invoice ${res.invoice_number || ""} sent to ${email}.`);
      const oldNotes = f(lead, LF.notes) || "";
      const line = `Square invoice sent ${new Date().toLocaleDateString("en-US")}: ${fmtMoney(amount)} (${label})${res.invoice_number ? ` — #${res.invoice_number}` : ""}.`;
      updateRecord("leads", lead.id, { [LF.notes]: oldNotes ? `${oldNotes}\n${line}` : line }).catch(() => {});
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setSending(false);
  };

  const pill = (key, title, value) => (
    <button
      key={key}
      data-testid={`invoice-amount-${key}`}
      onClick={() => setChoice(key)}
      className={`flex-1 rounded-lg border px-3 py-2.5 text-left transition-colors ${
        choice === key ? "border-[#E8743B] bg-[#E8743B]/10" : "border-slate-200 bg-white hover:border-slate-400"
      }`}
    >
      <div className="text-xs font-semibold text-slate-500">{title}</div>
      <div className="font-display font-bold text-[#1B2A4A]">{value}</div>
    </button>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="square-invoice-modal" className="max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <FileText className="w-5 h-5 text-[#E8743B]" /> Send Square invoice
          </DialogTitle>
          <DialogDescription>Square builds the invoice and emails it to the customer. They pay online.</DialogDescription>
        </DialogHeader>

        {result ? (
          <div data-testid="invoice-success" className="space-y-3">
            <div className="flex items-start gap-2 border border-emerald-200 bg-emerald-50 rounded-lg p-3 text-sm text-emerald-800">
              <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
              <div>
                Invoice {result.invoice_number ? `#${result.invoice_number}` : ""} for <strong>{fmtMoney(result.amount)}</strong> is on its way to <Private>{email}</Private>.
              </div>
            </div>
            {result.public_url && (
              <Button asChild variant="outline" className="w-full gap-1.5" data-testid="invoice-view-link">
                <a href={result.public_url} target="_blank" rel="noreferrer">
                  <ExternalLink className="w-4 h-4" /> View the invoice page
                </a>
              </Button>
            )}
            <Button onClick={() => onOpenChange(false)} className="w-full bg-[#1B2A4A] hover:bg-[#26395f]" data-testid="invoice-done-btn">
              Done
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            {square && square.environment === "sandbox" && square.configured && (
              <div className="flex items-start gap-2 border border-amber-200 bg-amber-50 rounded-lg px-3 py-2 text-xs text-amber-800">
                <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                Test mode (sandbox) — no real money moves. Switch to your production Square keys when ready.
              </div>
            )}
            {square && !square.configured && (
              <div className="flex items-start gap-2 border border-red-200 bg-red-50 rounded-lg px-3 py-2 text-xs text-red-700">
                <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                Square is not connected. Add SQUARE_ACCESS_TOKEN and SQUARE_LOCATION_ID in the secrets panel.
              </div>
            )}

            <div className="text-sm border border-slate-200 rounded-lg p-3 space-y-1">
              <div><span className="text-slate-500">To:</span> <Private className="font-semibold">{name}</Private></div>
              <div><span className="text-slate-500">Email:</span> {email ? <Private className="font-semibold">{email}</Private> : <span className="text-red-600 font-semibold">No email on this lead — add one first.</span>}</div>
            </div>

            <div>
              <Label className="mb-1.5 block">How much?</Label>
              <div className="flex gap-2">
                {quote ? pill("deposit", `${rates.depositPercent}% deposit`, fmtMoney(deposit)) : null}
                {quote ? pill("full", "Full quote", fmtMoney(quote)) : null}
                {pill("custom", "Custom", choice === "custom" && custom ? fmtMoney(Number(custom)) : "You pick")}
              </div>
              {choice === "custom" && (
                <Input
                  data-testid="invoice-custom-amount-input"
                  type="number"
                  min="1"
                  step="1"
                  placeholder="Amount in dollars"
                  className="mt-2"
                  value={custom}
                  onChange={(e) => setCustom(e.target.value)}
                />
              )}
            </div>

            <Button
              data-testid="invoice-review-btn"
              onClick={() => setConfirmOpen(true)}
              disabled={!canSend || sending}
              className="w-full gap-2 bg-[#E8743B] hover:bg-[#d4632e]"
            >
              <Send className="w-4 h-4" /> {sending ? "Sending…" : `Send ${amount > 0 ? fmtMoney(amount) : ""} invoice…`}
            </Button>
            <p className="text-[11px] text-slate-400">Nothing sends yet — you'll confirm on the next step.</p>
          </div>
        )}

        <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <AlertDialogContent data-testid="invoice-confirm-dialog">
            <AlertDialogHeader>
              <AlertDialogTitle className="font-display">Really send this invoice?</AlertDialogTitle>
              <AlertDialogDescription>
                Square will email an invoice for <strong className="text-[#1B2A4A]">{fmtMoney(amount)}</strong> to{" "}
                <strong className="text-[#1B2A4A]">{email}</strong> ({label}). The customer can pay it right away. Double-check the amount before you press send.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel data-testid="invoice-confirm-cancel">Not yet</AlertDialogCancel>
              <AlertDialogAction data-testid="invoice-confirm-send" onClick={send} className="bg-[#E8743B] hover:bg-[#d4632e]">
                Yes, send invoice
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </DialogContent>
    </Dialog>
  );
}
