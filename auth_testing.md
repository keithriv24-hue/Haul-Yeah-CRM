# Auth Testing Playbook — Haul Yeah CRM (three shared-password roles)

This app uses THREE shared passwords (no user accounts, no MongoDB):
- Owner: env `APP_PASSWORD` = HaulYeah2026! → full access
- Sales: env `SALES_PASSWORD` = SellMoves2026! → /api/tables/leads only
- Employee: env `EMPLOYEE_PASSWORD` = CrewDay2026! → /api/tables/projects + /api/tables/tasks only (projects responses strip Quote / Deposit Collected / Final Revenue field IDs)

Login returns `{"token": <JWT with role claim>, "role": "owner|sales|employee"}`. `/api/auth/me` returns `{"ok": true, "role": ...}`.
Owner project responses include computed `internal: {crew_cost, margin}` — crew rates live only in the backend.
Cross-role table access returns 403 "Your role can't open this." `/api/airtable/verify` is owner-only.

## API tests

```
API_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2)

# 1. Wrong password -> 401 "Wrong password. Try again."
curl -s -X POST "$API_URL/api/auth/login" -H "Content-Type: application/json" -d '{"password":"nope"}'

# 2. Correct password -> {"token": "..."}
TOKEN=$(curl -s -X POST "$API_URL/api/auth/login" -H "Content-Type: application/json" -d '{"password":"HaulYeah2026!"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

# 3. /me with token -> {"ok": true}
curl -s "$API_URL/api/auth/me" -H "Authorization: Bearer $TOKEN"

# 4. Protected route without token -> 401
curl -s "$API_URL/api/tables/leads"

# 5. Protected route with token -> 200 (or 503 if AIRTABLE_API_KEY unset)
curl -s "$API_URL/api/tables/leads" -H "Authorization: Bearer $TOKEN"
```

## Frontend flow
- Visiting any page without a stored token shows the login screen (data-testid `login-form`).
- Wrong password shows `login-error`. Correct password unlocks the app and persists in localStorage (`hy_token`).
- A 401 from any API call clears the token and returns the user to the login screen.
- Brute force: 5 wrong tries from one IP -> 429 lockout for 15 minutes (avoid triggering in automated runs).
