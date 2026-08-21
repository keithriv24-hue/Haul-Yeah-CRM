import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { availabilityOverviewApi, ownerSetAvailabilityApi, apiErrorMessage } from "@/lib/api";
import { fmtDate, todayISO } from "@/lib/format";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const DayEditDialog = ({ day, crew, onOpenChange, onChanged }) => {
  const offIds = new Set((day?.off || []).map((o) => o.user_id));
  const toggle = async (u, isOff) => {
    try {
      await ownerSetAvailabilityApi(u.user_id, day.date, isOff);
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };
  return (
    <Dialog open={!!day} onOpenChange={() => onOpenChange(null)}>
      <DialogContent data-testid="availability-day-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">{day ? fmtDate(day.date) : ""} — who's off?</DialogTitle>
          <DialogDescription>Flip someone ON if they can't work that day. They can also mark it themselves from Days Off.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {crew.map((u) => (
            <div key={u.user_id} className="flex items-center justify-between text-sm rounded-md border border-border px-3 py-2">
              <span className="font-semibold text-primary">{u.name}</span>
              <div className="flex items-center gap-2">
                <span className={`text-xs font-semibold ${offIds.has(u.user_id) ? "text-destructive" : "text-success"}`}>
                  {offIds.has(u.user_id) ? "Off" : "Available"}
                </span>
                <Switch data-testid={`day-off-switch-${u.user_id}`} checked={offIds.has(u.user_id)} onCheckedChange={(v) => toggle(u, !v)} />
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export const AvailabilityTab = () => {
  const [month, setMonth] = useState(() => {
    const n = new Date();
    return new Date(n.getFullYear(), n.getMonth(), 1);
  });
  const [data, setData] = useState(null);
  const [editDay, setEditDay] = useState(null);

  const start = iso(month);
  const end = iso(new Date(month.getFullYear(), month.getMonth() + 1, 0));

  const load = useCallback(() => {
    availabilityOverviewApi(start, end).then(setData).catch(() => setData({ days: [], crew: [] }));
  }, [start, end]);
  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (editDay && data) setEditDay((d) => (d ? data.days.find((x) => x.date === d.date) || null : null));
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps

  const days = data?.days || [];
  const shortWeekends = days.filter((d) => d.weekend && d.short);
  const today = todayISO();
  const firstDow = new Date(month.getFullYear(), month.getMonth(), 1).getDay();

  return (
    <div className="mt-4 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button data-testid="availability-prev-month" variant="outline" size="sm" onClick={() => setMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1))}>
          <ChevronLeft className="w-4 h-4" />
        </Button>
        <span className="font-display font-bold text-primary w-40 text-center" data-testid="availability-month-label">
          {month.toLocaleDateString("en-US", { month: "long", year: "numeric" })}
        </span>
        <Button data-testid="availability-next-month" variant="outline" size="sm" onClick={() => setMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1))}>
          <ChevronRight className="w-4 h-4" />
        </Button>
        <div className="flex items-center gap-3 ml-auto text-[11px] text-faint">
          <span className="inline-flex items-center gap-1"><span className="w-3 h-3 rounded bg-accent/12 border border-accent/25 inline-block" /> weekend</span>
          <span className="inline-flex items-center gap-1"><span className="w-3 h-3 rounded ring-2 ring-destructive/40 inline-block" /> short on crew</span>
        </div>
      </div>

      {shortWeekends.length > 0 && (
        <div data-testid="short-weekend-banner" className="border border-destructive/30 bg-destructive/10 rounded-lg px-4 py-3 text-sm text-destructive flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>
            <strong>Heads up:</strong> not enough available crew for the booked jobs on{" "}
            {shortWeekends.map((d) => fmtDate(d.date)).join(", ")}. Tap the day to sort it out.
          </span>
        </div>
      )}

      {data === null ? (
        <p className="text-sm text-faint">Loading availability…</p>
      ) : (
        <div className="surface p-3" data-testid="availability-grid">
          <div className="grid grid-cols-7 gap-1 mb-1">
            {WEEKDAYS.map((w, i) => (
              <div key={w} className={`text-center text-[11px] font-bold uppercase ${i === 0 || i === 6 ? "text-accent-ink" : "text-faint"}`}>{w}</div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {Array.from({ length: firstDow }).map((_, i) => <div key={`pad-${i}`} />)}
            {days.map((d) => (
              <button
                key={d.date}
                data-testid={`availability-day-${d.date}`}
                onClick={() => setEditDay(d)}
                className={`text-left rounded-md border p-1.5 min-h-[84px] transition-colors hover:border-accent/60 ${
                  d.weekend ? "bg-accent/10 border-accent/25" : "bg-surface border-border"
                } ${d.short ? "ring-2 ring-destructive/40" : ""}`}
              >
                <div className="flex items-center justify-between">
                  <span className={`text-xs font-bold ${d.date === today ? "text-accent-ink" : "text-primary"}`}>{Number(d.date.slice(8))}</span>
                  {d.short && <AlertTriangle className="w-3.5 h-3.5 text-destructive" />}
                </div>
                {d.jobs > 0 && (
                  <span className="inline-block mt-0.5 text-[10px] font-bold bg-primary text-white rounded px-1">
                    {d.jobs} job{d.jobs === 1 ? "" : "s"} · needs {d.needed}
                  </span>
                )}
                <div className={`text-[10px] font-semibold mt-0.5 ${d.short ? "text-destructive" : "text-success"}`}>
                  {d.available.length} available
                </div>
                {d.off.slice(0, 3).map((o) => (
                  <div key={o.user_id} className="text-[10px] text-destructive truncate">✕ {o.name}</div>
                ))}
                {d.off.length > 3 && <div className="text-[10px] text-destructive">+{d.off.length - 3} more off</div>}
              </button>
            ))}
          </div>
        </div>
      )}

      <DayEditDialog day={editDay} crew={data?.crew || []} onOpenChange={setEditDay} onChanged={load} />
    </div>
  );
};
