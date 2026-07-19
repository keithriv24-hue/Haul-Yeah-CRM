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

## Current status / blockers
- AIRTABLE_API_KEY not yet added by user (secrets panel). All data routes return friendly 503 until then. Verify with GET /api/airtable/verify after key is added.
- Production deploy exists (moving-ops-1.emergent.host); production env needs APP_PASSWORD, JWT_SECRET, AIRTABLE_API_KEY set at deploy time.
- Full end-to-end testing-agent run over Airtable data flows is pending the key.

## Backlog (prioritized)
- P0: Verify Airtable connection once key is added; run full testing-agent pass over all data flows (leads CRUD, quote save, book-as-job, kanban drag, invoices mark-paid)
- P1: Change-password affordance / logout button; delete-record support where useful; lead detail view with full notes history
- P2: Google OAuth (Gmail/Calendar API) in v2; Square API deposits in v2; blog post publishing to a public site

## Credentials
See /app/memory/test_credentials.md (owner password, endpoints).
