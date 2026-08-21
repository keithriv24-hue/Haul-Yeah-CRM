import React from "react";
import { AlertTriangle, ListChecks, MapPinOff, MessagesSquare } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { SCRIPT_SECTIONS, SURCHARGE_CHECKLIST, RED_FLAGS, NO_ADDRESS_RESPONSE, SCRIPT_EXAMPLES } from "@/lib/scriptContent";

const Say = ({ text, note }) => (
  <blockquote className="border-l-4 border-accent bg-accent/5 rounded-r-lg px-3 py-2 text-sm text-primary italic">
    "{text}"
    {note && <span className="block not-italic text-xs text-faint mt-1">{note}</span>}
  </blockquote>
);

const Block = ({ b }) => {
  if (b.type === "say") return <Say text={b.text} note={b.note} />;
  if (b.type === "sub") return <p className="text-xs font-bold uppercase tracking-wide text-faint pt-1">{b.text}</p>;
  if (b.type === "list") {
    return (
      <ul className="text-sm text-ink-2 space-y-1 list-disc pl-5">
        {b.items.map((it, i) => <li key={i}>{it}</li>)}
      </ul>
    );
  }
  return null;
};

export const ScriptPanel = ({ defaultOpen = ["opening"] }) => (
  <div data-testid="script-panel" className="surface">
    <div className="px-4 py-3 border-b border-border">
      <h2 className="font-display font-bold text-primary">Call script</h2>
      <p className="text-xs text-faint">Work top to bottom while you fill in the calculator.</p>
    </div>
    <Accordion type="multiple" defaultValue={defaultOpen} className="px-4">
      {SCRIPT_SECTIONS.map((s) => (
        <AccordionItem key={s.id} value={s.id}>
          <AccordionTrigger data-testid={`script-section-${s.id}`} className="font-display font-bold text-primary hover:no-underline">
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
    <div className="p-4 space-y-3 border-t border-border">
      <div data-testid="script-surcharges" className="rounded-lg border border-border bg-surface-sunk/70 p-3">
        <p className="text-xs font-bold uppercase tracking-wide text-ink-2 flex items-center gap-1.5 mb-2">
          <ListChecks className="w-3.5 h-3.5 text-accent-ink" /> {SURCHARGE_CHECKLIST.title}
        </p>
        <ul className="text-xs text-ink-2 space-y-0.5 list-disc pl-4">
          {SURCHARGE_CHECKLIST.items.map((it) => <li key={it}>{it}</li>)}
        </ul>
      </div>
      <div data-testid="script-red-flags" className="rounded-lg border border-destructive/25 bg-destructive/10 p-3">
        <p className="text-xs font-bold uppercase tracking-wide text-destructive flex items-center gap-1.5 mb-2">
          <AlertTriangle className="w-3.5 h-3.5" /> {RED_FLAGS.title}
        </p>
        <ul className="text-xs text-destructive space-y-0.5 list-disc pl-4">
          {RED_FLAGS.items.map((it) => <li key={it}>{it}</li>)}
        </ul>
      </div>
      <div data-testid="script-examples" className="rounded-lg border border-border bg-surface-sunk/70 p-3">
        <p className="text-xs font-bold uppercase tracking-wide text-ink-2 flex items-center gap-1.5 mb-2">
          <MessagesSquare className="w-3.5 h-3.5 text-accent-ink" /> {SCRIPT_EXAMPLES.title}
        </p>
        <div className="space-y-2.5">
          {SCRIPT_EXAMPLES.examples.map((ex) => (
            <div key={ex.label}>
              <p className="text-[11px] font-bold text-primary mb-1">{ex.label}</p>
              <ul className="text-xs text-ink-2 space-y-0.5 pl-1">
                {ex.lines.map((l, i) => <li key={i}>{l}</li>)}
              </ul>
            </div>
          ))}
        </div>
      </div>
      <div data-testid="script-no-address" className="rounded-lg border border-info/25 bg-info/10 p-3">
        <p className="text-xs font-bold uppercase tracking-wide text-info flex items-center gap-1.5 mb-2">
          <MapPinOff className="w-3.5 h-3.5" /> {NO_ADDRESS_RESPONSE.title}
        </p>
        <Say text={NO_ADDRESS_RESPONSE.say} />
      </div>
    </div>
  </div>
);
