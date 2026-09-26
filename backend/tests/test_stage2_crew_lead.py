"""Stage 2 backend regression: Crew Lead 8-tap flow, corrections & depart-override.

Covers:
  - GET  /api/crew/job-lead/{id}     (crew view of state)
  - POST /api/assignments/{id}/crew-lead/correct   (owner note + clear)
  - POST /api/assignments/{id}/depart-override     (owner resolution)
  - RBAC: crew/helper cannot call owner-only correction/override endpoints.

We deliberately do NOT tap /api/crew/job-lead/{id}/{tap_key} here; the review
request warns tapping past depart is a permanent state change on the shared QA
assignment. The Playwright test drives the first two taps once as designed.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://haul-yeah-staging.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ASSIGNMENT_ID = "6467d362-6511-44a5-8b59-0979845c54a2"

OWNER = {"email": "HaulYeahAdmin", "password": "HaulYeah2026!"}
CREW  = {"email": "stage2.crew@haulyeah.test", "password": "Stage2Pass!"}
HELPER = {"email": "stage2.helper@haulyeah.test", "password": "Stage2Pass!"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def owner_headers():
    return _login(OWNER)


@pytest.fixture(scope="module")
def crew_headers():
    return _login(CREW)


@pytest.fixture(scope="module")
def helper_headers():
    return _login(HELPER)


# --- job-lead flow visibility -------------------------------------------------

class TestJobLeadFlowState:
    def test_crew_lead_sees_flow_with_steps(self, crew_headers):
        r = requests.get(f"{API}/crew/job-lead/{ASSIGNMENT_ID}", headers=crew_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("role_on_job") in ("primary", "secondary"), data
        assert data.get("is_lead") is True
        steps = data.get("steps") or []
        keys = [s.get("key") for s in steps]
        for k in ("clock_in", "depart", "arrived", "no_damage", "loaded",
                  "dropoff", "complete", "clock_out"):
            assert k in keys, f"missing step {k}: {keys}"
        assert "next_tap" in data

    def test_helper_flow_role_is_helper(self, helper_headers):
        r = requests.get(f"{API}/crew/job-lead/{ASSIGNMENT_ID}", headers=helper_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("role_on_job") == "helper", data
        assert data.get("is_lead") is False


# --- owner corrections --------------------------------------------------------

class TestCorrections:
    def test_note_correction_appends(self, owner_headers):
        r = requests.post(
            f"{API}/assignments/{ASSIGNMENT_ID}/crew-lead/correct",
            json={"tap_key": "depart", "action": "note",
                  "reason": "TEST_pytest note — verifying correction endpoint appends an entry"},
            headers=owner_headers, timeout=15,
        )
        assert r.status_code == 200, r.text
        cl = r.json().get("crew_lead") or {}
        corrs = cl.get("corrections") or []
        assert corrs, "expected corrections array populated"
        last = corrs[-1]
        assert last["tap_key"] == "depart"
        assert last["action"] == "note"
        assert "TEST_pytest note" in last["reason"]

    def test_bad_step_returns_422(self, owner_headers):
        r = requests.post(
            f"{API}/assignments/{ASSIGNMENT_ID}/crew-lead/correct",
            json={"tap_key": "no_such_step", "action": "note",
                  "reason": "TEST_pytest — bad step key should 422"},
            headers=owner_headers, timeout=15,
        )
        assert r.status_code == 422, r.text

    def test_short_reason_returns_422(self, owner_headers):
        r = requests.post(
            f"{API}/assignments/{ASSIGNMENT_ID}/crew-lead/correct",
            json={"tap_key": "depart", "action": "note", "reason": "x"},
            headers=owner_headers, timeout=15,
        )
        assert r.status_code == 422, r.text

    def test_crew_cannot_correct(self, crew_headers):
        r = requests.post(
            f"{API}/assignments/{ASSIGNMENT_ID}/crew-lead/correct",
            json={"tap_key": "depart", "action": "note",
                  "reason": "TEST_pytest crew user should NOT be allowed to correct"},
            headers=crew_headers, timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_helper_cannot_correct(self, helper_headers):
        r = requests.post(
            f"{API}/assignments/{ASSIGNMENT_ID}/crew-lead/correct",
            json={"tap_key": "depart", "action": "note",
                  "reason": "TEST_pytest helper user should NOT be allowed to correct"},
            headers=helper_headers, timeout=15,
        )
        assert r.status_code == 403, r.text


# --- owner depart-override ----------------------------------------------------

class TestDepartOverride:
    def test_short_reason_returns_422(self, owner_headers):
        r = requests.post(
            f"{API}/assignments/{ASSIGNMENT_ID}/depart-override",
            json={"reason": "too short", "resolution": "corrected"},
            headers=owner_headers, timeout=15,
        )
        assert r.status_code == 422, r.text

    def test_corrected_resolution_persists(self, owner_headers):
        r = requests.post(
            f"{API}/assignments/{ASSIGNMENT_ID}/depart-override",
            json={"reason": "TEST_pytest owner review — corrected & verified defect for QA",
                  "resolution": "corrected"},
            headers=owner_headers, timeout=15,
        )
        assert r.status_code == 200, r.text
        cl = r.json().get("crew_lead") or {}
        ov = cl.get("depart_override") or {}
        assert ov.get("resolution") == "corrected", ov
        assert "TEST_pytest" in (ov.get("reason") or "")

    def test_override_resolution_persists(self, owner_headers):
        r = requests.post(
            f"{API}/assignments/{ASSIGNMENT_ID}/depart-override",
            json={"reason": "TEST_pytest owner review — authorized departure despite defect for QA",
                  "resolution": "override"},
            headers=owner_headers, timeout=15,
        )
        assert r.status_code == 200, r.text
        cl = r.json().get("crew_lead") or {}
        ov = cl.get("depart_override") or {}
        assert ov.get("resolution") == "override", ov

    def test_crew_cannot_override(self, crew_headers):
        r = requests.post(
            f"{API}/assignments/{ASSIGNMENT_ID}/depart-override",
            json={"reason": "TEST_pytest crew must be blocked from override", "resolution": "override"},
            headers=crew_headers, timeout=15,
        )
        assert r.status_code == 403, r.text


# --- crew_lead assignment shape (dispatch card indicator) ---------------------

class TestAssignmentCrewLeadShape:
    def test_assignment_exposes_crew_lead_primary_name(self, owner_headers):
        r = requests.get(f"{API}/assignments", headers=owner_headers, timeout=15)
        assert r.status_code == 200, r.text
        rows = r.json().get("assignments") or []
        match = next((x for x in rows if x.get("_id") == ASSIGNMENT_ID or x.get("id") == ASSIGNMENT_ID), None)
        assert match, "QA assignment not returned in /api/assignments list"
        cl = match.get("crew_lead") or {}
        assert cl.get("primary_name"), f"crew_lead.primary_name missing: {cl}"
