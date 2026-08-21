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
    <div className="fixed bottom-[calc(76px+env(safe-area-inset-bottom))] md:bottom-6 right-3 z-[45] print:hidden">
      {open && (
        <div data-testid="owner-contacts-panel" className="mb-2 w-[17rem] animate-pop-in rounded-xl border border-white/15 bg-primary p-4 text-white shadow-pop">
          <p className="text-xs font-bold uppercase tracking-wide text-white/60 mb-2">Call the bosses</p>
          {OWNERS.map((o) => (
            <div key={o.phone} data-testid="owner-contact-row" className="flex items-center justify-between py-2 border-b border-white/10 last:border-0">
              <div>
                <p className="text-sm font-semibold">{o.name}</p>
                <p className="text-xs text-white/60">Owner — {o.phone}</p>
              </div>
              <div className="flex gap-1.5">
                <a data-testid={`owner-call-${o.phone}`} href={telUrl(o.phone)} className="press grid h-10 w-10 place-items-center rounded-full bg-success text-white transition-colors hover:brightness-110">
                  <Phone className="w-4 h-4" />
                </a>
                <a data-testid={`owner-text-${o.phone}`} href={smsUrl(o.phone)} className="press grid h-10 w-10 place-items-center rounded-full bg-info text-white transition-colors hover:brightness-110">
                  <MessageSquare className="w-4 h-4" />
                </a>
              </div>
            </div>
          ))}
          <p className="text-[11px] text-accent font-medium mt-2">If you text, start with your name and why you're reaching out.</p>
        </div>
      )}
      <button
        data-testid="owner-contacts-bubble"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close boss contacts" : "Call the bosses"}
        aria-expanded={open}
        className="press ml-auto grid h-12 w-12 place-items-center rounded-full bg-accent text-white shadow-pop transition-colors hover:bg-accent-press"
      >
        {open ? <X className="w-5 h-5" /> : <Headset className="w-5 h-5" />}
      </button>
    </div>
  );
};
