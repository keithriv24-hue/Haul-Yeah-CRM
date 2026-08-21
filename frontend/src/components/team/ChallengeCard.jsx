import React from "react";
import { Trophy, CalendarDays, Gift, UserCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { TEAM_CHIP } from "@/components/team/BadgeMedallion";
import { fmtDate } from "@/lib/format";

const daysLeft = (end) => {
  const diff = Math.ceil((new Date(`${end}T23:59:59`) - new Date()) / 86400000);
  return diff;
};

export const ChallengeCard = ({ ch, me, children }) => {
  const left = daysLeft(ch.end);
  const rewardLabel = ch.reward?.kind === "title" ? `“${ch.reward.title}” title` : "a badge";
  return (
    <div data-testid="challenge-card" className="surface p-4">
      <div className="flex flex-wrap items-center gap-2 mb-1">
        <h3 className="font-display font-bold text-primary">{ch.name}</h3>
        <Badge variant="outline" className={`text-[10px] capitalize ${TEAM_CHIP[ch.team] || ""}`}>{ch.team}</Badge>
        <Badge variant="outline" className="text-[10px] capitalize bg-surface-sunk text-ink-2 border-border-strong">
          {ch.type === "individual" ? "everyone can win" : "one winner"}
        </Badge>
        {ch.metric === "owner_verified" && (
          <Badge variant="outline" className="text-[10px] bg-warning/10 text-warning border-warning/30 gap-1">
            <UserCheck className="w-3 h-3" /> owner-verified
          </Badge>
        )}
      </div>
      {ch.description && <p className="text-sm text-faint mb-2">{ch.description}</p>}
      <div className="flex flex-wrap items-center gap-3 text-xs text-faint mb-3">
        <span className="inline-flex items-center gap-1"><CalendarDays className="w-3.5 h-3.5" />{fmtDate(ch.start)} – {fmtDate(ch.end)}</span>
        {ch.status === "active" && (
          <span className={`font-semibold ${left <= 3 ? "text-destructive" : "text-ink-2"}`}>
            {left > 0 ? `${left} day${left === 1 ? "" : "s"} left` : "ends today"}
          </span>
        )}
        <span className="inline-flex items-center gap-1"><Gift className="w-3.5 h-3.5 text-accent-ink" />Reward: {rewardLabel}</span>
      </div>

      {ch.status === "needs_verify" && (
        <div data-testid="challenge-needs-verify-note" className="text-xs bg-warning/10 border border-warning/25 text-warning rounded-md px-3 py-2 mb-3">
          This one ended — waiting on the owner to confirm the winner(s).
        </div>
      )}
      {(ch.status === "awarded" || ch.status === "ended") && (
        <div data-testid="challenge-winners" className="flex flex-wrap items-center gap-2 text-sm mb-3">
          <Trophy className="w-4 h-4 text-warning" />
          {ch.winners?.length ? (
            ch.winners.map((w) => (
              <span key={w.user_id} className="font-semibold text-primary">{w.name || "Someone"}</span>
            ))
          ) : (
            <span className="text-faint">No one hit the goal this time.</span>
          )}
        </div>
      )}

      {ch.type === "individual" && ch.target ? (
        <div className="space-y-1.5">
          {(ch.progress || []).map((r) => {
            const pct = Math.min(100, Math.round((r.value / ch.target) * 100));
            const mine = me && r.user_id === me;
            return (
              <div key={r.user_id} data-testid="challenge-progress-row" className={`rounded-md px-2 py-1.5 ${mine ? "bg-accent/10 border border-accent/25" : ""}`}>
                <div className="flex items-center justify-between text-xs mb-0.5">
                  <span className={`font-semibold ${mine ? "text-accent-ink" : "text-primary"}`}>{r.name}{mine ? " (you)" : ""}</span>
                  <span className="text-faint font-mono">{r.value}/{ch.target}</span>
                </div>
                <div className="h-1.5 bg-surface-sunk rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${pct >= 100 ? "bg-success" : "bg-accent"}`} style={{ width: `${pct}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="space-y-1">
          {(ch.progress || []).map((r, i) => {
            const mine = me && r.user_id === me;
            return (
              <div key={r.user_id} data-testid="challenge-leader-row" className={`flex items-center gap-2 text-sm rounded-md px-2 py-1 ${mine ? "bg-accent/10 border border-accent/25" : ""}`}>
                <span className={`w-5 text-center font-bold ${i === 0 && r.value > 0 ? "text-warning" : "text-faint"}`}>{i + 1}</span>
                <span className={`flex-1 truncate ${mine ? "font-semibold text-accent-ink" : "text-primary"}`}>{r.name}{mine ? " (you)" : ""}</span>
                <span className="font-mono text-ink-2">{r.value}</span>
              </div>
            );
          })}
        </div>
      )}
      {children}
    </div>
  );
};
