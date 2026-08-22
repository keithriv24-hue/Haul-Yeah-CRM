import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Trophy, Coins } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { PageTitle, InstructionBanner, EmptyState, LoadingRows } from "@/components/Bits";
import { ChallengeCard, rewardLabel } from "@/components/team/ChallengeCard";
import { listChallengesApi, rewardsWalletApi } from "@/lib/api";

const seenKey = (id) => `hy_celebrated_${id}`;

const CelebrationDialog = ({ ch, onClose }) => {
  const monetary = (ch?.reward?.amount || 0) > 0 || (ch?.reward?.points || 0) > 0;
  return (
    <Dialog open={!!ch} onOpenChange={() => onClose()}>
      <DialogContent data-testid="challenge-celebration-dialog" className="text-center max-w-sm">
        <DialogHeader>
          <div className="mx-auto w-14 h-14 rounded-full bg-warning/15 border border-warning/30 flex items-center justify-center mb-1">
            <Trophy className="w-7 h-7 text-warning" />
          </div>
          <DialogTitle className="font-display text-xl text-center">Challenge complete!</DialogTitle>
          <DialogDescription className="text-center">
            You won <strong className="text-primary">“{ch?.name}”</strong>
          </DialogDescription>
        </DialogHeader>
        <p data-testid="celebration-reward" className="text-sm font-semibold text-accent-ink">{rewardLabel(ch?.reward)}</p>
        {monetary && <p className="text-xs text-faint">Reward pending owner approval — watch your wallet.</p>}
        <DialogFooter className="sm:justify-center">
          <Button data-testid="celebration-close-btn" onClick={onClose} className="bg-accent hover:bg-accent-press">Let's go</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default function Challenges() {
  const [data, setData] = useState(null);
  const [wallet, setWallet] = useState(null);
  const [celebrate, setCelebrate] = useState(null);

  useEffect(() => {
    listChallengesApi().then((d) => {
      setData(d);
      if (d.me) {
        const won = (d.challenges || []).find(
          (c) => c.status === "awarded" && (c.winners || []).some((w) => w.user_id === d.me) && !localStorage.getItem(seenKey(c.id)));
        if (won) setCelebrate(won);
      }
    }).catch(() => setData({ challenges: [], me: null }));
    rewardsWalletApi().then(setWallet).catch(() => {});
  }, []);

  const closeCelebrate = () => {
    if (celebrate) localStorage.setItem(seenKey(celebrate.id), "1");
    setCelebrate(null);
  };

  const all = data?.challenges || [];
  const active = all.filter((c) => c.status === "active");
  const waiting = all.filter((c) => c.status === "needs_verify");
  const done = all.filter((c) => c.status === "awarded" || c.status === "ended");

  return (
    <div data-testid="challenges-page">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageTitle title="Challenges" subtitle="Team goals with real rewards — badges, titles, Haul Points, and bonuses." />
        {wallet && (
          <Link to={`/team/${wallet.user_id}`} data-testid="challenges-points-chip"
            className="inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent/10 px-3 py-1.5 text-sm font-bold text-accent-ink hover:bg-accent/20 mb-4">
            <Coins className="w-4 h-4" /> {wallet.balance} Haul Points
          </Link>
        )}
      </div>
      <InstructionBanner testId="challenges-banner">
        Progress fills in automatically from job credits. Anything marked "owner-verified" gets confirmed by the owner before the reward goes out. Money and point rewards land in your wallet after approval.
      </InstructionBanner>
      {data === null ? (
        <LoadingRows />
      ) : all.length === 0 ? (
        <EmptyState>No challenges for your team yet. Check back soon.</EmptyState>
      ) : (
        <div className="space-y-8">
          <section>
            <h2 className="label-eyebrow mb-3">Live now</h2>
            {active.length === 0 ? (
              <EmptyState>Nothing running right now.</EmptyState>
            ) : (
              <div className="grid lg:grid-cols-2 gap-4" data-testid="active-challenges">
                {active.map((ch) => (
                  <ChallengeCard key={ch.id} ch={ch} me={data.me} />
                ))}
              </div>
            )}
          </section>
          {waiting.length > 0 && (
            <section>
              <h2 className="label-eyebrow mb-3">Waiting on the owner</h2>
              <div className="grid lg:grid-cols-2 gap-4" data-testid="waiting-challenges">
                {waiting.map((ch) => (
                  <ChallengeCard key={ch.id} ch={ch} me={data.me} />
                ))}
              </div>
            </section>
          )}
          {done.length > 0 && (
            <section>
              <h2 className="label-eyebrow mb-3">Finished</h2>
              <div className="grid lg:grid-cols-2 gap-4" data-testid="finished-challenges">
                {done.map((ch) => (
                  <ChallengeCard key={ch.id} ch={ch} me={data.me} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
      <CelebrationDialog ch={celebrate} onClose={closeCelebrate} />
    </div>
  );
}
