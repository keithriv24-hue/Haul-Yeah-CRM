# Haul Yeah Moving — Internal CRM

A mobile-responsive PWA for Haul Yeah Moving (North & Central New Jersey).
**Weekend moves, flat price, no surprises.**

The single source of truth is an existing **Airtable base** (`appFAHTRNrRckuxI8`). The FastAPI backend
proxies every read/write through the Airtable REST API using **field IDs** (never field names) with a
5 req/sec rate limiter. The frontend never touches the Airtable token.

## Environment variables (backend/.env)

| Variable | Purpose |
|---|---|
| `AIRTABLE_API_KEY` | Airtable Personal Access Token. **Add via the secrets panel — never in code or chat.** |
| `AIRTABLE_BASE_ID` | The Airtable base (`appFAHTRNrRckuxI8`). |

## Backend API routes (all prefixed `/api`)

| Method | Route | What it does |
|---|---|---|
| GET | `/api/health` | Is the Airtable key configured? |
| GET | `/api/airtable/verify` | Fetches 1 record from Leads to confirm the connection works |
| GET | `/api/tables/{table}` | List all records (paginated internally, `returnFieldsByFieldId=true`) |
| POST | `/api/tables/{table}` | Create a record (`{"fields": {fieldId: value}}`, typecast on) |
| PATCH | `/api/tables/{table}/{record_id}` | Update a record (partial fields, typecast on) |

`{table}` ∈ `leads`, `contacts`, `projects`, `tasks`, `blog`, `invoices`, `subscriptions`.

## Frontend routes

| Route | View |
|---|---|
| `/` | Dashboard — KPI cards, leads doughnut, money bar chart, upcoming jobs, high-priority tasks |
| `/leads` | Lead card grid with live speed-to-lead timers, quote calculator, deposit links, book-as-job |
| `/contacts` | Contact cards filtered by type, call/email/Gmail-search buttons |
| `/projects` | Jobs sorted by date, editable, internal margin math (crew cost) |
| `/tasks` | 4-column drag-and-drop kanban (Backlog / To Do / In Progress / Done) |
| `/blog` | Content pipeline by status with body editor |
| `/invoices` | Invoice KPIs + table with one-click "Mark paid" |
| `/subscriptions` | Monthly burn + annualized totals |
| `/partner` | Read-only financial summary — no customer names |
| `/help` | The full lead-to-cash flow, in plain language |

## Key behaviors

- **Privacy Mode** (header toggle, saved in localStorage) blurs every name, phone, email, address, and dollar figure.
- **Quote logic (locked):** `crew × hours × $65` + travel ($125 truck / $75 labor) + stairs ($85/flight) + piano ($500/$800) = low; high = low × 1.10; deposit = 25% of high. Quotes always render as ranges with "Final price confirmed by phone."
- **Deposit flow:** no Square API. Keith pastes a Square payment link; it's saved to the lead's Notes and a pre-written mailto email opens.
- **Optimistic writes** with visible error toasts and automatic rollback.
- Records with `Lead source = "Sample Data"` are seeded test records.
