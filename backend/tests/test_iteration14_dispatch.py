"""
Iteration 14 backend tests — Dispatch Board (Phase A).

Endpoint under test:
    GET /api/dispatch/board?date=YYYY-MM-DD   (owner-only)

Also exercises the reused PATCH /api/assignments/{id} 409 conflict-warning flow
to verify the dispatch board mutation path.

Covers all bullets from the review-request:
  1. GET /dispatch/board (owner today): shape + counts + QA state
  2. Role gates: crew/sales/marketing ghosts → 403
  3. `behind` logic: future arrival → false; In-Progress → excluded from behind
     and counted in `active`
  4. Crew pool: jobs_today / jobs_week / clocked_in / off fields present;
     Crew1 shows jobs_today=1
  5. Truck pool: Truck 1 on_job = 'QA Dispatch Move — Montclair'
  6. Date param: future empty day → is_today=false, behind all false
  7. PATCH assignment conflict flow (409 warnings) — reused by dispatch UI
"""
import os
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import requests
from dotenv import load_dotenv
from test_config import OWNER_PASSWORD

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
NOW_ET = datetime.now(ZoneInfo("America/New_York"))
TODAY_ET = NOW_ET.strftime("%Y-%m-%d")
FUTURE_DAY = (NOW_ET + timedelta(days=30)).strftime("%Y-%m-%d")
# Hoboken QA job arrives 14:30; board marks it behind 15 min after arrival
HOBOKEN_BEHIND = NOW_ET > NOW_ET.replace(hour=14, minute=45, second=0, microsecond=0)
# An arrival time safely in the future for today (never behind)
FUTURE_ARRIVAL = ((NOW_ET + timedelta(hours=1)).strftime("%H:%M")
                  if NOW_ET.hour < 22 else "23:59")

OWNER = {"email": "HaulYeahAdmin", "password": OWNER_PASSWORD}
SALES = {"email": "TestSalesAdmin", "password": OWNER_PASSWORD}
MARKETING = {"email": "TestMarketingAdmin", "password": OWNER_PASSWORD}
CREW = {"email": "TestCrewAdmin", "password": OWNER_PASSWORD}


def _login(payload):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=payload, timeout=15)
    assert r.status_code == 200, f"login failed for {payload['email']}: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def owner_h(): return _login(OWNER)


@pytest.fixture(scope="module")
def sales_h(): return _login(SALES)


@pytest.fixture(scope="module")
def marketing_h(): return _login(MARKETING)


@pytest.fixture(scope="module")
def crew_h(): return _login(CREW)


@pytest.fixture(scope="module")
def board_today(owner_h):
    r = requests.get(f"{BASE_URL}/api/dispatch/board", headers=owner_h,
                     params={"date": TODAY_ET}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


# ============================================================ 1. Board shape + QA state
class TestDispatchBoardOwner:
    def test_board_top_level_shape(self, board_today):
        for k in ("date", "is_today", "assignments", "crew", "trucks",
                 "revenue_today", "counts"):
            assert k in board_today, f"missing key {k}"

    def test_board_is_today_and_date(self, board_today):
        assert board_today["date"] == TODAY_ET
        assert board_today["is_today"] == True

    def test_board_counts_match_qa_state(self, board_today):
        c = board_today["counts"]
        assert c["total"] == 2
        # Hoboken (Assigned) goes behind only once its 14:30 arrival + grace has passed
        assert c["behind"] >= (1 if HOBOKEN_BEHIND else 0)
        assert c["needs_crew"] == 1

    def test_board_revenue_today_zero_square_live(self, board_today):
        # Square is LIVE — no test invoices → revenue_today expected 0
        assert board_today["revenue_today"] == 0 or board_today["revenue_today"] == 0.0

    def test_qa_assignments_present_and_behind(self, board_today):
        names = {a["job_name"] for a in board_today["assignments"]}
        assert "QA Dispatch Move — Montclair" in names
        assert "QA Dispatch Move — Hoboken" in names
        hoboken = next(a for a in board_today["assignments"] if a["job_name"] == "QA Dispatch Move — Hoboken")
        assert hoboken["behind"] == HOBOKEN_BEHIND
        assert hoboken["exec_status"] == "Assigned"

    def test_montclair_has_crew_and_truck(self, board_today):
        m = next(a for a in board_today["assignments"] if "Montclair" in a["job_name"])
        assert m.get("arrival_time") == "08:00"
        assert m.get("truck_name") == "Truck 1"
        crew = m.get("crew") or []
        assert len(crew) == 1
        assert crew[0]["name"] == "QA Crew One"
        assert crew[0]["position"] == "Driver"

    def test_hoboken_no_crew_no_truck(self, board_today):
        h = next(a for a in board_today["assignments"] if "Hoboken" in a["job_name"])
        assert h.get("arrival_time") == "14:30"
        assert not (h.get("crew") or [])
        assert not h.get("truck_id")


# ============================================================ 2. Role gates
class TestDispatchRoleGates:
    def test_crew_ghost_forbidden(self, crew_h):
        r = requests.get(f"{BASE_URL}/api/dispatch/board", headers=crew_h, timeout=15)
        assert r.status_code == 403

    def test_sales_ghost_forbidden(self, sales_h):
        r = requests.get(f"{BASE_URL}/api/dispatch/board", headers=sales_h, timeout=15)
        assert r.status_code == 403

    def test_marketing_ghost_forbidden(self, marketing_h):
        r = requests.get(f"{BASE_URL}/api/dispatch/board", headers=marketing_h, timeout=15)
        assert r.status_code == 403

    def test_no_auth_forbidden(self):
        r = requests.get(f"{BASE_URL}/api/dispatch/board", timeout=15)
        assert r.status_code == 401


# ============================================================ 3. Crew + Truck pool
class TestCrewAndTruckPool:
    def test_crew_pool_has_crew1_with_jobs_today(self, board_today):
        jav = next((u for u in board_today["crew"] if u["name"] == "QA Crew One"), None)
        assert jav is not None
        for f in ("id", "name", "jobs_today", "jobs_week", "clocked_in", "off"):
            assert f in jav
        assert jav["jobs_today"] == 1
        assert jav["jobs_week"] >= 1
        assert isinstance(jav["clocked_in"], bool)
        assert isinstance(jav["off"], bool)

    def test_crew_pool_has_crew2(self, board_today):
        jun = next((u for u in board_today["crew"] if u["name"] == "QA Crew Two"), None)
        assert jun is not None
        assert jun["jobs_today"] == 0

    def test_truck_pool_truck1_on_montclair(self, board_today):
        t1 = next((t for t in board_today["trucks"] if t["name"] == "Truck 1"), None)
        assert t1 is not None
        assert t1["on_job"] == "QA Dispatch Move — Montclair"

    def test_truck_pool_others_free(self, board_today):
        others = [t for t in board_today["trucks"] if t["name"] != "Truck 1"]
        assert len(others) >= 1
        for t in others:
            assert t["on_job"] is None


# ============================================================ 4. Date param
class TestDateParam:
    def test_future_date_empty_not_today(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/dispatch/board", params={"date": FUTURE_DAY},
                         headers=owner_h, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["date"] == FUTURE_DAY
        assert d["is_today"] == False
        for a in d["assignments"]:
            assert a["behind"] == False, "non-today assignments must never be behind"

    def test_date_param_preserves_pools(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/dispatch/board", params={"date": FUTURE_DAY},
                         headers=owner_h, timeout=15)
        d = r.json()
        # Crew + trucks pool are always present regardless of date
        assert len(d["crew"]) >= 2
        assert len(d["trucks"]) >= 1


# ============================================================ 5. Behind logic dynamic
class TestBehindLogic:
    """Create a temp assignment for today with FUTURE arrival — behind must be false.
    Then flip exec_status to In Progress → excluded from behind, counted in active.
    Clean up at the end.
    """
    tmp_id = None

    def test_create_future_arrival_not_behind(self, owner_h):
        payload = {
            "project_id": None,
            "job_name": f"TEST_dispatch_future_{uuid.uuid4().hex[:6]}",
            "job_date": TODAY_ET,
            "arrival_time": FUTURE_ARRIVAL,  # safely in the future → never behind
            "start_address": "",
            "end_address": "",
            "truck_id": None,
            "job_size": "",
            "crew": [],
            "ignore_warnings": True,
        }
        r = requests.post(f"{BASE_URL}/api/assignments", json=payload,
                          headers=owner_h, timeout=20)
        assert r.status_code in (200, 201), r.text
        created = r.json()
        TestBehindLogic.tmp_id = created.get("id") or created.get("_id")
        assert TestBehindLogic.tmp_id

        # Board should now include it with behind=false
        b = requests.get(f"{BASE_URL}/api/dispatch/board",
                        headers=owner_h, timeout=15).json()
        rec = next((a for a in b["assignments"]
                    if a.get("id", a.get("_id")) == TestBehindLogic.tmp_id), None)
        assert rec is not None
        assert rec["behind"] == False

    def test_in_progress_excluded_from_behind_counted_active(self, owner_h):
        assert TestBehindLogic.tmp_id
        # Force exec_status via direct assignment update; owner PATCH accepts full payload
        # Use the mongo-independent path: PATCH /api/assignments/{id}
        # But exec_status isn't in the PATCH payload. Use crew status POST won't work
        # because owner isn't in crew list. So we use PATCH with fields we know work
        # and then mongo direct — actually simpler: use a dedicated status endpoint
        # or PATCH — server does update via mongo. We'll use a raw mongo update
        # via a helper by hitting the crew endpoint after adding owner to crew.
        # SIMPLER: PATCH accepts exec_status? Check by reading server.
        # Fall back: use mongo directly through backend fixture.
        # Actually — use pymongo directly to mongo_url.
        import pymongo
        client = pymongo.MongoClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        res = db.assignments.update_one(
            {"_id": TestBehindLogic.tmp_id},
            {"$set": {"exec_status": "In Progress"}},
        )
        assert res.matched_count == 1

        b = requests.get(f"{BASE_URL}/api/dispatch/board",
                        headers=owner_h, timeout=15).json()
        rec = next((a for a in b["assignments"]
                    if a.get("id", a.get("_id")) == TestBehindLogic.tmp_id), None)
        assert rec is not None
        assert rec["behind"] == False, "In Progress is never behind"
        assert rec["exec_status"] == "In Progress"
        # counts.active should include this record (>=1)
        assert b["counts"]["active"] >= 1

    def test_cleanup_temp_assignment(self, owner_h):
        if TestBehindLogic.tmp_id:
            r = requests.delete(f"{BASE_URL}/api/assignments/{TestBehindLogic.tmp_id}",
                                headers=owner_h, timeout=15)
            assert r.status_code in (200, 204, 404)

    def test_qa_assignments_still_present_after_cleanup(self, owner_h):
        """Ensure we didn't disturb the two demo QA assignments."""
        b = requests.get(f"{BASE_URL}/api/dispatch/board",
                        headers=owner_h, timeout=15).json()
        names = {a["job_name"] for a in b["assignments"]}
        assert "QA Dispatch Move — Montclair" in names
        assert "QA Dispatch Move — Hoboken" in names
        assert b["counts"]["total"] == 2


# ============================================================ 6. 409 conflict flow (reused by UI)
class TestAssignmentConflictFlow:
    """Assign Crew1 (already on Montclair today) to Hoboken → 409 with warnings."""

    def test_conflict_409_with_warnings(self, owner_h, board_today):
        hob = next(a for a in board_today["assignments"] if "Hoboken" in a["job_name"])
        jav_id = next(u["id"] for u in board_today["crew"] if u["name"] == "QA Crew One")

        payload = {
            "project_id": hob.get("project_id"),
            "job_name": hob["job_name"],
            "job_date": hob["job_date"],
            "arrival_time": hob.get("arrival_time") or "",
            "start_address": hob.get("start_address") or "",
            "end_address": hob.get("end_address") or "",
            "truck_id": hob.get("truck_id"),
            "job_size": hob.get("job_size") or "",
            "crew": [{"user_id": jav_id, "position": "Helper"}],
            "ignore_warnings": False,
        }
        hob_id = hob.get("id") or hob.get("_id")
        r = requests.patch(f"{BASE_URL}/api/assignments/{hob_id}", json=payload,
                          headers=owner_h, timeout=20)
        assert r.status_code == 409, f"expected 409 got {r.status_code}: {r.text}"
        detail = r.json().get("detail", {})
        assert detail.get("error") == "conflicts"
        warns = detail.get("warnings") or []
        assert warns
        # Warning text should mention Crew1 or "already"
        blob = " ".join(warns).lower()
        assert "crew1" in blob or "already" in blob or "double-booked" in blob

    def test_hoboken_still_has_no_crew_after_409(self, owner_h):
        """409 must not have persisted the change."""
        b = requests.get(f"{BASE_URL}/api/dispatch/board",
                        headers=owner_h, timeout=15).json()
        hob = next(a for a in b["assignments"] if "Hoboken" in a["job_name"])
        assert not (hob.get("crew") or []), "409 should NOT have written crew"
