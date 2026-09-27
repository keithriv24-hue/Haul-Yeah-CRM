"""Stage 6 — Calculator Accuracy workspace: RBAC + revenue redaction + response shape.

Measurement-only endpoint. Owner sees dollar metrics; Quality must NOT. Sales/crew/marketing 403.
No suggested-calibration values may appear (Stage 7 only).
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://haul-yeah-staging.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

OWNER_USER, OWNER_PASS = "HaulYeahAdmin", "HaulYeah2026!"
QUALITY_USER = "testqualityadmin"
SALES_USER = "testsalesadmin"
GHOST_PASS = "HaulYeah2026!"
EP = f"{API}/quality/calculator-accuracy"


def _login(email, password):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)


def _tok(email, password):
    r = _login(email, password)
    assert r.status_code == 200, r.text
    return r.json().get("token") or r.json().get("access_token")


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def owner_token():
    return _tok(OWNER_USER, OWNER_PASS)


@pytest.fixture(scope="module")
def quality_token():
    return _tok(QUALITY_USER, GHOST_PASS)


@pytest.fixture(scope="module")
def sales_token():
    return _tok(SALES_USER, GHOST_PASS)


def test_unauth_401():
    assert requests.get(EP, timeout=20).status_code == 401


def test_sales_forbidden(sales_token):
    assert requests.get(EP, headers=_h(sales_token), timeout=20).status_code == 403


def test_owner_shape(owner_token):
    r = requests.get(EP, headers=_h(owner_token), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["role"] == "owner"
    for k in ("summary", "trends", "coverage", "review_queue", "current_parameters", "progress"):
        assert k in d, f"missing {k}"
    s = d["summary"]
    assert "work_mh" in s and "sample" in s["work_mh"]
    # owner sees revenue metrics
    assert "dollars" in s
    # coverage groups present
    cov = d["coverage"]
    for k in ("base_rate", "packing", "access", "specialty", "packages", "crew"):
        assert k in cov
    assert len(cov["access"]) == 10 and len(cov["packing"]) == 4
    # current params are non-monetary + read-only
    cp = d["current_parameters"]
    assert cp["base_rate_mh_per_100cuft"] is not None
    assert "packing_multipliers" in cp and "access_per_mh" in cp
    # Stage 6 measures only — learning must be OFF; no suggested-value FIELDS anywhere
    assert d["progress"]["stage7_enabled"] is False
    def _no_suggestion_keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert not any(w in k.lower() for w in ("suggest", "recommend", "proposed")), f"suggestion field leaked: {k}"
                _no_suggestion_keys(v)
        elif isinstance(obj, list):
            for v in obj:
                _no_suggestion_keys(v)
    _no_suggestion_keys(d)


def test_quality_redaction(quality_token):
    r = requests.get(EP, headers=_h(quality_token), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["role"] == "quality"
    # NO revenue for Quality
    assert "dollars" not in d["summary"], "Quality must not see dollar metrics"
    for t in d["trends"]:
        assert "mean_dollar_variance" not in t, "Quality trend leaked dollars"
    # review queue must not surface the owner-only 'final_total_missing' reason
    for row in d["review_queue"]:
        assert "final_total_missing" not in row["reasons"], "Quality saw a revenue-derived review reason"
    # man-hour accuracy is non-monetary and still present
    assert "work_mh" in d["summary"]


def test_coverage_labels_valid(owner_token):
    d = requests.get(EP, headers=_h(owner_token), timeout=30).json()
    valid = {"no_data", "insufficient", "limited", "ok"}
    for grp in ("packing", "access", "packages", "crew"):
        for c in d["coverage"][grp]:
            assert c["label"] in valid
    assert d["coverage"]["base_rate"]["label"] in valid
    assert d["coverage"]["specialty"]["label"] in valid
