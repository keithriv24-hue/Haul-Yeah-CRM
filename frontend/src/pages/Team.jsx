import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Trophy, UserRound } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageTitle, InstructionBanner, SearchBar, searchMatch, EmptyState, LoadingRows } from "@/components/Bits";
import { MemberAvatar } from "@/components/team/MemberAvatar";
import { BadgeMedallion, TEAM_CHIP } from "@/components/team/BadgeMedallion";
import { teamMembersApi } from "@/lib/api";

export default function Team() {
  const [data, setData] = useState(null);
  const [query, setQuery] = useState("");

  const load = useCallback(() => teamMembersApi().then(setData).catch(() => setData({ members: [], me: null })), []);
  useEffect(() => {
    load();
  }, [load]);

  const members = (data?.members || []).filter((m) =>
    searchMatch(query, m.name, m.display_name, m.nickname, m.role_title, ...(m.teams || []), ...(m.roles || []))
  );

  return (
    <div data-testid="team-page">
      <PageTitle
        title="Team"
        subtitle="Everyone at Haul Yeah — tap a card to see their profile and badges."
        action={
          data?.me && (
            <Button asChild variant="outline" className="gap-1.5" data-testid="my-profile-btn">
              <Link to={`/team/${data.me}`}>
                <UserRound className="w-4 h-4" /> My profile
              </Link>
            </Button>
          )
        }
      />
      <InstructionBanner testId="team-banner">
        Set up your own profile from "My profile" — add a photo, a nickname, and pin your best badges.
      </InstructionBanner>
      <SearchBar value={query} onChange={setQuery} placeholder="Search name, nickname, or team…" testId="team-page-search-input" className="mb-4" />
      {data === null ? (
        <LoadingRows />
      ) : members.length === 0 ? (
        <EmptyState>{query ? "No one matches that search." : "No team members yet."}</EmptyState>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {members.map((m) => (
            <Link
              key={m.id}
              to={`/team/${m.id}`}
              data-testid="team-member-card"
              className="bg-white border border-slate-200 rounded-lg p-4 hover:border-[#E8743B]/50 hover:shadow-sm transition-all block"
            >
              <div className="flex items-start gap-3">
                <MemberAvatar id={m.id} name={m.display_name || m.name} hasPhoto={m.has_photo} />
                <div className="min-w-0 flex-1">
                  <p className="font-display font-bold text-[#1B2A4A] truncate">
                    {m.display_name || m.name}
                    {data.me === m.id && <span className="ml-1.5 text-[10px] font-bold text-[#E8743B]">(you)</span>}
                  </p>
                  {m.nickname && <p className="text-xs text-slate-500 truncate">“{m.nickname}”</p>}
                  {m.role_title && <p className="text-xs text-slate-400 truncate">{m.role_title}</p>}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-1.5 mt-2.5">
                {(m.teams || []).map((t) => (
                  <Badge key={t} variant="outline" className={`text-[10px] capitalize ${TEAM_CHIP[t]}`}>{t}</Badge>
                ))}
                {(m.roles || []).filter((r) => !["crew", "sales", "employee"].includes(r)).map((r) => (
                  <Badge key={r} variant="outline" className="text-[10px] capitalize bg-slate-50 text-slate-600 border-slate-300">{r}</Badge>
                ))}
                {(m.titles || []).map((t) => (
                  <Badge key={t} variant="outline" className="text-[10px] gap-1 bg-yellow-50 text-yellow-800 border-yellow-300">
                    <Trophy className="w-3 h-3" /> {t}
                  </Badge>
                ))}
              </div>
              {(m.pinned || []).length > 0 && (
                <div className="flex gap-1.5 mt-3">
                  {m.pinned.map((b) => (
                    <BadgeMedallion key={b.id} badge={b} size="sm" />
                  ))}
                </div>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
