# Haul Yeah CRM — 56-Problem QA Audit (repair, do NOT rebuild)

Delivered by the Owner as a 9-prompt series. Each problem is eventually labeled:
FIXED + tested · ALREADY FIXED + verified · REQUIRES OWNER DECISION · CANNOT SAFELY TEST + reason.

Strict protocol: one phase at a time, test, present evidence, get explicit "yes" before the next.

## Master checklist status
- Problem #1 (exposed credentials / hidden accounts): FIXED + tested — 2026-06 (this phase).
- Problem #7 (owner "View As" security): FIXED + tested — 2026-06 (this phase).
- Problems #2, #24, #25 (Airtable field-name/ID normalization): FIXED + tested — 2026-10-02.
  ONE normalization layer in server.py: `_schema_fields` (shared schema fetch/cache) →
  `_table_field_index`/`normalize_write_fields` (coerce any incoming write to canonical field-ID
  keys; best-effort pass-through if schema unreadable) and `_airtable_write_body` (every write now
  sends `returnFieldsByFieldId:true`+`typecast`). create_record/update_record normalize → strip blocked
  (by ID) → write → role-filter the id-keyed save response. Fixes mixed ID/name representation in app
  state, permission-stripping on save responses, and automation reads (Booked alert name, failed-audit
  → Nonconformance). Regression: tests/test_partc_airtable_norm.py (7/7).
- Prompts 2–6 (canonical job, payment ledger, reporting/commissions/Meta, assignment system,
  calculator snapshot): NOT STARTED. Order: Prompt 2 → 3 → 4 → 5 → 6.

---

## PROMPT 1 OF 9 — SECURITY + AIRTABLE DATA INTEGRITY
Rules: Do not rebuild. Do not redesign working features. Do not remove working functionality.
Do not destructively alter production records without Owner approval. Do not send real customer
texts/invoices/emails/refunds/payments/Meta test events. Do not silently change pricing. Backend
permissions must be authoritative. Fix root causes. Production migrations backward-compatible. Add
regression tests. Do not deploy partial architecture. If an irreversible production action is
needed, STOP and ask. Do not trust old line numbers — inspect current main.

Before changing code: pull main, record commit, compare to Sept 27 QA findings, check if already
fixed, reproduce safely, don't reintroduce old behavior.

### PART A — Problem #1 Exposed credentials / hidden accounts
- Remove passwords/secrets/credentials from tracked files.
- Remove hardcoded hidden/backdoor account creation.
- Every legitimate user must appear in Team Admin.
- Remove automatic startup recreation of test accounts.
- Remove credential/hash backup files from the repo.
- Move required secrets to env/secrets.
- Add practical secret scanning.
- Verify prod auth no longer depends on old hardcoded creds.
- Do NOT rewrite git history / force-push without Owner approval.
- Produce rotation instructions for every exposed credential.

### PART B — Problem #7 Owner "View As" security
A View As (Sales/Quality/Manager/other) session must: remain associated with the authenticated
owner; be short-lived; never be an independent long-lived auth session; never let the impersonated
role request owner access; only the original authenticated owner session may return to owner.
Enforce on backend (frontend hiding insufficient). Tests for: switched owner sessions, direct API
attempts to regain owner, token/session expiration, unauthorized role changes.

### PART C — Airtable data corruption root cause (Problems #2, #24, #25)
One consistent Airtable record representation. Don't let one request return ID-keyed fields and
another name-keyed when consumers expect one format. Ensure: editing one field doesn't erase
untouched fields; edit forms don't submit blanks for unchanged fields; PATCH partial updates
preferred; permission filtering works whether incoming data used field IDs or names; outgoing save
responses still pass role filtering; automation can read the saved record; customer names remain
available; alert names remain available; final revenue/outcome lookup works; failed Quality audit
correctly creates its Nonconformance record; server-side validation works regardless of field rep.
Create ONE normalization layer/service (not scattered conversions).

Required tests: response normalization, partial updates, untouched-field preservation, role
filtering after saves, direct API permission bypass, switched owner sessions, hidden-account
removal, failed Quality audit → NC creation. Run backend/frontend/permission/integration tests +
build; resolve failures (don't skip).

DO NOT start canonical job/payment architecture or optimizer changes in this prompt.

Report back: commit tested, problems fixed, already fixed, files changed, owner security actions,
tests added, tests run + results, anything unsafe to test in prod, confirmation that login/role
routing/role restrictions still work.

---

## PROMPT 2 OF 9 — ONE CANONICAL JOB + SAFE MIGRATION
Objective: ONE canonical identity per job. Canonical business/job record = the Airtable Project.
Every related record references it via `project_record_id` (Mongo job, Dispatch assignment, crew
assignment, payment, quote, customer portal session, outcome, Quality record, compliance record).
NO fuzzy matching as an authoritative relationship (no customer name, name prefix, date+crew,
date+customer, same-day guesses, first N records).
Addresses Problems #3, #6, #8, #9, #10, #11, #12, #23, #26, #31, #36, #37.

- ONE authoritative Project-creation service (every caller uses it): stable relationship check
  before create, return existing when appropriate, idempotent, one lead ≠ multiple Projects,
  webhook/retry safe, all new linked records get project_record_id.
- Booking definition: Booked = required deposit received OR explicit authorized Owner override. A
  salesperson clicking "Book as job" must not falsely make an unpaid lead look financially booked.
  On real deposit satisfied: update booking state, create/link Project, associate id, update funnel.
- Job edit propagation: date change → Project/Dispatch/crew/reminders/portal/scheduling;
  cancellation → stop Dispatch/upcoming crew/reminders/portal/workflows (preserve financial+audit);
  price change → authoritative total/balance/portal/commission/reporting (don't destroy committed
  quote); address change → Project/Dispatch/crew/portal.
- Migration/backfill: existing prod records may lack project_record_id. Build a migration/report
  across Project/Mongo job/Dispatch/payments/lead/quote; deterministic → backfill; ambiguous → DO
  NOT GUESS, create Owner review queue. Preserve legacy read compat; don't remove fuzzy fallback
  until replacement + safe migration exist, then remove authoritative fuzzy matching.
- Completed-job editing: require reason, record before/after/user/timestamp.
Tests: 1 lead→1 Project; repeat create→same; deposit retry→no dup; date/address/price/cancel
propagation; ambiguous migration→Owner review; project_record_id consistent across linked records.
DO NOT redesign optimizer / finish Square ledger / change pricing yet.

---

## PROMPT 3 OF 9 — ONE PAYMENT LEDGER + SQUARE + ONE MONEY ENGINE
Verify project_record_id architecture works first. Completes Problems #3, #6, #26, #31, #55 +
financial portions.

- ONE canonical payment ledger linked to project_record_id. Supports Square, deposits, remaining
  balance, custom/partial, cash, Zelle, ACH, authorized manual entry, refunds, adjustments. Entry:
  project_record_id, external txn id (when applicable), method, amount, type, status, timestamp,
  source, entered_by (manual), refund relationship. Refunds = negative/reversing activity.
- Canonical calcs: collected = sum(valid ledger); balance_due = authoritative job total − collected;
  paid_in_full = collected >= authoritative total. Never mark paid-in-full just because an invoice
  is named balance/remaining/custom/final.
- Square invoices: deposit, remaining balance (server-calculated), authorized partial/custom.
  Remaining balance computed server-side (e.g. $2000 total − $500 deposit → $1500).
- Square webhook: store ACTUAL amount received (e.g. $50 custom payment increases collected by $50,
  decreases balance by $50, paid_in_full stays false).
- Refunds: Square refund updates ledger/collected/balance/paid status/commissions/dashboard/booking
  state/owner alert.
- Cash/Zelle/ACH: owner-authorized manual entry on the SAME ledger + reporting pipeline (not a
  disconnected subsystem); record who/method/amount/timestamp/project/note; permissioned.
- Square idempotency (Problem #55): reuse Square customers; deterministic idempotency keys
  (project/lead + purpose + amount + operation/version); retry never duplicates customer/invoice/charge.
- ONE money engine: centralized backend financial functions; all consumers derive from same source.
  Job total (active = committed total; completed = Final Revenue per existing logic); collected =
  ledger; balance = total − collected; labor (architecture allows later approved punches × stored
  historical rate snapshot); margin = revenue − recognized actual costs. Migrate Dashboard, Partner
  View, Job Detail, Marketing, customer portal, commissions, financial reports.
Tests: partial payments, refund, cash parity, server-calculated remaining balance, idempotency,
cross-screen money consistency. No real invoices/payments in QA.

---

## PROMPT 4 OF 9 — REPORTING + COMMISSIONS + META TRACKING
Continue from completed canonical job + payment-ledger architecture (Prompts 2+3). Do not rebuild.
### PART A — Financial reporting consistency (Problems #6, #23)
Dashboard, Partner View, Job Detail, Marketing, customer portal, financial reports ALL use the same
canonical job + payment + financial services. One job must not show multiple versions of revenue /
collected / owed / labor / margin. Add cross-screen regression tests: for the SAME test project,
Job Detail / Dashboard / Partner / Marketing revenue all agree; also compare collected / owed /
labor (where implemented) / margin. No duplicated formulas in frontend pages.
### PART B — Commissions (Problem #4)
Attribution recorded by the system. Sales users must NOT create their own commission base, set
arbitrary quote revenue for commission, or reassign attribution without authorization. Commission
calc depends on: system-recorded attribution + correct tier/rate + ACTUAL collected revenue from the
canonical ledger. Refunded money reduces applicable commissions. Only authorized Owner controls may
manually alter attribution; every manual change logs old/new/person/reason/timestamp. Test
permissions through DIRECT APIs, not just UI.
### PART C — Meta tracking (Problem #5)
ONE authoritative Meta sender per business event. Prevent duplicate events from BOTH Airtable
automation AND backend. One event-ID/dedup strategy. QA/test records must NOT send real conversion
events. Clear semantics: Lead = new marketing lead; Schedule = scheduled/survey conversion if
tracked; Purchase/Booking = documented conversion. Don't double-count; don't report full move value
and a deposit as the same purchase event unless they're intentionally separate documented
conversions. Before disabling any Airtable Meta automation: confirm backend coverage, verify delivery
architecture, preserve legitimate production tracking. (Do not send real Meta test conversions.)
Report: reporting consumers migrated, before/after consistency example, commission architecture, Meta
architecture, Airtable automations that may eventually be disabled, tests/results, owner action.

## PROMPT 5 OF 9 — ONE ASSIGNMENT SYSTEM + DISPATCH/CREW SYNC + NO-SHOW + TIMEZONE + FLEET
Continue from completed canonical job architecture; everything uses project_record_id; no fuzzy
matching reintroduced. Fixes #8, #10, #17, #29, #33, #42 + remaining crew/Dispatch sync defects.
- ONE assignment system: authoritative crew + truck assignments. Jobs, Job Detail, Dispatch, Crew
  Today, My Jobs all show the SAME actual assignment. "Assign Crew" on Job Detail modifies the
  canonical job assignment; an assignment made anywhere appears everywhere; no independent conflicting
  states.
- Crew Lead security: remove/disable legacy Helper bypass of Crew Lead restrictions; only an
  authorized Crew Lead flow may transition operational move states (where that's the rule); truck
  safety blocks apply regardless of endpoint. Test backend authorization directly.
- Wrong-customer communication defect: ANY customer communication resolves job/customer via
  project_record_id — NEVER fall back to same-date+same-crew / nearby-job / name-fragment. If the
  link is missing: DO NOT SEND, log the failure, alert Owner/Manager. Never guess the recipient.
- No-show scan: viewing an old Dispatch date must NEVER mutate records. Move no-show detection into
  the scheduled/background workflow. Opening a historical Dispatch screen must not mark no-shows.
- Timezones: business tz America/New_York. Store consistently, convert explicitly; lateness/no-show
  use Eastern business time.
- Fleet status: a truck In Shop / Unavailable / Out of Service is not normally assignable; Owner
  override only where permitted, logged; preserve double-booking protection.
Tests: assign once → identical in all 5 screens; In Shop blocks normal assignment; Helper Crew-Lead
transition rejected by backend; missing customer/project link → message not sent; historical Dispatch
open → no mutation; Eastern day-boundary; double-booking still protected. No real SMS in QA.

## PROMPT 6 OF 9 — CALCULATOR: SERVER-AUTHORITATIVE PRICING + IMMUTABLE SNAPSHOT + HANDOFF
Continue from repaired job/assignment/money foundations. Do NOT rebuild/redesign the optimizer or
auto-apply recommendations; preserve calibration history/versioning. Fixes #13,#14,#15,#19,#20,#21,
#30,#44,#54,#56. If a new dollar amount/rate is required → STOP and present an Owner Decision (never
invent a price or ship loss-making logic).
- Server authoritative for COMMITTED pricing: browser may preview; backend recomputes committed
  pricing from submitted scope inputs + current approved pricing config. Never trust browser
  finalTotal. Reject invalid inputs (negative qty/miles/prices, unauthorized manual values,
  unsupported out-of-state where hard guard applies). Owner-authorized overrides log
  user/timestamp/original/override/reason.
- Committed quote snapshot (immutable): scope inputs, itemized pricing, crew rec, truck rec, est
  hours, man-hours, pricing/settings snapshot, calibration/version ID, surveyor, quoter, timestamp,
  override info. Reopening an old committed quote must NOT reprice with today's settings.
- Quote → Project hand-off: transfer price, crew, hours, man-hours, trucks, itemized lines,
  inventory/scope, settings snapshot, pricing version. Stop reading obsolete quote formats.
- Quote PDF/customer output: itemized from the committed quote; don't fall back to a single-line
  quote when itemized detail exists.
- Heavy specialty items (700lb safe, grand piano, slate pool table, etc.): must not produce an
  unsafe low crew count; crew safety floors consistent for predefined AND custom inventory; don't
  silently lower specialty surcharges due to an unrelated % cap unless business rules require it. If
  a dollar rate must change → STOP, show current rule / proposed rule / before-after example.
- Quick-start packages are minimum floors — larger real inventory wins (more crew/hours/trucks).
- Access/stairs/drive-time modeled via existing settings; do NOT invent a new charge (Owner Decision
  if a new rate is truly required).
- Overrides below safe/model recommendation require Owner/authorized pricing role + reason +
  old/new + audit.
- Very large jobs: don't show a 23-hour move as a normal one-day job; above configured workable
  duration → split multi-day if supported ELSE return Manual/Custom Quote Required.
- Restricted customer picker: survey/calculator-authorized crew can attach a scope to the correct
  customer with a restricted lookup (name/town/move date only — no unnecessary PII), no unrestricted
  Sales access.
- Mobile ~390px: quantity controls / primary actions / critical buttons ~44px tap targets where
  practical; don't bloat desktop controls.
Tests: quote immutability (commit → change settings → reopen unchanged); tampered client total
rejected/recomputed; packages (real inventory above package increases requirements); heavy item
safety (predefined + custom); large-job routing; unauthorized override blocked; mobile 390/tablet/
desktop; JS/Python calculator consistency intact.

## PROMPTS 7–9 — NOT YET PROVIDED
Still pending from the Owner (likely outcomes/compliance, cron jobs, payroll, final 56-problem
report). Ask for 7–9 when Prompt 6 nears completion.

## DEPENDENCY / SEQUENCING NOTE (as of 2026-10-02)
Done: Phase 1 Problems #1 + #7. NOT done: Phase 1 Part C (Airtable normalization #2/#24/#25),
Prompt 2 (canonical job + project_record_id backfill + one project-creation service), Prompt 3 (one
payment ledger + money engine + Square idempotency). Prompts 4/5/6 DEPEND on 2 and 3 and must follow
them. Current code: project_record_id only lightly used (day-sheet sync); NO canonical payment
ledger (only points_ledger for rewards); money/summary computes ad hoc from Square + jobs.
