import React from "react";
import { AlertTriangle, ListChecks, MapPinOff } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { SCRIPT_SECTIONS, SURCHARGE_CHECKLIST, RED_FLAGS, NO_ADDRESS_RESPONSE } from "@/lib/scriptContent";

const Say = ({ text, note }) => (
  <blockquote className="border-l-4 border-[#E8743B] bg-[#E8743B]/5 rounded-r-lg px-3 py-2 text-sm text-[#1B2A4A] italic">
    "{text}"
    {note && <span className="block not-italic text-xs text-slate-500 mt-1">{note}</span>}
  </blockquote>
);

const Block = ({ b }) => {
  if (b.type === "say") return <Say text={b.text} note={b.note} />;
  if (b.type === "sub") return <p className="text-xs font-bold uppercase tracking-wide text-slate-500 pt-1">{b.text}</p>;
  if (b.type === "list") {
    return (
      <ul className="text-sm text-slate-700 space-y-1 list-disc pl-5">
        {b.items.map((it, i) => <li key={i}>{it}</li>)}
      </ul>
    );
  }
  return null;
};

export const ScriptPanel = ({ defaultOpen = ["opening"] }) => (
  <div data-testid="script-panel" className="bg-white border border-slate-200 rounded-lg">
    <div className="px-4 py-3 border-b border-slate-100">
      <h2 className="font-display font-bold text-[#1B2A4A]">Call script</h2>
      <p className="text-xs text-slate-400">Work top to bottom while you fill in the calculator.</p>
    </div>
    <Accordion type="multiple" defaultValue={defaultOpen} className="px-4">
      {SCRIPT_SECTIONS.map((s) => (
        <AccordionItem key={s.id} value={s.id}>
          <AccordionTrigger data-testid={`script-section-${s.id}`} className="font-display font-bold text-[#1B2A4A] hover:no-underline">
            {s.title}
          </AccordionTrigger>
          <AccordionContent>
            <div className="space-y-2.5">
              {s.blocks.map((b, i) => <Block key={i} b={b} />)}
            </div>
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
    <div className="p-4 space-y-3 border-t border-slate-100">
      <div data-testid="script-surcharges" className="rounded-lg border border-slate-200 bg-slate-50/70 p-3">
        <p className="text-xs font-bold uppercase tracking-wide text-slate-600 flex items-center gap-1.5 mb-2">
          <ListChecks className="w-3.5 h-3.5 text-[#E8743B]" /> {SURCHARGE_CHECKLIST.title}
        </p>
        <ul className="text-xs text-slate-600 space-y-0.5 list-disc pl-4">
          {SURCHARGE_CHECKLIST.items.map((it) => <li key={it}>{it}</li>)}
        </ul>
      </div>
      <div data-testid="script-red-flags" className="rounded-lg border border-red-200 bg-red-50/70 p-3">
        <p className="text-xs font-bold uppercase tracking-wide text-red-700 flex items-center gap-1.5 mb-2">
          <AlertTriangle className="w-3.5 h-3.5" /> {RED_FLAGS.title}
        </p>
        <ul className="text-xs text-red-800/80 space-y-0.5 list-disc pl-4">
          {RED_FLAGS.items.map((it) => <li key={it}>{it}</li>)}
        </ul>
      </div>
      <div data-testid="script-no-address" className="rounded-lg border border-sky-200 bg-sky-50/70 p-3">
        <p className="text-xs font-bold uppercase tracking-wide text-sky-700 flex items-center gap-1.5 mb-2">
          <MapPinOff className="w-3.5 h-3.5" /> {NO_ADDRESS_RESPONSE.title}
        </p>
        <Say text={NO_ADDRESS_RESPONSE.say} />
      </div>
    </div>
  </div>
);
