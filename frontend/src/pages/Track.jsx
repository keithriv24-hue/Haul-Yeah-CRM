import React, { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Truck, MapPin } from "lucide-react";
import { trackApi } from "@/lib/api";
import { fmtTime12 } from "@/lib/maps";

const fmtDay = (d) =>
  d ? new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" }) : "";

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

  return (
    <div data-testid="track-page" className="min-h-screen bg-[#1B2A4A] text-white flex flex-col items-center px-4 py-10">
      <img src="/logo.png" alt="Haul Yeah Moving" className="w-48 rounded-lg" />
      <div className="w-full max-w-md mt-8 bg-white/5 border border-white/10 rounded-2xl p-6 text-center">
        {error ? (
          <>
            <MapPin className="w-10 h-10 text-white/30 mx-auto" />
            <p data-testid="track-error" className="mt-3 text-sm text-white/80">{error}</p>
          </>
        ) : !data ? (
          <p className="text-sm text-white/60">Loading your move…</p>
        ) : (
          <>
            <p className="text-xs uppercase tracking-wide text-white/50 font-bold">Your move</p>
            <p data-testid="track-invoice" className="text-3xl font-bold mt-1">Job #{data.invoice_number}</p>
            {data.job_date && (
              <p className="text-sm text-white/60 mt-1">
                {fmtDay(data.job_date)}{data.start_time ? ` · crew starts ${fmtTime12(data.start_time)}` : ""}
              </p>
            )}
            <div className="mt-5">
              {data.live && pos ? (
                <>
                  <p data-testid="track-status" className="inline-flex items-center gap-2 text-emerald-300 font-bold">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
                    Your crew is on the move!
                  </p>
                  <div className="mt-4 rounded-xl overflow-hidden border border-white/15">
                    <iframe
                      title="Crew location"
                      data-testid="track-map"
                      className="w-full h-72 bg-white"
                      src={`https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${pos.lat},${pos.lng}`}
                    />
                  </div>
                  {data.updated_minutes_ago != null && (
                    <p className="text-xs text-white/50 mt-2">Updated {data.updated_minutes_ago < 1 ? "just now" : `${data.updated_minutes_ago} min ago`}</p>
                  )}
                </>
              ) : data.live ? (
                <p data-testid="track-status" className="inline-flex items-center gap-2 text-emerald-300 font-bold">
                  <Truck className="w-5 h-5" /> Crew is on the clock — waiting for a location signal…
                </p>
              ) : data.updated_minutes_ago != null ? (
                <p data-testid="track-status" className="text-amber-300 font-bold">
                  Crew is en route — last updated {data.updated_minutes_ago} minute{data.updated_minutes_ago === 1 ? "" : "s"} ago.
                </p>
              ) : (
                <p data-testid="track-status" className="text-white/70 font-medium">
                  Your crew will show up here on moving day. Check back soon!
                </p>
              )}
            </div>
            <p className="text-xs text-white/40 mt-6">Link not working? Reply to our text and we'll send you a new one.</p>
          </>
        )}
      </div>
      <p className="mt-8 text-sm text-white/50 italic">Weekend moves, flat price, no surprises.</p>
    </div>
  );
}
