export const SCRIPT_SECTIONS = [
  {
    id: "opening",
    title: "Opening",
    blocks: [
      { type: "say", text: "Thanks for reaching out to Haul Yeah Moving. I can give you an accurate quote over the phone in about 5 minutes — I just need a few quick questions. Sound good?" },
      { type: "say", text: "When are you looking to move?", note: "(date drives crew availability and pricing)" },
      { type: "say", text: "Is this a local move within New Jersey, or farther?" },
    ],
  },
  {
    id: "scope",
    title: "Scope",
    blocks: [
      { type: "say", text: "How many bedrooms are you moving from?", note: "(Studio/1BR = 2-man, 3.5–4.5 hrs | 2BR = 3-man, 5–6.5 hrs | 3BR+ = 4-man, 5.5–8 hrs)" },
      { type: "say", text: "Lightly furnished, fully furnished, or in between?" },
      { type: "say", text: "Roughly how many boxes? Most stuff boxed already, or loose in closets?" },
      { type: "say", text: "Any large/heavy items — dining table, sectional, bed frame, TV, appliances?" },
      { type: "say", text: "Any furniture already broken down, or does it all need to come apart on move day?", note: "(disassembly = +30–60 min)" },
    ],
  },
  {
    id: "access",
    title: "Access",
    blocks: [
      { type: "sub", text: "Origin" },
      { type: "list", items: [
        "\u201cHouse, apartment, or townhouse?\u201d",
        "[Apt] \u201cWhat floor, elevator?\u201d · \u201cHow many flights?\u201d · \u201cStairs narrow or wide?\u201d · \u201cLobby/hallway/doors to know about?\u201d",
        "[House] \u201cFront steps or ground level?\u201d · \u201cHow far from truck to door — long/narrow carry?\u201d · \u201cAnything blocking the door — trees, cars, narrow driveway?\u201d",
      ] },
      { type: "sub", text: "Destination" },
      { type: "list", items: [
        "\u201cSame questions for the new place — floor, elevator, stairs?\u201d",
        "\u201cFurnished or empty?\u201d",
        "\u201cSomeone there to let us in? Parking restrictions?\u201d",
      ] },
    ],
  },
  {
    id: "special",
    title: "Special Items",
    blocks: [
      { type: "say", text: "Piano, pool table, safe, gym equipment, antiques, anything needing special handling?" },
      { type: "list", items: [
        "[Piano] \u201cUpright or grand?\u201d (upright $500 | grand $800) · \u201cHeirloom or standard?\u201d",
        "[Safe] \u201cHow heavy, what dimensions?\u201d (may need extra crew)",
        "[Gym] \u201cJust weights, or treadmill/squat rack/machinery?\u201d",
        "[Antiques/Art] \u201cAnything fragile or high-value to treat extra carefully?\u201d",
      ] },
    ],
  },
  {
    id: "distance",
    title: "Distance",
    blocks: [
      { type: "say", text: "Distance to the new place? Do you have the address?", note: "(pull Google Maps; 20 mi round-trip included, then $0.85/mile)" },
      { type: "say", text: "Need help packing, or everything packed?" },
      { type: "say", text: "Have boxes, or need us to bring them?" },
    ],
  },
  {
    id: "timing",
    title: "Timing",
    blocks: [
      { type: "list", items: [
        "\u201cWeekday or weekend?\u201d",
        "\u201cArrival time?\u201d",
        "\u201cHard deadline or flexible?\u201d",
        "\u201cAnything time-sensitive — move-in/out date?\u201d (rush / month-end = premium)",
      ] },
    ],
  },
  {
    id: "close",
    title: "Close (after calculating)",
    blocks: [
      { type: "say", text: "Here's what I'm seeing: [X]-man crew, about [Y] hours, starting price [Z]. That includes truck, fuel, equipment, and careful handling. Any questions?" },
      { type: "say", text: "The only thing that changes it is if the actual situation differs — stairs narrower than described, or traffic. This is a solid floor estimate." },
      { type: "say", text: "Our deposit is 25% to secure the date; the rest is due at completion. We accept [payment methods]." },
      { type: "say", text: "We'll confirm 48 hours before, and the crew texts you the morning of with an ETA. Sound good?" },
    ],
  },
];

export const SURCHARGE_CHECKLIST = {
  title: "Surcharge checklist (v1.0)",
  items: [
    "Stairs $85/flight (origin AND destination)",
    "Long carry >50 ft — $50–100",
    "Piano — upright $500 / grand $800",
    "Safe — $300–800",
    "Gym equipment — $150–300",
    "Disassembly — $75–150/piece",
    "Distance overage — (mi over 20 round-trip) × $0.85",
    "Travel — $125 ($75 labor-only)",
    "Cushion — 10%",
  ],
};

export const RED_FLAGS = {
  title: "Red flags (add crew or +1–2 hrs)",
  items: [
    "4+ flights, no elevator",
    "Ground floor + long carry",
    "Piano / heavy safe",
    "Destination tighter than origin",
    "Full packing",
    "Rush / month-end",
    "Tight turns / narrow halls",
    "Oversized sectional or antiques",
  ],
};

export const NO_ADDRESS_RESPONSE = {
  title: "No-address response",
  say: "No problem — give me the town and I'll estimate distance. Or I'll give you a base quote for a [size] move and fine-tune once you have the address. We can lock the date now and adjust the final price later.",
};
