# Auth Testing Playbook — Haul Yeah CRM (single owner password)

This app uses ONE shared owner password (env `APP_PASSWORD`), not email/password accounts. No MongoDB users.

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
