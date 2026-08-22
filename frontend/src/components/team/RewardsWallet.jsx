import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Coins, Gift, Clock, CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { redeemPointsApi, rewardsCatalogApi, rewardsWalletApi, apiErrorMessage } from "@/lib/api";
import { fmtDate } from "@/lib/format";

const STATUS_CHIP = {
  pending: "bg-warning/10 text-warning border-warning/30",
  approved: "bg-info/10 text-info border-info/30",
  fulfilled: "bg-success/10 text-success border-success/30",
  denied: "bg-surface-sunk text-faint border-border-strong",
  voided: "bg-surface-sunk text-faint border-border-strong",
};

const Stat = ({ label, value, testId }) => (
  <div data-testid={testId} className="rounded-lg border border-border bg-surface-sunk/50 p-3 text-center">
    <div className="font-display text-xl font-extrabold text-primary tnum">{value}</div>
    <div className="text-[10px] font-semibold uppercase tracking-wide text-faint">{label}</div>
  </div>
);

export const RewardsWallet = ({ userId, isSelf }) => {
  const [wallet, setWallet] = useState(null);
  const [catalog, setCatalog] = useState(null);
  const [busy, setBusy] = useState("");
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(() => {
    rewardsWalletApi(isSelf ? undefined : userId).then(setWallet).catch(() => setWallet(null));
    if (isSelf) rewardsCatalogApi().then(setCatalog).catch(() => {});
  }, [userId, isSelf]);
  useEffect(() => { load(); }, [load]);

  if (!wallet) return null;

  const redeem = async (item) => {
    setBusy(item.id);
    try {
      await redeemPointsApi(item.id);
      toast.success(`Request sent — the owner will review your ${item.name}.`);
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy("");
  };

  const available = wallet.balance - (wallet.held_points || 0);
  const history = showAll ? wallet.rewards : wallet.rewards.slice(0, 6);

  return (
    <div className="surface p-5" data-testid="rewards-wallet">
      <div className="flex items-center justify-between mb-3">
        <h2 className="label-eyebrow flex items-center gap-1.5"><Coins className="w-3.5 h-3.5 text-accent-ink" /> Rewards wallet</h2>
        <span className="text-[11px] text-faint">Only {isSelf ? "you" : "they"} and the owner can see this.</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <Stat testId="wallet-balance" label="Haul Points" value={wallet.balance} />
        <Stat testId="wallet-lifetime" label="Lifetime points" value={wallet.lifetime} />
        <Stat testId="wallet-cash" label="Cash rewards" value={`$${wallet.cash_earned}`} />
        <Stat testId="wallet-pending" label="Pending rewards" value={wallet.pending_count} />
      </div>

      {isSelf && catalog && (
        <div className="mb-4">
          <h3 className="text-xs font-bold uppercase tracking-wide text-faint mb-2">Redeem your points</h3>
          {wallet.held_points > 0 && (
            <p className="text-[11px] text-warning mb-2">{wallet.held_points} points are held by pending requests.</p>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {catalog.items.filter((i) => i.active).map((item) => {
              const can = available >= item.points_cost;
              return (
                <div key={item.id} data-testid={`catalog-item-${item.id}`}
                  className={`rounded-lg border p-3 flex flex-col gap-1.5 ${can ? "border-accent/30 bg-accent/5" : "border-border bg-surface-sunk/40 opacity-70"}`}>
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-sm font-semibold text-primary leading-tight">{item.name}</span>
                    <Gift className={`w-4 h-4 shrink-0 ${can ? "text-accent-ink" : "text-faint"}`} />
                  </div>
                  <div className="flex items-center justify-between mt-auto">
                    <span className="text-xs font-bold text-accent-ink tnum">{item.points_cost} pts</span>
                    <Button data-testid={`redeem-btn-${item.id}`} size="sm" variant={can ? "default" : "outline"}
                      className={`h-7 text-xs ${can ? "bg-accent hover:bg-accent-press" : ""}`}
                      disabled={!can || busy === item.id} onClick={() => redeem(item)}>
                      {busy === item.id ? "Sending…" : "Redeem"}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
          <p className="text-[11px] text-faint mt-2">Redemptions go to the owner for approval — points are held until they're reviewed.</p>
        </div>
      )}

      <h3 className="text-xs font-bold uppercase tracking-wide text-faint mb-2">Reward history</h3>
      {wallet.rewards.length === 0 ? (
        <p className="text-sm text-faint" data-testid="wallet-empty-note">Nothing yet — win a challenge and it lands here.</p>
      ) : (
        <div className="space-y-1.5" data-testid="wallet-history">
          {history.map((r) => (
            <div key={r.id} data-testid="wallet-reward-row" className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2 text-sm">
              {r.status === "fulfilled" ? <CheckCircle2 className="w-4 h-4 text-success shrink-0" /> : <Clock className="w-4 h-4 text-faint shrink-0" />}
              <div className="flex-1 min-w-[140px]">
                <span className="font-semibold text-primary">{r.reward_name}</span>
                <span className="block text-[11px] text-faint">{r.reason || r.challenge_name || r.source}</span>
              </div>
              <span className="text-xs font-bold text-ink-2 tnum">
                {r.reward_type === "redemption" ? `−${r.points} pts` : [r.amount > 0 && `$${r.amount}`, r.points > 0 && `${r.points} pts`].filter(Boolean).join(" + ")}
              </span>
              <Badge variant="outline" className={`text-[10px] capitalize ${STATUS_CHIP[r.status] || ""}`}>{r.status}</Badge>
              <span className="text-[11px] text-faint">{fmtDate((r.earned_at || "").slice(0, 10))}</span>
            </div>
          ))}
          {wallet.rewards.length > 6 && (
            <button data-testid="wallet-show-all-btn" onClick={() => setShowAll(!showAll)}
              className="text-xs font-semibold text-accent-ink hover:underline">
              {showAll ? "Show less" : `Show all ${wallet.rewards.length}`}
            </button>
          )}
        </div>
      )}
    </div>
  );
};
