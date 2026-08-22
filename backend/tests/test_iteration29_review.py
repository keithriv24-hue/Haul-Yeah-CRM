"""Iteration 29 review tests: login retirement, money summary, ops facts, rates, role gating."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://haul-yeah-staging.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

OWNER_USER = "HaulYeahAdmin"
OWNER_PASS = "HaulYeah2026!"
SALES_USER = "testsalesadmin"
CREW_USER = "testcrewadmin"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    return r


@pytest.fixture(scope="module")
def owner_token():
    r = _login(OWNER_USER, OWNER_PASS)
    assert r.status_code == 200, r.text
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def sales_token():
    r = _login(SALES_USER, OWNER_PASS)
    assert r.status_code == 200, r.text
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def crew_token():
    r = _login(CREW_USER, OWNER_PASS)
    assert r.status_code == 200, r.text
    return r.json().get("token") or r.json().get("access_token")


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# --- Auth: shared password retired ---
def test_login_password_only_retired():
    r = requests.post(f"{API}/auth/login", json={"password": OWNER_PASS}, timeout=20)
    assert r.status_code == 401
    body = r.text.lower()
    assert "retired" in body or "shared" in body, f"Expected retired msg, got {r.text}"


def test_login_owner_ok(owner_token):
    assert owner_token


def test_login_wrong_password_once():
    # single wrong attempt to avoid lockout
    r = requests.post(f"{API}/auth/login", json={"email": OWNER_USER, "password": "definitely_wrong_once"}, timeout=20)
    assert r.status_code == 401


# --- Money summary ---
def test_money_summary_owner(owner_token):
    r = requests.get(f"{API}/money/summary", headers=_h(owner_token), timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ["source", "booked_total", "jobs_count", "collected_total", "outstanding_total", "unpaid_jobs", "revenue_today"]:
        assert k in data, f"missing {k} in {data.keys()}"
    assert data["source"] == "square"


def test_money_summary_sales_forbidden(sales_token):
    r = requests.get(f"{API}/money/summary", headers=_h(sales_token), timeout=20)
    assert r.status_code == 403


def test_money_summary_no_auth():
    r = requests.get(f"{API}/money/summary", timeout=20)
    assert r.status_code == 401


# --- Ops facts / brief must reflect money summary ---
def test_ops_facts_matches_money(owner_token):
    ms = requests.get(f"{API}/money/summary", headers=_h(owner_token), timeout=20).json()
    # Try known routes
    candidates = ["/ai/ops-facts", "/ai/ops-brief", "/ai/ops-brief?refresh=1"]
    resp = None
    for c in candidates:
        rr = requests.get(f"{API}{c}", headers=_h(owner_token), timeout=30)
        if rr.status_code == 200:
            resp = rr.json()
            break
    assert resp is not None, "no ops endpoint responded 200"
    text = str(resp)
    # money numbers should appear
    assert str(int(ms["outstanding_total"])) in text or f"{ms['outstanding_total']}" in text, "outstanding not present in ops"


# --- Rates ---
def test_rates_owner(owner_token):
    r = requests.get(f"{API}/settings/rates", headers=_h(owner_token), timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    # unwrap if nested
    if "values" in d and isinstance(d["values"], dict):
        d = d["values"]
    assert d.get("stairFlightFee") == 85
    assert d.get("mileageFreeMiles") == 20
    assert float(d.get("mileageRatePerMile")) == 0.85
    assert "zone1Fee" not in d and "zone2Fee" not in d and "zone3Fee" not in d


def test_pricing_values_owner(owner_token):
    r = requests.get(f"{API}/scopes/pricing-values", headers=_h(owner_token), timeout=20)
    assert r.status_code == 200
    d = r.json()
    if "values" in d and isinstance(d["values"], dict):
        d = d["values"]
    assert d.get("stairFlightFee") == 85
    assert d.get("mileageFreeMiles") == 20


def test_pricing_values_sales_folded(sales_token):
    r = requests.get(f"{API}/scopes/pricing-values", headers=_h(sales_token), timeout=20)
    assert r.status_code == 200
    d = r.json()
    if "values" in d and isinstance(d["values"], dict):
        d = d["values"]
    # folded ghost sales
    assert abs(float(d.get("manHourRate", 0)) - 71.5) < 0.01, d
    assert abs(float(d.get("mileageRatePerMile", 0)) - 0.935) < 0.01, d
    assert float(d.get("cushionPercent", -1)) == 0


# --- Role gating regression ---
@pytest.mark.parametrize("path", ["/tables/projects", "/tables/invoices", "/tables/subscriptions", "/tables/contacts"])
def test_sales_forbidden_on_owner_tables(sales_token, path):
    r = requests.get(f"{API}{path}", headers=_h(sales_token), timeout=20)
    assert r.status_code == 403, f"{path} => {r.status_code}"


def test_crew_forbidden_on_leads(crew_token):
    r = requests.get(f"{API}/tables/leads", headers=_h(crew_token), timeout=20)
    assert r.status_code == 403
