import React, { useEffect, useState } from "react";
import { Trophy, Medal } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { PageTitle, InstructionBanner, EmptyState, LoadingRows } from "@/components/Bits";
import { TEAM_CHIP } from "@/components/team/BadgeMedallion";
import { leaderboardApi, hallOfFameApi } from "@/lib/api";

const RANK_COLOR = ["text-warning", "text-faint", "text-warning"];

const monthLabel = (m) => {
  if (!m) return "";
  const [y, mm] = m.split("-");
  return new Date(Number(y), Number(mm) - 1, 1).toLocaleDateString("en-US", { month: "long", year: "numeric" });
};

const Board = ({ rows, unit, testId }) => (
  <div data-testid={testId} className="surface divide-y divide-border mt-3">
    {rows.length === 0 ? (
      <p className="text-sm text-faint text-center py-8">No {unit} logged yet this month. First one on the board wins bragging rights.</p>
    ) : (
      rows.map((r, i) => (
        <div key={r.user_id} data-testid="leaderboard-row" className="flex items-center gap-3 px-4 py-3">
          {i < 3 && r.count > 0 ? (
            <Trophy className={`w-5 h-5 shrink-0 ${RANK_COLOR[i]}`} />
          ) : (
            <span className="w-5 text-center font-bold text-faint">{i + 1}</span>
          )}
          <span className="flex-1 font-semibold text-primary truncate">{r.name}</span>
          <span className="font-display font-extrabold text-lg text-primary">{r.count}</span>
          <span className="text-xs text-faint w-12">{unit}</span>
        </div>
      ))
    )}
  </div>
);

export default function Leaderboard() {
  const [board, setBoard] = useState(null);
  const [fame, setFame] = useState([]);

  useEffect(() => {
    leaderboardApi().then(setBoard).catch(() => setBoard({ crew: [], sales: [] }));
    hallOfFameApi().then(setFame).catch(() => {});
  }, []);

  return (
    <div data-testid="leaderboard-page">
      <PageTitle title="Leaderboard" subtitle={board ? `${monthLabel(board.month)} — resets on the 1st.` : ""} />
      <InstructionBanner testId="leaderboard-banner">
        Counts only — never pay or prices. Each month's winner gets a permanent spot in the Hall of Fame below.
      </InstructionBanner>
      {board === null ? (
        <LoadingRows />
      ) : (
        <Tabs defaultValue="crew">
          <TabsList>
            <TabsTrigger data-testid="leaderboard-tab-crew" value="crew">Crew</TabsTrigger>
            <TabsTrigger data-testid="leaderboard-tab-sales" value="sales">Sales</TabsTrigger>
          </TabsList>
          <TabsContent value="crew">
            <Board rows={board.crew || []} unit="jobs" testId="leaderboard-crew" />
          </TabsContent>
          <TabsContent value="sales">
            <Board rows={board.sales || []} unit="closes" testId="leaderboard-sales" />
          </TabsContent>
        </Tabs>
      )}

      <div className="mt-8">
        <h2 className="font-display font-bold text-xl text-primary flex items-center gap-2 mb-3">
          <Medal className="w-5 h-5 text-accent-ink" /> Hall of Fame
        </h2>
        {fame.length === 0 ? (
          <EmptyState>No months in the books yet. Finish a month on top and your name lives here forever.</EmptyState>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="hall-of-fame-grid">
            {fame.map((e) => (
              <div key={`${e.month}:${e.team}`} data-testid="hall-of-fame-entry" className="surface p-4 flex items-center gap-3">
                <Trophy className="w-6 h-6 text-warning shrink-0" />
                <div className="min-w-0">
                  <p className="font-semibold text-primary truncate">{e.winner_name}</p>
                  <p className="text-xs text-faint">
                    {monthLabel(e.month)} · {e.count} {e.team === "crew" ? "jobs" : "closes"}
                  </p>
                </div>
                <Badge variant="outline" className={`ml-auto text-[10px] capitalize ${TEAM_CHIP[e.team]}`}>{e.team}</Badge>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
