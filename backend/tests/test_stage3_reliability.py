"""Stage 3 backend regression: helpers, clocks, reliability, accountability & records.

Covers (against the live preview backend + direct Mongo for disposable fixtures):
  - GET  /api/reliability/flags            (owner-only board review + grace_minutes)
  - POST /api/reliability/flags/{id}/resolve  (owner, reason required, audit)
  - GET  /api/crew/my-flags                (crew sees only their own)
  - POST /api/crew/my-flags/{id}/dispute   (crew disputes own flag; 404 on others')
  - POST /api/crew/jobs/{id}/report-problem (any crew on the job; validation)
  - GET  /api/dispatch/board               (reliability[] + per-crew unresolved count)
  - GET  /api/team/members/{id}            (records only for self/owner; not others)

Mutation success paths use a DISPOSABLE flag inserted straight into Mongo and
deleted afterwards, so the seeded QA flags that the Playwright run drives are
left untouched.
"""
import os
import uuid
from datetime import datetime, timezone

import pymongo
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://haul-yeah-staging.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ASSIGNMENT_ID = "6467d362-6511-44a5-8b59-0979845c54a2"
HELPER_ID = "3e8a1121-98ed-4185-85a1-5c4d1a37ba05"
TESTER_ID = "71f3092c-aebf-472f-ab02-d384af51e8f8"

OWNER = {"email": "HaulYeahAdmin", "password": "HaulYeah2026!"}
CREW = {"email": "stage2.crew@haulyeah.test", "password": "Stage2Pass!"}       # Stage2 Tester (Driver / lead)
HELPER = {"email": "stage2.helper@haulyeah.test", "password": "Stage2Pass!"}   # Stage2 Helper


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


@pytest.fixture
def db():
    client = pymongo.MongoClient(os.environ["MONGO_URL"])
    yield client[os.environ["DB_NAME"]]
    client.close()


@pytest.fixture
def temp_flag(db):
    """A disposable OPEN reliability flag on the Helper, cleaned up after the test."""
    fid = f"test-stage3-{uuid.uuid4()}"
    day = datetime.now(timezone.utc).astimezone().date().isoformat()
    db.reliability_flags.insert_one({
        "_id": fid, "assignment_id": ASSIGNMENT_ID, "job_name": "Stage 2 QA — Crew Lead Demo",
        "job_date": day, "user_id": HELPER_ID, "user_name": "Stage2 Helper",
        "type": "early_clock_out", "status": "open",
        "detail": "TEST_stage3 disposable flag — safe to delete.",
        "meta": {}, "created_at": datetime.now(timezone.utc).isoformat(),
        "resolved_by": None, "resolved_at": None, "resolve_reason": None,
        "disputed_at": None, "dispute_reason": None})
    yield fid
    db.reliability_flags.delete_one({"_id": fid})


# --- owner board review -------------------------------------------------------

class TestOwnerFlagReview:
    def test_owner_lists_flags(self, owner_headers):
        r = requests.get(f"{API}/reliability/flags", headers=owner_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "flags" in data and isinstance(data["flags"], list)
        assert isinstance(data.get("grace_minutes"), int)
        assert "open_count" in data

    def test_crew_cannot_list_flags(self, crew_headers):
        r = requests.get(f"{API}/reliability/flags", headers=crew_headers, timeout=15)
        assert r.status_code == 403, r.text

    def test_resolve_requires_reason(self, owner_headers, temp_flag):
        r = requests.post(f"{API}/reliability/flags/{temp_flag}/resolve",
                          headers=owner_headers, json={"reason": "x"}, timeout=15)
        assert r.status_code == 422, r.text

    def test_owner_resolves_flag(self, owner_headers, temp_flag, db):
        r = requests.post(f"{API}/reliability/flags/{temp_flag}/resolve", headers=owner_headers,
                          json={"reason": "Confirmed with the crew — left early with approval."}, timeout=15)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["status"] == "resolved"
        assert out["resolve_reason"]
        doc = db.reliability_flags.find_one({"_id": temp_flag})
        assert doc["status"] == "resolved" and doc["resolved_by"]

    def test_crew_cannot_resolve(self, crew_headers, temp_flag):
        r = requests.post(f"{API}/reliability/flags/{temp_flag}/resolve",
                          headers=crew_headers, json={"reason": "trying to self-resolve"}, timeout=15)
        assert r.status_code == 403, r.text


# --- crew's own flags + dispute ----------------------------------------------

class TestCrewFlags:
    def test_helper_sees_only_own_flags(self, helper_headers):
        r = requests.get(f"{API}/crew/my-flags", headers=helper_headers, timeout=15)
        assert r.status_code == 200, r.text
        flags = r.json().get("flags", [])
        assert all(f.get("user_name") == "Stage2 Helper" for f in flags), flags

    def test_dispute_requires_reason(self, helper_headers, temp_flag):
        r = requests.post(f"{API}/crew/my-flags/{temp_flag}/dispute",
                          headers=helper_headers, json={"reason": "x"}, timeout=15)
        assert r.status_code == 422, r.text

    def test_helper_disputes_own_flag(self, helper_headers, temp_flag, db):
        r = requests.post(f"{API}/crew/my-flags/{temp_flag}/dispute", headers=helper_headers,
                          json={"reason": "I clocked out after we finished loading, not early."}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "disputed"
        assert db.reliability_flags.find_one({"_id": temp_flag})["dispute_reason"]

    def test_tester_cannot_dispute_helpers_flag(self, crew_headers, temp_flag):
        # temp_flag belongs to the Helper; the Tester (different crew) must get 404.
        r = requests.post(f"{API}/crew/my-flags/{temp_flag}/dispute",
                          headers=crew_headers, json={"reason": "not mine but trying"}, timeout=15)
        assert r.status_code == 404, r.text


# --- helper problem report ----------------------------------------------------

class TestReportProblem:
    def test_helper_reports_problem(self, helper_headers):
        r = requests.post(f"{API}/crew/jobs/{ASSIGNMENT_ID}/report-problem", headers=helper_headers,
                          json={"message": "TEST_stage3 — elevator is out of service at pickup."}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_report_problem_validates_message(self, helper_headers):
        r = requests.post(f"{API}/crew/jobs/{ASSIGNMENT_ID}/report-problem",
                          headers=helper_headers, json={"message": "x"}, timeout=15)
        assert r.status_code == 422, r.text

    def test_report_problem_only_for_assigned_crew(self, helper_headers):
        r = requests.post(f"{API}/crew/jobs/not-a-real-assignment/report-problem",
                          headers=helper_headers, json={"message": "should be blocked"}, timeout=15)
        assert r.status_code == 404, r.text


# --- dispatch board reliability payload --------------------------------------

class TestDispatchBoardReliability:
    def test_board_has_reliability_and_crew_flag_counts(self, owner_headers):
        day = datetime.now(timezone.utc).astimezone().date().isoformat()
        r = requests.get(f"{API}/dispatch/board", headers=owner_headers, params={"date": day}, timeout=20)
        assert r.status_code == 200, r.text
        board = r.json()
        assert "reliability" in board and isinstance(board["reliability"], list)
        # every flag surfaced on the board must be unresolved (owner-reviewable)
        assert all(f["status"] in ("open", "unverified", "disputed") for f in board["reliability"])
        for u in board.get("crew", []):
            assert isinstance(u.get("flags"), int)


# --- team member work record (accountability) --------------------------------

class TestWorkRecord:
    def test_owner_sees_records(self, owner_headers):
        r = requests.get(f"{API}/team/members/{TESTER_ID}", headers=owner_headers, timeout=15)
        assert r.status_code == 200, r.text
        rec = r.json().get("records")
        assert rec is not None, "owner should receive the work record"
        assert "jobs" in rec and "documentation" in rec and "flags" in rec

    def test_self_sees_own_records(self, crew_headers):
        r = requests.get(f"{API}/team/members/{TESTER_ID}", headers=crew_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("is_self") is True
        assert data.get("records") is not None

    def test_other_crew_cannot_see_records(self, helper_headers):
        # Helper viewing the Tester's profile must NOT receive the private records block.
        r = requests.get(f"{API}/team/members/{TESTER_ID}", headers=helper_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("is_self") is False
        assert data.get("records") is None
        assert "stats" not in data
