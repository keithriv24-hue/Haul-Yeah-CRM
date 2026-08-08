"""Iteration 19 — Meta CAPI fixes HTTP-level flows.

Focus:
 - FIX 1: Schedule fires on Quoted->Booked edge (log line assertion)
 - Edge-only: repeat Booked -> no new fire log
 - Non-Booked PATCH (Quoted -> Contacted) -> no fire log
 - Cleanup delete disposable lead
 - /api/marketing/capi-test skipped/404/auth
 - /api/webhooks/tally bad signature -> 401
 - Regression: login, capi-status, list leads
"""
import os
import re
import time
import subprocess

import pytest
import requests

from test_config import OWNER_EMAIL as OWNER_USER, OWNER_PASSWORD as OWNER_PASS

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

# Airtable field IDs
F_NAME = "fldsBIJdaasQ9fh9a"
F_EMAIL = "fldi6lWGr530XQ4YE"
F_PHONE = "fldQMF5LKSd0yI8Bs"
F_STATUS = "fldplIOmtbERJFG6X"


@pytest.fixture(scope="module")
def owner_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": OWNER_USER, "password": OWNER_PASS}, timeout=30)
    assert r.status_code == 200, f"Owner login failed: {r.status_code} {r.text}"
    token = r.json().get("token")
    assert token, f"No token in login response: {r.text}"
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def test_lead(owner_session):
    """Create disposable test lead, yield id, delete after."""
    payload = {"fields": {
        F_NAME: "CAPI Test Lead ZZZ",
        F_EMAIL: "capitest@example.com",
        F_PHONE: "9735550199",
        F_STATUS: "Quoted",
    }}
    r = owner_session.post(f"{BASE_URL}/api/tables/leads", json=payload, timeout=30)
    if r.status_code == 503:
        pytest.skip(f"Airtable not configured in preview (503): {r.text}")
    assert r.status_code in (200, 201), f"Create lead failed: {r.status_code} {r.text}"
    data = r.json()
    rec_id = data.get("id") or data.get("record", {}).get("id")
    assert rec_id, f"No id in create response: {data}"
    yield rec_id
    # Cleanup
    d = owner_session.delete(f"{BASE_URL}/api/tables/leads/{rec_id}", timeout=30)
    assert d.status_code == 200, f"Cleanup delete failed: {d.status_code} {d.text}"


def _grep_schedule_log(record_id: str) -> list:
    """Grep for CAPI Schedule firing log lines mentioning the given lead id."""
    try:
        out = subprocess.run(
            ["bash", "-lc", f"grep 'CAPI Schedule firing for lead {record_id}' /var/log/supervisor/backend.*.log || true"],
            capture_output=True, text=True, timeout=10,
        )
        return [ln for ln in out.stdout.strip().splitlines() if ln]
    except Exception as e:
        return [f"grep_error: {e}"]


# ---------- Regression basics ----------

def test_owner_login(owner_session):
    # already logged in via fixture; issue a whoami-like call
    r = owner_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert r.status_code == 200


def test_capi_status(owner_session):
    r = owner_session.get(f"{BASE_URL}/api/meta/capi-status", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body.get("configured") is False, f"Expected configured=false in preview, got {body}"


def test_list_leads(owner_session):
    r = owner_session.get(f"{BASE_URL}/api/tables/leads", timeout=30)
    if r.status_code == 503:
        pytest.skip(f"Airtable not configured in preview (503)")
    assert r.status_code == 200


# ---------- capi-test endpoint ----------

def test_capi_test_unauth():
    r = requests.post(f"{BASE_URL}/api/marketing/capi-test", json={}, timeout=15)
    assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"


def test_capi_test_skipped(owner_session):
    r = owner_session.post(f"{BASE_URL}/api/marketing/capi-test", json={}, timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    body = r.json()
    assert body.get("skipped") is True, f"Expected skipped=true, got {body}"


def test_capi_test_bogus_lead(owner_session):
    r = owner_session.post(
        f"{BASE_URL}/api/marketing/capi-test",
        json={"lead_id": "recDOESNOTEXIST1"},
        timeout=20,
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code} {r.text}"


# ---------- Tally webhook regression ----------

def test_tally_bad_signature():
    r = requests.post(f"{BASE_URL}/api/webhooks/tally", json={"any": "body"}, timeout=15)
    # Should be 401 bad signature (secret unset in preview)
    assert r.status_code == 401, f"Expected 401, got {r.status_code} {r.text}"


# ---------- Schedule edge tests (rely on test_lead fixture) ----------

def test_patch_to_contacted_no_fire(owner_session, test_lead):
    """PATCH to non-Booked status (Contacted) - should NOT fire Schedule."""
    before = _grep_schedule_log(test_lead)
    r = owner_session.patch(
        f"{BASE_URL}/api/tables/leads/{test_lead}",
        json={"fields": {F_STATUS: "Contacted"}},
        timeout=30,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    time.sleep(1.5)
    after = _grep_schedule_log(test_lead)
    assert len(after) == len(before), f"Unexpected new Schedule log lines: before={before}, after={after}"


def test_patch_back_to_quoted(owner_session, test_lead):
    """Set back to Quoted so next PATCH tests the Quoted->Booked edge."""
    r = owner_session.patch(
        f"{BASE_URL}/api/tables/leads/{test_lead}",
        json={"fields": {F_STATUS: "Quoted"}},
        timeout=30,
    )
    assert r.status_code == 200
    time.sleep(1.0)


def test_patch_to_booked_fires_schedule(owner_session, test_lead):
    """FIX 1: Quoted -> Booked should log 'CAPI Schedule firing for lead {id} (prev status: Quoted)'."""
    before = _grep_schedule_log(test_lead)
    r = owner_session.patch(
        f"{BASE_URL}/api/tables/leads/{test_lead}",
        json={"fields": {F_STATUS: "Booked"}},
        timeout=30,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    # Give async task a moment
    time.sleep(2.5)
    after = _grep_schedule_log(test_lead)
    new_lines = [ln for ln in after if ln not in before]
    assert new_lines, f"Expected new 'CAPI Schedule firing' log line for {test_lead}. before={before} after={after}"
    joined = "\n".join(new_lines)
    assert "prev status: Quoted" in joined, f"Expected prev status Quoted in: {joined}"


def test_patch_booked_again_no_fire(owner_session, test_lead):
    """Second PATCH to Booked - should NOT fire again (prev status already Booked)."""
    before = _grep_schedule_log(test_lead)
    r = owner_session.patch(
        f"{BASE_URL}/api/tables/leads/{test_lead}",
        json={"fields": {F_STATUS: "Booked"}},
        timeout=30,
    )
    assert r.status_code == 200
    time.sleep(2.0)
    after = _grep_schedule_log(test_lead)
    assert len(after) == len(before), f"Should not fire again. before={len(before)} after={len(after)}\nnew={[l for l in after if l not in before]}"
