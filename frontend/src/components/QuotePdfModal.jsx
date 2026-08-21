import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { FileText, ExternalLink, MessageSquare, Mail, Copy, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Private } from "@/components/Bits";
import { useApp } from "@/context/AppContext";
import { LF, f } from "@/lib/fields";
import { fmtMoney, smsLink } from "@/lib/format";
import { depositFromQuote } from "@/lib/pricing";
import { getQuoteBreakdownApi, saveQuoteBreakdownApi, apiErrorMessage } from "@/lib/api";

export default function QuotePdfModal({ lead, open, onOpenChange }) {
  const { rates } = useApp();
  const quote = f(lead, LF.quote);
  const name = f(lead, LF.name) || "Customer";
  const phone = f(lead, LF.phone) || "";
  const email = f(lead, LF.email) || "";
  const [data, setData] = useState(null);
  const [building, setBuilding] = useState(false);

  useEffect(() => {
    if (open) getQuoteBreakdownApi(lead.id).then(setData).catch(() => setData({}));
  }, [open, lead.id]);

  const b = data?.breakdown;
  const pdfUrl = data?.token && b ? `${window.location.origin}/api/quote-pdf/${data.token}` : null;
  const first = name.split(" ")[0];
  const smsBody = `Hi ${first}, here's your Haul Yeah Moving quote — one flat price, no surprises: ${pdfUrl} Reply here with any questions!`;
  const emailHref = pdfUrl && email
    ? `mailto:${email}?subject=${encodeURIComponent("Your Haul Yeah Moving quote")}&body=${encodeURIComponent(
        `Hi ${first},\n\nThanks for talking with us! Here's your full quote — one flat price with everything spelled out:\n\n${pdfUrl}\n\nReply with any questions.\n\nHaul Yeah Moving\nWeekend moves, flat price, no surprises.`
      )}`
    : undefined;
  const balance = b ? Math.round(((b.finalQuote || 0) - (b.deposit || 0)) * 100) / 100 : 0;

  const buildSimple = async () => {
    setBuilding(true);
    try {
      const r = await saveQuoteBreakdownApi(lead.id, {
        lines: [{ name: "Local Moving Service — flat rate", amount: Number(quote) }],
        finalQuote: Number(quote),
        deposit: depositFromQuote(quote, rates.depositPercent),
        customerName: name,
        customerPhone: phone,
        fromAddress: f(lead, LF.from) || "",
        toAddress: f(lead, LF.to) || "",
        moveDate: f(lead, LF.moveDate) || "",
      });
      setData(await getQuoteBreakdownApi(lead.id));
      toast.success(r.sms_sent ? "PDF ready — and texted to the customer." : "PDF is ready.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBuilding(false);
  };

  const copyLink = () => navigator.clipboard.writeText(pdfUrl).then(() => toast.success("Link copied."));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="quote-pdf-modal" className="max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <FileText className="w-5 h-5 text-accent-ink" /> Quote PDF for {name}
          </DialogTitle>
          <DialogDescription>
            A clean branded one-pager for the customer. No cushion or internal numbers — the lines add up exactly to the flat price.
          </DialogDescription>
        </DialogHeader>
        {!quote ? (
          <p className="text-sm text-faint">Save a quote to this lead first (Quote button), then come back.</p>
        ) : data === null ? (
          <p className="text-sm text-faint">Loading…</p>
        ) : !b ? (
          <div className="space-y-3">
            <p className="text-sm text-ink-2">This quote was saved before itemized PDFs existed.</p>
            <Button data-testid="pdf-build-simple-btn" onClick={buildSimple} disabled={building} className="w-full gap-2 bg-primary hover:bg-[#16233d]">
              {building ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
              Make a one-line PDF ({fmtMoney(quote)} flat)
            </Button>
            <p className="text-xs text-faint">
              Want the full line-by-line breakdown (travel, stairs, big items)? Open Quote, re-enter the move, press Save — then reopen this window.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <div data-testid="pdf-preview-lines" className="border border-border rounded-md overflow-hidden">
              {(b.lines || []).map((l, i) => (
                <div key={i} className="flex items-center justify-between px-3 py-1.5 text-sm border-b border-border">
                  <span className="text-ink-2">{l.name}</span>
                  <span className="font-medium text-primary"><Private>{fmtMoney(l.amount)}</Private></span>
                </div>
              ))}
              <div className="flex items-center justify-between px-3 py-2 bg-primary text-white text-sm font-bold">
                <span>Flat total</span>
                <span data-testid="pdf-preview-total" className="text-accent-ink"><Private>{fmtMoney(b.finalQuote)}</Private></span>
              </div>
              <div className="flex items-center justify-between px-3 py-1.5 text-xs text-faint">
                <span>Deposit <Private>{fmtMoney(b.deposit)}</Private></span>
                <span>Balance on move day <Private>{fmtMoney(balance)}</Private></span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Button data-testid="pdf-open-btn" asChild className="gap-1.5 bg-accent hover:bg-accent-press">
                <a href={pdfUrl} target="_blank" rel="noreferrer"><ExternalLink className="w-4 h-4" /> Open PDF</a>
              </Button>
              <Button data-testid="pdf-copy-btn" variant="outline" className="gap-1.5" onClick={copyLink}>
                <Copy className="w-4 h-4" /> Copy link
              </Button>
              <Button data-testid="pdf-text-btn" asChild variant="outline" className="gap-1.5" disabled={!phone}>
                <a href={phone ? smsLink(phone, smsBody) : undefined}><MessageSquare className="w-4 h-4" /> Text it</a>
              </Button>
              <Button data-testid="pdf-email-btn" asChild variant="outline" className="gap-1.5" disabled={!email}>
                <a href={emailHref}><Mail className="w-4 h-4" /> Email it</a>
              </Button>
            </div>
            <p className="text-[11px] text-faint">The link always opens the newest saved quote for this lead.</p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
