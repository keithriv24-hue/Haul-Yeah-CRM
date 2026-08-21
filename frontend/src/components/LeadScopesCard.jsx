import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { PencilRuler, Plus, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { apiErrorMessage, listScopesApi, patchScopeVideoApi } from "@/lib/api";

const money = (n) => "$" + Math.round(n || 0).toLocaleString();

const scopePrice = (s) => {
  if (s.result?.mode === "final" && s.result?.finalTotal) return `${money(s.result.finalTotal)} firm`;
  if (s.result?.bandLo != null) return `${money(s.result.bandLo)}–${money(s.result.bandHi)} range`;
  return s.tier === "survey" ? "Survey scope — priced by owner" : "No price yet";
};

const VideoSurveyBlock = ({ scope, onSaved }) => {
  const v = scope.video || {};
  const [form, setForm] = useState({ link: v.link || "", received: !!v.received, date: v.received_date || "" });
  const [busy, setBusy] = useState(false);
  const dirty = form.link !== (v.link || "") || form.received !== !!v.received || form.date !== (v.received_date || "");

  const save = async () => {
    setBusy(true);
    try {
      await patchScopeVideoApi(scope._id, { link: form.link, received: form.received, received_date: form.date });
      toast.success("Video survey saved on the latest scope.");
      onSaved();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    setBusy(false);
  };

  return (
    <div className="mt-3 pt-3 border-t border-border" data-testid="lead-video-survey">
      <p className="text-[10px] tracking-[.16em] uppercase text-faint font-bold mb-1.5 flex items-center gap-1"><Video className="w-3 h-3" /> Video survey</p>
      <div className="flex flex-wrap items-center gap-2">
        <Input data-testid="lead-video-link-input" placeholder="Video link (Drive, iCloud, YouTube…)" className="h-8 text-xs flex-1 min-w-[180px]"
          value={form.link} onChange={(e) => setForm((s) => ({ ...s, link: e.target.value }))} />
        <label className="flex items-center gap-1.5 text-xs font-semibold text-primary cursor-pointer">
          <Checkbox data-testid="lead-video-received-checkbox" checked={form.received}
            onCheckedChange={(val) => setForm((s) => ({ ...s, received: !!val, date: val && !s.date ? new Date().toISOString().slice(0, 10) : s.date }))} />
          Received
        </label>
        {form.received && (
          <Input data-testid="lead-video-date-input" type="date" className="h-8 text-xs w-[140px]"
            value={form.date} onChange={(e) => setForm((s) => ({ ...s, date: e.target.value }))} />
        )}
        {dirty && (
          <Button data-testid="lead-video-save-btn" size="sm" className="h-8 text-xs bg-accent hover:bg-accent-press" disabled={busy} onClick={save}>
            {busy ? "Saving…" : "Save"}
          </Button>
        )}
      </div>
      {form.received && <p className="text-[10.5px] text-success mt-1">Counts as a completed survey — final mode unlocks in the calculator.</p>}
    </div>
  );
};

export const LeadScopesCard = ({ leadId, leadName, role }) => {
  const navigate = useNavigate();
  const [scopes, setScopes] = useState(null);
  const canSee = role === "owner" || role === "sales";

  useEffect(() => {
    if (!canSee) return;
    listScopesApi(leadId).then(setScopes).catch(() => setScopes([]));
  }, [leadId, canSee]);

  if (!canSee) return null;

  const go = (extra = "") =>
    navigate(`/scope-calculator?lead=${encodeURIComponent(leadId)}&name=${encodeURIComponent(leadName || "")}${extra}`);

  return (
    <div className="surface p-5" data-testid="lead-scopes-card">
      <div className="flex items-center justify-between mb-2">
        <h2 className="font-display font-bold text-primary">Scopes</h2>
        <Button data-testid="lead-scope-new-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => go()}>
          <Plus className="w-3.5 h-3.5" /> Start a new scope
        </Button>
      </div>
      {scopes === null && <p className="text-sm text-faint">Loading…</p>}
      {scopes && scopes.length === 0 && (
        <p className="text-sm text-faint" data-testid="lead-scopes-empty">No scopes yet. Start one to size this move room by room.</p>
      )}
      {scopes && scopes.length > 0 && (
        <div className="space-y-1">
          {scopes.map((s) => (
            <div key={s._id} data-testid="lead-scope-row" className="flex items-center justify-between gap-2 rounded-md px-2 py-2 hover:bg-surface-sunk">
              <div className="min-w-0 text-[13px]">
                <span className="font-semibold text-primary">{scopePrice(s)}</span>
                <span className="text-faint ml-2">
                  {s.created_by} · {new Date(s.created_at).toLocaleString()}
                  {s.refined_from ? " · refined" : ""}
                  {s.survey_complete ? " · survey ✓" : ""}
                  {s.video?.received ? ` · video ✓${s.video.received_date ? ` ${s.video.received_date}` : ""}` : ""}
                </span>
              </div>
              <Button data-testid="lead-scope-refine-btn" variant="outline" size="sm" className="gap-1 text-xs shrink-0"
                onClick={() => go(`&refine=${encodeURIComponent(s._id)}`)}>
                <PencilRuler className="w-3.5 h-3.5" /> Refine this scope
              </Button>
            </div>
          ))}
        </div>
      )}
      {scopes && scopes.length > 0 && <VideoSurveyBlock scope={scopes[0]} onSaved={() => listScopesApi(leadId).then(setScopes).catch(() => {})} />}
    </div>
  );
};
