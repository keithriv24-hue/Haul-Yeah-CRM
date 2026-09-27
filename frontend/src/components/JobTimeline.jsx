import React, { useEffect, useState } from "react";
import { CalendarPlus, Flag, Users, Truck, ClipboardCheck, AlarmClock, Camera, CircleDot, ShieldAlert, MessageSquareWarning } from "lucide-react";
import { jobTimelineApi } from "@/lib/api";

const KIND_ICON = { created: CalendarPlus, status: Flag, crew: Users, truck: Truck, checklist: ClipboardCheck, clock: AlarmClock, photo: Camera, problem: MessageSquareWarning, flag: ShieldAlert };
const KIND_LABEL = { problem: "Problem reported", flag: "Reliability flag" };
const KIND_ACCENT = { problem: "text-destructive", flag: "text-warning" };

const fmtAt = (iso) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

export const JobTimeline = ({ assignmentId }) => {
  const [events, setEvents] = useState(null);
  useEffect(() => {
    jobTimelineApi(assignmentId).then((d) => setEvents(d.events)).catch(() => setEvents([]));
  }, [assignmentId]);
  if (events === null) return <p className="text-xs text-faint">Loading timeline…</p>;
  if (events.length === 0) return <p className="text-sm text-faint text-center py-6">Nothing logged on this job yet.</p>;
  return (
    <div data-testid="job-timeline" className="relative pl-5 space-y-3 max-h-[55vh] overflow-y-auto mt-2">
      <span className="absolute left-[7px] top-1 bottom-1 w-px bg-muted" />
      {events.map((e, i) => {
        const Icon = KIND_ICON[e.kind] || CircleDot;
        const label = KIND_LABEL[e.kind];
        return (
          <div key={i} data-testid="timeline-event" className="relative">
            <span className="absolute -left-5 top-0.5 w-4 h-4 rounded-full bg-surface border border-border-strong flex items-center justify-center">
              <Icon className={`w-2.5 h-2.5 ${KIND_ACCENT[e.kind] || "text-accent-ink"}`} />
            </span>
            {label && (
              <span data-testid={`timeline-label-${e.kind}`} className={`text-[10px] font-bold uppercase tracking-wide ${KIND_ACCENT[e.kind] || "text-faint"}`}>{label}</span>
            )}
            <p className="text-sm text-primary font-medium leading-tight">{e.title}</p>
            {e.detail && <p className="text-xs text-ink-2 leading-snug mt-0.5">{e.detail}</p>}
            <p className="text-[10px] text-faint">{fmtAt(e.at)}{e.by ? ` · ${e.by}` : ""}</p>
          </div>
        );
      })}
    </div>
  );
};
