import React from "react";
import { Calculator } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { LF, f } from "@/lib/fields";
import { QuoteCalculator } from "@/components/QuoteCalculator";

export default function QuoteModal({ lead, open, onOpenChange }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="quote-modal" className="max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <Calculator className="w-5 h-5 text-accent-ink" /> Quote for {f(lead, LF.name) || "lead"}
          </DialogTitle>
          <DialogDescription>Fill in the job — the price updates as you type.</DialogDescription>
        </DialogHeader>
        <QuoteCalculator lead={lead} onSaved={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}
