import React, { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Truck, MapPin, Users, CalendarDays } from "lucide-react";
import { trackApi } from "@/lib/api";
import { fmtTime12 } from "@/lib/maps";
import { PortalBalance, PortalDetails, PortalUploads, PortalTip, PortalReview } from "@/components/portal/PortalSections";

const fmtDay = (d) =>
  d ? new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" }) : "";

const daysUntil = (d) => {
  if (!d) return null;
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });
  return Math.round((new Date(`${d}T12:00:00`) - new Date(`${today}T12:00:00`)) / 86400000);
};

const STATUS_LABEL = {
  Scheduled: "Your move is booked",
  "Crew assigned": "Your crew is locked in",
  "En Route": "Crew is on the way",
  Arrived: "Crew has arrived",
  "In Progress": "Your move is underway",
  Complete: "Move complete!",
};

export default function Track() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    trackApi(token)
      .then((d) => { setData(d); setError(""); })
      .catch((e) => setError(e?.response?.data?.detail || "This tracking link is no longer active."));
  }, [token]);

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  const pos = data?.position;
  const bbox = pos ? `${pos.lng - 0.008},${pos.lat - 0.008},${pos.lng + 0.008},${pos.lat + 0.008}` : null;
  const days = daysUntil(data?.job_date);
  const firstName = (data?.customer_name || "").split(" ")[0];
  const crewNames = (data?.crew || []).map((c) => c.name.split(" ")[0]).join(", ");

  return (
    <div data-testid="track-page" className="min-h-screen bg-primary text-white flex flex-col items-center px-4 py-10 gap-4">
      <img src="/logo.png" alt="Haul Yeah Moving" className="w-48 rounded-lg" />
      <div className="w-full max-w-md mt-4 bg-white/5 border border-white/10 rounded-2xl p-6 text-center">
        {error ? (
          <>
            <MapPin className="w-10 h-10 text-white/30 mx-auto" />
            <p data-testid="track-error" className="mt-3 text-sm text-white/80">{error}</p>
          </>
        ) : !data ? (
          <p className="text-sm text-white/60">Loading your move…</p>
        ) : (
          <>
            <p className="text-xs uppercase tracking-wide text-white/50 font-bold">{firstName ? `${firstName}'s move` : "Your move"}</p>
            <p data-testid="track-invoice" className="text-3xl font-bold mt-1">Job #{data.invoice_number}</p>
            {data.job_date && (
              <p className="text-sm text-white/60 mt-1">
                {fmtDay(data.job_date)}{data.start_time ? ` · crew starts ${fmtTime12(data.start_time)}` : ""}
              </p>
            )}
            {days != null && days > 0 && (
              <p data-testid="track-countdown" className="mt-3 inline-flex items-center gap-2 rounded-full bg-accent/20 border border-accent/40 text-accent-ink font-bold text-sm px-4 py-1.5">
                <CalendarDays className="w-4 h-4" /> {days} day{days === 1 ? "" : "s"} until your move
              </p>
            )}
            {days === 0 && (
              <p data-testid="track-countdown" className="mt-3 inline-flex items-center gap-2 rounded-full bg-success/20 border border-success/30 text-success font-bold text-sm px-4 py-1.5">
                <Truck className="w-4 h-4" /> Move day is today!
              </p>
            )}
            {data.status && (
              <p data-testid="track-job-status" className="mt-2 text-sm font-semibold text-white/80">{STATUS_LABEL[data.status] || data.status}</p>
            )}
            <div className="mt-5">
              {data.live && pos ? (
                <>
                  <p data-testid="track-status" className="inline-flex items-center gap-2 text-success font-bold">
                    <span className="w-2.5 h-2.5 rounded-full bg-success animate-pulse" />
                    Your crew is on the move!
                  </p>
                  <div className="mt-4 rounded-xl overflow-hidden border border-white/15">
                    <iframe
                      title="Crew location"
                      data-testid="track-map"
                      className="w-full h-72 bg-surface"
                      src={`https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${pos.lat},${pos.lng}`}
                    />
                  </div>
                  {data.updated_minutes_ago != null && (
                    <p className="text-xs text-white/50 mt-2">Updated {data.updated_minutes_ago < 1 ? "just now" : `${data.updated_minutes_ago} min ago`}</p>
                  )}
                </>
              ) : data.live ? (
                <p data-testid="track-status" className="inline-flex items-center gap-2 text-success font-bold">
                  <Truck className="w-5 h-5" /> Crew is on the clock — waiting for a location signal…
                </p>
              ) : data.updated_minutes_ago != null && data.updated_minutes_ago <= 120 ? (
                <p data-testid="track-status" className="text-warning font-bold">
                  Crew is en route — last updated {data.updated_minutes_ago} minute{data.updated_minutes_ago === 1 ? "" : "s"} ago.
                </p>
              ) : (
                <p data-testid="track-status" className="text-white/70 font-medium">
                  Live crew tracking lights up here on moving day.
                </p>
              )}
            </div>
            {((data.crew || []).length > 0 || data.truck_name) && (
              <div data-testid="track-crew-info" className="mt-5 border-t border-white/10 pt-4 text-sm text-white/80 space-y-1.5">
                {(data.crew || []).length > 0 && (
                  <p className="flex items-center justify-center gap-2">
                    <Users className="w-4 h-4 text-white/40" />
                    {(data.crew || []).map((c) => `${c.name.split(" ")[0]} (${c.position})`).join(", ")}
                  </p>
                )}
                {data.truck_name && (
                  <p className="flex items-center justify-center gap-2">
                    <Truck className="w-4 h-4 text-white/40" /> {data.truck_name}
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {data && !error && (
        <>
          <PortalBalance data={data} />
          <PortalDetails token={token} initial={data.details} />
          <PortalUploads token={token} initial={data.uploads} />
          {data.tips_enabled && <PortalTip token={token} crewNames={crewNames} />}
          <PortalReview token={token} reviewLink={data.review_link} alreadyDone={data.review_submitted} />
        </>
      )}

      <p className="text-xs text-white/40 mt-2">Link not working? Reply to our text and we'll send you a new one.</p>
      <p className="mt-2 text-sm text-white/50 italic">Weekend moves, flat price, no surprises.</p>
    </div>
  );
}
