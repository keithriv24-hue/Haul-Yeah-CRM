import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PencilRuler, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { listScopesApi } from "@/lib/api";

const money = (n) => "$" + Math.round(n || 0).toLocaleString();

const scopePrice = (s) => {
  if (s.result?.mode === "final" && s.result?.finalTotal) return `${money(s.result.finalTotal)} firm`;
  if (s.result?.bandLo != null) return `${money(s.result.bandLo)}–${money(s.result.bandHi)} range`;
  return s.tier === "survey" ? "Survey scope — priced by owner" : "No price yet";
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
    </div>
  );
};
