import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { CreditPromptsCard } from "@/components/team/CreditPromptsCard";
import { TEAM_CHIP } from "@/components/team/BadgeMedallion";
import { teamMembersApi, listCreditsApi, addCreditApi, deleteCreditApi, apiErrorMessage } from "@/lib/api";
import { fmtDate, todayISO } from "@/lib/format";

export const AdminCreditsTab = () => {
  const [members, setMembers] = useState([]);
  const [credits, setCredits] = useState(null);
  const [form, setForm] = useState({ user_id: "", team: "crew", role_tag: "driver", job_ref: "", date: todayISO() });
  const [busy, setBusy] = useState(false);

  const loadCredits = useCallback(() => listCreditsApi({ limit: 100 }).then(setCredits).catch(() => setCredits([])), []);
  useEffect(() => {
    teamMembersApi().then((d) => setMembers(d.members.filter((m) => m.teams.length > 0))).catch(() => {});
    loadCredits();
  }, [loadCredits]);

  const pickedMember = members.find((m) => m.id === form.user_id);
  const memberTeams = pickedMember?.teams || ["crew", "sales"];

  const setMember = (id) => {
    const m = members.find((x) => x.id === id);
    const team = m && !m.teams.includes(form.team) ? m.teams[0] : form.team;
    setForm((f) => ({ ...f, user_id: id, team }));
  };

  const add = async () => {
    setBusy(true);
    try {
      const res = await addCreditApi({
        user_id: form.user_id, team: form.team,
        role_tag: form.team === "crew" ? form.role_tag : null,
        job_ref: form.job_ref || "Job", date: form.date,
      });
      toast.success("Credit added.");
      (res.newly_unlocked || []).forEach((n) => toast.success(`Badge unlocked: ${n}!`));
      setForm((f) => ({ ...f, job_ref: "" }));
      loadCredits();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  const remove = async (c) => {
    try {
      await deleteCreditApi(c.id);
      toast.success("Credit removed.");
      loadCredits();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  return (
    <div className="space-y-4 mt-4">
      <CreditPromptsCard onResolved={loadCredits} />

      <div className="surface p-4" data-testid="manual-credit-card">
        <h2 className="font-bold text-primary mb-3">Credit a job by hand</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
          <div>
            <Label>Who</Label>
            <Select value={form.user_id} onValueChange={setMember}>
              <SelectTrigger data-testid="credit-member-select"><SelectValue placeholder="Pick a member" /></SelectTrigger>
              <SelectContent>
                {members.map((m) => (
                  <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Team</Label>
            <Select value={form.team} onValueChange={(v) => setForm((f) => ({ ...f, team: v }))}>
              <SelectTrigger data-testid="credit-team-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                {memberTeams.map((t) => (
                  <SelectItem key={t} value={t}>{t === "crew" ? "Crew (job)" : "Sales (close)"}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {form.team === "crew" && (
            <div>
              <Label>Worked as</Label>
              <Select value={form.role_tag} onValueChange={(v) => setForm((f) => ({ ...f, role_tag: v }))}>
                <SelectTrigger data-testid="credit-roletag-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="driver">Driver</SelectItem>
                  <SelectItem value="helper">Helper</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
          <div>
            <Label>Job / lead name</Label>
            <Input data-testid="credit-jobref-input" value={form.job_ref} onChange={(e) => setForm((f) => ({ ...f, job_ref: e.target.value }))} placeholder="Smith move" />
          </div>
          <div>
            <Label>Date</Label>
            <Input data-testid="credit-date-input" type="date" value={form.date} onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))} />
          </div>
        </div>
        <Button data-testid="credit-add-btn" size="sm" className="mt-3 gap-1.5 bg-accent hover:bg-accent-press" disabled={busy || !form.user_id || !form.date} onClick={add}>
          <Plus className="w-4 h-4" /> Add credit
        </Button>
      </div>

      <div className="surface" data-testid="credits-list">
        <h2 className="font-bold text-primary px-4 py-3 border-b border-border">Recent credits</h2>
        <div className="divide-y divide-border">
          {credits === null && <p className="text-sm text-faint px-4 py-6 text-center">Loading…</p>}
          {credits?.length === 0 && <p className="text-sm text-faint px-4 py-6 text-center">No credits yet — everyone starts at zero from launch day.</p>}
          {(credits || []).map((c) => (
            <div key={c.id} data-testid="credit-row" className="flex flex-wrap items-center gap-2 px-4 py-2.5 text-sm">
              <span className="font-semibold text-primary">{c.user_name}</span>
              <Badge variant="outline" className={`text-[10px] capitalize ${TEAM_CHIP[c.team]}`}>{c.team === "crew" ? c.role_tag || "crew" : "close"}</Badge>
              <span className="text-faint truncate flex-1 min-w-[120px]">{c.job_ref}</span>
              <span className="text-xs text-faint">{fmtDate(c.date)}</span>
              <span className="text-[10px] text-faint/70 uppercase">{c.source}</span>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button data-testid="credit-delete-btn" variant="ghost" size="sm" className="h-7 px-2 text-destructive hover:text-destructive">
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle className="font-display">Remove this credit?</AlertDialogTitle>
                    <AlertDialogDescription>
                      {c.user_name} loses this tally. Badges already unlocked stay unless you take them back on the Badges tab.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Keep it</AlertDialogCancel>
                    <AlertDialogAction data-testid="credit-delete-confirm" onClick={() => remove(c)} className="bg-destructive hover:bg-destructive/90">Yes, remove</AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
