import React, { useState } from "react";
import { Phone, MessageSquare, X, Headset } from "lucide-react";
import { telUrl, smsUrl } from "@/lib/maps";

const OWNERS = [
  { name: "Keith Rivera", phone: "201-247-8446" },
  { name: "Romeo Perry", phone: "862-224-6176" },
];

export const CrewContactsBubble = () => {
  const [open, setOpen] = useState(false);
  return (
    <div className="fixed bottom-20 md:bottom-6 right-3 z-[60] print:hidden">
      {open && (
        <div data-testid="owner-contacts-panel" className="mb-2 w-72 bg-[#1B2A4A] text-white rounded-xl shadow-2xl border border-white/15 p-4">
          <p className="text-xs font-bold uppercase tracking-wide text-white/60 mb-2">Call the bosses</p>
          {OWNERS.map((o) => (
            <div key={o.phone} data-testid="owner-contact-row" className="flex items-center justify-between py-2 border-b border-white/10 last:border-0">
              <div>
                <p className="text-sm font-semibold">{o.name}</p>
                <p className="text-xs text-white/60">Owner — {o.phone}</p>
              </div>
              <div className="flex gap-1.5">
                <a data-testid={`owner-call-${o.phone}`} href={telUrl(o.phone)} className="p-2 rounded-full bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30">
                  <Phone className="w-4 h-4" />
                </a>
                <a data-testid={`owner-text-${o.phone}`} href={smsUrl(o.phone)} className="p-2 rounded-full bg-sky-500/20 text-sky-300 hover:bg-sky-500/30">
                  <MessageSquare className="w-4 h-4" />
                </a>
              </div>
            </div>
          ))}
          <p className="text-[11px] text-[#E8743B] font-medium mt-2">If you text, start with your name and why you're reaching out.</p>
        </div>
      )}
      <button
        data-testid="owner-contacts-bubble"
        onClick={() => setOpen((v) => !v)}
        className="ml-auto flex items-center gap-2 rounded-full bg-[#E8743B] hover:bg-[#d4632e] text-white font-bold text-sm px-4 py-3 shadow-xl transition-colors"
      >
        {open ? <X className="w-4 h-4" /> : <Headset className="w-4 h-4" />}
        {open ? "Close" : "Bosses"}
      </button>
    </div>
  );
};
