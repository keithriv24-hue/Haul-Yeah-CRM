# Haul Yeah CRM — 56-Problem QA Audit (repair, do NOT rebuild)

Delivered by the Owner as a 9-prompt series. Each problem is eventually labeled:
FIXED + tested · ALREADY FIXED + verified · REQUIRES OWNER DECISION · CANNOT SAFELY TEST + reason.

Strict protocol: one phase at a time, test, present evidence, get explicit "yes" before the next.

## Master checklist status
- Problem #1 (exposed credentials / hidden accounts): FIXED + tested — 2026-06 (this phase).
- Problem #7 (owner "View As" security): FIXED + tested — 2026-06 (this phase).
- Problems #2, #24, #25 (Airtable field-name/ID normalization): Part C of Prompt 1 — DEFERRED
  (Owner scoped this session to #1 + #7 only). Next up.
- Prompts 2–9 (Problems #3,#6,#8–#12,#23,#26,#31,#36,#37,#55, payment ledger, reporting, etc.):
  NOT STARTED.

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

## PROMPTS 4–9 — NOT YET PROVIDED
The Owner has only shared prompts 1–3 so far. Ask for prompts 4–9 (reporting, commissions, Meta
tracking, crew dispatch, quote handoff, outcomes, compliance, cron jobs, payroll, final report)
when Phase 3 nears completion.
