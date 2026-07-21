import React, { useEffect, useState } from "react";
import { PageTitle, InstructionBanner, EmptyState, LoadingRows } from "@/components/Bits";
import { ChallengeCard } from "@/components/team/ChallengeCard";
import { listChallengesApi } from "@/lib/api";

export default function Challenges() {
  const [data, setData] = useState(null);

  useEffect(() => {
    listChallengesApi().then(setData).catch(() => setData({ challenges: [], me: null }));
  }, []);

  const all = data?.challenges || [];
  const active = all.filter((c) => c.status === "active");
  const waiting = all.filter((c) => c.status === "needs_verify");
  const done = all.filter((c) => c.status === "awarded" || c.status === "ended");

  return (
    <div data-testid="challenges-page">
      <PageTitle title="Challenges" subtitle="Team goals with real rewards — badges and titles." />
      <InstructionBanner testId="challenges-banner">
        Progress fills in automatically from job credits. Anything marked "owner-verified" gets confirmed by the owner before the reward goes out.
      </InstructionBanner>
      {data === null ? (
        <LoadingRows />
      ) : all.length === 0 ? (
        <EmptyState>No challenges for your team yet. Check back soon.</EmptyState>
      ) : (
        <div className="space-y-8">
          <section>
            <h2 className="font-display font-bold text-lg text-[#1B2A4A] mb-3">Live now</h2>
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
              <h2 className="font-display font-bold text-lg text-[#1B2A4A] mb-3">Waiting on the owner</h2>
              <div className="grid lg:grid-cols-2 gap-4" data-testid="waiting-challenges">
                {waiting.map((ch) => (
                  <ChallengeCard key={ch.id} ch={ch} me={data.me} />
                ))}
              </div>
            </section>
          )}
          {done.length > 0 && (
            <section>
              <h2 className="font-display font-bold text-lg text-[#1B2A4A] mb-3">Finished</h2>
              <div className="grid lg:grid-cols-2 gap-4" data-testid="finished-challenges">
                {done.map((ch) => (
                  <ChallengeCard key={ch.id} ch={ch} me={data.me} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
