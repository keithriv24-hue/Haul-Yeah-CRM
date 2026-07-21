import React, { useEffect, useState } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { EmptyState } from "@/components/Bits";
import { crewComparisonApi, auditLogApi } from "@/lib/api";

export const AdminInsightsTab = () => {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    crewComparisonApi().then(setRows).catch(() => setRows([]));
  }, []);

  const max = Math.max(1, ...(rows || []).map((r) => Math.max(r.driver, r.helper)));

  return (
    <div className="mt-4">
      <div className="bg-white border border-slate-200 rounded-lg" data-testid="crew-comparison-table">
        <div className="px-4 py-3 border-b border-slate-100">
          <h2 className="font-bold text-[#1B2A4A]">Driver vs. Helper — who's comfortable where</h2>
          <p className="text-xs text-slate-400 mt-0.5">Counts come from job credits since launch. Only you see this.</p>
        </div>
        {rows === null ? (
          <p className="text-sm text-slate-400 px-4 py-6 text-center">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-slate-400 px-4 py-6 text-center">No crew members yet.</p>
        ) : (
          <div className="divide-y divide-slate-100">
            {rows.map((r) => (
              <div key={r.user_id} data-testid="comparison-row" className="px-4 py-3">
                <div className="flex items-center justify-between text-sm mb-1.5">
                  <span className="font-semibold text-[#1B2A4A]">{r.name}</span>
                  <span className="text-xs text-slate-400">{r.total} jobs total</span>
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="w-14 text-slate-500">Driver</span>
                    <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full bg-[#1B2A4A] rounded-full" style={{ width: `${(r.driver / max) * 100}%` }} />
                    </div>
                    <span className="w-6 text-right font-mono font-bold text-[#1B2A4A]">{r.driver}</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="w-14 text-slate-500">Helper</span>
                    <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full bg-[#E8743B] rounded-full" style={{ width: `${(r.helper / max) * 100}%` }} />
                    </div>
                    <span className="w-6 text-right font-mono font-bold text-[#E8743B]">{r.helper}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const TEAM_ACTIONS = ["credit", "badge", "challenge", "tally", "profile", "roles"];

export const AdminLogTab = () => {
  const [entries, setEntries] = useState(null);
  const [teamOnly, setTeamOnly] = useState(true);

  useEffect(() => {
    auditLogApi(300).then(setEntries).catch(() => setEntries([]));
  }, []);

  const shown = (entries || []).filter(
    (e) => !teamOnly || TEAM_ACTIONS.some((k) => (e.action || "").toLowerCase().includes(k))
  );

  return (
    <div className="mt-4 space-y-3">
      <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
        <Checkbox data-testid="log-team-only-check" checked={teamOnly} onCheckedChange={() => setTeamOnly((v) => !v)} />
        Only show credits, badges, challenges, and role changes
      </label>
      {entries === null ? (
        <p className="text-sm text-slate-400 py-6 text-center">Loading…</p>
      ) : shown.length === 0 ? (
        <EmptyState>Nothing logged yet.</EmptyState>
      ) : (
        <div className="bg-white border border-slate-200 rounded-lg divide-y divide-slate-100" data-testid="audit-log-list">
          {shown.map((e, i) => (
            <div key={i} data-testid="audit-log-row" className="px-4 py-2.5 text-sm flex flex-wrap items-baseline gap-x-2">
              <span className="font-semibold text-[#1B2A4A]">{e.actor}</span>
              <span className="text-slate-600">{e.action}</span>
              {e.target && <span className="text-slate-500">— {e.target}</span>}
              <span className="ml-auto text-xs text-slate-400">{new Date(e.at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
