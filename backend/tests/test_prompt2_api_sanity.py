"""Prompt 2 API sanity tests via public backend URL (owner-only migration, booking)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://haul-yeah-staging.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "HaulYeahAdmin", "password": "HaulYeah2026!"}, timeout=20)
    assert r.status_code == 200, r.text
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def auth_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}"}


def test_migration_scan_requires_auth():
    r = requests.post(f"{BASE_URL}/api/migration/project-ids/scan", timeout=20)
    assert r.status_code in (401, 403)


def test_migration_status_requires_auth():
    r = requests.get(f"{BASE_URL}/api/migration/status", timeout=20)
    assert r.status_code in (401, 403)


def test_migration_review_requires_auth():
    r = requests.get(f"{BASE_URL}/api/migration/review", timeout=20)
    assert r.status_code in (401, 403)


def test_migration_scan_owner(auth_headers):
    r = requests.post(f"{BASE_URL}/api/migration/project-ids/scan", headers=auth_headers, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "counts" in data
    counts = data["counts"]
    for k in ("scanned", "already_linked", "deterministically_linked", "ambiguous", "skipped", "failed"):
        assert k in counts, f"missing {k}"
    assert counts["scanned"] >= 0


def test_migration_status_owner(auth_headers):
    r = requests.get(f"{BASE_URL}/api/migration/status", headers=auth_headers, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "last_scan" in data
    assert "pending_review" in data


def test_migration_review_owner(auth_headers):
    r = requests.get(f"{BASE_URL}/api/migration/review", headers=auth_headers, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_booking_state_unknown_lead(auth_headers):
    r = requests.get(f"{BASE_URL}/api/leads/anyid/booking-state", headers=auth_headers, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("booking_state") == "none"
    assert data.get("booked") is False


def test_mark_booked_override_reason_too_short(auth_headers):
    r = requests.post(f"{BASE_URL}/api/leads/x/mark-booked-override", json={"reason": "no"}, headers=auth_headers, timeout=20)
    assert r.status_code == 422, r.text


def test_cancel_unknown_job(auth_headers):
    r = requests.post(f"{BASE_URL}/api/jobs/nope/cancel", json={"reason": "customer rescheduled"}, headers=auth_headers, timeout=20)
    assert r.status_code == 404, r.text
