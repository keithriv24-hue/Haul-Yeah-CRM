import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { useApp } from "@/context/AppContext";
import { createAssignmentApi, updateAssignmentApi, apiErrorMessage } from "@/lib/api";
import { PF, f } from "@/lib/fields";

const BLANK = { project_id: "", job_name: "", job_date: "", arrival_time: "", start_address: "", end_address: "", truck_id: "" };

export const AssignmentModal = ({ open, onOpenChange, initial, users, trucks, onSaved }) => {
  const { records, loadTable } = useApp();
  const [form, setForm] = useState(BLANK);
  const [crewSel, setCrewSel] = useState({});
  const [warnings, setWarnings] = useState([]);
  const [busy, setBusy] = useState(false);

  const crewUsers = users.filter((u) => u.role === "crew" && u.active);
  const activeTrucks = trucks.filter((t) => t.active);
  const projects = records("projects").filter((p) => f(p, PF.status) !== "Cancelled");

  useEffect(() => {
    if (!open) return;
    loadTable("projects");
    if (initial) {
      setForm({
        project_id: initial.project_id || "",
        job_name: initial.job_name || "",
        job_date: initial.job_date || "",
        arrival_time: initial.arrival_time || "",
        start_address: initial.start_address || "",
        end_address: initial.end_address || "",
        truck_id: initial.truck_id || "",
      });
      setCrewSel(Object.fromEntries((initial.crew || []).map((c) => [c.user_id, c.position])));
    } else {
      setForm(BLANK);
      setCrewSel({});
    }
    setWarnings([]);
  }, [open, initial]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k) => (v) => setForm((prev) => ({ ...prev, [k]: v }));

  const pickProject = (id) => {
    if (id === "none") {
      set("project_id")("");
      return;
    }
    const rec = projects.find((p) => p.id === id);
    if (!rec) return;
    setForm((prev) => ({
      ...prev,
      project_id: id,
      job_name: f(rec, PF.jobName) || prev.job_name,
      job_date: (f(rec, PF.jobDate) || prev.job_date || "").slice(0, 10),
      start_address: f(rec, PF.fromAddr) || prev.start_address,
      end_address: f(rec, PF.toAddr) || prev.end_address,
    }));
  };

  const toggleCrew = (uid) =>
    setCrewSel((s) => {
      const next = { ...s };
      if (next[uid]) delete next[uid];
      else next[uid] = "Helper";
      return next;
    });

  const save = async (ignore = false) => {
    setBusy(true);
    setWarnings([]);
    const payload = {
      ...form,
      project_id: form.project_id || null,
      truck_id: form.truck_id || null,
      crew: Object.entries(crewSel).map(([user_id, position]) => ({ user_id, position })),
      ignore_warnings: ignore,
    };
    try {
      if (initial) await updateAssignmentApi(initial.id, payload);
      else await createAssignmentApi(payload);
      toast.success(initial ? "Job updated — crew changes were sent out." : "Crew assigned — they've been notified.");
      onOpenChange(false);
      onSaved();
    } catch (e) {
      const det = e?.response?.data?.detail;
      if (e?.response?.status === 409 && det?.warnings) setWarnings(det.warnings);
      else toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="assignment-modal" className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-display">{initial ? "Edit job assignment" : "Assign a job"}</DialogTitle>
          <DialogDescription>Pick a booked job (or type one in), choose the crew, and they get notified.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Link to a booked job (optional)</Label>
            <Select value={form.project_id || "none"} onValueChange={pickProject}>
              <SelectTrigger data-testid="assignment-project-select"><SelectValue placeholder="Pick a job" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No link — type it in</SelectItem>
                {projects.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{f(p, PF.jobName) || "Untitled job"}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Job name</Label>
            <Input data-testid="assignment-name-input" value={form.job_name} onChange={(e) => set("job_name")(e.target.value)} placeholder="Smith move — Montclair" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Date</Label>
              <Input data-testid="assignment-date-input" type="date" value={form.job_date} onChange={(e) => set("job_date")(e.target.value)} />
            </div>
            <div>
              <Label>Arrival time</Label>
              <Input data-testid="assignment-time-input" type="time" value={form.arrival_time} onChange={(e) => set("arrival_time")(e.target.value)} />
            </div>
          </div>
          <div>
            <Label>Start address</Label>
            <Input data-testid="assignment-from-input" value={form.start_address} onChange={(e) => set("start_address")(e.target.value)} placeholder="123 Main St, Montclair NJ" />
          </div>
          <div>
            <Label>End address</Label>
            <Input data-testid="assignment-to-input" value={form.end_address} onChange={(e) => set("end_address")(e.target.value)} placeholder="456 Oak Ave, Newark NJ" />
          </div>
          <div>
            <Label>Truck</Label>
            <Select value={form.truck_id || "none"} onValueChange={(v) => set("truck_id")(v === "none" ? "" : v)}>
              <SelectTrigger data-testid="assignment-truck-select"><SelectValue placeholder="Pick a truck" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No truck / labor only</SelectItem>
                {activeTrucks.map((t) => (
                  <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Crew</Label>
            <div className="space-y-2 mt-1">
              {crewUsers.length === 0 && <p className="text-xs text-slate-400">No active crew accounts yet — add them on the Team tab.</p>}
              {crewUsers.map((u) => (
                <div key={u.id} data-testid="assignment-crew-row" className="flex items-center gap-3">
                  <Checkbox data-testid="assignment-crew-checkbox" id={`crew-${u.id}`} checked={!!crewSel[u.id]} onCheckedChange={() => toggleCrew(u.id)} />
                  <label htmlFor={`crew-${u.id}`} className="text-sm flex-1 cursor-pointer">{u.name}</label>
                  {crewSel[u.id] && (
                    <Select value={crewSel[u.id]} onValueChange={(v) => setCrewSel((s) => ({ ...s, [u.id]: v }))}>
                      <SelectTrigger data-testid="assignment-position-select" className="w-28 h-8 text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Driver">Driver</SelectItem>
                        <SelectItem value="Helper">Helper</SelectItem>
                      </SelectContent>
                    </Select>
                  )}
                </div>
              ))}
            </div>
          </div>
          {warnings.length > 0 && (
            <div data-testid="assignment-warnings" className="bg-amber-50 border border-amber-200 rounded-md p-3 space-y-1">
              <p className="text-xs font-bold text-amber-800 flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> Hold on:</p>
              {warnings.map((w, i) => (
                <p key={i} className="text-xs text-amber-800">• {w}</p>
              ))}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          {warnings.length > 0 ? (
            <Button data-testid="assignment-force-save" disabled={busy} onClick={() => save(true)} className="bg-amber-600 hover:bg-amber-700">
              Assign anyway
            </Button>
          ) : (
            <Button data-testid="assignment-save" disabled={busy || !form.job_name || !form.job_date} onClick={() => save(false)} className="bg-[#E8743B] hover:bg-[#d4632e]">
              {initial ? "Save changes" : "Assign job"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
