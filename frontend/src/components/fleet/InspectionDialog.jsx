import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, ClipboardCheck, Camera } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { createInspectionApi, uploadTruckPhotoApi, apiErrorMessage } from "@/lib/api";

const ITEMS = [
  { key: "lights", label: "Lights & signals working" },
  { key: "tires", label: "Tires — pressure & tread OK" },
  { key: "brakes", label: "Brakes feel right" },
  { key: "fluids", label: "No leaks — oil / coolant OK" },
  { key: "glass", label: "Mirrors & windshield clean, no cracks" },
  { key: "wipers", label: "Horn & wipers working" },
  { key: "equipment", label: "Straps, dollies & pads on board" },
  { key: "interior", label: "Cab & box clean and secure" },
];
const allOk = () => Object.fromEntries(ITEMS.map((i) => [i.key, true]));

export const InspectionDialog = ({ open, onOpenChange, truckId, truckName, assignmentId, onDone }) => {
  const [items, setItems] = useState(allOk());
  const [odometer, setOdometer] = useState("");
  const [notes, setNotes] = useState("");
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setItems(allOk());
      setOdometer("");
      setNotes("");
      setFiles([]);
    }
  }, [open]);

  const failCount = ITEMS.filter((i) => !items[i.key]).length;

  const submit = async () => {
    setBusy(true);
    try {
      const res = await createInspectionApi(truckId, {
        items,
        odometer: odometer ? Number(odometer) : null,
        notes,
        assignment_id: assignmentId || null,
      });
      for (const f of files) {
        try {
          await uploadTruckPhotoApi(truckId, f, "inspection", res.id);
        } catch {
          toast.error(`One photo didn't upload (${f.name}).`);
        }
      }
      toast.success(res.passed ? `${truckName} passed inspection — you're good to roll.` : "Inspection filed — the boss was pinged about the issues.");
      onOpenChange(false);
      onDone && onDone(res);
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="inspection-dialog" className="sm:max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <ClipboardCheck className="w-4 h-4 text-[#E8743B]" /> Daily inspection — {truckName}
          </DialogTitle>
          <DialogDescription>Flip anything that's NOT right to red. Issues ping the owner automatically.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {ITEMS.map((it) => (
            <div key={it.key} data-testid={`inspection-item-${it.key}`} className={`flex items-center justify-between gap-2 rounded-md border px-3 py-2 ${items[it.key] ? "border-slate-200" : "border-red-300 bg-red-50"}`}>
              <span className={`text-sm ${items[it.key] ? "text-slate-700" : "text-red-700 font-semibold"}`}>{it.label}</span>
              <Switch data-testid={`inspection-switch-${it.key}`} checked={items[it.key]}
                onCheckedChange={(v) => setItems((s) => ({ ...s, [it.key]: !!v }))} />
            </div>
          ))}
          <div className="flex items-center gap-2 pt-1">
            <Label className="w-24 text-xs">Odometer</Label>
            <Input data-testid="inspection-odometer" type="number" className="h-8" placeholder="e.g. 84210" value={odometer} onChange={(e) => setOdometer(e.target.value)} />
          </div>
          <Textarea data-testid="inspection-notes" placeholder="Anything worth noting? (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} />
          <label className="inline-flex">
            <input data-testid="inspection-photo-input" type="file" accept="image/*" multiple className="hidden"
              onChange={(e) => setFiles(Array.from(e.target.files || []))} />
            <span className="inline-flex items-center gap-1.5 cursor-pointer rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50">
              <Camera className="w-3.5 h-3.5" /> {files.length ? `${files.length} photo${files.length > 1 ? "s" : ""} attached` : "Attach photos"}
            </span>
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="inspection-submit" disabled={busy} onClick={submit}
            className={failCount ? "bg-amber-600 hover:bg-amber-700 gap-1.5" : "bg-emerald-600 hover:bg-emerald-700 gap-1.5"}>
            {busy && <Loader2 className="w-4 h-4 animate-spin" />}
            {failCount ? `File with ${failCount} issue${failCount > 1 ? "s" : ""}` : "All good — file it"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
