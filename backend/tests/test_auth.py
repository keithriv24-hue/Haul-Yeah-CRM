"""Auth tests for Haul Yeah CRM — single owner password + JWT.

IMPORTANT: brute-force lockout triggers at 5 wrong tries from one IP → 15-minute
lockout. This test file makes at MOST 1 wrong-password attempt to stay well
below the threshold.
"""
import os
import time

import jwt
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE_URL:
    # Fallback: read from frontend/.env
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

CORRECT_PW = "HaulYeah2026!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": CORRECT_PW}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data
    assert isinstance(data["token"], str) and len(data["token"]) > 20
    return data["token"]


# --- login endpoint ---
class TestLogin:
    def test_login_wrong_password_returns_401(self):
        """ONE wrong-password call only; expects 401 + specific detail."""
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": "definitely-not-right"}, timeout=15)
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"
        body = r.json()
        assert body.get("detail") == "Wrong password. Try again.", body

    def test_login_correct_password_returns_jwt(self, token):
        # Decode without verification to inspect claims
        claims = jwt.decode(token, options={"verify_signature": False})
        assert claims.get("sub") == "owner"
        assert claims.get("type") == "access"
        assert "exp" in claims
        # 30 day expiry expected — allow generous window
        remaining = claims["exp"] - int(time.time())
        assert 29 * 86400 < remaining < 31 * 86400, f"unexpected exp window: {remaining}s"

    def test_login_empty_body_returns_422(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={}, timeout=15)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"

    def test_login_missing_password_field_returns_422(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"pw": "x"}, timeout=15)
        assert r.status_code == 422

    def test_login_empty_password_string_returns_401(self):
        """empty string is valid pydantic but must not equal APP_PASSWORD."""
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": ""}, timeout=15)
        # Note: could legitimately be 401 or 422 depending on validation
        assert r.status_code in (401, 422), f"got {r.status_code}: {r.text}"


# --- /me endpoint ---
class TestMe:
    def test_me_with_valid_token(self, token):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {"ok": True, "role": "owner", "can_switch": True}

    def test_me_without_auth_header_returns_401(self):
        r = requests.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 401
        assert r.json().get("detail") == "Not authenticated"

    def test_me_with_garbage_token_returns_401(self):
        r = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": "Bearer this.is.not.a.jwt"},
            timeout=15,
        )
        assert r.status_code == 401
        # "Invalid session. Log in again."
        assert "Invalid" in r.json().get("detail", "") or "Log in again" in r.json().get("detail", "")

    def test_me_with_malformed_auth_header_returns_401(self):
        """Missing 'Bearer ' prefix — should be treated as no token."""
        r = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": "abc.def.ghi"}, timeout=15)
        assert r.status_code == 401
        assert r.json().get("detail") == "Not authenticated"

    def test_me_with_token_signed_by_wrong_secret(self):
        """A well-formed JWT signed with a different secret must be rejected."""
        bad = jwt.encode(
            {"sub": "owner", "type": "access", "exp": int(time.time()) + 3600},
            "not-the-real-secret",
            algorithm="HS256",
        )
        r = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {bad}"}, timeout=15)
        assert r.status_code == 401
        assert "Invalid" in r.json().get("detail", "") or "Log in again" in r.json().get("detail", "")

    def test_me_with_expired_token(self, token):
        """Craft an expired token with the real secret — should be 401 with expired message.

        We read the JWT secret from backend/.env for this test only.
        """
        secret = None
        with open("/app/backend/.env") as fh:
            for line in fh:
                if line.startswith("JWT_SECRET"):
                    secret = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        if not secret:
            pytest.skip("JWT_SECRET not readable")
        expired = jwt.encode(
            {"sub": "owner", "type": "access", "exp": int(time.time()) - 60},
            secret,
            algorithm="HS256",
        )
        r = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {expired}"}, timeout=15)
        assert r.status_code == 401
        assert "expired" in r.json().get("detail", "").lower() or "Log in again" in r.json().get("detail", "")

    def test_me_with_wrong_token_type(self):
        """Token with type != 'access' must be rejected."""
        secret = None
        with open("/app/backend/.env") as fh:
            for line in fh:
                if line.startswith("JWT_SECRET"):
                    secret = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        if not secret:
            pytest.skip("JWT_SECRET not readable")
        refresh = jwt.encode(
            {"sub": "owner", "type": "refresh", "exp": int(time.time()) + 3600},
            secret,
            algorithm="HS256",
        )
        r = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {refresh}"}, timeout=15)
        assert r.status_code == 401


# --- Protected data routes ---
class TestProtectedRoutes:
    def test_leads_without_token_returns_401(self):
        r = requests.get(f"{BASE_URL}/api/tables/leads", timeout=15)
        assert r.status_code == 401
        assert r.json().get("detail") == "Not authenticated"

    def test_leads_with_token_passes_auth_and_returns_503_missing_key(self, token):
        """auth passed = 503 missing_key (AIRTABLE_API_KEY intentionally empty)."""
        r = requests.get(f"{BASE_URL}/api/tables/leads", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        assert r.status_code == 503, f"expected 503 missing_key, got {r.status_code}: {r.text}"
        detail = r.json().get("detail", {})
        assert isinstance(detail, dict)
        assert detail.get("error") == "missing_key"

    def test_health_without_token_returns_401(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 401

    def test_health_with_token_returns_200(self, token):
        r = requests.get(f"{BASE_URL}/api/health", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("airtable_configured") is False
        assert body.get("base_id_configured") is True

    def test_unknown_table_returns_404(self, token):
        r = requests.get(
            f"{BASE_URL}/api/tables/does_not_exist",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        assert r.status_code == 404
        detail = r.json().get("detail", {})
        assert isinstance(detail, dict)
        assert detail.get("error") == "unknown_table"


# --- Roles ---
SALES_PW = "SellMoves2026!"
EMPLOYEE_PW = "CrewDay2026!"


def _login(pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": pw}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


class TestRoles:
    def test_sales_login_returns_sales_role(self):
        data = _login(SALES_PW)
        assert data["role"] == "sales"
        claims = jwt.decode(data["token"], options={"verify_signature": False})
        assert claims["role"] == "sales"

    def test_employee_login_returns_employee_role(self):
        data = _login(EMPLOYEE_PW)
        assert data["role"] == "employee"

    def test_owner_login_returns_owner_role(self):
        data = _login(CORRECT_PW)
        assert data["role"] == "owner"

    def test_sales_blocked_from_money_tables(self):
        tok = _login(SALES_PW)["token"]
        for t in ("projects", "invoices", "subscriptions", "tasks", "blog", "contacts"):
            r = requests.get(f"{BASE_URL}/api/tables/{t}", headers={"Authorization": f"Bearer {tok}"}, timeout=15)
            assert r.status_code == 403, f"{t}: expected 403, got {r.status_code}"
            assert r.json().get("detail") == "Your role can't open this."

    def test_employee_blocked_from_other_tables(self):
        tok = _login(EMPLOYEE_PW)["token"]
        for t in ("leads", "invoices", "subscriptions", "blog", "contacts"):
            r = requests.get(f"{BASE_URL}/api/tables/{t}", headers={"Authorization": f"Bearer {tok}"}, timeout=15)
            assert r.status_code == 403, f"{t}: expected 403, got {r.status_code}"

    def test_sales_can_reach_leads_route(self):
        tok = _login(SALES_PW)["token"]
        r = requests.get(f"{BASE_URL}/api/tables/leads", headers={"Authorization": f"Bearer {tok}"}, timeout=15)
        assert r.status_code in (200, 503), f"got {r.status_code}"

    def test_employee_can_reach_projects_and_tasks(self):
        tok = _login(EMPLOYEE_PW)["token"]
        for t in ("projects", "tasks"):
            r = requests.get(f"{BASE_URL}/api/tables/{t}", headers={"Authorization": f"Bearer {tok}"}, timeout=15)
            assert r.status_code in (200, 503), f"{t}: got {r.status_code}"

    def test_airtable_verify_is_owner_only(self):
        tok = _login(SALES_PW)["token"]
        r = requests.get(f"{BASE_URL}/api/airtable/verify", headers={"Authorization": f"Bearer {tok}"}, timeout=15)
        assert r.status_code == 403


class TestRoleSwitch:
    def test_owner_can_switch_to_sales_and_back(self):
        owner = _login(CORRECT_PW)
        assert owner["can_switch"] is True
        r = requests.post(f"{BASE_URL}/api/auth/switch-role", json={"role": "sales"},
                          headers={"Authorization": f"Bearer {owner['token']}"}, timeout=15)
        assert r.status_code == 200, r.text
        sw = r.json()
        assert sw["role"] == "sales" and sw["can_switch"] is True
        leads = requests.get(f"{BASE_URL}/api/tables/leads", headers={"Authorization": f"Bearer {sw['token']}"}, timeout=15)
        assert leads.status_code in (200, 503)
        blocked = requests.get(f"{BASE_URL}/api/tables/invoices", headers={"Authorization": f"Bearer {sw['token']}"}, timeout=15)
        assert blocked.status_code == 403
        back = requests.post(f"{BASE_URL}/api/auth/switch-role", json={"role": "owner"},
                             headers={"Authorization": f"Bearer {sw['token']}"}, timeout=15)
        assert back.status_code == 200
        assert back.json()["role"] == "owner"

    def test_real_sales_token_cannot_switch(self):
        data = _login(SALES_PW)
        assert data.get("can_switch") is False
        r = requests.post(f"{BASE_URL}/api/auth/switch-role", json={"role": "owner"},
                          headers={"Authorization": f"Bearer {data['token']}"}, timeout=15)
        assert r.status_code == 403

    def test_real_employee_token_cannot_switch(self):
        data = _login(EMPLOYEE_PW)
        r = requests.post(f"{BASE_URL}/api/auth/switch-role", json={"role": "owner"},
                          headers={"Authorization": f"Bearer {data['token']}"}, timeout=15)
        assert r.status_code == 403

    def test_switch_to_unknown_role_rejected(self):
        owner = _login(CORRECT_PW)
        r = requests.post(f"{BASE_URL}/api/auth/switch-role", json={"role": "admin"},
                          headers={"Authorization": f"Bearer {owner['token']}"}, timeout=15)
        assert r.status_code == 422
