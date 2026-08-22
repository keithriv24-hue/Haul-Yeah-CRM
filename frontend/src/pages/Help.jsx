import React, { useEffect, useState } from "react";
import { PhoneCall, Calculator, CreditCard, Truck, CheckCircle2, Star, Video } from "lucide-react";
import { InstructionBanner, PageTitle } from "@/components/Bits";
import { Button } from "@/components/ui/button";
import { fmtMoney } from "@/lib/format";
import { getRates } from "@/lib/api";
import { DEFAULT_RATES } from "@/lib/pricing";

const STEPS = [
  {
    icon: PhoneCall,
    title: "1. Respond in under 5 minutes",
    text: "When a lead comes in, call or text right away. The timer on each New lead card turns red after 5 minutes. Fast replies win the most jobs.",
  },
  {
    icon: Calculator,
    title: "2. Scope and quote the move",
    text: "Use the Quote button on the lead card or the Scope Calculator page. Pick a package or scope room by room, set distance and access, and read the range out loud. After a survey (or a received video), it becomes one firm price.",
  },
  {
    icon: CreditCard,
    title: "3. Send the deposit link",
    text: "Send a Square invoice for the 25% deposit shown by the calculator, or make a payment link in your Square dashboard and paste it in the Deposit window. The app saves it to the lead and writes the email for you.",
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
  const [rates, setRates] = useState(DEFAULT_RATES);
  useEffect(() => {
    getRates().then(setRates).catch(() => {});
  }, []);
  return (
    <div data-testid="help-page">
      <PageTitle title="Help" subtitle="From new lead to cash in the bank." />
      <InstructionBanner>How money moves through the business, step by step. Follow this every time.</InstructionBanner>

      <div className="space-y-4 mb-8">
        {STEPS.map(({ icon: Icon, title, text }) => (
          <div key={title} className="surface p-5 flex gap-4">
            <div className="w-10 h-10 rounded-lg bg-accent/10 border border-accent/25 flex items-center justify-center shrink-0">
              <Icon className="w-5 h-5 text-accent-ink" />
            </div>
            <div>
              <h2 className="label-eyebrow">{title}</h2>
              <p className="text-sm text-ink-2 mt-1">{text}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="bg-primary text-white rounded-lg p-6 mb-8" data-testid="help-pricing-cheatsheet">
        <h2 className="font-display font-bold text-lg mb-3">Pricing cheat sheet (v2.0 — current values)</h2>
        <ul className="text-sm space-y-1.5 text-white/85">
          <li>{fmtMoney(rates.manHourRate)} per man-hour, flat for every crew size</li>
          <li>Trip fee: {fmtMoney(rates.tripFeeTruck)} truck · {fmtMoney(rates.tripFeeLabor)} labor-only (covers the first {rates.mileageFreeMiles} miles)</li>
          <li>Mileage one-way: first {rates.mileageFreeMiles} mi included · every mile after that +{fmtMoney(rates.mileageRatePerMile)}/mi</li>
          <li>Stairs: {fmtMoney(rates.stairFlightFee)} per flight, pickup AND drop-off counted separately</li>
          <li>Long carry over 50 ft: {fmtMoney(rates.longCarryFee)} per location · Disassembly: {fmtMoney(rates.disassemblyFee)} per major piece</li>
          <li>Piano: upright {fmtMoney(rates.surchargeUprightPiano)} / grand {fmtMoney(rates.surchargeGrandPiano)} · Pool table (slate) {fmtMoney(rates.surchargePoolTable)}</li>
          <li>Safe: under 300 lb {fmtMoney(rates.surchargeSafeT1)} · 300–700 lb {fmtMoney(rates.surchargeSafeT2)} · over 700 lb {fmtMoney(rates.surchargeSafeT3)}</li>
          <li>Gym: treadmill/single machine {fmtMoney(rates.surchargeGymT1)} · rack/multi-station {fmtMoney(rates.surchargeGymT2)} · free weights billed in hours</li>
          <li>Floors: {fmtMoney(rates.floorTruck)} truck / {fmtMoney(rates.floorLabor)} labor-only · Minimums: {rates.minHoursTruck} hrs truck / {rates.minHoursLabor} hrs labor-only · 3BR+ has a hard {rates.hardFloorHours}-hour floor</li>
          <li>Final number rounds UP to the nearest {fmtMoney(rates.roundingIncrement)} · Deposit = {rates.depositPercent}% · balance on completion</li>
          <li>Service area: {rates.serviceStates} only — out-of-state moves are declined, full stop</li>
        </ul>
        <p className="text-xs text-white/60 mt-3">Quote a range on the call; one firm price after the survey. Change these numbers on the Settings page — the calculator follows instantly.</p>
      </div>

      <div className="surface p-5">
        <h2 className="label-eyebrow mb-3">Quick tools</h2>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" className="gap-1.5" data-testid="help-meet-btn">
            <a href="https://meet.google.com/new" target="_blank" rel="noreferrer"><Video className="w-4 h-4" /> Start a video call</a>
          </Button>
          <Button asChild variant="outline" className="gap-1.5" data-testid="help-gmail-btn">
            <a href="https://mail.google.com/mail/?view=cm&fs=1" target="_blank" rel="noreferrer"><PhoneCall className="w-4 h-4" /> New Gmail message</a>
          </Button>
        </div>
        <p className="text-xs text-faint mt-3">
          Privacy Mode (top right) blurs names, numbers, and dollar amounts on every page — turn it on before you share your screen.
        </p>
      </div>
    </div>
  );
}
