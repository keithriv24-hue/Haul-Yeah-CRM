import React, { useEffect, useState } from "react";
import dayjs from "dayjs";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { InstructionBanner } from "@/components/Bits";
import { myAvailabilityApi, setAvailabilityApi, apiErrorMessage } from "@/lib/api";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export default function DaysOff() {
  const [month, setMonth] = useState(() => dayjs().startOf("month"));
  const [avail, setAvail] = useState({});

  useEffect(() => {
    myAvailabilityApi().then(setAvail).catch(() => {});
  }, []);

  const toggle = async (dateStr) => {
    const nowAvailable = avail[dateStr] !== false;
    const next = !nowAvailable ? true : false;
    setAvail((a) => ({ ...a, [dateStr]: next }));
    try {
      await setAvailabilityApi(dateStr, next);
    } catch (e) {
      setAvail((a) => ({ ...a, [dateStr]: nowAvailable }));
      toast.error(apiErrorMessage(e));
    }
  };

  const firstDay = month.day();
  const daysInMonth = month.daysInMonth();
  const today = dayjs().format("YYYY-MM-DD");
  const cells = [...Array(firstDay).fill(null), ...Array.from({ length: daysInMonth }, (_, i) => i + 1)];

  return (
    <div data-testid="days-off-page" className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-bold text-[#1B2A4A]">Days Off</h1>
        <p className="text-sm text-slate-500">Tell the boss when you can't work.</p>
      </div>
      <InstructionBanner testId="days-off-banner">
        Tap any day you can't work — it turns red so you won't get booked. Tap again if plans change.
      </InstructionBanner>
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="flex items-center justify-between mb-3">
          <Button data-testid="daysoff-prev-month" variant="outline" size="sm" onClick={() => setMonth((m) => m.subtract(1, "month"))}>
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <p data-testid="daysoff-month-label" className="font-bold text-[#1B2A4A]">{month.format("MMMM YYYY")}</p>
          <Button data-testid="daysoff-next-month" variant="outline" size="sm" onClick={() => setMonth((m) => m.add(1, "month"))}>
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
        <div className="grid grid-cols-7 gap-1 text-center">
          {WEEKDAYS.map((d) => (
            <div key={d} className="text-[10px] uppercase tracking-wide text-slate-400 font-bold py-1">{d}</div>
          ))}
          {cells.map((d, i) => {
            if (d === null) return <div key={`b${i}`} />;
            const dateStr = month.date(d).format("YYYY-MM-DD");
            const off = avail[dateStr] === false;
            const isToday = dateStr === today;
            return (
              <button
                key={dateStr}
                data-testid="daysoff-day-cell"
                data-date={dateStr}
                onClick={() => toggle(dateStr)}
                className={`aspect-square rounded-md text-sm font-semibold flex flex-col items-center justify-center transition-colors ${
                  off ? "bg-red-500 text-white border border-red-600 shadow-inner" : "bg-slate-50 text-[#1B2A4A] border border-transparent hover:border-slate-300"
                } ${isToday ? "ring-2 ring-[#E8743B]" : ""}`}
              >
                {d}
                {off && <span className="text-[8px] font-bold uppercase">off</span>}
              </button>
            );
          })}
        </div>
      </div>
      <p className="text-xs text-slate-400">Weekends are our busy days — flag them early if you need one off.</p>
    </div>
  );
}
