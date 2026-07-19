# PRD — Haul Yeah Moving Internal CRM

## Original problem statement
Full-stack internal CRM PWA for Haul Yeah Moving (weekend moving company, North & Central NJ), used by owner Keith on desktop and phone. The database is an EXISTING Airtable base (`appFAHTRNrRckuxI8`) — all reads/writes proxied through the FastAPI backend using field IDs, token in `AIRTABLE_API_KEY` (backend only, never frontend). 9 views + Help, global Privacy Mode, quote calculator with locked pricing, speed-to-lead timers, deposit-link workflow (no Square API), Gmail/Calendar deep links only, sixth-grade-level copy with instruction banners, labeled buttons (icon + word).

## Architecture
- Backend: FastAPI proxy at `/api` → Airtable REST (httpx, 5 req/sec rate limiter, `returnFieldsByFieldId=true`, typecast on writes, friendly error normalization). No Mongo shadow copies — Airtable is the single source of truth.
- Frontend: React (CRA + craco), shadcn/ui, Recharts, sonner toasts, native HTML5 drag-and-drop kanban. Basic PWA (manifest + icons, installable).
- Auth: three shared-password roles — owner (`APP_PASSWORD`, full access), sales (`SALES_PASSWORD`, Leads + Quote Calculator only), employee (`EMPLOYEE_PASSWORD`, Projects without money fields + To-Do only). 30-day JWT with role claim in localStorage; backend enforces role route access and strips Quote/Deposit/Final Revenue from employee project reads+writes; crew cost rates ($28/$24) backend-only, owner project responses carry computed `internal: {crew_cost, margin}`. 5 wrong tries/IP = 15-min lockout.
- Brand: navy #1B2A4A, orange #E8743B, Cabinet Grotesk + IBM Plex Sans.

## User personas
- Keith (owner): runs the whole lead-to-cash flow on desktop and phone.
- Capital partner: sees Partner View only (financial summary, no customer details).

## Core requirements (static)
- Airtable field IDs only; optimistic writes with toast + rollback; quotes always as ranges with "Final price confirmed by phone"; crew cost ($28/$24) internal-only on Project detail; privacy mode masks all PII and dollar figures; locked pricing v1.0 ($65/man-hr, travel $125/$75, stairs $85, piano $500/$800, 10% cushion, 25% deposit).

## Implemented (June 2026)
- [x] Backend Airtable proxy: /api/health, /api/airtable/verify, GET/POST/PATCH /api/tables/{table} for 7 tables, rate limiter, pagination, error normalization
- [x] All 10 views: Dashboard (7 KPIs, doughnut, money bar chart, upcoming jobs, high-priority tasks), Leads (card grid, live age timers red >5 min, status dropdowns, filter chips, Call/Email/Quote/Deposit/Book buttons, new-lead modal), Contacts, Projects (inline edits + internal margin), To-Do kanban (drag-and-drop), Blog pipeline, Invoices (KPIs + mark-paid), Subscriptions (burn + annualized), Partner View, Help
- [x] Quote calculator modal (exact locked formula), deposit-link modal (Square link → notes + mailto), book-as-job (creates linked Project, lead → Booked)
- [x] Privacy Mode (blur, localStorage), live-from-Airtable indicator + Refresh, key-missing banner
- [x] PWA manifest + icons, mobile bottom tab bar, desktop sidebar
- [x] Owner password auth (APP_PASSWORD + 30-day JWT, per-device persistence, brute-force lockout) — 17 pytest cases pass; UI flow verified in browser
- [x] Log out button in header
- [x] Three-role system (owner / sales / employee): role-matched login, role chip in header, role-filtered nav + routes, backend route & field enforcement, standalone mobile-first Quote Calculator page for sales (with home-size pre-fill + coaching line), Add-note + specialty items on lead cards, employee Projects without money — 25 pytest cases + testing-agent browser pass (iteration_1.json)
- [x] Owner Settings page: editable calculator rates (man-hour, travel ×2, stairs, pianos) stored in MongoDB, GET /api/settings/rates (all roles) + PUT (owner only), "Save preferences" updates every account; QuoteModal/Calculator/Help all use dynamic rates (10% cushion + 25% deposit stay fixed) — verified via curl + browser (rate change propagated to sales calculator: $1,175–$1,293/$323)
- [x] Crew account: Privacy toggle removed (and blur never applies to employee role)
- [x] Sales "Script" page: 6-step call script with say-this boxes + objection handling, sales nav only
- [x] Owner account switcher: header dropdown (Owner/Sales/Crew view) swaps role tokens via POST /api/auth/switch-role with signed owner_switch claim; real sales/crew tokens get 403; data cache cleared on switch — 29 pytest + browser verified
- [x] Calendar section on Projects page (owner: all non-cancelled jobs; crew: Scheduled + In Progress only) — month grid with job pills, month nav
- [x] Google Calendar sync: OAuth connect (owner only, /api/oauth/calendar/login|callback|status|disconnect), POST /api/calendar/sync pushes all non-cancelled jobs as all-day events with dedup map in Mongo; needs GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/PUBLIC_BASE_URL env — 34 pytest + browser verified (awaiting user's Google credentials)
- [x] Tally form fields on lead cards: GET /api/schema/{table} fetches live field names via Airtable Meta API (10-min cache, role-filtered); lead cards auto-render every unmapped field (Stairs, Elevators, etc.) with real labels — requires token scope schema.bases:read — 37 pytest passing
- [x] Gmail deep links complete (June 2026): Contacts already had compose + "Mail log" (Gmail search); added matching "Mail log" button to every lead card (searches by email, falls back to name). Browser-verified button pattern on Contacts; Leads verified in code (table empty pending Airtable key)
- [x] Quote rounding: computeQuote low & high now round to nearest $50 (deposit stays 25% of rounded high) — browser-verified ($975+$125 → $1,100–$1,200, deposit $300)
- [x] Login password show/hide eye toggle (data-testid login-toggle-password-btn) — browser-verified
- [x] Re-verified June 2026: global Privacy Mode (blur + localStorage hy_privacy) and To-Do kanban drag-and-drop implementations intact
- [x] Lead Detail page (/leads/:id, owner + sales): full-page view with move details, extra Tally fields, quote box, full action set, and complete notes history timeline (newest first); lead card names link to it (data-testid lead-open-link)
- [x] Delete records: DELETE /api/tables/{table}/{id} (owner-only, 403 otherwise — 34 pytest passing); Delete buttons with confirm dialog (ConfirmDeleteButton in Bits.jsx) on lead cards, contact cards, and lead detail; optimistic removal with rollback in AppContext.deleteRecord
- [x] Text quote button on lead cards + detail: sms: deep link drafting "Hi {first}... quote $low–$high... $deposit locks your date" (low derived via lowFromHigh = round50(high/1.1))
- [x] All Gmail links (compose + search) now open as contact@haulyeahmoves.com (authuser param / /u/{email}/ path) — SENDER_EMAIL in format.js
- [x] Inline lead editing: Edit button on lead detail "Move details" card unlocks name/phone/email/move date/home size/from/to with Save+Cancel (writes via PATCH)
- [x] Follow-up reminders: red "quiet N days — call them back" badge (FollowUpBadge) on lead cards + detail for Quoted leads with no deposit and no note activity for 2+ days (lastTouch parses dates from notes, falls back to createdTime); nextStepHint updated too
- [x] Review request text: owner-only "Ask for review" button on Completed jobs (Projects) drafting an SMS to the linked lead's phone; Google review link stored via GET/PUT /api/settings/business (Mongo, PUT owner-only) with a Settings box — 36 pytest + browser-verified persistence
- [x] Call-backs due Dashboard KPI (kpi-callbacks, red alert when > 0) counting needsFollowUp leads — browser-verified
- [x] Review tracking: clicking "Ask for review" appends "Review asked {date}." to project notes; button flips to emerald "Review asked ✓" (regex on notes), tapping again re-texts
- [x] Callback list: Call-backs KPI is a Link to /leads?filter=Call back; Leads filter now lives in the URL (useSearchParams) with a red "Call back (n)" chip filtering needsFollowUp leads — browser-verified navigation + chip selection
- [x] Weekly recap: "Weekly recap" button on Dashboard opens Gmail compose (from contact@haulyeahmoves.com) with a plain-text summary: last weekend's jobs (Sat+Sun by jobDate) + revenue, collected, owed, open leads + pipeline, call-backs due — browser-verified body content
- [x] Header cleanup: role switcher/chip, Privacy, Refresh, Log out moved off the header — desktop: bottom of sidebar (same testids); mobile: bottom tab bar after a divider (tab-account-select, tab-refresh-btn, tab-privacy-btn, tab-logout-btn). Header keeps live indicator + New Meet — browser-verified both viewports
- [x] Brand logo (user-supplied PNG): login card, desktop sidebar, mobile header, PWA icons (icon-192/512, apple-touch-icon, favicon regenerated from logo with orange bg padding) — browser-verified
- [x] Square Invoices (SANDBOX): POST /api/square/invoice (owner-only) chains customer→order→invoice→publish via Square REST (httpx, Square-Version 2024-08-21); GET /api/square/status; env vars SQUARE_ACCESS_TOKEN/SQUARE_LOCATION_ID/SQUARE_ENVIRONMENT in backend/.env. SquareInvoiceModal ("Invoice" button on owner lead cards + detail): amount picker (25% deposit / full quote / custom), secondary AlertDialog confirmation before send, sandbox test-mode banner, success panel with pay link, auto note appended to lead. Live sandbox invoice #000001 created via curl; 39 pytest passing. TO GO LIVE: swap production token+location and set SQUARE_ENVIRONMENT=production
- [x] Invoice status sync: invoices persisted in Mongo (square_invoices: lead_id, invoice_id, number, amount, status, public_url); GET /api/square/invoices (owner-only) refreshes non-terminal statuses from Square (60s throttle per invoice); InvoiceBadge (paid=emerald, waiting=amber, canceled=slate, links to pay page) on lead cards + detail Quote box; refreshes after each send — curl-verified with sandbox invoice #000004
- NOTE: user's supplied Square key confirmed SANDBOX-ONLY (401 on production host, location "Default Test Account"). Awaiting real production token+location to flip SQUARE_ENVIRONMENT=production
- [x] Square LIVE (production): user supplied production token + location L15944ZHWTJ8R ("Haul Yeah Moving", ACTIVE — verified via /v2/locations); SQUARE_ENVIRONMENT=production; sandbox invoice docs cleared from Mongo. Real invoices now send to real customers
- [x] Paid auto-update: when status refresh finds an invoice newly PAID, backend PATCHes the lead's Deposit Paid checkbox (fld7BsZG5A6S1oh7Z) in Airtable (once per invoice via deposit_synced flag; 404s throttle checked_at); frontend loadSquareInvoices also flips depositPaid locally for synced PAID leads — 39 pytest passing
- [x] Money-landed banner + cha-ching: AppContext polls /api/square/invoices every 60s (owner only); newly-PAID invoices (tracked in localStorage hy_paid_seen, baseline-inits silently on first run) trigger playChaChing (/chaching.wav — synthesized coin+bell), a toast, and a dismissible emerald "Money landed!" banner on Dashboard — browser-verified via seeded Mongo doc (then cleaned)
- [x] Win-back texts: "Win back" sms button (winBackSmsBody) on Lost/Cold lead cards + detail; stamps "Win-back text sent {date}." note on tap
- [x] Payment nudge texts: "Nudge pay" sms button on lead cards + detail when latest Square invoice is UNPAID/PARTIALLY_PAID/SCHEDULED (includes pay link, stamps note); Invoices page rows (Sent/Overdue) get "Text nudge" with phone looked up by customer-name match in Contacts→Leads (disabled + tooltip if no match) — pages render clean, sms bodies in format.js
- [x] Crew day sheet: /day-sheet route (owner + employee) with date picker (defaults today), Print button (window.print), jobs for that date (non-cancelled) showing from→to, truck, crew, est hours, blank start-time line, notes; no money on the sheet. Layout chrome (aside/header/bottom nav/padding) print:hidden — print-mode browser-verified; "Day sheet" button on Projects page header
- [x] Tappable address maps: mapsLink() (google.com/maps/dir destination) on day-sheet From/To rows (day-sheet-from-link/day-sheet-to-link, plain text when printed) and Projects job-card From/To addresses (project-from-map-link/project-to-map-link) — pages render clean

## Current status / blockers
- AIRTABLE_API_KEY not yet added by user (secrets panel). All data routes return friendly 503 until then. Verify with GET /api/airtable/verify after key is added.
- Production deploy exists (moving-ops-1.emergent.host); production env needs APP_PASSWORD, JWT_SECRET, AIRTABLE_API_KEY set at deploy time.
- Full end-to-end testing-agent run over Airtable data flows is pending the key.

## Backlog (prioritized)
- P0: Verify Airtable connection once key is added; run full testing-agent pass over all data flows (leads CRUD incl. delete + detail page, quote save, text-quote link, book-as-job, kanban drag, invoices mark-paid)
- P1: Lead detail polish (edit fields inline); delete support for other tables if useful
- P2: Square API deposits in v2; blog post publishing to a public site

## Credentials
See /app/memory/test_credentials.md (owner password, endpoints).

## Session: July 19, 2026 — Airtable Job Time Log + Work Calendar + Trucks (COMPLETE)
- Crew module FRONTEND completed & tested (iteration_2: 100% UI pass): new email/username login (owner = HaulYeahOwner, legacy shared passwords as backup), forced first-login password change, crew mobile view (My Jobs status workflow + photos, GPS Time Clock w/ consent, Days Off), owner Crew page (Team/Schedule/Time/Map/Report), notifications bell.
- Airtable "Job Time Log" auto-mirror (tbl6mv59JAOwUyI4Y, all field IDs per user spec, typecast:true, ET timestamps, Entry "Job – M/D/YY"): first clock-in creates ONE record (dedupe via stored record id + {Entry} formula search), later events PATCH (Clock In never overwritten), last clock-out/Complete writes Clock Out + Delay Factors + Notes, Projects link via project_id or name+date match. Never deletes Airtable records. Reliability: at-least-once queue (assignment.timelog_sync.status=pending → background sync → 90s retry loop); owner sync badge on Dashboard; GET /api/timelog/status.
- Owner Dashboard "Work calendar" (owner-only): month grid w/ dots, tap day → job cards (crew DRIVER/HELPER labels, job size, crew size, truck name+plate, delay chips, notes, actual hours first-in→last-out). GET /api/calendar/jobs?month=YYYY-MM.
- Trucks: name + license plate + hard remove w/ confirm (history preserved via truck_name snapshot on assignments); seeded Truck 1-5; assignment dropdown = active/existing trucks only.
- Assignment modal: Job Size dropdown (6 options) auto-prefilled from linked lead home size; crew Finish dialog: delay-factor checkboxes ("None" exclusive).
- Fixes: crew-view 403 console noise (role-guarded AppContext fetches), Days Off red contrast, labor report field-ID param, pending_jobs now include assignment_id, loadTable short-circuits when Airtable key known-missing.
- Testing: iteration_3 backend 13/13 new-feature tests + regression pass; delay-factor UI bug found by tester → fixed → self-verified E2E (checkboxes render, factors stored, calendar shows chips).
- Deployment: deployment_agent scan PASS. AIRTABLE_API_KEY still EMPTY in preview (user asleep, will provide). Production deploy requires user to click Deploy in Emergent UI — agent cannot deploy.

### Pending for user (morning)
1. Click Deploy in Emergent UI to push live (build checks passed).
2. Add Airtable personal access token as AIRTABLE_API_KEY (preview secrets panel AND ensure production has a token with read/write scope to base appFAHTRNrRckuxI8 incl. Job Time Log table). Queued punches auto-flush once key works.
3. Note: owner login username is now HaulYeahOwner (old password-only login still works as backup).

## Session: July 19, 2026 (later) — Update overlay + live crew status
- UpdateOverlay.jsx (App root, works pre-login): polls /api/health every 25s; 2 consecutive network/502/503/504 fails → full-screen branded "The website is updating" overlay; polls every 5s while down; auto window.location.reload() on recovery (loads fresh deployed bundle). Offline variant message via navigator.onLine.
- "Who's on the clock" card on owner Dashboard (CrewStatusCard.jsx + GET /api/team/status, owner-only): every active crew member with green pulsing "On the clock since X · job" or gray "Not active right now"; polls 30s. Verified live flip on clock-in/out via curl + screenshot.
- Both features verified self-test (curl + screenshots incl. real backend-stop overlay test). User must REDEPLOY to get these on haulyeahadmin.com. AIRTABLE_API_KEY still not provided (asked twice).
