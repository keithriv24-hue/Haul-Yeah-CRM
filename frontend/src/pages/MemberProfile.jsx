import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Pencil, Pin, Trophy, Sparkles, Lock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, LoadingRows } from "@/components/Bits";
import { MemberAvatar } from "@/components/team/MemberAvatar";
import { BadgeMedallion, RARITY_CHIP, TEAM_CHIP } from "@/components/team/BadgeMedallion";
import { EditProfileDialog } from "@/components/team/EditProfileDialog";
import { PinPicker } from "@/components/team/PinPicker";
import { RewardsWallet } from "@/components/team/RewardsWallet";
import { memberDetailApi, listChallengesApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";

const StatBox = ({ label, value, testId }) => (
  <div data-testid={testId} className="surface p-3 text-center">
    <div className="font-display text-2xl font-extrabold text-primary tnum">{value}</div>
    <div className="text-[11px] font-semibold uppercase tracking-wide text-faint">{label}</div>
  </div>
);

const TRACK_LABEL = { crew: "Crew track", sales: "Sales track" };

export default function MemberProfile() {
  const { id } = useParams();
  const [detail, setDetail] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [pinOpen, setPinOpen] = useState(false);
  const [myChallenges, setMyChallenges] = useState([]);
  const [photoVer, setPhotoVer] = useState(0);

  const load = useCallback(() => {
    memberDetailApi(id)
      .then((d) => {
        setDetail(d);
        setPhotoVer((v) => v + 1);
        if (d.is_self) {
          listChallengesApi()
            .then((c) => setMyChallenges((c.challenges || []).filter((ch) => ch.status === "active" && d.teams.includes(ch.team))))
            .catch(() => {});
        }
      })
      .catch(() => setNotFound(true));
  }, [id]);
  useEffect(() => {
    load();
  }, [load]);

  if (notFound) return <EmptyState>Couldn't find that team member.</EmptyState>;
  if (!detail) return <LoadingRows />;

  const progressMap = Object.fromEntries((detail.progress || []).map((p) => [p.badge_id, p]));
  const nearest = (detail.progress || []).slice(0, 3);
  const isRookie = detail.unlocked_count === 0 && detail.teams.length > 0;

  return (
    <div data-testid="member-profile-page" className="space-y-4">
      <Link to="/team" data-testid="back-to-team-link" className="inline-flex items-center gap-1.5 text-sm font-semibold text-accent-ink hover:underline">
        <ArrowLeft className="w-4 h-4" /> Team
      </Link>

      <div className="surface p-5">
        <div className="flex flex-wrap items-start gap-4">
          <MemberAvatar id={detail.id} name={detail.profile.display_name || detail.name} hasPhoto={detail.has_photo} size="lg" version={photoVer} />
          <div className="flex-1 min-w-[200px]">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-display text-2xl font-extrabold text-primary tnum" data-testid="profile-name">
                {detail.profile.display_name || detail.name}
              </h1>
              {detail.profile.nickname && <span className="text-faint">“{detail.profile.nickname}”</span>}
            </div>
            <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
              {detail.teams.map((t) => (
                <Badge key={t} variant="outline" className={`text-[10px] capitalize ${TEAM_CHIP[t]}`}>{t}</Badge>
              ))}
              {(detail.titles || []).map((t) => (
                <Badge key={t} data-testid="profile-title-chip" variant="outline" className="text-[10px] gap-1 bg-warning/10 text-warning border-warning/30">
                  <Trophy className="w-3 h-3" /> {t}
                </Badge>
              ))}
            </div>
            <p className="text-xs text-faint mt-1.5">
              {detail.profile.role_title && <span className="font-semibold text-faint">{detail.profile.role_title} · </span>}
              On the team since {fmtDate(detail.member_since?.slice(0, 10))}
            </p>
            {detail.profile.bio && <p className="text-sm text-ink-2 mt-2" data-testid="profile-bio-text">{detail.profile.bio}</p>}
            <div className="flex flex-wrap gap-x-6 gap-y-1 mt-2 text-xs text-faint">
              {detail.profile.favorite_move && <span><strong className="text-ink-2">Favorite move:</strong> {detail.profile.favorite_move}</span>}
              {detail.profile.fun_fact && <span><strong className="text-ink-2">Fun fact:</strong> {detail.profile.fun_fact}</span>}
            </div>
          </div>
          {detail.can_edit && (
            <Button data-testid="profile-edit-btn" variant="outline" size="sm" className="gap-1.5" onClick={() => setEditOpen(true)}>
              <Pencil className="w-3.5 h-3.5" /> Edit profile
            </Button>
          )}
        </div>
      </div>

      {detail.teams.length > 0 && (
        <div className="surface p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="label-eyebrow">Pinned badges</h2>
            {detail.is_self && (
              <Button data-testid="pin-badges-btn" variant="outline" size="sm" className="gap-1.5" onClick={() => setPinOpen(true)}>
                <Pin className="w-3.5 h-3.5" /> Pin badges
              </Button>
            )}
          </div>
          {(detail.pinned || []).length === 0 ? (
            <p className="text-sm text-faint" data-testid="no-pins-note">
              {detail.is_self
                ? detail.unlocked_count > 0
                  ? "Pick up to 3 badges to show off here."
                  : "Unlock a badge and it can live here."
                : "Nothing pinned yet."}
            </p>
          ) : (
            <div className="flex flex-wrap gap-5">
              {detail.pinned.map((b) => (
                <div key={b.id} data-testid="pinned-badge" className="flex flex-col items-center gap-1.5 w-24 text-center">
                  <BadgeMedallion badge={b} size="md" />
                  <span className="text-xs font-semibold text-primary leading-tight">{b.name}</span>
                  <span className={`border rounded-full px-1.5 text-[10px] font-bold capitalize ${RARITY_CHIP[b.rarity]}`}>{b.rarity}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {isRookie && (
        <div data-testid="rookie-card" className="border-2 border-dashed border-accent/50 bg-accent/10 rounded-lg p-5">
          <h2 className="font-display font-bold text-primary flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-accent-ink" /> Rookie
          </h2>
          <p className="text-sm text-ink-2 mt-1">
            {detail.is_self ? "Your first badge is one job away. Here's what's closest:" : "Every legend starts at zero — the first badge is one job away."}
          </p>
          {detail.can_see_numbers && nearest.length > 0 && (
            <div className="flex flex-wrap gap-4 mt-3">
              {nearest.map((p) => (
                <div key={p.badge_id} className="flex items-center gap-2 bg-surface border border-accent/25 rounded-md px-3 py-2 text-sm">
                  <span className="font-semibold text-primary">{p.name}</span>
                  <span className="text-xs text-faint font-mono">{p.count}/{p.threshold}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {detail.stats && (
        <div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3" data-testid="profile-stats-block">
            {detail.teams.includes("crew") && (
              <>
                <StatBox testId="stat-jobs-total" label="Jobs completed" value={detail.stats.jobs_total} />
                <StatBox testId="stat-jobs-month" label="Jobs this month" value={detail.stats.jobs_month} />
                <StatBox testId="stat-driver" label="As Driver" value={detail.stats.driver} />
                <StatBox testId="stat-helper" label="As Helper" value={detail.stats.helper} />
              </>
            )}
            {detail.teams.includes("sales") && (
              <>
                <StatBox testId="stat-closes-total" label="Moves closed" value={detail.stats.closes_total} />
                <StatBox testId="stat-closes-month" label="Closes this month" value={detail.stats.closes_month} />
              </>
            )}
          </div>
          {detail.teams.length > 0 && (
            <p className="text-[11px] text-faint mt-1.5">Only {detail.is_self ? "you" : "they"} and the owner can see these numbers.</p>
          )}
        </div>
      )}

      {detail.can_see_numbers && detail.teams.length > 0 && (
        <RewardsWallet userId={detail.id} isSelf={detail.is_self} />
      )}

      {detail.is_self && myChallenges.length > 0 && (
        <div className="surface p-5" data-testid="profile-active-challenges">
          <div className="flex items-center justify-between mb-3">
            <h2 className="label-eyebrow">Your live challenges</h2>
            <Link to="/challenges" className="text-xs font-semibold text-accent-ink hover:underline">See all</Link>
          </div>
          <div className="space-y-2">
            {myChallenges.map((ch) => {
              const mine = (ch.progress || []).find((r) => r.user_id === detail.id);
              const pct = ch.target ? Math.min(100, Math.round(((mine?.value || 0) / ch.target) * 100)) : null;
              return (
                <div key={ch.id} className="rounded-md border border-border px-3 py-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-semibold text-primary">{ch.name}</span>
                    <span className="text-xs text-faint font-mono">
                      {ch.target ? `${mine?.value || 0}/${ch.target}` : `${mine?.value || 0} so far`}
                    </span>
                  </div>
                  {pct !== null && (
                    <div className="h-1.5 bg-surface-sunk rounded-full overflow-hidden mt-1">
                      <div className={`h-full rounded-full ${pct >= 100 ? "bg-success" : "bg-accent"}`} style={{ width: `${pct}%` }} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {detail.teams.length === 0 ? (
        <EmptyState>No badge tracks here — badges live on the Crew and Sales teams.</EmptyState>
      ) : (
        <div className="surface p-5" data-testid="badge-gallery">
          <h2 className="font-display font-bold text-lg text-primary mb-1">All badges</h2>
          <p className="text-xs text-faint mb-4">Colored ones are unlocked. Grey ones are still out there.</p>
          {detail.teams.map((t) => (
            <div key={t} className="mb-5 last:mb-0">
              <h3 className="text-xs font-bold uppercase tracking-wide text-faint mb-3">{TRACK_LABEL[t]}</h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                {(detail.gallery[t] || []).map((b) => {
                  const prog = !b.unlocked ? progressMap[b.id] : null;
                  return (
                    <div key={b.id} data-testid={`gallery-badge-${b.id}`} className={`flex items-center gap-2.5 rounded-lg border p-2.5 ${b.unlocked ? "border-border" : "border-border bg-surface-sunk/60"}`}>
                      <BadgeMedallion badge={b} unlocked={b.unlocked} size="sm" />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1">
                          <span className={`text-xs font-semibold truncate ${b.unlocked ? "text-primary" : "text-faint"}`}>{b.name}</span>
                          {!b.unlocked && <Lock className="w-3 h-3 text-faint/70 shrink-0" />}
                        </div>
                        <span className={`inline-block border rounded-full px-1.5 text-[9px] font-bold capitalize ${RARITY_CHIP[b.rarity]}`}>{b.rarity}</span>
                        {prog && (
                          <div className="mt-1">
                            <div className="h-1 bg-muted rounded-full overflow-hidden">
                              <div className="h-full bg-accent rounded-full" style={{ width: `${Math.min(100, Math.round((prog.count / prog.threshold) * 100))}%` }} />
                            </div>
                            <span className="text-[9px] text-faint font-mono">{prog.count}/{prog.threshold}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {(detail.challenge_wins || []).length > 0 && (
        <div className="surface p-5" data-testid="challenge-wins-section">
          <h2 className="label-eyebrow mb-3">Challenge wins</h2>
          <ul className="space-y-2">
            {detail.challenge_wins.map((w) => (
              <li key={w.id} className="flex items-center gap-2 text-sm">
                <Trophy className="w-4 h-4 text-warning shrink-0" />
                <span className="font-semibold text-primary">{w.name}</span>
                <Badge variant="outline" className={`text-[10px] capitalize ${TEAM_CHIP[w.team]}`}>{w.team}</Badge>
                <span className="text-xs text-faint ml-auto">{fmtDate(w.end)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <EditProfileDialog open={editOpen} onOpenChange={setEditOpen} member={detail} onSaved={load} />
      <PinPicker open={pinOpen} onOpenChange={setPinOpen} member={detail} onSaved={load} />
    </div>
  );
}
