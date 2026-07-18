import React from "react";
import { PhoneCall, Search, Calculator, CreditCard, StickyNote, ShieldQuestion } from "lucide-react";
import { InstructionBanner, PageTitle } from "@/components/Bits";
import { QUOTE_COACH_LINE } from "@/lib/quote";

const SayThis = ({ children }) => (
  <blockquote className="border-l-4 border-[#E8743B] bg-[#E8743B]/5 rounded-r-lg px-4 py-3 text-sm text-[#1B2A4A] italic">
    "{children}"
  </blockquote>
);

const STEPS = [
  {
    icon: PhoneCall,
    title: "1. Answer fast and warm",
    body: (
      <>
        <p className="text-sm text-slate-600 mb-2">Call or text every New lead in under 5 minutes. Speed wins the job.</p>
        <SayThis>
          Hi, this is [your name] with Haul Yeah Moving — weekend moves, flat price, no surprises. I saw you asked about a move. Do you have two minutes?
        </SayThis>
      </>
    ),
  },
  {
    icon: Search,
    title: "2. Ask the five questions",
    body: (
      <>
        <p className="text-sm text-slate-600 mb-2">Get these before you price anything. Type them into the lead's card as you go.</p>
        <ul className="text-sm text-slate-700 space-y-1 list-disc pl-5">
          <li>When is the move date?</li>
          <li>Where from, and where to?</li>
          <li>How big is the place? (Studio/1BR, 2BR, 3BR, 4BR+)</li>
          <li>Any stairs? How many flights at each end?</li>
          <li>Anything heavy or special — piano, safe, gym gear?</li>
        </ul>
      </>
    ),
  },
  {
    icon: Calculator,
    title: "3. Quote the range",
    body: (
      <>
        <p className="text-sm text-slate-600 mb-2">
          Open the Quote Calculator, plug in the answers, and read the range out loud. {QUOTE_COACH_LINE}
        </p>
        <SayThis>
          Based on what you told me, you're looking at [low] to [high] for the whole move. The final price gets confirmed by phone once we check the access details — no surprises on move day.
        </SayThis>
      </>
    ),
  },
  {
    icon: CreditCard,
    title: "4. Ask for the deposit",
    body: (
      <>
        <p className="text-sm text-slate-600 mb-2">The deposit is 25% of the high end. It locks their date. Weekends fill up fast — say so.</p>
        <SayThis>
          To lock in your date, we take a 25% deposit. Weekends go fast this time of year. Want me to have the payment link sent over today?
        </SayThis>
      </>
    ),
  },
  {
    icon: ShieldQuestion,
    title: "5. Handle the pushback",
    body: (
      <div className="space-y-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-1">"That's more than I expected."</p>
          <SayThis>
            Totally fair. Our price covers the crew, the truck, and the travel — one number, no add-ons on move day. A lot of cheaper quotes grow once the truck shows up. Ours doesn't.
          </SayThis>
        </div>
        <div>
          <p className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-1">"I need to think about it."</p>
          <SayThis>
            No problem. One heads-up: I can't hold the date without a deposit, and weekends book up. Can I check back with you tomorrow?
          </SayThis>
        </div>
        <div>
          <p className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-1">"I'm getting other quotes."</p>
          <SayThis>
            Smart move. When you compare, ask if their number is a flat price or an estimate. Ours is a range with a firm top — it never goes above the high number we agreed on.
          </SayThis>
        </div>
      </div>
    ),
  },
  {
    icon: StickyNote,
    title: "6. Write it down",
    body: (
      <p className="text-sm text-slate-600">
        Before you hang up: set the lead's status (Contacted, Warm, Hot, or Quoted) and press "Add note" with what they said and when to follow up. If you saved a quote, the breakdown is already on their card.
      </p>
    ),
  },
];

export default function Script() {
  return (
    <div data-testid="script-page" className="max-w-lg">
      <PageTitle title="Sales Script" subtitle="What to say on every call." />
      <InstructionBanner>Follow these six steps on every call. The words in orange boxes are ready to say out loud.</InstructionBanner>
      <div className="space-y-4">
        {STEPS.map(({ icon: Icon, title, body }) => (
          <div key={title} className="bg-white border border-slate-200 rounded-lg p-5">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-9 h-9 rounded-lg bg-[#E8743B]/10 border border-[#E8743B]/25 flex items-center justify-center shrink-0">
                <Icon className="w-4.5 h-4.5 text-[#E8743B]" />
              </div>
              <h2 className="font-display font-bold text-lg text-[#1B2A4A]">{title}</h2>
            </div>
            {body}
          </div>
        ))}
      </div>
    </div>
  );
}
