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
import { PF, LF, f } from "@/lib/fields";

const BLANK = { project_id: "", job_name: "", job_date: "", arrival_time: "", start_address: "", end_address: "", truck_id: "", job_size: "" };
const JOB_SIZES = ["Studio/1BR", "2BR", "3BR", "4BR+", "Office/Commercial", "Labor-only (no truck)"];

export const AssignmentModal = ({ open, onOpenChange, initial, users, trucks, onSaved }) => {
  const { records, loadTable } = useApp();
  const [form, setForm] = useState(BLANK);
  const [crewSel, setCrewSel] = useState({});
  const [leadPrimary, setLeadPrimary] = useState("");
  const [leadSecondary, setLeadSecondary] = useState("");
  const [warnings, setWarnings] = useState([]);
  const [busy, setBusy] = useState(false);

  const crewUsers = users.filter((u) => u.role === "crew" && u.active);
  const activeTrucks = trucks.filter((t) => t.active);
  const projects = records("projects").filter((p) => f(p, PF.status) !== "Cancelled");
  const selectedCrew = crewUsers.filter((u) => crewSel[u.id]).map((u) => ({ id: u.id, name: u.name }));

  useEffect(() => {
    if (!open) return;
    loadTable("projects");
    loadTable("leads");
    if (initial) {
      setForm({
        project_id: initial.project_id || "",
        job_name: initial.job_name || "",
        job_date: initial.job_date || "",
        arrival_time: initial.arrival_time || "",
        start_address: initial.start_address || "",
        end_address: initial.end_address || "",
        truck_id: initial.truck_id || "",
        job_size: initial.job_size || "",
      });
      setCrewSel(Object.fromEntries((initial.crew || []).map((c) => [c.user_id, c.position])));
      setLeadPrimary(initial.crew_lead?.primary_id || "");
      setLeadSecondary(initial.crew_lead?.secondary_id || "");
    } else {
      setForm(BLANK);
      setCrewSel({});
      setLeadPrimary("");
      setLeadSecondary("");
    }
    setWarnings([]);
  }, [open, initial]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the Crew Lead selection valid: default the primary to the Driver (else first crew),
  // drop any lead who is no longer on the crew, and never let the backup equal the primary.
  useEffect(() => {
    const ids = Object.keys(crewSel);
    setLeadPrimary((cur) => {
      if (cur && crewSel[cur]) return cur;
      if (!ids.length) return "";
      return ids.find((id) => crewSel[id] === "Driver") || ids[0];
    });
    setLeadSecondary((cur) => (cur && crewSel[cur] ? cur : ""));
  }, [crewSel]);

  useEffect(() => {
    if (leadSecondary && leadSecondary === leadPrimary) setLeadSecondary("");
  }, [leadPrimary, leadSecondary]);

  const set = (k) => (v) => setForm((prev) => ({ ...prev, [k]: v }));

  const pickProject = (id) => {
    if (id === "none") {
      set("project_id")("");
      return;
    }
    const rec = projects.find((p) => p.id === id);
    if (!rec) return;
    const leadIds = f(rec, PF.lead) || [];
    const lead = records("leads").find((l) => leadIds.includes(l.id));
    const homeSize = lead ? f(lead, LF.homeSize) : null;
    setForm((prev) => ({
      ...prev,
      project_id: id,
      job_name: f(rec, PF.jobName) || prev.job_name,
      job_date: (f(rec, PF.jobDate) || prev.job_date || "").slice(0, 10),
      start_address: f(rec, PF.fromAddr) || prev.start_address,
      end_address: f(rec, PF.toAddr) || prev.end_address,
      job_size: JOB_SIZES.includes(homeSize) ? homeSize : prev.job_size,
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
      crew_lead_id: leadPrimary || null,
      crew_lead_secondary_id: leadSecondary || null,
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
            <Label>Job size (goes on the time log)</Label>
            <Select value={form.job_size || "none"} onValueChange={(v) => set("job_size")(v === "none" ? "" : v)}>
              <SelectTrigger data-testid="assignment-size-select"><SelectValue placeholder="Pick a size" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Not set</SelectItem>
                {JOB_SIZES.map((s) => (
                  <SelectItem key={s} value={s}>{s}</SelectItem>
                ))}
              </SelectContent>
            </Select>
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
              {crewUsers.length === 0 && <p className="text-xs text-faint">No active crew accounts yet — add them on the Team tab.</p>}
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
          {selectedCrew.length > 0 && (
            <div data-testid="assignment-crew-lead-block" className="rounded-md border border-accent/25 bg-accent/5 p-3 space-y-3">
              <p className="text-xs font-bold uppercase tracking-wide text-accent-ink">Crew Lead for this truck</p>
              <div>
                <Label>Primary Crew Lead</Label>
                <Select value={leadPrimary || undefined} onValueChange={setLeadPrimary}>
                  <SelectTrigger data-testid="assignment-lead-primary-select"><SelectValue placeholder="Pick the Crew Lead" /></SelectTrigger>
                  <SelectContent>
                    {selectedCrew.map((u) => (
                      <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-faint mt-1">Runs the move-day checklist. A job role only — it doesn't change Driver/Helper pay.</p>
              </div>
              <div>
                <Label>Backup Crew Lead (optional)</Label>
                <Select value={leadSecondary || "none"} onValueChange={(v) => setLeadSecondary(v === "none" ? "" : v)}>
                  <SelectTrigger data-testid="assignment-lead-secondary-select"><SelectValue placeholder="None" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    {selectedCrew.filter((u) => u.id !== leadPrimary).map((u) => (
                      <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
          {warnings.length > 0 && (
            <div data-testid="assignment-warnings" className="bg-warning/10 border border-warning/25 rounded-md p-3 space-y-1">
              <p className="text-xs font-bold text-warning flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> Hold on:</p>
              {warnings.map((w, i) => (
                <p key={i} className="text-xs text-warning">• {w}</p>
              ))}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          {warnings.length > 0 ? (
            <Button data-testid="assignment-force-save" disabled={busy} onClick={() => save(true)} className="bg-warning hover:bg-warning">
              Assign anyway
            </Button>
          ) : (
            <Button data-testid="assignment-save" disabled={busy || !form.job_name || !form.job_date} onClick={() => save(false)} className="bg-accent hover:bg-accent-press">
              {initial ? "Save changes" : "Assign job"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
