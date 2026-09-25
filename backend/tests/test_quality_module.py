"""Quality & Compliance module (prompt 1 of 3) tests.
Airtable is unavailable in preview, so table-backed flows return 503; those are
asserted as "gated correctly, or 503". The cost-stripped quote (Mongo-backed) and
all role gating ARE fully exercised here."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://haul-yeah-staging.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

OWNER_USER = "HaulYeahAdmin"
GHOST_PASS = "HaulYeah2026!"
SALES_USER = "testsalesadmin"
CREW_USER = "testcrewadmin"
QUALITY_USER = "testqualityadmin"

FORBIDDEN = ["cushion", "cushionPercent", "crewCost", "margin", "commission", "cost", "costs", "profit"]
ALLOWED_SENT = {
    "customerName": "Jane Doe", "customerPhone": "555-1212", "finalQuote": 1250,
    "deposit": 312.5, "bandLo": 1150, "bandHi": 1250, "crewSize": 3,
    "estimatedHours": 5, "hourlyRate": 65, "tripFee": 125, "subtotal": 1136, "stairs": 170,
}
INTERNAL_SENT = {"cushion": 113.6, "cushionPercent": 10, "crewCost": 420, "cost": 420, "margin": 700, "commission": 150, "profit": 550}


def _login(email, password=GHOST_PASS):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)


def _tok(r):
    return r.json().get("token") or r.json().get("access_token")


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def owner_token():
    r = _login(OWNER_USER)
    assert r.status_code == 200, r.text
    return _tok(r)


@pytest.fixture(scope="module")
def sales_token():
    r = _login(SALES_USER)
    assert r.status_code == 200, r.text
    return _tok(r)


@pytest.fixture(scope="module")
def crew_token():
    r = _login(CREW_USER)
    assert r.status_code == 200, r.text
    return _tok(r)


@pytest.fixture(scope="module")
def quality_token():
    r = _login(QUALITY_USER)
    assert r.status_code == 200, r.text
    return _tok(r)


def test_quality_login_and_role(quality_token):
    r = requests.get(f"{API}/auth/me", headers=_h(quality_token), timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "quality"


LEAD_ID = "QUALITY-TEST-LEAD"


def test_seed_quote_as_owner(owner_token):
    payload = {"breakdown": {**ALLOWED_SENT, **INTERNAL_SENT}}
    r = requests.put(f"{API}/quotes/{LEAD_ID}", json=payload, headers=_h(owner_token), timeout=20)
    assert r.status_code == 200, r.text


def test_owner_sees_full_quote(owner_token):
    r = requests.get(f"{API}/quotes/{LEAD_ID}", headers=_h(owner_token), timeout=20)
    assert r.status_code == 200, r.text
    b = r.json()["breakdown"]
    assert "cushion" in b and "margin" in b and "commission" in b


def test_quality_quote_is_cost_stripped(quality_token):
    r = requests.get(f"{API}/quotes/{LEAD_ID}", headers=_h(quality_token), timeout=20)
    assert r.status_code == 200, r.text
    b = r.json()["breakdown"]
    # spec: response must contain NONE of the internal keys
    for k in FORBIDDEN:
        assert k not in b, f"leaked internal key {k}"
    # and it must still carry the customer-facing figures
    for k in ["finalQuote", "deposit", "crewSize", "estimatedHours", "tripFee", "subtotal"]:
        assert k in b, f"missing customer-facing key {k}"


def test_quote_get_blocked_for_crew(crew_token):
    r = requests.get(f"{API}/quotes/{LEAD_ID}", headers=_h(crew_token), timeout=20)
    assert r.status_code == 403


def test_audit_queue_gating(sales_token, quality_token):
    assert requests.get(f"{API}/quality/audit-queue", headers=_h(sales_token), timeout=30).status_code == 403
    r = requests.get(f"{API}/quality/audit-queue", headers=_h(quality_token), timeout=30)
    assert r.status_code in (200, 503), r.text


def test_quote_accuracy_gating(sales_token, quality_token, owner_token):
    assert requests.get(f"{API}/quality/quote-accuracy", headers=_h(sales_token), timeout=30).status_code == 403
    for tok in (quality_token, owner_token):
        assert requests.get(f"{API}/quality/quote-accuracy", headers=_h(tok), timeout=30).status_code in (200, 503)


def test_feedback_create_and_visibility(quality_token, sales_token):
    # sales cannot log feedback
    assert requests.post(f"{API}/quality/feedback", json={"what_was_off": "x"}, headers=_h(sales_token), timeout=20).status_code == 403
    # who is the sales ghost?
    me = requests.get(f"{API}/auth/me", headers=_h(sales_token), timeout=20).json()
    sales_uid = me["user"]["id"]
    # feedback aimed at the sales rep
    r1 = requests.post(f"{API}/quality/feedback", headers=_h(quality_token), timeout=20, json={
        "job_id": "recQTEST1", "job_name": "QTest — to sales", "rep_user_id": sales_uid,
        "rep_name": "Sales Ghost", "what_was_off": "Underestimated stairs", "what_to_do": "Ask about elevator"})
    assert r1.status_code == 200, r1.text
    # feedback aimed at a different rep
    r2 = requests.post(f"{API}/quality/feedback", headers=_h(quality_token), timeout=20, json={
        "job_id": "recQTEST2", "job_name": "QTest — to someone else", "rep_user_id": "someone-else-id",
        "rep_name": "Other Rep", "what_was_off": "Wrong crew size"})
    assert r2.status_code == 200, r2.text
    # quality sees all
    q = requests.get(f"{API}/quality/feedback", headers=_h(quality_token), timeout=20).json()["feedback"]
    jobs = {f.get("job_id") for f in q}
    assert "recQTEST1" in jobs and "recQTEST2" in jobs
    # the sales rep sees ONLY their own, never another rep's
    s = requests.get(f"{API}/quality/feedback", headers=_h(sales_token), timeout=20).json()["feedback"]
    assert all(f.get("rep_user_id") == sales_uid for f in s)
    assert any(f.get("job_id") == "recQTEST1" for f in s)
    assert all(f.get("job_id") != "recQTEST2" for f in s)


def test_feedback_requires_what_was_off(quality_token):
    r = requests.post(f"{API}/quality/feedback", json={"what_was_off": "   "}, headers=_h(quality_token), timeout=20)
    assert r.status_code == 422
