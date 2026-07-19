import React, { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { MapPin } from "lucide-react";
import { gpsLiveApi } from "@/lib/api";
import { ageLabel, minutesSince } from "@/lib/format";

const fmtTime = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "—");

export const MapTab = () => {
  const mapRef = useRef(null);
  const mapObj = useRef(null);
  const layerRef = useRef(null);
  const [crew, setCrew] = useState(null);

  useEffect(() => {
    if (!mapRef.current || mapObj.current) return;
    const map = L.map(mapRef.current).setView([40.735, -74.3], 9);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    layerRef.current = L.layerGroup().addTo(map);
    mapObj.current = map;
    return () => {
      map.remove();
      mapObj.current = null;
    };
  }, []);

  useEffect(() => {
    let stop = false;
    const load = async () => {
      try {
        const list = await gpsLiveApi();
        if (stop) return;
        setCrew(list);
        const layer = layerRef.current;
        if (!layer) return;
        layer.clearLayers();
        const pts = [];
        list.forEach((c) => {
          if (c.lat == null || c.lng == null) return;
          pts.push([c.lat, c.lng]);
          const icon = L.divIcon({
            className: "",
            html: `<div style="background:#E8743B;color:#fff;font-weight:700;font-size:11px;padding:3px 8px;border-radius:999px;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.35);white-space:nowrap;">${(c.name || "?").split(" ")[0]}</div>`,
            iconAnchor: [20, 12],
          });
          L.marker([c.lat, c.lng], { icon })
            .addTo(layer)
            .bindPopup(`<b>${c.name}</b><br/>${c.job_name || "No job linked"}<br/>Clocked in ${fmtTime(c.clocked_in_at)}<br/>Last ping ${c.last_ping ? ageLabel(minutesSince(c.last_ping)) + " ago" : "—"}`);
        });
        if (pts.length && mapObj.current) mapObj.current.fitBounds(L.latLngBounds(pts).pad(0.4), { maxZoom: 13 });
      } catch {}
    };
    load();
    const id = setInterval(load, 30000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, []);

  const list = crew || [];

  return (
    <div className="mt-4 space-y-4">
      <div data-testid="live-map" ref={mapRef} className="h-[420px] rounded-lg border border-slate-200 z-0" />
      <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
        <p className="px-4 py-2.5 text-sm font-bold text-[#1B2A4A]">Clocked in right now ({list.length})</p>
        {crew !== null && list.length === 0 && (
          <p className="text-sm text-slate-400 px-4 py-6 text-center">Nobody's on the clock. Pins show up here the moment someone clocks in.</p>
        )}
        {list.map((c) => (
          <div key={c.user_id} data-testid="live-crew-row" className="flex items-center justify-between px-4 py-2.5 text-sm">
            <div>
              <p className="font-semibold text-[#1B2A4A]">{c.name}</p>
              <p className="text-xs text-slate-500">{c.job_name || "No job linked"} · in since {fmtTime(c.clocked_in_at)}</p>
            </div>
            <span className="text-xs text-slate-500 inline-flex items-center gap-1">
              <MapPin className={`w-3.5 h-3.5 ${c.lat != null ? "text-emerald-500" : "text-slate-300"}`} />
              {c.lat != null ? (c.last_ping ? `${ageLabel(minutesSince(c.last_ping))} ago` : "located") : "no GPS yet"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
