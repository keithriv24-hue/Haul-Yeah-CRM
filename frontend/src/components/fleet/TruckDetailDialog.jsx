import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Trash2, Plus, ClipboardCheck, Fuel, Wrench, Camera, CheckCircle2, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { InspectionDialog } from "@/components/fleet/InspectionDialog";
import {
  patchTruckApi, truckInspectionsApi, truckLogsApi, addTruckLogApi, deleteTruckLogApi,
  truckDamageApi, reportDamageApi, patchDamageApi, uploadTruckPhotoApi, truckPhotoUrl, apiErrorMessage,
} from "@/lib/api";
import { fmtDate, fmtMoney } from "@/lib/format";

const Overview = ({ truck, onChanged }) => {
  const [form, setForm] = useState({});
  const [newRem, setNewRem] = useState({ title: "", due_date: "" });
  useEffect(() => {
    setForm({
      mileage: truck.mileage ?? "",
      reg_number: truck.registration?.number || "", reg_expires: truck.registration?.expires || "",
      ins_carrier: truck.insurance?.carrier || "", ins_policy: truck.insurance?.policy || "",
      ins_expires: truck.insurance?.expires || "",
    });
  }, [truck]);

  const save = async () => {
    try {
      await patchTruckApi(truck.id, {
        mileage: form.mileage === "" ? null : Number(form.mileage),
        registration: { number: form.reg_number, expires: form.reg_expires },
        insurance: { carrier: form.ins_carrier, policy: form.ins_policy, expires: form.ins_expires },
      });
      toast.success("Truck file saved.");
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  const saveReminders = async (reminders) => {
    try {
      await patchTruckApi(truck.id, { reminders });
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const reminders = truck.reminders || [];

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Label className="w-24 text-xs">Mileage</Label>
        <Input data-testid="truck-mileage-input" type="number" className="h-8" value={form.mileage} onChange={set("mileage")} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div><Label className="text-xs">Registration #</Label><Input data-testid="truck-reg-number" className="h-8" value={form.reg_number} onChange={set("reg_number")} /></div>
        <div><Label className="text-xs">Reg expires</Label><Input data-testid="truck-reg-expires" type="date" className="h-8" value={form.reg_expires} onChange={set("reg_expires")} /></div>
        <div><Label className="text-xs">Insurance carrier</Label><Input data-testid="truck-ins-carrier" className="h-8" value={form.ins_carrier} onChange={set("ins_carrier")} /></div>
        <div><Label className="text-xs">Policy #</Label><Input data-testid="truck-ins-policy" className="h-8" value={form.ins_policy} onChange={set("ins_policy")} /></div>
        <div><Label className="text-xs">Ins. expires</Label><Input data-testid="truck-ins-expires" type="date" className="h-8" value={form.ins_expires} onChange={set("ins_expires")} /></div>
      </div>
      <Button data-testid="truck-overview-save" size="sm" className="bg-[#E8743B] hover:bg-[#d4632e]" onClick={save}>Save truck file</Button>

      <div className="border-t border-slate-100 pt-3">
        <p className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-2">Maintenance reminders</p>
        <div className="space-y-1.5">
          {reminders.map((r) => (
            <div key={r.id} data-testid="truck-reminder-row" className="flex items-center gap-2 text-sm">
              <span className={`flex-1 ${r.done ? "line-through text-slate-400" : "text-slate-700"}`}>
                {r.title} {r.due_date && <span className="text-[10px] text-slate-400">due {fmtDate(r.due_date)}</span>}
              </span>
              <Button data-testid="truck-reminder-toggle" variant="ghost" size="sm" className="h-6 px-1.5"
                onClick={() => saveReminders(reminders.map((x) => (x.id === r.id ? { ...x, done: !x.done } : x)))}>
                {r.done ? <RotateCcw className="w-3.5 h-3.5 text-slate-400" /> : <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />}
              </Button>
              <Button data-testid="truck-reminder-delete" variant="ghost" size="sm" className="h-6 px-1.5 text-red-500"
                onClick={() => saveReminders(reminders.filter((x) => x.id !== r.id))}>
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </div>
          ))}
          {reminders.length === 0 && <p className="text-xs text-slate-400">Nothing scheduled — add oil changes, DOT dates, tire rotations…</p>}
          <div className="flex gap-2 pt-1">
            <Input data-testid="truck-reminder-title" className="h-8" placeholder="Oil change" value={newRem.title} onChange={(e) => setNewRem((s) => ({ ...s, title: e.target.value }))} />
            <Input data-testid="truck-reminder-date" type="date" className="h-8 w-36" value={newRem.due_date} onChange={(e) => setNewRem((s) => ({ ...s, due_date: e.target.value }))} />
            <Button data-testid="truck-reminder-add" size="sm" variant="outline" disabled={!newRem.title.trim()}
              onClick={() => { saveReminders([...reminders, { title: newRem.title, due_date: newRem.due_date, done: false }]); setNewRem({ title: "", due_date: "" }); }}>
              <Plus className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

const ServiceLog = ({ truck }) => {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ kind: "maintenance", date: "", odometer: "", cost: "", gallons: "", notes: "" });
  const load = useCallback(() => truckLogsApi(truck.id).then(setData).catch(() => setData({ logs: [], totals: {} })), [truck.id]);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    try {
      await addTruckLogApi(truck.id, {
        kind: form.kind, date: form.date || null,
        odometer: form.odometer ? Number(form.odometer) : null,
        cost: form.cost ? Number(form.cost) : null,
        gallons: form.gallons ? Number(form.gallons) : null,
        notes: form.notes,
      });
      setForm({ kind: "maintenance", date: "", odometer: "", cost: "", gallons: "", notes: "" });
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <Select value={form.kind} onValueChange={(v) => setForm((f) => ({ ...f, kind: v }))}>
          <SelectTrigger data-testid="log-kind-select" className="h-8"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="maintenance">Maintenance / repair</SelectItem>
            <SelectItem value="fuel">Fuel fill-up</SelectItem>
          </SelectContent>
        </Select>
        <Input data-testid="log-date" type="date" className="h-8" value={form.date} onChange={set("date")} />
        <Input data-testid="log-odometer" type="number" className="h-8" placeholder="Odometer" value={form.odometer} onChange={set("odometer")} />
        <Input data-testid="log-cost" type="number" className="h-8" placeholder="Cost $" value={form.cost} onChange={set("cost")} />
        {form.kind === "fuel" && <Input data-testid="log-gallons" type="number" className="h-8" placeholder="Gallons" value={form.gallons} onChange={set("gallons")} />}
      </div>
      <Input data-testid="log-notes" className="h-8" placeholder="What was done? (oil change, brake pads…)" value={form.notes} onChange={set("notes")} />
      <Button data-testid="log-add-btn" size="sm" className="bg-[#1B2A4A] hover:bg-[#152238]" onClick={add}>Add entry</Button>

      {data && (
        <>
          <p className="text-xs text-slate-500">
            Lifetime: <strong>{fmtMoney(data.totals?.maintenance || 0)}</strong> maintenance · <strong>{fmtMoney(data.totals?.fuel || 0)}</strong> fuel
          </p>
          <div className="space-y-1.5 max-h-[38vh] overflow-y-auto">
            {(data.logs || []).map((l) => (
              <div key={l.id} data-testid="truck-log-row" className="flex items-center gap-2 border border-slate-100 rounded-md px-2.5 py-1.5 text-sm">
                {l.kind === "fuel" ? <Fuel className="w-3.5 h-3.5 text-sky-500 shrink-0" /> : <Wrench className="w-3.5 h-3.5 text-[#E8743B] shrink-0" />}
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-slate-700 truncate">{l.notes || (l.kind === "fuel" ? "Fuel" : "Maintenance")}</p>
                  <p className="text-[10px] text-slate-400">
                    {fmtDate(l.date)}{l.odometer ? ` · ${Math.round(l.odometer).toLocaleString()} mi` : ""}{l.gallons ? ` · ${l.gallons} gal` : ""}
                  </p>
                </div>
                {l.cost != null && <span className="text-xs font-semibold text-[#1B2A4A]">{fmtMoney(l.cost)}</span>}
                <Button data-testid="truck-log-delete" variant="ghost" size="sm" className="h-6 px-1.5 text-red-500"
                  onClick={() => deleteTruckLogApi(l.id).then(load).catch((e) => toast.error(apiErrorMessage(e)))}>
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
            ))}
            {(data.logs || []).length === 0 && <p className="text-xs text-slate-400">No entries yet.</p>}
          </div>
        </>
      )}
    </div>
  );
};

const Inspections = ({ truck, onChanged }) => {
  const [list, setList] = useState(null);
  const [inspOpen, setInspOpen] = useState(false);
  const load = useCallback(() => truckInspectionsApi(truck.id).then((d) => setList(d.inspections)).catch(() => setList([])), [truck.id]);
  useEffect(() => { load(); }, [load]);
  return (
    <div className="space-y-2">
      <Button data-testid="file-inspection-btn" size="sm" variant="outline" className="gap-1.5 text-xs" onClick={() => setInspOpen(true)}>
        <ClipboardCheck className="w-3.5 h-3.5" /> File an inspection now
      </Button>
      <div className="space-y-1.5 max-h-[42vh] overflow-y-auto">
        {list === null && <p className="text-xs text-slate-400">Loading…</p>}
        {list && list.length === 0 && <p className="text-xs text-slate-400">No inspections yet — crew file them from the Warehouse Departure checklist.</p>}
        {(list || []).map((i) => (
          <div key={i.id} data-testid="inspection-row" className="border border-slate-100 rounded-md px-2.5 py-2">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className={`text-[10px] ${i.passed ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-red-50 text-red-700 border-red-200"}`}>
                {i.passed ? "Passed" : "Issues"}
              </Badge>
              <span className="text-xs text-slate-600 flex-1">{fmtDate(i.date)} · {i.by}{i.odometer ? ` · ${Math.round(i.odometer).toLocaleString()} mi` : ""}</span>
            </div>
            {i.failed.length > 0 && <p className="text-[11px] text-red-600 mt-1">Flagged: {i.failed.join(", ")}</p>}
            {i.notes && <p className="text-[11px] text-slate-500 mt-0.5">{i.notes}</p>}
            {i.photos.length > 0 && (
              <div className="flex gap-1.5 mt-1.5">
                {i.photos.map((pid) => (
                  <a key={pid} href={truckPhotoUrl(pid)} target="_blank" rel="noreferrer">
                    <img data-testid="inspection-photo-thumb" src={truckPhotoUrl(pid)} alt="inspection" className="w-12 h-12 object-cover rounded border border-slate-200" />
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      <InspectionDialog open={inspOpen} onOpenChange={setInspOpen} truckId={truck.id} truckName={truck.name}
        onDone={() => { load(); onChanged(); }} />
    </div>
  );
};

const Damage = ({ truck, onChanged }) => {
  const [list, setList] = useState(null);
  const [desc, setDesc] = useState("");
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => truckDamageApi(truck.id).then((d) => setList(d.reports)).catch(() => setList([])), [truck.id]);
  useEffect(() => { load(); }, [load]);

  const report = async () => {
    setBusy(true);
    try {
      const res = await reportDamageApi(truck.id, { description: desc });
      for (const f of files) {
        try { await uploadTruckPhotoApi(truck.id, f, "damage", res.id); } catch { toast.error("A photo didn't upload."); }
      }
      setDesc("");
      setFiles([]);
      toast.success("Damage report filed.");
      load();
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <div className="space-y-3">
      <Textarea data-testid="damage-desc" placeholder="What happened? (dented rear door on the loading dock…)" value={desc} onChange={(e) => setDesc(e.target.value)} />
      <div className="flex items-center gap-2">
        <label className="inline-flex">
          <input data-testid="damage-photo-input" type="file" accept="image/*" multiple className="hidden" onChange={(e) => setFiles(Array.from(e.target.files || []))} />
          <span className="inline-flex items-center gap-1.5 cursor-pointer rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50">
            <Camera className="w-3.5 h-3.5" /> {files.length ? `${files.length} attached` : "Attach photos"}
          </span>
        </label>
        <Button data-testid="damage-report-btn" size="sm" disabled={busy || !desc.trim()} onClick={report} className="bg-red-600 hover:bg-red-700">
          Report damage
        </Button>
      </div>
      <div className="space-y-1.5 max-h-[38vh] overflow-y-auto">
        {(list || []).map((d) => (
          <div key={d.id} data-testid="damage-row" className={`border rounded-md px-2.5 py-2 ${d.resolved ? "border-slate-100 opacity-60" : "border-red-200 bg-red-50/40"}`}>
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <p className="text-sm text-slate-700">{d.description}</p>
                <p className="text-[10px] text-slate-400 mt-0.5">{d.by} · {fmtDate((d.created_at || "").slice(0, 10))}{d.resolved ? " · resolved" : ""}</p>
              </div>
              <Button data-testid="damage-resolve-btn" variant="outline" size="sm" className="h-7 text-[11px]"
                onClick={() => patchDamageApi(d.id, !d.resolved).then(() => { load(); onChanged(); }).catch((e) => toast.error(apiErrorMessage(e)))}>
                {d.resolved ? "Reopen" : "Mark fixed"}
              </Button>
            </div>
            {d.photos.length > 0 && (
              <div className="flex gap-1.5 mt-1.5">
                {d.photos.map((pid) => (
                  <a key={pid} href={truckPhotoUrl(pid)} target="_blank" rel="noreferrer">
                    <img data-testid="damage-photo-thumb" src={truckPhotoUrl(pid)} alt="damage" className="w-12 h-12 object-cover rounded border border-slate-200" />
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
        {list && list.length === 0 && <p className="text-xs text-slate-400">No damage on record. Knock on wood.</p>}
      </div>
    </div>
  );
};

export const TruckDetailDialog = ({ truck, onOpenChange, onChanged }) => (
  <Dialog open={!!truck} onOpenChange={onOpenChange}>
    <DialogContent data-testid="truck-detail-dialog" className="sm:max-w-lg max-h-[92vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle className="font-display">{truck?.name}</DialogTitle>
        <DialogDescription>{truck?.plate || "No plate on file"}</DialogDescription>
      </DialogHeader>
      {truck && (
        <Tabs defaultValue="overview">
          <TabsList className="w-full">
            <TabsTrigger data-testid="truck-tab-overview" value="overview" className="flex-1 text-xs">Overview</TabsTrigger>
            <TabsTrigger data-testid="truck-tab-logs" value="logs" className="flex-1 text-xs">Service log</TabsTrigger>
            <TabsTrigger data-testid="truck-tab-inspections" value="inspections" className="flex-1 text-xs">Inspections</TabsTrigger>
            <TabsTrigger data-testid="truck-tab-damage" value="damage" className="flex-1 text-xs">Damage</TabsTrigger>
          </TabsList>
          <TabsContent value="overview"><Overview truck={truck} onChanged={onChanged} /></TabsContent>
          <TabsContent value="logs"><ServiceLog truck={truck} /></TabsContent>
          <TabsContent value="inspections"><Inspections truck={truck} onChanged={onChanged} /></TabsContent>
          <TabsContent value="damage"><Damage truck={truck} onChanged={onChanged} /></TabsContent>
        </Tabs>
      )}
    </DialogContent>
  </Dialog>
);
