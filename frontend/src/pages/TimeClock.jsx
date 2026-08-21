import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { AlarmClock, LogIn, LogOut, MapPin, Loader2, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { InstructionBanner } from "@/components/Bits";
import { useAuth } from "@/components/AuthGate";
import { myTimeApi, clockInApi, clockOutApi, gpsConsentApi, apiErrorMessage } from "@/lib/api";
import { getPosition } from "@/lib/geo";
import { fmtDate } from "@/lib/format";

const fmtTime = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "—");

const elapsedLabel = (iso, now) => {
  const secs = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 1000));
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
};

export default function TimeClock() {
  const { user, updateUser } = useAuth();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [consentOpen, setConsentOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [now, setNow] = useState(Date.now());
  const navigate = useNavigate();

  const load = useCallback(() => myTimeApi().then(setData).catch(() => setData({ entries: [], weekly_totals: {}, clocked_in: false })), []);
  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!data?.clocked_in) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [data?.clocked_in]);

  const punch = async (kind) => {
    setBusy(true);
    try {
      const pos = await getPosition();
      const res = kind === "in" ? await clockInApi(pos) : await clockOutApi(pos);
      if (kind === "in") {
        toast.success(res.job_name ? `Clocked in on "${res.job_name}" as ${res.position}.` : "Clocked in.");
      } else {
        toast.success(res.hours != null ? `Clocked out — ${res.hours} hours on the clock.` : "Clocked out.");
        if (res.review_prompt) setReviewOpen(true);
      }
      if (!pos) toast.warning("Heads up: we couldn't read your location, so this punch has no GPS.");
      await load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  const startClockIn = () => {
    if (user && !user.gps_consent) {
      setConsentOpen(true);
      return;
    }
    punch("in");
  };

  const agreeConsent = async () => {
    try {
      await gpsConsentApi();
      updateUser({ gps_consent: true });
      setConsentOpen(false);
      punch("in");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  const weeks = Object.entries(data?.weekly_totals || {}).sort((a, b) => (a[0] < b[0] ? 1 : -1)).slice(0, 4);

  return (
    <div data-testid="time-clock-page" className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-bold text-primary">Time Clock</h1>
        <p className="text-sm text-faint">Punch in when you start, punch out when you're done.</p>
      </div>
      <InstructionBanner testId="time-clock-banner">
        Clock in when your shift starts and out when it ends. Your location is only checked while you're on the clock.
      </InstructionBanner>

      <div className="surface p-6 text-center">
        {data === null ? (
          <p className="text-sm text-faint">Loading…</p>
        ) : data.clocked_in ? (
          <>
            <p className="text-xs uppercase tracking-wide text-success font-bold">On the clock</p>
            <p data-testid="clock-elapsed" className="text-4xl font-bold text-primary tabular-nums mt-1">
              {elapsedLabel(data.open_entry.clocked_in_at, now)}
            </p>
            <p className="text-xs text-faint mt-1">
              Since {fmtTime(data.open_entry.clocked_in_at)}
              {data.open_entry.job_name ? ` · ${data.open_entry.job_name}` : ""}
            </p>
            <Button data-testid="clock-out-btn" disabled={busy} onClick={() => punch("out")} className="w-full mt-4 h-14 text-lg gap-2">
              {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <LogOut className="w-5 h-5" />} Clock out
            </Button>
          </>
        ) : (
          <>
            <AlarmClock className="w-10 h-10 text-faint/70 mx-auto" />
            <p className="text-sm text-faint mt-2">You're off the clock.</p>
            <Button data-testid="clock-in-btn" disabled={busy} onClick={startClockIn} className="w-full mt-4 h-14 text-lg gap-2 bg-success hover:bg-success">
              {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <LogIn className="w-5 h-5" />} Clock in
            </Button>
          </>
        )}
      </div>

      {weeks.length > 0 && (
        <div data-testid="weekly-totals" className="grid grid-cols-2 gap-3">
          {weeks.map(([wk, hrs]) => (
            <div key={wk} className="surface p-4">
              <p className="text-[11px] uppercase tracking-wide text-faint">Week {wk.split("-W")[1]}</p>
              <p className="text-xl font-bold text-primary">{hrs} hrs</p>
            </div>
          ))}
        </div>
      )}

      <div>
        <h2 className="text-sm font-bold uppercase tracking-wide text-faint mb-2">Recent punches</h2>
        <div className="surface divide-y divide-border">
          {(data?.entries || []).slice(0, 14).map((e) => (
            <div key={e.id} data-testid="time-entry-row" className="flex items-center justify-between px-4 py-2.5 text-sm">
              <div>
                <p className="font-medium text-primary">{fmtDate(e.clock_in.at.slice(0, 10))}</p>
                <p className="text-xs text-faint">
                  {fmtTime(e.clock_in.at)} → {e.clock_out ? fmtTime(e.clock_out.at) : "still on"}
                  {e.job_name ? ` · ${e.job_name}` : ""}
                </p>
              </div>
              <span className="font-bold text-primary">{e.hours != null ? `${e.hours}h` : "—"}</span>
            </div>
          ))}
          {data && data.entries.length === 0 && <p className="text-sm text-faint px-4 py-6 text-center">No punches yet.</p>}
        </div>
      </div>

      <AlertDialog open={consentOpen} onOpenChange={setConsentOpen}>
        <AlertDialogContent data-testid="gps-consent-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-display flex items-center gap-2">
              <MapPin className="w-5 h-5 text-accent-ink" /> Location while you work
            </AlertDialogTitle>
            <AlertDialogDescription>
              When you're clocked in, the app records your location so the boss can see the crew is on site. It stops the second you clock out. One-time OK needed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="gps-consent-cancel">Not now</AlertDialogCancel>
            <AlertDialogAction data-testid="gps-consent-agree-btn" onClick={agreeConsent} className="bg-accent hover:bg-accent-press">
              OK, clock me in
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={reviewOpen} onOpenChange={setReviewOpen}>
        <AlertDialogContent data-testid="review-prompt-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-display flex items-center gap-2">
              <Star className="w-5 h-5 text-accent-ink" /> Job done!
            </AlertDialogTitle>
            <AlertDialogDescription>
              Nice work. Remember to ask the customer to leave a review. You can send it right from the Today page.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="review-prompt-close">Not now</AlertDialogCancel>
            <AlertDialogAction data-testid="review-prompt-open-btn" onClick={() => navigate("/today#review")} className="bg-accent hover:bg-accent-press">
              Ask for a review
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
