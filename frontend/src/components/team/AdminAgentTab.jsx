import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Bot, Check, Pencil, RefreshCw, Sparkles, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { TEAM_CHIP } from "@/components/team/BadgeMedallion";
import {
  agentDraftsApi, agentGenerateApi, agentRetryApi, agentStatusApi, apiErrorMessage,
  patchDraftApi, publishDraftApi, rejectDraftApi, saveRewardsConfigApi,
} from "@/lib/api";
import { rewardLabel } from "@/components/team/ChallengeCard";
import { fmtDate } from "@/lib/format";

const AI_TOGGLES = [
  ["aiEnabled", "AI Challenge Agent"],
  ["aiMonthlyGeneration", "Generate monthly (automatic)"],
  ["aiAutoPublish", "Auto-publish (skip your approval)"],
  ["aiRequireApproval", "Require owner approval"],
  ["aiAllowCompetition", "Allow competition challenges"],
  ["aiAllowTeamChallenges", "Allow team challenges"],
  ["aiAllowPoints", "Allow Haul Point rewards"],
  ["aiAllowCash", "Allow cash rewards"],
  ["aiAllowGiftCards", "Allow gift card rewards"],
];
const AI_NUMBERS = [
  ["aiCrewChallengesPerMonth", "Crew challenges / month"],
  ["aiSalesChallengesPerMonth", "Sales challenges / month"],
  ["aiMaxRewardPerChallenge", "Max AI reward per winner ($)"],
  ["aiCrewMonthlyBudget", "AI crew monthly budget ($)"],
  ["aiSalesMonthlyBudget", "AI sales monthly budget ($)"],
];

const EditDraftDialog = ({ draft, onOpenChange, onSaved }) => {
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (draft) setF({ name: draft.name, description: draft.description, target: draft.target || "",
      start: draft.start, end: draft.end, reward_amount: draft.reward?.amount || 0, reward_points: draft.reward?.points || 0 });
  }, [draft]);
  if (!draft || !f) return null;
  const save = async () => {
    setBusy(true);
    try {
      await patchDraftApi(draft.id, { ...f, target: Number(f.target) || null,
        reward_amount: Number(f.reward_amount) || 0, reward_points: Number(f.reward_points) || 0 });
      toast.success("Draft updated — guardrails re-checked.");
      onOpenChange(null);
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };
  return (
    <Dialog open={!!draft} onOpenChange={() => onOpenChange(null)}>
      <DialogContent data-testid="edit-draft-dialog" className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">Edit draft</DialogTitle>
          <DialogDescription>Edits go back through the safety and budget guardrails before saving.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div><Label>Name</Label><Input data-testid="draft-name-input" value={f.name} onChange={(e) => setF((s) => ({ ...s, name: e.target.value }))} /></div>
          <div><Label>Description</Label><Textarea data-testid="draft-desc-input" rows={3} value={f.description} onChange={(e) => setF((s) => ({ ...s, description: e.target.value }))} /></div>
          <div className="grid grid-cols-3 gap-3">
            {draft.type !== "competition" && (
              <div><Label>Target</Label><Input data-testid="draft-target-input" type="number" min="1" value={f.target} onChange={(e) => setF((s) => ({ ...s, target: e.target.value }))} /></div>
            )}
            <div><Label>Starts</Label><Input data-testid="draft-start-input" type="date" value={f.start} onChange={(e) => setF((s) => ({ ...s, start: e.target.value }))} /></div>
            <div><Label>Ends</Label><Input data-testid="draft-end-input" type="date" value={f.end} onChange={(e) => setF((s) => ({ ...s, end: e.target.value }))} /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Cash ($ per winner)</Label><Input data-testid="draft-amount-input" type="number" min="0" value={f.reward_amount} onChange={(e) => setF((s) => ({ ...s, reward_amount: e.target.value }))} /></div>
            <div><Label>Haul Points per winner</Label><Input data-testid="draft-points-input" type="number" min="0" value={f.reward_points} onChange={(e) => setF((s) => ({ ...s, reward_points: e.target.value }))} /></div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(null)}>Cancel</Button>
          <Button data-testid="draft-save-btn" disabled={busy} onClick={save} className="bg-accent hover:bg-accent-press">Save draft</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const DraftCard = ({ d, onPublish, onEdit, onRegenerate, onReject, busy }) => (
  <div data-testid="agent-draft-card" className="surface p-4">
    <div className="flex flex-wrap items-center gap-2 mb-1">
      <Sparkles className="w-4 h-4 text-accent-ink" />
      <h3 className="font-display font-bold text-primary">{d.name}</h3>
      <Badge variant="outline" className={`text-[10px] capitalize ${TEAM_CHIP[d.team] || ""}`}>{d.team}</Badge>
      <Badge variant="outline" className="text-[10px] capitalize bg-surface-sunk text-ink-2 border-border-strong">{(d.category || "").replace("_", " ")}</Badge>
      <Badge variant="outline" className="text-[10px] capitalize bg-info/10 text-info border-info/30">{d.difficulty}</Badge>
      {d.source === "fallback" && <Badge variant="outline" className="text-[10px] bg-warning/10 text-warning border-warning/30">template fallback</Badge>}
    </div>
    <p className="text-sm text-ink-2 mb-2">{d.description}</p>
    <div className="grid sm:grid-cols-2 gap-x-4 gap-y-1 text-xs text-faint mb-2">
      {d.target != null && <span>Target: <strong className="text-primary">{d.target}</strong> {d.baseline != null && <>· baseline ~{d.baseline}/member/mo</>}</span>}
      <span>Runs {fmtDate(d.start)} – {fmtDate(d.end)}</span>
      <span>Reward: <strong className="text-primary">{rewardLabel(d.reward)}</strong></span>
      <span>Max possible cost: <strong className="text-primary">${d.estimated_cost}</strong> ({d.estimated_winners} possible winner{d.estimated_winners === 1 ? "" : "s"})</span>
      <span>Verification: <strong className="text-primary">{d.verification === "auto" ? "auto (job credits)" : "owner-verified"}</strong></span>
      <span>Eligibility: <strong className="text-primary capitalize">{d.eligible_roles === "all" ? `${d.team} — all` : d.eligible_roles}</strong> · confidence {(d.confidence * 100).toFixed(0)}%</span>
    </div>
    {d.why && <p data-testid="draft-why" className="text-xs text-faint italic border-l-2 border-accent/40 pl-2 mb-3">Why: {d.why}</p>}
    <div className="flex flex-wrap gap-2">
      <Button data-testid="draft-publish-btn" size="sm" className="h-8 text-xs gap-1 bg-success hover:bg-success" disabled={busy} onClick={() => onPublish(d)}>
        <Check className="w-3.5 h-3.5" /> Approve & publish
      </Button>
      <Button data-testid="draft-edit-btn" size="sm" variant="outline" className="h-8 text-xs gap-1" disabled={busy} onClick={() => onEdit(d)}>
        <Pencil className="w-3.5 h-3.5" /> Edit
      </Button>
      <Button data-testid="draft-regenerate-btn" size="sm" variant="outline" className="h-8 text-xs gap-1" disabled={busy} onClick={() => onRegenerate(d)}>
        <RefreshCw className="w-3.5 h-3.5" /> Regenerate
      </Button>
      <Button data-testid="draft-reject-btn" size="sm" variant="outline" className="h-8 text-xs gap-1 text-destructive border-destructive/25" disabled={busy} onClick={() => onReject(d)}>
        <X className="w-3.5 h-3.5" /> Reject
      </Button>
    </div>
  </div>
);

export const AdminAgentTab = () => {
  const [status, setStatus] = useState(null);
  const [drafts, setDrafts] = useState(null);
  const [cfg, setCfg] = useState(null);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState("");

  const load = useCallback(() => {
    agentStatusApi().then((s) => { setStatus(s); setCfg(s.config); }).catch(() => {});
    agentDraftsApi().then(setDrafts).catch(() => setDrafts([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const generate = async (team) => {
    setBusy(`gen-${team}`);
    try {
      const res = await agentGenerateApi(team);
      const rej = res.rejected?.length ? ` (${res.rejected.length} rejected by guardrails)` : "";
      toast.success(`${res.drafts.length} draft${res.drafts.length === 1 ? "" : "s"} ready for review${rej}.${res.source === "fallback" ? " AI was unavailable — used the template generator." : ""}`);
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy("");
  };
  const publish = async (d) => {
    setBusy(d.id);
    try {
      await publishDraftApi(d.id);
      toast.success(`“${d.name}” is live — the ${d.team} team was notified.`);
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy("");
  };
  const reject = async (d) => {
    setBusy(d.id);
    try {
      await rejectDraftApi(d.id);
      toast.success("Draft rejected.");
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy("");
  };
  const regenerate = async (d) => {
    setBusy(d.id);
    try {
      await rejectDraftApi(d.id, "regenerated");
      const res = await agentGenerateApi(d.team, 1);
      toast.success(res.drafts.length ? "Fresh draft ready." : "Couldn't produce a new draft — guardrails rejected the candidates.");
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy("");
  };
  const saveCfg = async () => {
    setBusy("cfg");
    try {
      await saveRewardsConfigApi(cfg);
      toast.success("Agent settings saved.");
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy("");
  };
  const retry = async () => {
    await agentRetryApi().catch(() => {});
    await generate("both");
  };

  if (!status || !cfg) return <p className="text-sm text-faint mt-4">Loading…</p>;

  return (
    <div className="space-y-4 mt-4">
      <div className="surface p-4" data-testid="agent-status-card">
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <Bot className="w-4 h-4 text-accent-ink" />
          <h2 className="font-bold text-primary">Challenge Agent</h2>
          <Badge variant="outline" className={`text-[10px] ${cfg.aiEnabled ? "bg-success/10 text-success border-success/30" : "bg-surface-sunk text-faint border-border-strong"}`}>
            {cfg.aiEnabled ? "On" : "Off"}
          </Badge>
          {!status.llm_available && <Badge variant="outline" className="text-[10px] bg-warning/10 text-warning border-warning/30">AI key missing — template fallback only</Badge>}
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-faint mb-3" data-testid="agent-status-facts">
          <span>Drafts waiting: <strong className="text-primary">{status.drafts_waiting}</strong></span>
          <span>Published this month: <strong className="text-primary">{status.published_this_month}</strong></span>
          <span>AI spend — crew: <strong className="text-primary">${status.ai_spend.crew}</strong> of ${cfg.aiCrewMonthlyBudget}</span>
          <span>sales: <strong className="text-primary">${status.ai_spend.sales}</strong> of ${cfg.aiSalesMonthlyBudget}</span>
          {status.last_run && <span>Last auto-run: <strong className={status.last_run.status === "failed" ? "text-destructive" : "text-primary"}>{status.last_run.status}</strong></span>}
        </div>
        {status.last_run?.status === "failed" && (
          <div data-testid="agent-failed-banner" className="text-xs bg-destructive/10 border border-destructive/25 text-destructive rounded-md px-3 py-2 mb-3">
            Challenge generation failed — <button className="font-bold underline" onClick={retry}>retry now</button>. ({status.last_run.error})
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <Button data-testid="generate-both-btn" size="sm" className="gap-1.5 bg-accent hover:bg-accent-press" disabled={!!busy || !cfg.aiEnabled} onClick={() => generate("both")}>
            <Sparkles className="w-4 h-4" /> {busy === "gen-both" ? "Thinking…" : "Generate new challenges"}
          </Button>
          <Button data-testid="generate-crew-btn" size="sm" variant="outline" disabled={!!busy || !cfg.aiEnabled} onClick={() => generate("crew")}>
            {busy === "gen-crew" ? "Thinking…" : "Crew only"}
          </Button>
          <Button data-testid="generate-sales-btn" size="sm" variant="outline" disabled={!!busy || !cfg.aiEnabled} onClick={() => generate("sales")}>
            {busy === "gen-sales" ? "Thinking…" : "Sales only"}
          </Button>
        </div>
        <p className="text-[11px] text-faint mt-2">
          Targets come from your real job and close history — never invented. Every draft passes safety, fairness, duplicate, and budget checks, and nothing goes live without your approval{cfg.aiAutoPublish && !cfg.aiRequireApproval ? " (auto-publish is ON)" : ""}.
        </p>
      </div>

      {drafts !== null && drafts.length > 0 && (
        <div data-testid="agent-drafts-list">
          <h2 className="label-eyebrow mb-3">Drafts waiting on you</h2>
          <div className="grid lg:grid-cols-2 gap-4">
            {drafts.map((d) => (
              <DraftCard key={d.id} d={d} busy={!!busy} onPublish={publish} onEdit={setEditing} onRegenerate={regenerate} onReject={reject} />
            ))}
          </div>
        </div>
      )}
      {drafts !== null && drafts.length === 0 && (
        <p className="text-sm text-faint" data-testid="agent-no-drafts">No drafts waiting. Generate a fresh set any time.</p>
      )}

      <div className="surface p-4" data-testid="agent-settings-card">
        <h2 className="font-bold text-primary mb-3">Agent settings</h2>
        <div className="grid sm:grid-cols-2 gap-2 mb-3">
          {AI_TOGGLES.map(([key, label]) => (
            <label key={key} className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm">
              {label}
              <Switch data-testid={`agent-toggle-${key}`} checked={!!cfg[key]} onCheckedChange={(v) => setCfg((s) => ({ ...s, [key]: v }))} />
            </label>
          ))}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-3">
          {AI_NUMBERS.map(([key, label]) => (
            <div key={key}>
              <Label>{label}</Label>
              <Input data-testid={`agent-${key}-input`} type="number" min="0" value={cfg[key]} onChange={(e) => setCfg((s) => ({ ...s, [key]: e.target.value }))} />
            </div>
          ))}
          <div>
            <Label>Difficulty</Label>
            <Select value={cfg.aiDifficulty} onValueChange={(v) => setCfg((s) => ({ ...s, aiDifficulty: v }))}>
              <SelectTrigger data-testid="agent-difficulty-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="easy">Easy wins</SelectItem>
                <SelectItem value="moderate">Moderate</SelectItem>
                <SelectItem value="stretch">Stretch goals</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex justify-end">
          <Button data-testid="agent-settings-save-btn" size="sm" disabled={busy === "cfg"} onClick={saveCfg} className="bg-accent hover:bg-accent-press">Save agent settings</Button>
        </div>
      </div>

      <EditDraftDialog draft={editing} onOpenChange={setEditing} onSaved={load} />
    </div>
  );
};
