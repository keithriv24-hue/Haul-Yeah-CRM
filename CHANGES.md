# Haul Yeah CRM — frontend redesign

94 changed files. **Frontend only.** No backend file, no API call, no Airtable field ID,
no auth rule, no quote formula and no `data-testid` was changed.

## How to apply

Every file in this archive sits at its real path in the repo. Extract it over your
checkout of `Haul-Yeah-CRM` and the paths line up:

```
unzip haul-yeah-crm-redesign.zip -d /path/to/Haul-Yeah-CRM
```

A `.patch` of the same change set is included separately if you'd rather review it as a
diff (`git apply haul-yeah-frontend-redesign.patch`).

`frontend/package.json` and `package-lock.json` are untouched — the dependency list is
exactly what you had. No new dependencies were added.

---

## The design system

One direction, merged from the two concepts you picked: **V4's restraint and urgency
ladder, V5's thumb-first physicality and large figures.**

**Tokens live in one place.** `frontend/src/index.css` holds every colour, radius and
motion value as a CSS variable; `tailwind.config.js` maps each to a utility. Before this
there were three parallel colour systems — CSS variables, hardcoded hex (`#1B2A4A`,
`#E8743B`, `#F2F4F8`) sprinkled through 76 files, and raw `slate-*` classes. All 498 hex
literals and 731 palette classes are gone. Change a token now and the whole app follows.

**Orange means action, and only action.** `#E8743B` is untouched as your brand colour but
it is now reserved for the one thing to do on a panel. Status moved to `--success`,
`--warning`, `--destructive`, `--info`. Late timers are red because late is a state;
"Call Danielle" is orange because calling is the job.

**Type.** Kept Cabinet Grotesk + IBM Plex — they were already right. Page titles came down
from 36–48px to 22/26px, because the nav already told you where you are and a 48px
"Dashboard" was pushing real data below the fold on a phone. Every number now carries
tabular figures so columns line up.

**Motion.** Buttons scale to 0.975 on press, page content fades up on route change, the
mobile More sheet slides, skeletons shimmer, the late-lead clock ticks. All of it is
switched off under `prefers-reduced-motion`.

---

## The things that actually change how the app works to use

**Navigation.** The phone tab bar was 26 items in a horizontal scroll strip for the owner,
with Account, Refresh, Privacy and Log out crammed on the end. It is now four fixed
destinations per role plus a More sheet holding the rest, grouped, with the utility
controls at the bottom. The desktop sidebar is grouped into Today / Sales / Money / Team /
Business, and the empty header now carries a jump-to palette (⌘K / Ctrl+K) that searches
every page by name.

**The action ladder.** Lead and contact cards showed seven identical outline buttons, so
nothing was the next step. Now: one full-width accent band in the thumb zone, three
outline buttons, and the rest as quiet text links. The accent button is contextual and
follows the existing `nextStepHint()` logic, so the sentence and the button always agree —
a new lead says "Call Danielle", a quoted lead with a deposit says "Book as job".

**Tracking fields.** The lead card was printing `utm_source`, `utm_campaign`, `fbclid`,
`fbc`, `fbp` and `event_source_url` to your sales reps. They are still there, one tap
behind a "Show N tracking fields" toggle.

**Owner figures.** Eight identical KPI tiles became three labelled groups — Needs you now,
The money, Pipeline — with the money figures at 36px on a phone.

**Empty states.** "Who's on the clock" was rendering thirteen rows of "Not active right
now". It now shows who is working and puts the roster behind a toggle. The mobile job
calendar showed three characters of a job name in a 44px cell; it now shows one coloured
dot per job with a legend, and the full labels from tablet up.

---

## Verified

- **Production build passes** (`craco build`, exit 0). Lint: 0 errors.
- **No overlapping or clipped text** — audited programmatically on all 62
  route/role/viewport combinations at 390px and 1440px. 0 findings.
- **No horizontal overflow** on any screen at 390px.
- **WCAG AA contrast on every text style** — audited the same way. Went from 86 failing
  styles to 0.
- **24/24 functional checks pass**: role gating redirects, modals, quote modal, status
  dropdown, filter chips, search, More sheet, boss contacts, privacy mode masking, kanban
  cards, crew tab switching, sidebar nav, jump-to navigation — and no console errors in
  any role.

## One decision worth knowing about

White text on `#E8743B` is 3.09:1, which fails AA at button sizes. Rather than change your
orange, the accent button's text is now near-black on the same exact orange — 5.9:1. It
reads as confident rather than washed. If you prefer white text back, it is one token:
`--accent-foreground` in `index.css`. The trade is that you'd be shipping a primary button
that a lot of people can't read in sunlight.

## Pre-existing issue, not caused by this work

On the owner dashboard the Ops brain panel reports "Owed to you: $3,294" while the KPI
figure below reads "Owed to us: $0". They come from different sources and disagree. That
was true before the redesign and is a backend/data question, not a styling one.
