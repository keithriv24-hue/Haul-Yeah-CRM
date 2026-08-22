import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, Gift, Settings2, Star, Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import {
  apiErrorMessage, createCatalogItemApi, giveRecognitionApi, listBadgesApi, listRewardsApi,
  patchCatalogItemApi, rewardActionApi, rewardsCatalogApi, rewardsConfigApi, rewardsPayrollCsvApi,
  rewardsSummaryApi, saveRewardsConfigApi, teamMembersApi,
} from "@/lib/api";
import { fmtDate } from "@/lib/format";

const STATUS_CHIP = {
  pending: "bg-warning/10 text-warning border-warning/30",
  approved: "bg-info/10 text-info border-info/30",
  fulfilled: "bg-success/10 text-success border-success/30",
  denied: "bg-surface-sunk text-faint border-border-strong",
  voided: "bg-surface-sunk text-faint border-border-strong",
};

const BudgetBar = ({ label, b, testId }) => {
  const pct = b.budget > 0 ? Math.min(100, Math.round((b.committed / b.budget) * 100)) : 0;
  return (
    <div data-testid={testId} className="rounded-lg border border-border p-3">
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="font-bold text-primary capitalize">{label}</span>
        <span className="text-faint tnum">${b.committed} of ${b.budget} · ${b.remaining} left</span>
      </div>
      <div className="h-2 bg-surface-sunk rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${pct >= 90 ? "bg-destructive" : pct >= 70 ? "bg-warning" : "bg-success"}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
};

const RecognitionDialog = ({ open, onOpenChange, onSaved }) => {
  const [members, setMembers] = useState([]);
  const [badges, setBadges] = useState([]);
  const [f, setF] = useState({ user_id: "", reason: "", points: "", amount: "", badge_id: "", title: "" });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (open) {
      setF({ user_id: "", reason: "", points: "", amount: "", badge_id: "", title: "" });
      teamMembersApi().then((d) => setMembers(d.members.filter((m) => m.teams.length > 0))).catch(() => {});
      listBadgesApi().then(setBadges).catch(() => {});
    }
  }, [open]);
  const give = async () => {
    setBusy(true);
    try {
      const res = await giveRecognitionApi({
        user_id: f.user_id, reason: f.reason.trim(), points: Number(f.points) || 0,
        amount: Number(f.amount) || 0, badge_id: f.badge_id === "none" ? "" : f.badge_id, title: f.title.trim(),
      });
      toast.success(`Recognition sent — ${res.given.join(", ")}.`);
      onOpenChange(false);
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="recognition-dialog" className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">Give recognition</DialogTitle>
          <DialogDescription>Spot-reward someone who went above and beyond. Everything here is logged.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Member</Label>
            <Select value={f.user_id} onValueChange={(v) => setF((s) => ({ ...s, user_id: v }))}>
              <SelectTrigger data-testid="recognition-member-select"><SelectValue placeholder="Pick a member" /></SelectTrigger>
              <SelectContent>
                {members.map((m) => <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div><Label>Why (required — goes on the record)</Label>
            <Textarea data-testid="recognition-reason-input" rows={2} value={f.reason} onChange={(e) => setF((s) => ({ ...s, reason: e.target.value }))} placeholder="Stayed late to help the second crew finish the Maplewood job." /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Haul Points</Label><Input data-testid="recognition-points-input" type="number" min="0" value={f.points} onChange={(e) => setF((s) => ({ ...s, points: e.target.value }))} placeholder="250" /></div>
            <div><Label>Spot bonus ($)</Label><Input data-testid="recognition-amount-input" type="number" min="0" value={f.amount} onChange={(e) => setF((s) => ({ ...s, amount: e.target.value }))} placeholder="0" /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Badge (optional)</Label>
              <Select value={f.badge_id || "none"} onValueChange={(v) => setF((s) => ({ ...s, badge_id: v }))}>
                <SelectTrigger data-testid="recognition-badge-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No badge</SelectItem>
                  {badges.filter((b) => b.active).map((b) => <SelectItem key={b.id} value={b.id}>{b.name} ({b.track})</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div><Label>Title (optional)</Label><Input data-testid="recognition-title-input" value={f.title} onChange={(e) => setF((s) => ({ ...s, title: e.target.value }))} placeholder="Clutch Player" /></div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="recognition-send-btn" disabled={busy || !f.user_id || !f.reason.trim()} onClick={give} className="bg-accent hover:bg-accent-press gap-1.5">
            <Star className="w-4 h-4" /> Send recognition
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const CONFIG_FIELDS = [
  { key: "crewMonthlyBudget", label: "Crew monthly reward budget ($)" },
  { key: "salesMonthlyBudget", label: "Sales monthly reward budget ($)" },
  { key: "maxSingleReward", label: "Maximum single reward ($)" },
  { key: "pointsPerDollar", label: "Haul Points per $1" },
];
const TYPE_TOGGLES = ["points", "cash", "gift_card", "merch", "meal", "custom"];

const ConfigDialog = ({ open, onOpenChange, onSaved }) => {
  const [cfg, setCfg] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) rewardsConfigApi().then(setCfg).catch(() => {}); }, [open]);
  const save = async () => {
    setBusy(true);
    try {
      await saveRewardsConfigApi(cfg);
      toast.success("Reward settings saved.");
      onOpenChange(false);
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };
  if (!cfg) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="rewards-config-dialog" className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">Reward settings</DialogTitle>
          <DialogDescription>Budgets, the points rate, and which reward types are allowed. AI limits live on the AI Agent tab.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            {CONFIG_FIELDS.map(({ key, label }) => (
              <div key={key}>
                <Label>{label}</Label>
                <Input data-testid={`config-${key}-input`} type="number" min="0" value={cfg[key]}
                  onChange={(e) => setCfg((s) => ({ ...s, [key]: e.target.value }))} />
              </div>
            ))}
          </div>
          <p className="text-[11px] text-faint">At {Number(cfg.pointsPerDollar) || 10} points per $1: 250 pts = ${Math.round(250 / (Number(cfg.pointsPerDollar) || 10))} · 500 pts = ${Math.round(500 / (Number(cfg.pointsPerDollar) || 10))} · 1,000 pts = ${Math.round(1000 / (Number(cfg.pointsPerDollar) || 10))}.</p>
          <div>
            <Label className="mb-1.5 block">Enabled reward types</Label>
            <div className="grid grid-cols-2 gap-2">
              {TYPE_TOGGLES.map((t) => (
                <label key={t} className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm capitalize">
                  {t.replace("_", " ")}
                  <Switch data-testid={`config-type-${t}`} checked={(cfg.enabledRewardTypes || []).includes(t)}
                    onCheckedChange={(on) => setCfg((s) => ({
                      ...s,
                      enabledRewardTypes: on ? [...(s.enabledRewardTypes || []), t] : (s.enabledRewardTypes || []).filter((x) => x !== t),
                    }))} />
                </label>
              ))}
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="config-save-btn" disabled={busy} onClick={save} className="bg-accent hover:bg-accent-press">Save settings</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const CatalogManager = () => {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ name: "", points_cost: "", value: "", kind: "gift_card" });
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => rewardsCatalogApi().then(setData).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  const add = async () => {
    setBusy(true);
    try {
      await createCatalogItemApi({ name: form.name, points_cost: Number(form.points_cost) || 0, value: Number(form.value) || 0, kind: form.kind, active: true });
      toast.success("Catalog reward added.");
      setForm({ name: "", points_cost: "", value: "", kind: "gift_card" });
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };
  const toggle = async (item) => {
    try {
      await patchCatalogItemApi(item.id, { ...item, active: !item.active });
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };
  return (
    <div className="surface p-4" data-testid="catalog-manager">
      <h2 className="font-bold text-primary mb-1">Redemption catalog</h2>
      <p className="text-xs text-faint mb-3">What employees can spend Haul Points on. You fulfill these by hand — nothing is purchased automatically.</p>
      <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-2 items-end mb-3">
        <div className="lg:col-span-2"><Label>Name</Label><Input data-testid="catalog-name-input" value={form.name} onChange={(e) => setForm((s) => ({ ...s, name: e.target.value }))} placeholder="$25 coffee gift card" /></div>
        <div><Label>Points</Label><Input data-testid="catalog-points-input" type="number" min="1" value={form.points_cost} onChange={(e) => setForm((s) => ({ ...s, points_cost: e.target.value }))} /></div>
        <div><Label>Value ($)</Label><Input data-testid="catalog-value-input" type="number" min="0" value={form.value} onChange={(e) => setForm((s) => ({ ...s, value: e.target.value }))} /></div>
        <Button data-testid="catalog-add-btn" size="sm" className="gap-1 bg-primary hover:bg-[#152238]" disabled={busy || !form.name.trim() || !Number(form.points_cost)} onClick={add}>
          <Plus className="w-4 h-4" /> Add
        </Button>
      </div>
      <div className="divide-y divide-border">
        {(data?.items || []).map((item) => (
          <div key={item.id} data-testid="catalog-row" className={`flex items-center gap-3 py-2 ${item.active ? "" : "opacity-50"}`}>
            <Gift className="w-4 h-4 text-accent-ink shrink-0" />
            <span className="flex-1 text-sm font-semibold text-primary">{item.name}</span>
            <span className="text-xs font-bold text-accent-ink tnum">{item.points_cost} pts</span>
            <span className="text-xs text-faint tnum w-12 text-right">${item.value}</span>
            <Switch data-testid="catalog-active-switch" checked={item.active} onCheckedChange={() => toggle(item)} />
          </div>
        ))}
      </div>
    </div>
  );
};

const QUEUES = ["pending", "approved", "fulfilled", "all"];

export const AdminRewardsTab = () => {
  const [summary, setSummary] = useState(null);
  const [queue, setQueue] = useState("pending");
  const [rewards, setRewards] = useState(null);
  const [recogOpen, setRecogOpen] = useState(false);
  const [cfgOpen, setCfgOpen] = useState(false);
  const [busy, setBusy] = useState("");

  const load = useCallback(() => {
    rewardsSummaryApi().then(setSummary).catch(() => {});
    listRewardsApi(queue === "all" ? {} : { status: queue }).then(setRewards).catch(() => setRewards([]));
  }, [queue]);
  useEffect(() => { load(); }, [load]);

  const act = async (r, action) => {
    const reason = ["deny", "void"].includes(action) ? window.prompt(`Reason for ${action}?`) : null;
    if (["deny", "void"].includes(action) && reason === null) return;
    setBusy(r.id + action);
    try {
      await rewardActionApi(r.id, action, { reason: reason || "", notes: "" });
      toast.success(`Reward ${action === "deny" ? "denied" : action === "void" ? "voided" : action + "d"}.`);
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy("");
  };

  const downloadPayroll = async () => {
    try {
      const csv = await rewardsPayrollCsvApi(summary?.month);
      const blob = new Blob([csv], { type: "text/csv" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `rewards-payroll-${summary?.month || "current"}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  return (
    <div className="space-y-4 mt-4">
      <div className="flex flex-wrap gap-2 justify-end">
        <Button data-testid="give-recognition-btn" size="sm" className="gap-1.5 bg-accent hover:bg-accent-press" onClick={() => setRecogOpen(true)}>
          <Star className="w-4 h-4" /> Give recognition
        </Button>
        <Button data-testid="rewards-settings-btn" size="sm" variant="outline" className="gap-1.5" onClick={() => setCfgOpen(true)}>
          <Settings2 className="w-4 h-4" /> Reward settings
        </Button>
        <Button data-testid="payroll-csv-btn" size="sm" variant="outline" className="gap-1.5" onClick={downloadPayroll}>
          <Download className="w-4 h-4" /> Payroll CSV
        </Button>
      </div>

      {summary && (
        <div className="surface p-4" data-testid="rewards-summary-card">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-bold text-primary">This month — {summary.month}</h2>
            <span className="text-xs text-faint">Committed includes pending rewards, so you never promise past the budget.</span>
          </div>
          <div className="grid sm:grid-cols-2 gap-3 mb-3">
            <BudgetBar testId="budget-crew" label="Crew budget" b={summary.budgets.crew} />
            <BudgetBar testId="budget-sales" label="Sales budget" b={summary.budgets.sales} />
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-faint" data-testid="rewards-totals">
            <span>Cash: <strong className="text-primary">${summary.totals.cash}</strong></span>
            <span>Gift cards: <strong className="text-primary">${summary.totals.gift_card}</strong></span>
            <span>Points issued: <strong className="text-primary">{summary.totals.points_issued}</strong></span>
            <span>Points redeemed: <strong className="text-primary">{summary.totals.points_redeemed}</strong></span>
            <span>Total value: <strong className="text-primary">${summary.totals.total_value}</strong></span>
          </div>
        </div>
      )}

      <div className="surface p-4" data-testid="rewards-queue-card">
        <div className="flex flex-wrap items-center gap-1.5 mb-3">
          {QUEUES.map((q) => (
            <button key={q} data-testid={`queue-tab-${q}`} onClick={() => setQueue(q)}
              className={`px-3 py-1.5 rounded-full text-xs font-bold capitalize ${queue === q ? "bg-primary text-white" : "bg-surface-sunk text-faint hover:text-primary"}`}>
              {q}{q === "pending" && summary?.counts?.pending ? ` (${summary.counts.pending})` : ""}
            </button>
          ))}
        </div>
        {rewards === null ? (
          <p className="text-sm text-faint">Loading…</p>
        ) : rewards.length === 0 ? (
          <p className="text-sm text-faint" data-testid="rewards-queue-empty">Nothing {queue === "all" ? "yet" : queue} right now.</p>
        ) : (
          <div className="space-y-1.5">
            {rewards.map((r) => (
              <div key={r.id} data-testid="reward-admin-row" className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2 text-sm">
                <div className="flex-1 min-w-[180px]">
                  <span className="font-semibold text-primary">{r.user_name}</span>
                  <span className="text-ink-2"> — {r.reward_name}</span>
                  <span className="block text-[11px] text-faint">
                    {r.reason || r.challenge_name || r.source} · {fmtDate((r.earned_at || "").slice(0, 10))}
                    {r.payroll_required && <span className="text-warning font-semibold"> · payroll</span>}
                  </span>
                </div>
                <span className="text-xs font-bold text-ink-2 tnum">
                  {r.reward_type === "redemption" ? `−${r.points} pts / $${r.amount}` : [r.amount > 0 && `$${r.amount}`, r.points > 0 && `${r.points} pts`].filter(Boolean).join(" + ") || "—"}
                </span>
                <Badge variant="outline" className={`text-[10px] capitalize ${STATUS_CHIP[r.status] || ""}`}>{r.status}</Badge>
                {r.status === "pending" && (
                  <>
                    <Button data-testid="reward-approve-btn" size="sm" className="h-7 text-xs bg-success hover:bg-success" disabled={!!busy} onClick={() => act(r, "approve")}>Approve</Button>
                    <Button data-testid="reward-deny-btn" size="sm" variant="outline" className="h-7 text-xs text-destructive border-destructive/25" disabled={!!busy} onClick={() => act(r, "deny")}>Deny</Button>
                  </>
                )}
                {r.status === "approved" && (
                  <>
                    <Button data-testid="reward-fulfill-btn" size="sm" className="h-7 text-xs bg-accent hover:bg-accent-press" disabled={!!busy} onClick={() => act(r, "fulfill")}>Mark fulfilled</Button>
                    <Button data-testid="reward-void-btn" size="sm" variant="outline" className="h-7 text-xs text-destructive border-destructive/25" disabled={!!busy} onClick={() => act(r, "void")}>Void</Button>
                  </>
                )}
                {r.status === "fulfilled" && (
                  <Button data-testid="reward-void-btn" size="sm" variant="ghost" className="h-7 text-xs text-faint" disabled={!!busy} onClick={() => act(r, "void")}>Void</Button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <CatalogManager />
      <RecognitionDialog open={recogOpen} onOpenChange={setRecogOpen} onSaved={load} />
      <ConfigDialog open={cfgOpen} onOpenChange={setCfgOpen} onSaved={load} />
    </div>
  );
};
