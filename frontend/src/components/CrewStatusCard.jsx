import React, { useEffect, useState } from "react";
import { SectionTitle } from "@/components/Bits";
import { teamStatusApi } from "@/lib/api";

const fmtTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

const to12h = (t) => {
  if (!t) return "";
  const [h, m] = t.split(":").map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
};

const rowStyle = (c) => {
  if (c.clocked_in) return "border-success/25 bg-success/10";
  if (c.late) return "border-destructive/30 bg-destructive/10";
  return "border-border bg-surface-sunk/60";
};

const statusLabel = (c) => {
  if (c.clocked_in) return `On the clock since ${fmtTime(c.since)}${c.job_name ? ` · ${c.job_name}` : ""}`;
  if (c.late) return `LATE — was due at ${to12h(c.due_at)} for ${c.late_job}`;
  return "Not active right now";
};

export const CrewStatusCard = () => {
  const [crew, setCrew] = useState(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    const load = () => teamStatusApi().then((d) => setCrew(d.crew)).catch(() => {});
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, []);

  if (crew === null) return null;
  const onClock = crew.filter((c) => c.clocked_in).length;
  const lateCount = crew.filter((c) => c.late).length;

  /* Thirteen rows of "Not active right now" is not information. Show the people
     who are working or late; the rest stay one tap away. */
  const active = crew.filter((c) => c.clocked_in || c.late);
  const idle = crew.filter((c) => !c.clocked_in && !c.late);
  const shown = showAll ? crew : active;

  return (
    <div data-testid="crew-status-card" className="surface p-4 sm:p-5 mb-8">
      <SectionTitle
        action={
          idle.length > 0 && (
            <button
              data-testid="crew-status-toggle"
              onClick={() => setShowAll((v) => !v)}
              className="text-[12.5px] font-semibold text-primary transition-colors hover:text-accent-ink"
              aria-expanded={showAll}
            >
              {showAll ? "Show only working" : `Show all ${crew.length}`}
            </button>
          )
        }
      >
        Who's on the clock
      </SectionTitle>
      <p data-testid="crew-status-summary" className="-mt-1 mb-3 text-[13.5px] text-ink-2">
        {onClock ? `${onClock} of ${crew.length} crew working right now` : "Nobody's clocked in right now"}
        {lateCount > 0 && <span className="font-bold text-destructive"> · {lateCount} running late</span>}
      </p>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
        {shown.map((c) => (
          <div
            key={c.user_id}
            data-testid="crew-status-row"
            className={`flex items-center gap-2.5 rounded-lg border p-2.5 ${rowStyle(c)}`}
          >
            <span className="relative flex h-3 w-3 shrink-0">
              {(c.clocked_in || c.late) && (
                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${c.clocked_in ? "bg-success" : "bg-destructive"}`} />
              )}
              <span className={`relative inline-flex rounded-full h-3 w-3 ${c.clocked_in ? "bg-success" : c.late ? "bg-destructive" : "bg-muted"}`} />
            </span>
            <div className="min-w-0">
              <p className="truncate text-[13.5px] font-semibold text-primary">{c.name}</p>
              <p data-testid="crew-status-label" className={`truncate text-[12px] ${c.clocked_in ? "text-success" : c.late ? "font-semibold text-destructive" : "text-faint"}`}>
                {statusLabel(c)}
              </p>
            </div>
          </div>
        ))}
        {crew.length === 0 && <p className="text-[13.5px] text-faint">No crew accounts yet — add them on the Crew page.</p>}
        {crew.length > 0 && shown.length === 0 && (
          <p className="text-[13.5px] text-faint">Everyone is off the clock. Tap "Show all" to see the roster.</p>
        )}
      </div>
    </div>
  );
};
