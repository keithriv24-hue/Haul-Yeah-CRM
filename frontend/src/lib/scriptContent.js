/* Haul Yeah Moving — Weekend Move Phone Script (matches Pricing Spec v2.0 and the
   Scope Calculator exactly). Warm, fast, confident. Never mention costs, crew pay,
   margin, or the cushion — owner-only. */

export const SCRIPT_SECTIONS = [
  {
    id: "opening",
    title: "Opening",
    blocks: [
      { type: "say", text: "Hi [NAME], this is [REP] with Haul Yeah Moving — you just sent us the form for your move. Thanks for that! I can get you an accurate price in about five minutes. Mind if I run through a few quick questions?", note: "(You're calling within 5 minutes — that speed IS the pitch. Smile; they can hear it.)" },
      { type: "say", text: "Great. I've got what you typed in the form right here — I'll just confirm it so your price is right the first time.", note: "(Treat every form answer as unconfirmed. People under-count stairs and forget the safe in the basement.)" },
    ],
  },
  {
    id: "scope",
    title: "Qualify — scope",
    blocks: [
      { type: "say", text: "First, the date — you put [DATE]. That's a Saturday/Sunday, right?", note: "(We move SATURDAYS and SUNDAYS only. Weekday date? Say: \"We're a weekend crew — that's how we keep prices sharp. Would the Saturday before or the Sunday after work?\")" },
      { type: "say", text: "And you're going from [TOWN] to [TOWN] — both here in New Jersey?", note: "(If pickup OR drop-off is out of state — NY, PA, DE, anywhere — decline warmly. No quote, no referral, no \"let me check.\" See the decline example below.)" },
      { type: "say", text: "How many bedrooms are we moving?", note: "(Packages: Studio/1BR = 2 crew ~3.5h · 2BR = 3 crew ~5.5h · 3BR = 4 crew ~6.5h with a hard 6-hour floor · 4BR+ = 4 crew ~8h. Tap the package in the calculator.)" },
      { type: "say", text: "Will everything be in boxes by move day, or would you like packing help?", note: "(Not fully packed adds about 2.5 hours. Set packing status in the calculator — don't guess.)" },
    ],
  },
  {
    id: "access",
    title: "Qualify — access",
    blocks: [
      { type: "sub", text: "Pickup" },
      { type: "list", items: [
        "\u201cWhat floor are you on — any stairs? How many flights?\u201d",
        "\u201cIs there an elevator we can use?\u201d",
        "\u201cHow far is the walk from your door to where the truck parks — more than 50 feet?\u201d",
      ] },
      { type: "sub", text: "Drop-off — people always forget this end" },
      { type: "list", items: [
        "\u201cSame questions for the new place — floor, stairs, elevator?\u201d",
        "\u201cAnd the walk from the truck to the door there?\u201d",
      ] },
      { type: "say", text: "Anything that needs to come apart — bed frames, a big sectional, a dining table?", note: "(Stairs count at pickup AND drop-off separately. Enter each end in the calculator.)" },
    ],
  },
  {
    id: "special",
    title: "Qualify — specialty items",
    blocks: [
      { type: "say", text: "Any piano, pool table, safe, or gym equipment?", note: "(Ask it ONCE, plainly. Then STOP TALKING and let them answer. Only drill in on what they name.)" },
      { type: "list", items: [
        "[Piano] \u201cUpright or grand?\u201d — grand needs photos before move day",
        "[Safe] \u201cRoughly how heavy — under 300 pounds, 300 to 700, or over 700?\u201d",
        "[Gym] \u201cA treadmill or single machine, or a rack / multi-station setup?\u201d — loose free weights just ride in the hours",
        "[Pool table] \u201cIs it slate?\u201d",
      ] },
    ],
  },
  {
    id: "quote",
    title: "Quote & confirm",
    blocks: [
      { type: "say", text: "Give me one second while I put that together…", note: "(Enter everything into the Scope Calculator NOW — package, rooms, distance, stairs, specialty items. Read the range off the screen.)" },
      { type: "say", text: "Alright [NAME], based on everything you told me, you're looking at [LOW] to [HIGH], all-in. That covers the crew, the truck, fuel, pads, and wrap — no surprise fees on the day." },
      { type: "say", text: "That price holds as long as move day matches what you described — same stairs, same items, same access. If something's different when we get there, we adjust it fairly and we tell you before we start.", note: "(Say this line on EVERY call. The range becomes one firm number after a survey or a video walkthrough.)" },
    ],
  },
  {
    id: "objections",
    title: "Objections — itemize, never discount",
    blocks: [
      { type: "say", text: "Totally fair question. Let me show you where that number comes from: the stairs are [$X] of it — that's three flights at both ends. The piano is [$Y]. The rest is a [N]-person crew for about [H] hours.", note: "(ITEMIZE from the calculator's line items. Never say cushion, cost, or margin.)" },
      { type: "say", text: "I can't cut the rate — that's what keeps our crews careful instead of fast and sloppy. What I CAN do is throw in the wardrobe boxes free, or give you an hour of packing help on us.", note: "(Hold the number. Offer a value-add, never a rate cut.)" },
    ],
  },
  {
    id: "close",
    title: "Close — deposit locks the date",
    blocks: [
      { type: "say", text: "Want me to lock in [DATE] for you? A 25% deposit — [DEPOSIT] — holds your crew, and weekends fill up fast." },
      { type: "say", text: "You get a full refund if you cancel within 72 hours. The balance is due when we finish — most folks do the balance by bank transfer, it's quick and there's no card fee.", note: "(Steer the big balance payment to ACH. Send the Square deposit link while you're still on the phone.)" },
    ],
  },
  {
    id: "notready",
    title: "If they're not ready",
    blocks: [
      { type: "say", text: "No problem at all — I'll text you this range right now so you have it in writing. Dates do go fast on weekends, so I'll check back with you [DAY]. Sound good?", note: "(Use the Text quote button, then set a follow-up. A texted range within 5 minutes beats a competitor's callback tomorrow.)" },
    ],
  },
];

export const SURCHARGE_CHECKLIST = {
  title: "Cheat sheet (Pricing v2.0)",
  items: [
    "Trip fee — $125 truck / $75 labor-only (covers first 20 miles)",
    "Mileage one-way — first 20 mi included · $0.85 per mile after that",
    "Stairs — $85 per flight, pickup AND drop-off counted separately",
    "Long carry over 50 ft — $100 per location",
    "Disassembly / reassembly — $100 per major piece",
    "Piano — upright $500 / grand $800 (photos for grand)",
    "Pool table (slate) — $600",
    "Safe — under 300 lb $200 / 300–700 lb $500 / over 700 lb $800",
    "Gym — treadmill or single machine $150 / rack or multi-station $300 / free weights in the hours",
    "Not fully packed — adds about 2.5 hours",
    "Minimums — $650 truck / $375 labor-only · 3 hrs truck / 2 hrs labor-only · 3BR+ hard 6-hour floor",
    "Deposit — 25% locks the date · 72-hour full-refund window · balance on completion (steer to ACH)",
  ],
};

export const RED_FLAGS = {
  title: "Red flags (add crew or +1–2 hrs)",
  items: [
    "4+ flights, no elevator",
    "Long carry at both ends",
    "Piano / heavy safe",
    "Destination tighter than origin",
    "Nothing packed a week out",
    "\u201cJust a few things in the garage\u201d",
    "Tight turns / narrow halls",
    "Oversized sectional or antiques",
  ],
};

export const NO_ADDRESS_RESPONSE = {
  title: "No-address response",
  say: "No problem — give me the two towns and I'll get the mileage. The first 20 miles are included; after that it's just 85 cents a mile one-way. We can lock your date now and tighten the number once you have the address.",
};

export const SCRIPT_EXAMPLES = {
  title: "Sample exchanges",
  examples: [
    {
      label: "Clean 2BR quote",
      lines: [
        "REP: \u201cTwo bedrooms, second floor with one flight, everything boxed, about 12 miles to Montclair — you're looking at [LOW] to [HIGH] all-in. That's a 3-person crew for around five and a half hours.\u201d",
        "CUSTOMER: \u201cOkay, that works.\u201d",
        "REP: \u201cWant me to lock the date? The deposit is [DEPOSIT] and you're fully refundable for 72 hours.\u201d",
      ],
    },
    {
      label: "Stairs objection — itemize, don't discount",
      lines: [
        "CUSTOMER: \u201cThat's more than the other guys quoted.\u201d",
        "REP: \u201cI hear you. Here's the build: $510 of that is the stairs — three flights at your place and three at the new one, $85 a flight. Take the stairs out and we're right where they are. The difference is we showed you the number before move day, not after.\u201d",
      ],
    },
    {
      label: "Out-of-state decline — warm, firm",
      lines: [
        "CUSTOMER: \u201cWe're moving to Philly.\u201d",
        "REP: \u201cCongrats on the move! I wish we could take it — we're New Jersey only, so a Pennsylvania drop-off is outside what we're licensed for. I'd rather tell you straight than waste your week. Best of luck with it!\u201d",
      ],
    },
  ],
};
