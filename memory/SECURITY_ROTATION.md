# Security — credential rotation (Problem #1, Phase 1)

Date: 2026-06. Owner actions required after this phase deploys.

## What changed in the code
- Removed the hardcoded hidden/backdoor "ghost" POV accounts that were seeded on every
  backend startup (`testcrewadmin`, `testsalesadmin`, `testmarketingadmin`,
  `testqualityadmin`) with a hardcoded password. Startup now **actively deletes** any
  ghost accounts a prior deploy created, so production carries zero backdoor logins.
- The test suite seeds those ghost accounts **ephemerally** during pytest only
  (`backend/tests/conftest.py`) and deletes them when the run ends. Their password comes
  from `backend/tests/.env.test` (gitignored), not from source.
- Deleted the credential/hash backup file `memory/removed_users_backup.json` from the repo
  (it contained bcrypt password hashes). It is removed from the working tree and future
  commits.
- Added `scripts/scan_secrets.sh` — a practical scan of tracked files for bcrypt hashes,
  committed `.env` files, provider tokens, and hardcoded password literals.

## Owner actions — rotate anything that may have been exposed
Because these values previously lived in source / startup code and may remain in **git
history**, rotate them:

1. **Ghost/POV account password** — the literal `HaulYeah2026!` was the shared ghost
   password AND is currently the owner password. Change the Owner password in
   Team Management, and set a NEW, different value for `APP_PASSWORD` in the backend
   secrets panel. Do not reuse `HaulYeah2026!` anywhere.
2. **JWT_SECRET** (backend secrets) — rotate to a fresh 64-char random hex. This
   invalidates all existing sessions (everyone logs in again) and kills any old
   long-lived `owner_switch` tokens still in the wild. Recommended as part of this phase.
3. Review every value in the backend secrets panel that was ever present in a tracked
   file or in `removed_users_backup.json` and rotate it: `AIRTABLE_API_KEY`,
   Square token, `META_*`, `GOOGLE_*`, `WEBHOOK_CRON_SECRET`, `TALLY_WEBHOOK_SIGNING_SECRET`.
4. **Git history**: the old backup file and former hardcoded values still exist in prior
   commits. Removing them from history requires a history rewrite / force-push, which is
   NOT done without your approval. If you want history purged, say so and we'll plan it
   (e.g. `git filter-repo`) — otherwise rotation (above) is the safe mitigation.

## Verify
- After deploy, confirm `GET /api/users` (owner) shows ONLY legitimate users — no
  `Test … (Ghost)` rows.
- Run `bash scripts/scan_secrets.sh` — it should print "clean".
