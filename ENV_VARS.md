# Environment variables

**Names only. Never commit values.** Set every one of these in the Render
dashboard (or Emergent's secrets panel), not in this repository.

## Backend — required (the app will not start without these)

| Variable | Notes |
|---|---|
| `MONGO_URL` | MongoDB connection string. Read at import time — a typo means an instant boot crash. |
| `DB_NAME` | Database name. Also read at import time. |
| `JWT_SECRET` | Copy **exactly** from the current environment. Changing it invalidates every active session and logs everyone out. |

## Backend — core function

| Variable | Notes |
|---|---|
| `OWNER_EMAIL` | Copy **exactly**. Startup seeding rewrites the owner account's email to match this value, so a mismatch can lock you out. |
| `APP_PASSWORD` | Owner account seed password. |
| `AIRTABLE_API_KEY` | |
| `AIRTABLE_BASE_ID` | |
| `CORS_ORIGINS` | Comma-separated. Production: `https://www.haulyeahadmin.com` |
| `APP_BASE_URL` | Public URL of the app. |

## Backend — integrations

| Variable | Notes |
|---|---|
| `EMERGENT_LLM_KEY` | **Still required.** Authenticates the object store that holds all job, truck, profile and portal photos. |
| `OPENAI_API_KEY` | Powers the Dashboard "Ops brain" card. |
| `OPS_BRIEF_MODEL` | Optional. Defaults to `gpt-4o`. |
| `SQUARE_ACCESS_TOKEN` | |
| `SQUARE_ENVIRONMENT` | `production` or `sandbox`. Staging must use `sandbox`. |
| `SQUARE_LOCATION_ID` | |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Gmail OAuth. |
| `META_APP_ID` / `META_APP_SECRET` | |
| `META_CAPI_ACCESS_TOKEN` / `META_DATASET_ID` | Meta Conversions API. |
| `META_GRAPH_VERSION` / `META_TEST_EVENT_CODE` | |
| `TALLY_WEBHOOK_SIGNING_SECRET` | Lead form webhook. |

OpenPhone credentials are **not** environment variables — they live in the
MongoDB `settings` collection, alongside the runtime Square, Gmail and Meta
tokens. Migrating the database is what carries them across.

## Backend — deployment safety

| Variable | Notes |
|---|---|
| `DISABLE_BACKGROUND_LOOPS` | Defaults to **off**, so production behaviour is unchanged. Set to `true` on staging only. When off, five loops run every 90–300s; one chain writes "deposit paid" flags to the live Airtable base. Staging must never do that. |

## Backend — account defaults

`DEFAULT_STARTING_PASSWORD`, `TEST_GHOST_PASSWORD`,
`TEST_EMPLOYEE_LEGACY_PASSWORD`, `TEST_SALES_LEGACY_PASSWORD`,
`TEST_JUNIOR_INITIAL_PASSWORD`

## Frontend — build-time

| Variable | Notes |
|---|---|
| `REACT_APP_BACKEND_URL` | Baked into the bundle at build time. Changing it requires a rebuild, not just a restart. No trailing slash. |
| `ENABLE_HEALTH_CHECK` | Optional. |

## Operational notes

- **Never run more than one backend instance.** The background loops are not
  multi-instance safe — two instances double the Square syncing and alerting.
- Staging must use a **copy** of the database, never production.
