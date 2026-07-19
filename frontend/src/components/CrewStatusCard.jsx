import React, { useEffect, useState } from "react";
import { teamStatusApi } from "@/lib/api";

const fmtTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

export const CrewStatusCard = () => {
  const [crew, setCrew] = useState(null);

  useEffect(() => {
    const load = () => teamStatusApi().then((d) => setCrew(d.crew)).catch(() => {});
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, []);

  if (crew === null) return null;
  const onClock = crew.filter((c) => c.clocked_in).length;

  return (
    <div data-testid="crew-status-card" className="bg-white border border-slate-200 rounded-lg p-5 mb-8">
      <div className="mb-3">
        <h2 className="font-display font-bold text-lg text-[#1B2A4A]">Who's on the clock</h2>
        <p data-testid="crew-status-summary" className="text-xs text-slate-500">
          {onClock ? `${onClock} of ${crew.length} crew working right now` : "Nobody's clocked in right now"}
        </p>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {crew.map((c) => (
          <div
            key={c.user_id}
            data-testid="crew-status-row"
            className={`flex items-center gap-3 rounded-lg border p-3 ${c.clocked_in ? "border-emerald-200 bg-emerald-50/60" : "border-slate-200 bg-slate-50/60"}`}
          >
            <span className="relative flex h-3 w-3 shrink-0">
              {c.clocked_in && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />}
              <span className={`relative inline-flex rounded-full h-3 w-3 ${c.clocked_in ? "bg-emerald-500" : "bg-slate-300"}`} />
            </span>
            <div className="min-w-0">
              <p className="font-semibold text-sm text-[#1B2A4A] truncate">{c.name}</p>
              <p data-testid="crew-status-label" className={`text-xs truncate ${c.clocked_in ? "text-emerald-700" : "text-slate-400"}`}>
                {c.clocked_in ? `On the clock since ${fmtTime(c.since)}${c.job_name ? ` · ${c.job_name}` : ""}` : "Not active right now"}
              </p>
            </div>
          </div>
        ))}
        {crew.length === 0 && <p className="text-sm text-slate-400">No crew accounts yet — add them on the Crew page.</p>}
      </div>
    </div>
  );
};
