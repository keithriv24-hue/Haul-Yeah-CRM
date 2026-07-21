import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { BadgeMedallion, RARITY_CHIP } from "@/components/team/BadgeMedallion";
import { savePinsApi, apiErrorMessage } from "@/lib/api";

export const PinPicker = ({ open, onOpenChange, member, onSaved }) => {
  const [picked, setPicked] = useState([]);
  const [busy, setBusy] = useState(false);
  const unlocked = Object.values(member?.gallery || {}).flat().filter((b) => b.unlocked);

  useEffect(() => {
    if (open && member) setPicked((member.pinned || []).map((b) => b.id));
  }, [open, member]);

  const toggle = (id) => {
    setPicked((p) => {
      if (p.includes(id)) return p.filter((x) => x !== id);
      if (p.length >= 3) {
        toast("You can pin up to 3 badges.");
        return p;
      }
      return [...p, id];
    });
  };

  const save = async () => {
    setBusy(true);
    try {
      await savePinsApi(picked);
      toast.success("Pins saved.");
      onOpenChange(false);
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="pin-picker-dialog" className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">Pin your top badges</DialogTitle>
          <DialogDescription>Pick up to 3 unlocked badges to show at the top of your profile.</DialogDescription>
        </DialogHeader>
        {unlocked.length === 0 ? (
          <p className="text-sm text-slate-500 py-4 text-center">No badges unlocked yet — your first one is close!</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {unlocked.map((b) => (
              <button
                key={b.id}
                data-testid={`pin-option-${b.id}`}
                onClick={() => toggle(b.id)}
                className={`flex items-center gap-2.5 rounded-lg border p-2 text-left transition-colors ${
                  picked.includes(b.id) ? "border-[#E8743B] bg-orange-50" : "border-slate-200 hover:border-slate-300"
                }`}
              >
                <BadgeMedallion badge={b} size="sm" />
                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-[#1B2A4A] truncate">{b.name}</span>
                  <span className={`inline-block border rounded-full px-1.5 text-[10px] font-bold capitalize ${RARITY_CHIP[b.rarity]}`}>{b.rarity}</span>
                </span>
              </button>
            ))}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="pin-save-btn" disabled={busy} onClick={save} className="bg-[#E8743B] hover:bg-[#d4632e]">
            Save pins ({picked.length}/3)
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
