import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Medal, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { creditPromptsApi, resolvePromptApi, apiErrorMessage } from "@/lib/api";
import { fmtDate } from "@/lib/format";

export const CreditPromptsCard = ({ onResolved }) => {
  const [prompts, setPrompts] = useState([]);
  const [busy, setBusy] = useState(null);

  const load = useCallback(() => creditPromptsApi().then(setPrompts).catch(() => {}), []);
  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  const resolve = async (id, approve) => {
    setBusy(id);
    try {
      const res = await resolvePromptApi(id, approve);
      setPrompts((l) => l.filter((x) => x.id !== id));
      if (approve) {
        toast.success("Tally added.");
        (res.newly_unlocked || []).forEach((n) => toast.success(`Badge unlocked: ${n}!`));
      } else {
        toast("Skipped — no tally given.");
      }
      onResolved?.();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(null);
  };

  if (!prompts.length) return null;
  return (
    <div data-testid="credit-prompts-card" className="border border-[#E8743B]/40 bg-orange-50/70 rounded-lg p-4 mb-4">
      <h2 className="font-display font-bold text-[#1B2A4A] flex items-center gap-2 mb-2">
        <Medal className="w-4 h-4 text-[#E8743B]" /> Give credit?
      </h2>
      <div className="space-y-2">
        {prompts.map((p) => (
          <div key={p.id} data-testid="credit-prompt-item" className="flex flex-wrap items-center gap-2 bg-white border border-orange-200 rounded-md px-3 py-2.5">
            <div className="flex-1 min-w-[220px] text-sm text-[#1B2A4A]">
              {p.message}
              {p.date && <span className="text-xs text-slate-400 ml-1.5">({fmtDate(p.date)})</span>}
            </div>
            <Button
              data-testid="credit-prompt-approve"
              size="sm"
              disabled={busy === p.id}
              onClick={() => resolve(p.id, true)}
              className="gap-1 bg-emerald-600 hover:bg-emerald-700"
            >
              <Check className="w-3.5 h-3.5" /> Yes, give the tally
            </Button>
            <Button
              data-testid="credit-prompt-dismiss"
              size="sm"
              variant="outline"
              disabled={busy === p.id}
              onClick={() => resolve(p.id, false)}
              className="gap-1 text-slate-500"
            >
              <X className="w-3.5 h-3.5" /> Not this time
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
};
