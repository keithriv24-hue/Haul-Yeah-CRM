import React, { useState } from "react";
import { toast } from "sonner";
import { CreditCard, Save, Mail } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { depositFromQuote } from "@/lib/pricing";
import { fmtMoney } from "@/lib/format";
import { useApp } from "@/context/AppContext";
import { LF, f } from "@/lib/fields";
import { Money } from "@/components/Bits";

export default function DepositModal({ lead, open, onOpenChange }) {
  const { updateRecord, rates } = useApp();
  const [link, setLink] = useState("");
  const [saving, setSaving] = useState(false);
  const quote = f(lead, LF.quote);
  const deposit = depositFromQuote(quote, rates.depositPercent);
  const name = f(lead, LF.name) || "";
  const email = f(lead, LF.email) || "";

  const emailBody =
    `Hi ${name.split(" ")[0] || "there"},\n\n` +
    `Good news — we can lock in your move date. The deposit is ${fmtMoney(deposit)} (${rates.depositPercent}% of your quote).\n\n` +
    `Pay here: ${link || "[paste your Square link]"}\n\n` +
    `Final price confirmed by phone.\n\nThanks!\nHaul Yeah Moving\nWeekend moves, flat price, no surprises.`;

  const mailto = `mailto:${email}?subject=${encodeURIComponent("Your deposit link — Haul Yeah Moving")}&body=${encodeURIComponent(emailBody)}`;

  const saveLink = async () => {
    if (!link.trim()) {
      toast.error("Paste the Square payment link first.");
      return;
    }
    setSaving(true);
    const oldNotes = f(lead, LF.notes) || "";
    const line = `Deposit link (${fmtMoney(deposit)}) sent ${new Date().toLocaleDateString("en-US")}: ${link.trim()}`;
    try {
      await updateRecord("leads", lead.id, { [LF.notes]: oldNotes ? `${oldNotes}\n${line}` : line });
      toast.success("Deposit link saved to the lead's notes.");
    } catch {}
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="deposit-modal" className="max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <CreditCard className="w-5 h-5 text-accent-ink" /> Deposit for {name || "lead"}
          </DialogTitle>
          <DialogDescription>
            Make the payment link in your Square dashboard, then paste it here. We save it to the lead and write the email for you.
          </DialogDescription>
        </DialogHeader>
        <div className="border border-primary/15 bg-primary/[0.04] rounded-lg p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-faint">Deposit to collect ({rates.depositPercent}% of quote)</div>
          <div data-testid="deposit-amount" className="font-display text-3xl font-extrabold text-primary tnum"><Money value={deposit} /></div>
          {!quote && <p className="text-xs text-destructive mt-1">No quote saved yet. Use the Quote button first.</p>}
        </div>
        <div>
          <Label>Square payment link</Label>
          <Input data-testid="deposit-link-input" placeholder="https://square.link/u/…" value={link} onChange={(e) => setLink(e.target.value)} />
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <Button data-testid="deposit-save-btn" onClick={saveLink} disabled={saving} variant="outline" className="flex-1 gap-2">
            <Save className="w-4 h-4" /> {saving ? "Saving…" : "Save link to notes"}
          </Button>
          <Button data-testid="deposit-email-btn" asChild className="flex-1 gap-2 bg-accent hover:bg-accent-press">
            <a href={mailto}><Mail className="w-4 h-4" /> Open email</a>
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
