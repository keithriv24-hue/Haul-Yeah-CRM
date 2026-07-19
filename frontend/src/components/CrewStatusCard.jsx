import React, { useEffect, useState } from "react";
import { teamStatusApi } from "@/lib/api";

const fmtTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

const to12h = (t) => {
  if (!t) return "";
  const [h, m] = t.split(":").map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
};

const rowStyle = (c) => {
  if (c.clocked_in) return "border-emerald-200 bg-emerald-50/60";
  if (c.late) return "border-red-300 bg-red-50/70";
  return "border-slate-200 bg-slate-50/60";
};

const statusLabel = (c) => {
  if (c.clocked_in) return `On the clock since ${fmtTime(c.since)}${c.job_name ? ` · ${c.job_name}` : ""}`;
  if (c.late) return `LATE — was due at ${to12h(c.due_at)} for ${c.late_job}`;
  return "Not active right now";
};

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
  const lateCount = crew.filter((c) => c.late).length;

  return (
    <div data-testid="crew-status-card" className="bg-white border border-slate-200 rounded-lg p-5 mb-8">
      <div className="mb-3">
        <h2 className="font-display font-bold text-lg text-[#1B2A4A]">Who's on the clock</h2>
        <p data-testid="crew-status-summary" className="text-xs text-slate-500">
          {onClock ? `${onClock} of ${crew.length} crew working right now` : "Nobody's clocked in right now"}
          {lateCount > 0 && <span className="text-red-600 font-bold"> · {lateCount} running late</span>}
        </p>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {crew.map((c) => (
          <div
            key={c.user_id}
            data-testid="crew-status-row"
            className={`flex items-center gap-3 rounded-lg border p-3 ${rowStyle(c)}`}
          >
            <span className="relative flex h-3 w-3 shrink-0">
              {(c.clocked_in || c.late) && (
                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${c.clocked_in ? "bg-emerald-400" : "bg-red-400"}`} />
              )}
              <span className={`relative inline-flex rounded-full h-3 w-3 ${c.clocked_in ? "bg-emerald-500" : c.late ? "bg-red-500" : "bg-slate-300"}`} />
            </span>
            <div className="min-w-0">
              <p className="font-semibold text-sm text-[#1B2A4A] truncate">{c.name}</p>
              <p data-testid="crew-status-label" className={`text-xs truncate ${c.clocked_in ? "text-emerald-700" : c.late ? "text-red-600 font-semibold" : "text-slate-400"}`}>
                {statusLabel(c)}
              </p>
            </div>
          </div>
        ))}
        {crew.length === 0 && <p className="text-sm text-slate-400">No crew accounts yet — add them on the Crew page.</p>}
      </div>
    </div>
  );
};
