import React from "react";
import { PhoneCall, Calculator, CreditCard, Truck, CheckCircle2, Star, Video } from "lucide-react";
import { InstructionBanner, PageTitle } from "@/components/Bits";
import { Button } from "@/components/ui/button";
import { useApp } from "@/context/AppContext";
import { fmtMoney, fmtMoneyCents } from "@/lib/format";
import { useLivePricing } from "@/pages/Calculator";

const STEPS = [
  {
    icon: PhoneCall,
    title: "1. Respond in under 5 minutes",
    text: "When a lead comes in, call or text right away. The timer on each New lead card turns red after 5 minutes. Fast replies win the most jobs.",
  },
  {
    icon: Calculator,
    title: "2. Quote the move",
    text: "Use the Quote button on the lead card or the Quote Calculator page. Pick crew size, hours, travel type, miles, stairs, packing, and any big items. The app shows one final price plus the deposit. Say it with confidence.",
  },
  {
    icon: CreditCard,
    title: "3. Send the deposit link",
    text: "Send a Square invoice for the deposit shown by the calculator, or make a payment link in your Square dashboard and paste it in the Deposit window. The app saves it to the lead and writes the email for you.",
  },
  {
    icon: Truck,
    title: "4. Book the job",
    text: "Once the deposit is in, press \"Book as job\". A new Project is made and the lead is marked Booked. Manage the crew, truck, and hours on the Projects page.",
  },
  {
    icon: CheckCircle2,
    title: "5. Complete and invoice",
    text: "After the move, set the Project to Completed and enter the final revenue. Make an invoice and mark it Paid when the money lands.",
  },
  {
    icon: Star,
    title: "6. Ask for a Google review",
    text: "Happy customers say yes when you ask right away. Text them the review link the same day. Reviews bring the next lead in the door.",
  },
];

export default function Help() {
  const { rates: ctxRates } = useApp();
  const { rates, items } = useLivePricing(ctxRates);
  const activeItems = items.filter((it) => it.active);
  return (
    <div data-testid="help-page">
      <PageTitle title="Help" subtitle="From new lead to cash in the bank." />
      <InstructionBanner>How money moves through the business, step by step. Follow this every time.</InstructionBanner>

      <div className="space-y-4 mb-8">
        {STEPS.map(({ icon: Icon, title, text }) => (
          <div key={title} className="bg-white border border-slate-200 rounded-lg p-5 flex gap-4">
            <div className="w-10 h-10 rounded-lg bg-[#E8743B]/10 border border-[#E8743B]/25 flex items-center justify-center shrink-0">
              <Icon className="w-5 h-5 text-[#E8743B]" />
            </div>
            <div>
              <h2 className="font-display font-bold text-lg text-[#1B2A4A]">{title}</h2>
              <p className="text-sm text-slate-600 mt-1">{text}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="bg-[#1B2A4A] text-white rounded-lg p-6 mb-8">
        <h2 className="font-display font-bold text-lg mb-3">Pricing cheat sheet (current rates)</h2>
        <ul className="text-sm space-y-1.5 text-white/85">
          <li>{fmtMoney(rates.manHour)} per man-hour</li>
          <li>Travel fee: {fmtMoney(rates.travelTruck)} with truck · {fmtMoney(rates.travelLabor)} labor-only</li>
          <li>First {rates.mileageAllowance} round-trip miles free, then {fmtMoneyCents(rates.overageRate)} per extra mile</li>
          <li>Stairs: {fmtMoney(rates.stairFlight)} per flight · Packing: {fmtMoney(rates.packingRate)} per man-hour</li>
          {activeItems.length > 0 && (
            <li data-testid="help-items-line">Big items: {activeItems.map((it) => `${it.name} ${fmtMoney(it.price)}`).join(" · ")}</li>
          )}
          <li>Final quote = subtotal + {rates.cushionPercent}% cushion, rounded up to the nearest {fmtMoney(rates.roundingIncrement)}</li>
          <li>Deposit = {rates.depositPercent}% of the final quote</li>
        </ul>
        <p className="text-xs text-white/60 mt-3">One clean final price — no ranges. Change these numbers on the Settings page.</p>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-5">
        <h2 className="font-display font-bold text-lg text-[#1B2A4A] mb-3">Quick tools</h2>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" className="gap-1.5" data-testid="help-meet-btn">
            <a href="https://meet.google.com/new" target="_blank" rel="noreferrer"><Video className="w-4 h-4" /> Start a video call</a>
          </Button>
          <Button asChild variant="outline" className="gap-1.5" data-testid="help-gmail-btn">
            <a href="https://mail.google.com/mail/?view=cm&fs=1" target="_blank" rel="noreferrer"><PhoneCall className="w-4 h-4" /> New Gmail message</a>
          </Button>
        </div>
        <p className="text-xs text-slate-500 mt-3">
          Privacy Mode (top right) blurs names, numbers, and dollar amounts on every page — turn it on before you share your screen.
        </p>
      </div>
    </div>
  );
}
