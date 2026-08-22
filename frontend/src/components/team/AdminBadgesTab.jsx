import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Award as AwardIcon, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { BadgeMedallion, BADGE_ICONS, RARITY_CHIP } from "@/components/team/BadgeMedallion";
import { teamMembersApi, listBadgesApi, createBadgeApi, patchBadgeApi, awardBadgeApi, revokeBadgeApi, apiErrorMessage } from "@/lib/api";

const EMPTY = { track: "crew", name: "", description: "", rarity: "bronze", icon: "Medal", auto_metric: "", auto_threshold: "", unlock_points: "", unlock_amount: "" };
const METRIC_LABEL = { jobs: "jobs completed", driver: "jobs as Driver", helper: "jobs as Helper", closes: "moves closed", driver_and_helper: "jobs as Driver AND Helper" };

const BadgeFormDialog = ({ open, onOpenChange, editing, onSaved }) => {
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(editing
        ? { track: editing.track, name: editing.name, description: editing.description, rarity: editing.rarity,
            icon: editing.icon, auto_metric: editing.auto?.metric || "", auto_threshold: editing.auto?.threshold || "",
            unlock_points: String(editing.unlock_reward?.points || ""), unlock_amount: String(editing.unlock_reward?.amount || "") }
        : EMPTY);
    }
  }, [open, editing]);

  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setBusy(true);
    const payload = {
      track: form.track, name: form.name, description: form.description, rarity: form.rarity, icon: form.icon,
      auto_metric: form.auto_metric || (editing ? "" : null),
      auto_threshold: form.auto_metric ? Number(form.auto_threshold) || 0 : null,
      unlock_points: Number(form.unlock_points) || 0,
      unlock_amount: Number(form.unlock_amount) || 0,
    };
    try {
      if (editing) await patchBadgeApi(editing.id, payload);
      else await createBadgeApi(payload);
      toast.success(editing ? "Badge updated." : "Badge created.");
      onOpenChange(false);
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="badge-form-dialog" className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">{editing ? "Edit badge" : "New badge"}</DialogTitle>
          <DialogDescription>Badges with an auto-unlock count award themselves from job credits. Leave it off to hand them out yourself.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Track</Label>
              <Select value={form.track} onValueChange={set("track")} disabled={!!editing}>
                <SelectTrigger data-testid="badge-track-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="crew">Crew</SelectItem>
                  <SelectItem value="sales">Sales</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Rarity</Label>
              <Select value={form.rarity} onValueChange={set("rarity")}>
                <SelectTrigger data-testid="badge-rarity-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="bronze">Bronze</SelectItem>
                  <SelectItem value="silver">Silver</SelectItem>
                  <SelectItem value="gold">Gold</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div><Label>Name</Label><Input data-testid="badge-name-input" value={form.name} onChange={(e) => set("name")(e.target.value)} placeholder="Night Owl" /></div>
          <div><Label>What it's for</Label><Input data-testid="badge-desc-input" value={form.description} onChange={(e) => set("description")(e.target.value)} placeholder="Finished a job after 8pm" /></div>
          <div>
            <Label>Icon</Label>
            <div className="grid grid-cols-8 gap-1.5 mt-1">
              {Object.keys(BADGE_ICONS).map((name) => {
                const Icon = BADGE_ICONS[name];
                return (
                  <button
                    key={name}
                    data-testid={`badge-icon-${name}`}
                    onClick={() => set("icon")(name)}
                    className={`h-9 rounded-md border flex items-center justify-center transition-colors ${
                      form.icon === name ? "border-accent bg-accent/10 text-accent-ink" : "border-border text-faint hover:border-border-strong"
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                  </button>
                );
              })}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Auto-unlock (optional)</Label>
              <Select value={form.auto_metric || "none"} onValueChange={(v) => set("auto_metric")(v === "none" ? "" : v)}>
                <SelectTrigger data-testid="badge-metric-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Owner-awarded (no auto)</SelectItem>
                  <SelectItem value="jobs">Jobs completed</SelectItem>
                  <SelectItem value="driver">Jobs as Driver</SelectItem>
                  <SelectItem value="helper">Jobs as Helper</SelectItem>
                  <SelectItem value="closes">Moves closed</SelectItem>
                  <SelectItem value="driver_and_helper">Driver AND Helper (each)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {form.auto_metric && (
              <div>
                <Label>Count needed</Label>
                <Input data-testid="badge-threshold-input" type="number" min="1" value={form.auto_threshold} onChange={(e) => set("auto_threshold")(e.target.value)} />
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Milestone Haul Points (optional)</Label>
              <Input data-testid="badge-unlock-points-input" type="number" min="0" value={form.unlock_points} onChange={(e) => set("unlock_points")(e.target.value)} placeholder="0" />
            </div>
            <div>
              <Label>One-time bonus $ (optional)</Label>
              <Input data-testid="badge-unlock-amount-input" type="number" min="0" value={form.unlock_amount} onChange={(e) => set("unlock_amount")(e.target.value)} placeholder="0" />
            </div>
          </div>
          <p className="text-[11px] text-faint -mt-1">Milestone rewards fire once, when the badge unlocks \u2014 they wait in your Rewards queue for approval. Most badges should stay recognition-only.</p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="badge-save-btn" disabled={busy || !form.name.trim()} onClick={save} className="bg-accent hover:bg-accent-press">
            {editing ? "Save badge" : "Create badge"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export const AdminBadgesTab = () => {
  const [badges, setBadges] = useState([]);
  const [members, setMembers] = useState([]);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [award, setAward] = useState({ user_id: "", badge_id: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => listBadgesApi().then(setBadges).catch(() => {}), []);
  useEffect(() => {
    load();
    teamMembersApi().then((d) => setMembers(d.members.filter((m) => m.teams.length > 0))).catch(() => {});
  }, [load]);

  const doAward = async () => {
    setBusy(true);
    try {
      const res = await awardBadgeApi(award.badge_id, award.user_id);
      toast[res.awarded ? "success" : "info"](res.awarded ? `${res.badge} awarded to ${res.user}.` : `${res.user} already has ${res.badge}.`);
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  const doRevoke = async () => {
    setBusy(true);
    try {
      await revokeBadgeApi(award.badge_id, award.user_id);
      toast.success("Badge taken back.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  const toggleActive = async (b) => {
    try {
      await patchBadgeApi(b.id, { active: !b.active });
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  return (
    <div className="space-y-4 mt-4">
      <div className="surface p-4" data-testid="award-badge-card">
        <h2 className="font-bold text-primary mb-3">Award or take back a badge</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 items-end">
          <div>
            <Label>Member</Label>
            <Select value={award.user_id} onValueChange={(v) => setAward((a) => ({ ...a, user_id: v }))}>
              <SelectTrigger data-testid="award-member-select"><SelectValue placeholder="Pick a member" /></SelectTrigger>
              <SelectContent>
                {members.map((m) => (
                  <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Badge</Label>
            <Select value={award.badge_id} onValueChange={(v) => setAward((a) => ({ ...a, badge_id: v }))}>
              <SelectTrigger data-testid="award-badge-select"><SelectValue placeholder="Pick a badge" /></SelectTrigger>
              <SelectContent>
                {badges.filter((b) => b.active).map((b) => (
                  <SelectItem key={b.id} value={b.id}>{b.name} ({b.track})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button data-testid="award-badge-btn" size="sm" className="gap-1.5 bg-accent hover:bg-accent-press" disabled={busy || !award.user_id || !award.badge_id} onClick={doAward}>
            <AwardIcon className="w-4 h-4" /> Award it
          </Button>
          <Button data-testid="revoke-badge-btn" size="sm" variant="outline" className="gap-1.5 text-destructive border-destructive/25 hover:bg-destructive/10" disabled={busy || !award.user_id || !award.badge_id} onClick={doRevoke}>
            <Undo2 className="w-4 h-4" /> Take it back
          </Button>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <h2 className="font-bold text-primary">All badges</h2>
        <Button data-testid="new-badge-btn" size="sm" className="gap-1.5 bg-primary hover:bg-[#152238]" onClick={() => { setEditing(null); setFormOpen(true); }}>
          <Plus className="w-4 h-4" /> New badge
        </Button>
      </div>

      {["crew", "sales"].map((track) => (
        <div key={track} className="surface" data-testid={`badge-list-${track}`}>
          <h3 className="text-xs font-bold uppercase tracking-wide text-faint px-4 py-2.5 border-b border-border capitalize">{track} track</h3>
          <div className="divide-y divide-border">
            {badges.filter((b) => b.track === track).map((b) => (
              <div key={b.id} data-testid="badge-admin-row" className={`flex items-center gap-3 px-4 py-2.5 ${b.active ? "" : "opacity-50"}`}>
                <BadgeMedallion badge={b} size="sm" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-primary">{b.name}</span>
                    <Badge variant="outline" className={`text-[9px] font-bold capitalize ${RARITY_CHIP[b.rarity]}`}>{b.rarity}</Badge>
                  </div>
                  <p className="text-xs text-faint truncate">
                    {b.description}
                    {b.auto && <span className="text-faint"> · auto at {b.auto.threshold} {METRIC_LABEL[b.auto.metric]}</span>}
                    {!b.auto && <span className="text-faint"> · owner-awarded</span>}
                    {(b.unlock_reward?.points > 0 || b.unlock_reward?.amount > 0) && (
                      <span data-testid="badge-unlock-hint" className="text-accent-ink font-semibold"> · unlocks {[b.unlock_reward.points > 0 && `${b.unlock_reward.points} pts`, b.unlock_reward.amount > 0 && `$${b.unlock_reward.amount}`].filter(Boolean).join(" + ")}</span>
                    )}
                  </p>
                </div>
                <Button data-testid="edit-badge-btn" variant="ghost" size="sm" className="h-7 px-2" onClick={() => { setEditing(b); setFormOpen(true); }}>
                  <Pencil className="w-3.5 h-3.5" />
                </Button>
                <Switch data-testid="badge-active-switch" checked={b.active} onCheckedChange={() => toggleActive(b)} />
              </div>
            ))}
          </div>
        </div>
      ))}

      <BadgeFormDialog open={formOpen} onOpenChange={setFormOpen} editing={editing} onSaved={load} />
    </div>
  );
};
