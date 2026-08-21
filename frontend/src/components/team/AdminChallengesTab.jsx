import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, ClipboardCheck, Trophy, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { ChallengeCard } from "@/components/team/ChallengeCard";
import {
  listChallengesApi, createChallengeApi, patchChallengeApi, deleteChallengeApi,
  verifyChallengeApi, awardChallengeApi, listBadgesApi, apiErrorMessage,
} from "@/lib/api";

const EMPTY = {
  name: "", description: "", team: "crew", type: "individual", metric: "job_credits",
  target: "6", start: "", end: "", reward_kind: "badge", reward_badge_id: "", reward_title: "",
};

const ChallengeFormDialog = ({ open, onOpenChange, editing, badges, onSaved }) => {
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(editing
        ? { name: editing.name, description: editing.description, team: editing.team, type: editing.type,
            metric: editing.metric, target: String(editing.target || ""), start: editing.start, end: editing.end,
            reward_kind: editing.reward?.kind || "badge", reward_badge_id: editing.reward?.badge_id || "",
            reward_title: editing.reward?.title || "" }
        : EMPTY);
    }
  }, [open, editing]);

  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setBusy(true);
    const payload = { ...form, target: form.type === "individual" ? Number(form.target) || 0 : null };
    try {
      if (editing) await patchChallengeApi(editing.id, payload);
      else await createChallengeApi(payload);
      toast.success(editing ? "Challenge updated." : "Challenge is live.");
      onOpenChange(false);
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="challenge-form-dialog" className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">{editing ? "Edit challenge" : "New challenge"}</DialogTitle>
          <DialogDescription>Auto-tracked challenges fill in from job credits. Owner-verified ones you update yourself.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div><Label>Name</Label><Input data-testid="challenge-name-input" value={form.name} onChange={(e) => set("name")(e.target.value)} placeholder="Full House October" /></div>
          <div><Label>What's the goal?</Label><Textarea data-testid="challenge-desc-input" rows={2} value={form.description} onChange={(e) => set("description")(e.target.value)} placeholder="Complete 6 jobs this month." /></div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <Label>Team</Label>
              <Select value={form.team} onValueChange={set("team")}>
                <SelectTrigger data-testid="challenge-team-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="crew">Crew</SelectItem>
                  <SelectItem value="sales">Sales</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Type</Label>
              <Select value={form.type} onValueChange={set("type")}>
                <SelectTrigger data-testid="challenge-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="individual">Individual (everyone can win)</SelectItem>
                  <SelectItem value="competition">Competition (one winner)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Tracked by</Label>
              <Select value={form.metric} onValueChange={set("metric")}>
                <SelectTrigger data-testid="challenge-metric-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="job_credits">Job credits (auto)</SelectItem>
                  <SelectItem value="owner_verified">Owner-verified</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {form.type === "individual" && (
              <div><Label>Goal count</Label><Input data-testid="challenge-target-input" type="number" min="1" value={form.target} onChange={(e) => set("target")(e.target.value)} /></div>
            )}
            <div><Label>Starts</Label><Input data-testid="challenge-start-input" type="date" value={form.start} onChange={(e) => set("start")(e.target.value)} /></div>
            <div><Label>Ends</Label><Input data-testid="challenge-end-input" type="date" value={form.end} onChange={(e) => set("end")(e.target.value)} /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Reward</Label>
              <Select value={form.reward_kind} onValueChange={set("reward_kind")}>
                <SelectTrigger data-testid="challenge-reward-kind-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="badge">A badge</SelectItem>
                  <SelectItem value="title">A profile title</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {form.reward_kind === "badge" ? (
              <div>
                <Label>Which badge</Label>
                <Select value={form.reward_badge_id} onValueChange={set("reward_badge_id")}>
                  <SelectTrigger data-testid="challenge-reward-badge-select"><SelectValue placeholder="Pick a badge" /></SelectTrigger>
                  <SelectContent>
                    {badges.filter((b) => b.active && b.track === form.team).map((b) => (
                      <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : (
              <div><Label>Title text</Label><Input data-testid="challenge-reward-title-input" value={form.reward_title} onChange={(e) => set("reward_title")(e.target.value)} placeholder="October MVP" /></div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="challenge-save-btn" disabled={busy || !form.name.trim() || !form.start || !form.end} onClick={save} className="bg-accent hover:bg-accent-press">
            {editing ? "Save challenge" : "Launch it"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const VerifyDialog = ({ ch, onOpenChange, onSaved }) => {
  const [values, setValues] = useState({});
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (ch) setValues(Object.fromEntries((ch.progress || []).map((r) => [r.user_id, r.value])));
  }, [ch]);

  const save = async () => {
    setBusy(true);
    try {
      for (const r of ch.progress || []) {
        const v = Number(values[r.user_id]) || 0;
        if (v !== r.value) await verifyChallengeApi(ch.id, r.user_id, v);
      }
      toast.success("Progress updated.");
      onOpenChange(null);
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <Dialog open={!!ch} onOpenChange={() => onOpenChange(null)}>
      <DialogContent data-testid="verify-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Update progress — {ch?.name}</DialogTitle>
          <DialogDescription>Type each person's confirmed count. This is the number the challenge uses.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {(ch?.progress || []).map((r) => (
            <div key={r.user_id} className="flex items-center gap-3">
              <span className="flex-1 text-sm font-semibold text-primary">{r.name}</span>
              <Input data-testid={`verify-input-${r.user_id}`} type="number" min="0" className="w-24 h-8" value={values[r.user_id] ?? 0} onChange={(e) => setValues((v) => ({ ...v, [r.user_id]: e.target.value }))} />
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(null)}>Cancel</Button>
          <Button data-testid="verify-save-btn" disabled={busy} onClick={save} className="bg-accent hover:bg-accent-press">Save progress</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const AwardDialog = ({ ch, onOpenChange, onSaved }) => {
  const [picked, setPicked] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (ch) {
      if (ch.type === "individual" && ch.target) setPicked((ch.progress || []).filter((r) => r.value >= ch.target).map((r) => r.user_id));
      else {
        const top = ch.progress?.[0]?.value || 0;
        setPicked(top > 0 ? (ch.progress || []).filter((r) => r.value === top).map((r) => r.user_id) : []);
      }
    }
  }, [ch]);

  const award = async () => {
    setBusy(true);
    try {
      await awardChallengeApi(ch.id, picked);
      toast.success(picked.length ? "Rewards sent out." : "Challenge closed with no winner.");
      onOpenChange(null);
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <Dialog open={!!ch} onOpenChange={() => onOpenChange(null)}>
      <DialogContent data-testid="award-challenge-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Confirm winners — {ch?.name}</DialogTitle>
          <DialogDescription>Check everyone who earned the reward, then send it out. This can't be undone.</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          {(ch?.progress || []).map((r) => (
            <label key={r.user_id} className="flex items-center gap-2.5 text-sm cursor-pointer rounded-md border border-border px-3 py-2">
              <Checkbox
                data-testid={`winner-check-${r.user_id}`}
                checked={picked.includes(r.user_id)}
                onCheckedChange={() => setPicked((p) => (p.includes(r.user_id) ? p.filter((x) => x !== r.user_id) : [...p, r.user_id]))}
              />
              <span className="flex-1 font-semibold text-primary">{r.name}</span>
              <span className="font-mono text-faint">{r.value}</span>
            </label>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(null)}>Cancel</Button>
          <Button data-testid="award-challenge-confirm-btn" disabled={busy} onClick={award} className="bg-success hover:bg-success gap-1.5">
            <Trophy className="w-4 h-4" /> Send rewards ({picked.length})
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export const AdminChallengesTab = () => {
  const [data, setData] = useState(null);
  const [badges, setBadges] = useState([]);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [verifying, setVerifying] = useState(null);
  const [awarding, setAwarding] = useState(null);

  const load = useCallback(() => listChallengesApi().then(setData).catch(() => setData({ challenges: [] })), []);
  useEffect(() => {
    load();
    listBadgesApi().then(setBadges).catch(() => {});
  }, [load]);

  const remove = async (ch) => {
    try {
      await deleteChallengeApi(ch.id);
      toast.success("Challenge deleted.");
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  const all = data?.challenges || [];
  const order = { needs_verify: 0, active: 1, awarded: 2, ended: 2 };
  const sorted = [...all].sort((a, b) => (order[a.status] ?? 3) - (order[b.status] ?? 3));

  return (
    <div className="space-y-4 mt-4">
      <div className="flex justify-end">
        <Button data-testid="new-challenge-btn" size="sm" className="gap-1.5 bg-accent hover:bg-accent-press" onClick={() => { setEditing(null); setFormOpen(true); }}>
          <Plus className="w-4 h-4" /> New challenge
        </Button>
      </div>
      <div className="grid lg:grid-cols-2 gap-4" data-testid="admin-challenges-list">
        {sorted.map((ch) => (
          <ChallengeCard key={ch.id} ch={ch} me={null}>
            <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-border">
              {ch.metric === "owner_verified" && ["active", "needs_verify"].includes(ch.status) && (
                <Button data-testid="challenge-verify-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => setVerifying(ch)}>
                  <ClipboardCheck className="w-3.5 h-3.5" /> Update progress
                </Button>
              )}
              {ch.status === "needs_verify" && (
                <Button data-testid="challenge-award-btn" size="sm" className="gap-1 text-xs bg-success hover:bg-success" onClick={() => setAwarding(ch)}>
                  <Trophy className="w-3.5 h-3.5" /> Confirm winners
                </Button>
              )}
              {ch.status === "active" && (
                <Button data-testid="challenge-edit-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => { setEditing(ch); setFormOpen(true); }}>
                  <Pencil className="w-3.5 h-3.5" /> Edit
                </Button>
              )}
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button data-testid="challenge-delete-btn" variant="outline" size="sm" className="gap-1 text-xs text-destructive border-destructive/25 hover:bg-destructive/10">
                    <Trash2 className="w-3.5 h-3.5" /> Delete
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle className="font-display">Delete “{ch.name}”?</AlertDialogTitle>
                    <AlertDialogDescription>It disappears for the team. Badges or titles already handed out stay.</AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Keep it</AlertDialogCancel>
                    <AlertDialogAction data-testid="challenge-delete-confirm" onClick={() => remove(ch)} className="bg-destructive hover:bg-destructive/90">Yes, delete</AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </ChallengeCard>
        ))}
      </div>

      <ChallengeFormDialog open={formOpen} onOpenChange={setFormOpen} editing={editing} badges={badges} onSaved={load} />
      <VerifyDialog ch={verifying} onOpenChange={setVerifying} onSaved={load} />
      <AwardDialog ch={awarding} onOpenChange={setAwarding} onSaved={load} />
    </div>
  );
};
