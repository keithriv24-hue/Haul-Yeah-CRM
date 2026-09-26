import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  CheckCircle2, Circle, LogIn, Truck, MapPin, ShieldCheck, PackageCheck, Home, Flag, LogOut,
  Loader2, AlertTriangle, Camera, Lock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { crewLeadFlowApi, crewLeadTapApi, clockInApi, clockOutApi, uploadJobPhotoApi, apiErrorMessage } from "@/lib/api";

const STEP_ICON = {
  clock_in: LogIn, depart: Truck, arrived: MapPin, no_damage: ShieldCheck,
  loaded: PackageCheck, dropoff: Home, complete: Flag, clock_out: LogOut,
};
const DELAY_FACTORS = ["Stairs", "Long carry", "Elevator wait", "Customer not packed", "Heavy/specialty items", "Traffic", "Weather", "Customer added items", "None"];

// Best-effort geolocation — resolves {} if denied/unavailable (never blocks a tap).
const getCoords = () =>
  new Promise((resolve) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) return resolve({});
    let done = false;
    const finish = (v) => { if (!done) { done = true; resolve(v); } };
    navigator.geolocation.getCurrentPosition(
      (pos) => finish({ lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy: pos.coords.accuracy }),
      () => finish({}), { timeout: 6000, maximumAge: 60000 });
    setTimeout(() => finish({}), 6500);
  });

const fmt = (at) => (at ? new Date(at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "");

export const JobLeadFlow = ({ assignmentId, onChanged, seedFlow }) => {
  const [flow, setFlow] = useState(seedFlow || null);
  const [busy, setBusy] = useState(null);
  const [departOpen, setDepartOpen] = useState(false);
  const [insp, setInsp] = useState(() =>
    seedFlow ? Object.fromEntries((seedFlow.inspection_items || []).map((i) => [i.key, true])) : {});
  const [completeOpen, setCompleteOpen] = useState(false);
  const [notes, setNotes] = useState("");
  const [identity, setIdentity] = useState(() => seedFlow?.primary_name || "");
  const [factors, setFactors] = useState([]);
  const [clockoutOpen, setClockoutOpen] = useState(false);
  const [noDefects, setNoDefects] = useState(true);
  const damageInputRef = React.useRef(null);

  const load = useCallback(() => {
    crewLeadFlowApi(assignmentId).then((f) => {
      setFlow(f);
      setInsp(Object.fromEntries((f.inspection_items || []).map((i) => [i.key, true])));
      setIdentity((prev) => prev || f.primary_name || "");
    }).catch(() => setFlow(null));
  }, [assignmentId]);
  useEffect(() => { if (!seedFlow) load(); }, [load]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!flow) return null;

  const done = flow.steps.filter((s) => s.done).length;

  // ---- helper (not a Crew Lead): read-only view ----
  if (!flow.is_lead) {
    return (
      <div data-testid="job-lead-helper-note" className="mt-3 border-t border-border pt-3">
        <div className="flex items-center gap-2 text-[13px] text-primary">
          <Lock className="w-4 h-4 text-faint" />
          <span>You're on this job as a <strong>Helper</strong>. <strong>{flow.primary_name || "Your Crew Lead"}</strong> runs the checklist.</span>
        </div>
        <p className="text-xs text-faint mt-1">Your Crew Lead handles job updates and checklists. Clock in and out from the top of the page.</p>
        <StepRail steps={flow.steps} />
      </div>
    );
  }

  const runTap = async (key, body = {}) => {
    setBusy(key);
    try {
      const coords = await getCoords();
      const res = await crewLeadTapApi(assignmentId, key, { ...coords, ...body });
      setFlow(res);
      onChanged?.();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (detail && detail.error === "critical_defect") {
        toast.error("Critical truck defect — the owner has to clear it before you can depart.");
        load();
      } else {
        toast.error(apiErrorMessage(e));
      }
    }
    setBusy(null);
  };

  const doClockIn = async () => {
    setBusy("clock_in");
    const coords = await getCoords();
    try { await clockInApi(coords); } catch { /* already clocked in is fine */ }
    try {
      const res = await crewLeadTapApi(assignmentId, "clock_in", coords);
      setFlow(res); onChanged?.(); toast.success("Clocked in to this job.");
    } catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy(null);
  };

  const confirmDepart = async () => {
    setDepartOpen(false);
    await runTap("depart", flow.truck_id ? { inspection_items: insp } : {});
  };

  const doDamagePhoto = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy("no_damage");
    try {
      await uploadJobPhotoApi(assignmentId, file);
      const coords = await getCoords();
      const res = await crewLeadTapApi(assignmentId, "no_damage", { ...coords, damage_found: true });
      setFlow(res); onChanged?.(); toast.success("Damage photo saved and logged.");
    } catch (err) { toast.error(apiErrorMessage(err)); }
    setBusy(null);
    e.target.value = "";
  };

  const confirmComplete = async () => {
    setCompleteOpen(false);
    await runTap("complete", { notes, lead_identity: identity, delay_factors: factors.length ? factors : ["None"] });
    setNotes(""); setFactors([]);
  };

  const doClockOut = async () => {
    setClockoutOpen(false);
    setBusy("clock_out");
    const coords = await getCoords();
    try { await clockOutApi(coords); } catch { /* not clocked in is fine */ }
    try {
      const res = await crewLeadTapApi(assignmentId, "clock_out", { ...coords, no_defects: noDefects });
      setFlow(res); onChanged?.(); toast.success(noDefects ? "Clocked out — no defects logged." : "Clocked out — defect reported to the owner.");
    } catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy(null);
  };

  const toggleFactor = (fct) => setFactors((cur) => {
    if (cur.includes(fct)) return cur.filter((x) => x !== fct);
    if (fct === "None") return ["None"];
    return [...cur.filter((x) => x !== "None"), fct];
  });

  const nextTap = flow.next_tap;
  const blocked = nextTap === "depart" && flow.depart_blocker && !flow.depart_override;
  const spinning = (k) => busy === k;

  // main Next action button
  const NextButton = () => {
    if (!nextTap) return null;
    const Icon = STEP_ICON[nextTap];
    const base = "w-full mt-3 gap-2 min-h-[52px] text-[15px] font-bold";
    if (nextTap === "clock_in")
      return <Button data-testid="job-lead-next-btn" data-step="clock_in" disabled={spinning("clock_in")} onClick={doClockIn} className={`${base} bg-primary hover:bg-[#152238]`}>{spinning("clock_in") ? <Loader2 className="w-5 h-5 animate-spin" /> : <Icon className="w-5 h-5" />} Clock in to this job</Button>;
    if (nextTap === "depart")
      return (
        <>
          {blocked && (
            <div data-testid="job-lead-depart-blocker" className="mt-3 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2.5 text-[13px] text-primary">
              <p className="font-bold text-destructive flex items-center gap-1.5"><AlertTriangle className="w-4 h-4" /> Departure blocked — critical defect</p>
              <p className="mt-0.5">{(flow.depart_blocker.failed_labels || []).join(", ")}. The owner must clear it before you can leave.</p>
            </div>
          )}
          {flow.depart_override && (
            <div className="mt-3 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-[12.5px] text-primary">
              Owner cleared the defect ({flow.depart_override.reason}). You can depart.
            </div>
          )}
          <Button data-testid="job-lead-next-btn" data-step="depart" disabled={spinning("depart")} onClick={() => (flow.truck_id ? setDepartOpen(true) : runTap("depart"))} className={`${base} bg-primary hover:bg-[#152238]`}>{spinning("depart") ? <Loader2 className="w-5 h-5 animate-spin" /> : <Icon className="w-5 h-5" />} All good — Depart</Button>
        </>
      );
    if (nextTap === "arrived")
      return <Button data-testid="job-lead-next-btn" data-step="arrived" disabled={spinning("arrived")} onClick={() => runTap("arrived")} className={`${base} bg-primary hover:bg-[#152238]`}>{spinning("arrived") ? <Loader2 className="w-5 h-5 animate-spin" /> : <Icon className="w-5 h-5" />} Arrived — walkthrough done</Button>;
    if (nextTap === "no_damage")
      return (
        <div className="mt-3 space-y-2">
          <Button data-testid="job-lead-next-btn" data-step="no_damage" disabled={spinning("no_damage")} onClick={() => runTap("no_damage", { damage_found: false })} className={`${base} mt-0 bg-success hover:bg-success`}>{spinning("no_damage") ? <Loader2 className="w-5 h-5 animate-spin" /> : <ShieldCheck className="w-5 h-5" />} No damage</Button>
          <label className="block">
            <input ref={damageInputRef} data-testid="job-lead-damage-input" type="file" accept="image/*" className="hidden" onChange={doDamagePhoto} />
            <Button data-testid="job-lead-damage-btn" variant="outline" className="w-full gap-2 min-h-[44px]" type="button" onClick={() => damageInputRef.current?.click()}><Camera className="w-4 h-4" /> Existing damage — add photos</Button>
          </label>
        </div>
      );
    if (nextTap === "loaded")
      return <Button data-testid="job-lead-next-btn" data-step="loaded" disabled={spinning("loaded")} onClick={() => runTap("loaded")} className={`${base} bg-primary hover:bg-[#152238]`}>{spinning("loaded") ? <Loader2 className="w-5 h-5 animate-spin" /> : <Icon className="w-5 h-5" />} Loaded — leaving pickup</Button>;
    if (nextTap === "dropoff")
      return <Button data-testid="job-lead-next-btn" data-step="dropoff" disabled={spinning("dropoff")} onClick={() => runTap("dropoff")} className={`${base} bg-primary hover:bg-[#152238]`}>{spinning("dropoff") ? <Loader2 className="w-5 h-5 animate-spin" /> : <Icon className="w-5 h-5" />} At drop-off</Button>;
    if (nextTap === "complete")
      return <Button data-testid="job-lead-next-btn" data-step="complete" disabled={spinning("complete")} onClick={() => setCompleteOpen(true)} className={`${base} bg-success hover:bg-success`}>{spinning("complete") ? <Loader2 className="w-5 h-5 animate-spin" /> : <Icon className="w-5 h-5" />} All as quoted &amp; Complete</Button>;
    if (nextTap === "clock_out")
      return <Button data-testid="job-lead-next-btn" data-step="clock_out" disabled={spinning("clock_out")} onClick={() => { setNoDefects(true); setClockoutOpen(true); }} className={`${base} bg-primary hover:bg-[#152238]`}>{spinning("clock_out") ? <Loader2 className="w-5 h-5 animate-spin" /> : <Icon className="w-5 h-5" />} Clock out &amp; No defects</Button>;
    return null;
  };

  return (
    <div data-testid="job-lead-flow" className="mt-3 border-t border-border pt-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-bold tracking-[.14em] uppercase text-accent-ink">Crew Lead flow</span>
        <Badge variant="outline" className="text-[10px]">{done} / 8 done</Badge>
      </div>
      <p className="text-xs text-faint mt-0.5">
        You're the {flow.role_on_job === "secondary" ? "backup " : ""}Crew Lead. Tap each step as it happens — nothing advances on its own.
      </p>
      <StepRail steps={flow.steps} />
      {nextTap ? <NextButton /> : (
        <div data-testid="job-lead-done" className="mt-3 rounded-lg border border-success/40 bg-success/10 px-3 py-2.5 text-[13px] text-primary flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-success" /> All eight steps logged. Nice work.
        </div>
      )}

      {/* Depart inspection */}
      <Dialog open={departOpen} onOpenChange={setDepartOpen}>
        <DialogContent data-testid="job-lead-depart-dialog" className="max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">Pre-trip truck check — {flow.truck_name || "truck"}</DialogTitle>
            <DialogDescription>Confirm each item before you roll. A critical item (brakes, tires, lights, leaks) blocks departure until the owner clears it.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            {(flow.inspection_items || []).map((it) => {
              const critical = (flow.critical_keys || []).includes(it.key);
              return (
                <label key={it.key} data-testid={`job-lead-insp-${it.key}`} className="flex items-center gap-2.5 text-sm cursor-pointer">
                  <Checkbox checked={!!insp[it.key]} onCheckedChange={(v) => setInsp((s) => ({ ...s, [it.key]: !!v }))} />
                  <span className="flex-1">{it.label}</span>
                  {critical && <span className="text-[10px] font-bold text-destructive uppercase">critical</span>}
                </label>
              );
            })}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDepartOpen(false)}>Cancel</Button>
            <Button data-testid="job-lead-depart-confirm-btn" onClick={confirmDepart} className="bg-primary hover:bg-[#152238] gap-1.5"><Truck className="w-4 h-4" /> Confirm &amp; Depart</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Complete */}
      <Dialog open={completeOpen} onOpenChange={setCompleteOpen}>
        <DialogContent data-testid="job-lead-complete-dialog" className="max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">Finish "{flow.job_name}"?</DialogTitle>
            <DialogDescription>Confirm the job ran as quoted, log anything that slowed you down, and sign it with your name. This does NOT record any payment.</DialogDescription>
          </DialogHeader>
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-faint mb-2">Anything slow you down?</p>
            <div className="grid grid-cols-2 gap-x-3 gap-y-2">
              {DELAY_FACTORS.map((fct) => (
                <label key={fct} data-testid={`job-lead-delay-${fct}`} className="flex items-center gap-2 text-sm cursor-pointer">
                  <Checkbox checked={factors.includes(fct)} onCheckedChange={() => toggleFactor(fct)} /> {fct}
                </label>
              ))}
            </div>
          </div>
          <Textarea data-testid="job-lead-asfound-input" placeholder="As-found notes: extra items, differences from the quote, great customer…" value={notes} onChange={(e) => setNotes(e.target.value)} />
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-faint mb-1">Your name (who's confirming)</p>
            <Input data-testid="job-lead-identity-input" value={identity} onChange={(e) => setIdentity(e.target.value)} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCompleteOpen(false)}>Not yet</Button>
            <Button data-testid="job-lead-complete-confirm-btn" onClick={confirmComplete} className="bg-success hover:bg-success gap-1.5"><Flag className="w-4 h-4" /> Mark complete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Clock out */}
      <Dialog open={clockoutOpen} onOpenChange={setClockoutOpen}>
        <DialogContent data-testid="job-lead-clockout-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">Clock out</DialogTitle>
            <DialogDescription>Confirm the post-trip truck check. If this is the truck's last job today, this records the end-of-day inspection.</DialogDescription>
          </DialogHeader>
          <label data-testid="job-lead-defect-toggle" className="flex items-center gap-2.5 text-sm cursor-pointer">
            <Checkbox checked={!noDefects} onCheckedChange={(v) => setNoDefects(!v)} />
            <span>There's a truck defect to report</span>
          </label>
          <DialogFooter>
            <Button variant="outline" onClick={() => setClockoutOpen(false)}>Cancel</Button>
            <Button data-testid="job-lead-clockout-confirm-btn" onClick={doClockOut} className="bg-primary hover:bg-[#152238] gap-1.5"><LogOut className="w-4 h-4" /> {noDefects ? "Clock out — no defects" : "Clock out — report defect"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

const StepRail = ({ steps }) => (
  <div className="mt-3 space-y-1.5">
    {steps.map((s) => {
      const Icon = STEP_ICON[s.key] || Circle;
      return (
        <div key={s.key} data-testid={`job-lead-step-${s.key}`} className="flex items-center gap-2.5 text-[13px]">
          {s.done ? <CheckCircle2 className="w-4 h-4 text-success shrink-0" /> : <Icon className="w-4 h-4 text-faint shrink-0" />}
          <span className={s.done ? "text-primary" : "text-faint"}>{s.label}</span>
          {s.done && s.by && <span className="text-[11px] text-faint ml-auto shrink-0">{s.by}{s.at ? ` · ${fmt(s.at)}` : ""}</span>}
        </div>
      );
    })}
  </div>
);
