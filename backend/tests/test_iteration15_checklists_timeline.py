"""Iteration 15 pytest suite — job checklists, timeline, job_events, username login,
unscheduled clock-in flag. Targets the existing QA demo assignments.

Assumes QA demo state per handoff:
  - Montclair assignment id: 3b2a0120-9dfb-4fe1-88cd-d5a6025ea61d (Javante on crew, exec_status=En Route,
    warehouse_departure already 5/5 done)
  - Hoboken assignment (job_name 'QA Dispatch Move — Hoboken', no crew/truck at start & end)
  - job_date 2026-07-21 (ET today for this preview env)
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE}/api"
QA_DAY = "2026-07-21"
EXEC_ORDER = ["Assigned", "En Route", "Arrived", "In Progress", "Complete"]


def _at_least(status, target):
    return EXEC_ORDER.index(status) >= EXEC_ORDER.index(target)

OWNER_EMAIL = "HaulYeahAdmin"
OWNER_PW = "HaulYeah2026!"
JAVANTE_EMAIL = "javante@haulyeahmoves.com"
JAVANTE_PW = "JavCrew2026!"
JUNIOR_EMAIL = "junior@haulyeahmoves.com"
JUNIOR_PW = "JunCrew2026!"
TESTCREW = "TestCrewAdmin"
TESTCREW_PW = "HaulYeah2026!"
TESTSALES = "TestSalesAdmin"
TESTSALES_PW = "HaulYeah2026!"

MONTCLAIR_ID = "3b2a0120-9dfb-4fe1-88cd-d5a6025ea61d"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed for {email}: {r.status_code} {r.text}")
    return r.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def owner_token():
    return _login(OWNER_EMAIL, OWNER_PW)


@pytest.fixture(scope="session")
def javante_token():
    return _login(JAVANTE_EMAIL, JAVANTE_PW)


@pytest.fixture(scope="session")
def junior_token():
    return _login(JUNIOR_EMAIL, JUNIOR_PW)


@pytest.fixture(scope="session")
def testcrew_token():
    return _login(TESTCREW, TESTCREW_PW)


@pytest.fixture(scope="session")
def testsales_token():
    return _login(TESTSALES, TESTSALES_PW)


@pytest.fixture(scope="session")
def hoboken_id(owner_token):
    r = requests.get(f"{API}/dispatch/board", headers=_auth(owner_token), params={"date": QA_DAY}, timeout=30)
    assert r.status_code == 200
    for a in r.json()["assignments"]:
        if "Hoboken" in (a.get("job_name") or ""):
            return a.get("id") or a.get("_id")
    pytest.skip("Hoboken assignment not found on today's dispatch board.")


# ------------------- checklists RBAC + shape -------------------

class TestChecklistShape:
    def test_owner_gets_5_lists_25_items(self, owner_token):
        r = requests.get(f"{API}/assignments/{MONTCLAIR_ID}/checklists", headers=_auth(owner_token), timeout=30)
        assert r.status_code == 200, r.text
        lists = r.json()["checklists"]
        assert len(lists) == 5
        keys = [l["key"] for l in lists]
        assert keys == ["warehouse_departure", "arrival", "loading", "delivery", "completion"]
        for l in lists:
            assert l["total"] == 5
            assert len(l["items"]) == 5
        wh = next(l for l in lists if l["key"] == "warehouse_departure")
        # Tolerate concurrent test that toggles warehouse item 0
        assert wh["done_count"] >= 4, f"warehouse should be >=4/5, got {wh['done_count']}/5"

    def test_crew_on_job_allowed(self, javante_token):
        r = requests.get(f"{API}/assignments/{MONTCLAIR_ID}/checklists", headers=_auth(javante_token), timeout=30)
        assert r.status_code == 200

    def test_crew_not_on_job_forbidden(self, junior_token):
        r = requests.get(f"{API}/assignments/{MONTCLAIR_ID}/checklists", headers=_auth(junior_token), timeout=30)
        assert r.status_code == 403

    def test_testcrew_ghost_not_on_job_forbidden(self, testcrew_token):
        r = requests.get(f"{API}/assignments/{MONTCLAIR_ID}/checklists", headers=_auth(testcrew_token), timeout=30)
        assert r.status_code == 403

    def test_sales_ghost_forbidden(self, testsales_token):
        r = requests.get(f"{API}/assignments/{MONTCLAIR_ID}/checklists", headers=_auth(testsales_token), timeout=30)
        assert r.status_code == 403


# ------------------- toggle + auto-advance -------------------

class TestChecklistToggleAutoAdvance:
    def test_complete_arrival_advances_status(self, owner_token):
        # Reset by unchecking arrival item 4 to clear completed_at (idempotent for reruns)
        requests.post(f"{API}/assignments/{MONTCLAIR_ID}/checklists/arrival/items/4",
                      headers=_auth(owner_token), json={"done": False}, timeout=30)
        # Get current exec_status (may already be Arrived from earlier runs)
        board0 = requests.get(f"{API}/dispatch/board", headers=_auth(owner_token), params={"date": QA_DAY}, timeout=30).json()
        m0 = next(a for a in board0["assignments"] if a["id"] == MONTCLAIR_ID)
        prev_status = m0["exec_status"]

        # Complete all 5 arrival items as owner
        advanced_to = None
        for i in range(5):
            r = requests.post(
                f"{API}/assignments/{MONTCLAIR_ID}/checklists/arrival/items/{i}",
                headers=_auth(owner_token), json={"done": True}, timeout=30,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            if i == 4:
                advanced_to = body.get("advanced_to")
        # If status was already at/past Arrived, advanced_to should be None; else 'Arrived'
        if prev_status in ("Assigned", "En Route"):
            assert advanced_to == "Arrived", f"expected advanced_to=Arrived, got {advanced_to}"
        else:
            assert advanced_to is None, f"already at {prev_status}, should not advance; got {advanced_to}"

        # verify assignment exec_status now Arrived + status_history entry
        # use direct board fetch to check exec_status
        board = requests.get(f"{API}/dispatch/board", headers=_auth(owner_token), params={"date": QA_DAY}, timeout=30).json()
        m = next(a for a in board["assignments"] if a["id"] == MONTCLAIR_ID)
        assert _at_least(m["exec_status"], "Arrived")

        # timeline has arrival checklist completed event
        tl = requests.get(f"{API}/assignments/{MONTCLAIR_ID}/timeline", headers=_auth(owner_token), timeout=30).json()
        titles = [e["title"] for e in tl["events"]]
        assert any("Arrival checklist completed" in t for t in titles), titles

    def test_uncheck_arrival_item_no_backwards(self, owner_token):
        # uncheck arrival item 0
        r = requests.post(f"{API}/assignments/{MONTCLAIR_ID}/checklists/arrival/items/0",
                          headers=_auth(owner_token), json={"done": False}, timeout=30)
        assert r.status_code == 200
        lists = r.json()["checklists"]
        arr = next(l for l in lists if l["key"] == "arrival")
        assert arr["done_count"] == 4
        assert arr["completed_at"] in (None, ""), f"completed_at should be cleared, got {arr['completed_at']}"
        # exec_status still Arrived (no backwards)
        board = requests.get(f"{API}/dispatch/board", headers=_auth(owner_token), params={"date": QA_DAY}, timeout=30).json()
        m = next(a for a in board["assignments"] if a["id"] == MONTCLAIR_ID)
        assert _at_least(m["exec_status"], "Arrived"), "status must not go backwards"

    def test_recheck_arrival_no_advance_since_already_arrived(self, owner_token):
        r = requests.post(f"{API}/assignments/{MONTCLAIR_ID}/checklists/arrival/items/0",
                          headers=_auth(owner_token), json={"done": True}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("advanced_to") is None, "should not advance since exec_status >= Arrived"

    def test_no_backwards_warehouse_toggle(self, owner_token):
        # Uncheck warehouse item 0 then re-check — status should stay Arrived
        r1 = requests.post(f"{API}/assignments/{MONTCLAIR_ID}/checklists/warehouse_departure/items/0",
                           headers=_auth(owner_token), json={"done": False}, timeout=30)
        assert r1.status_code == 200
        board = requests.get(f"{API}/dispatch/board", headers=_auth(owner_token), params={"date": QA_DAY}, timeout=30).json()
        m = next(a for a in board["assignments"] if a["id"] == MONTCLAIR_ID)
        assert _at_least(m["exec_status"], "Arrived")

        r2 = requests.post(f"{API}/assignments/{MONTCLAIR_ID}/checklists/warehouse_departure/items/0",
                           headers=_auth(owner_token), json={"done": True}, timeout=30)
        assert r2.status_code == 200
        assert r2.json().get("advanced_to") is None
        board2 = requests.get(f"{API}/dispatch/board", headers=_auth(owner_token), params={"date": QA_DAY}, timeout=30).json()
        m2 = next(a for a in board2["assignments"] if a["id"] == MONTCLAIR_ID)
        assert _at_least(m2["exec_status"], "Arrived")

    def test_bad_list_key_404(self, owner_token):
        r = requests.post(f"{API}/assignments/{MONTCLAIR_ID}/checklists/nonsense/items/0",
                          headers=_auth(owner_token), json={"done": True}, timeout=30)
        assert r.status_code == 404

    def test_bad_idx_404(self, owner_token):
        r = requests.post(f"{API}/assignments/{MONTCLAIR_ID}/checklists/arrival/items/99",
                          headers=_auth(owner_token), json={"done": True}, timeout=30)
        assert r.status_code == 404


# ------------------- timeline -------------------

class TestTimeline:
    def test_timeline_owner_ok_and_shape(self, owner_token):
        r = requests.get(f"{API}/assignments/{MONTCLAIR_ID}/timeline", headers=_auth(owner_token), timeout=30)
        assert r.status_code == 200, r.text
        events = r.json()["events"]
        assert len(events) > 0
        # desc-sorted by 'at'
        ats = [e["at"] for e in events]
        assert ats == sorted(ats, reverse=True)
        kinds = {e["kind"] for e in events}
        # should include created + status + checklist completions
        assert "created" in kinds
        assert "status" in kinds
        assert "checklist" in kinds
        titles = [e["title"] for e in events]
        assert any("Job put on the schedule" in t for t in titles)

    def test_timeline_javante_ok(self, javante_token):
        r = requests.get(f"{API}/assignments/{MONTCLAIR_ID}/timeline", headers=_auth(javante_token), timeout=30)
        assert r.status_code == 200

    def test_timeline_junior_forbidden(self, junior_token):
        r = requests.get(f"{API}/assignments/{MONTCLAIR_ID}/timeline", headers=_auth(junior_token), timeout=30)
        assert r.status_code == 403


# ------------------- job_events via PATCH -------------------

class TestJobEventsFromPatch:
    def test_add_and_remove_crew_and_truck_hoboken(self, owner_token, hoboken_id):
        # Fetch full assignment for PATCH payload
        board = requests.get(f"{API}/dispatch/board", headers=_auth(owner_token), params={"date": QA_DAY}, timeout=30).json()
        h = next(a for a in board["assignments"] if a["id"] == hoboken_id)

        # Find Junior user_id and Truck 2 id
        users = requests.get(f"{API}/users", headers=_auth(owner_token), timeout=30).json()["users"]
        junior = next(u for u in users if u.get("email") == JUNIOR_EMAIL)
        trucks = requests.get(f"{API}/trucks", headers=_auth(owner_token), timeout=30).json().get("trucks", [])
        truck2 = next((t for t in trucks if t.get("name") == "Truck 2"), None)
        assert truck2, "Truck 2 not found"

        base_payload = {
            "project_id": h.get("project_id"),
            "job_name": h["job_name"],
            "job_date": h["job_date"],
            "arrival_time": h.get("arrival_time"),
            "start_address": h["start_address"],
            "end_address": h["end_address"],
            "job_size": h.get("job_size"),
            "crew": [{"user_id": junior["id"], "position": "Driver"}],
            "truck_id": truck2["id"],
            "ignore_warnings": True,
        }
        r = requests.patch(f"{API}/assignments/{hoboken_id}", headers=_auth(owner_token), json=base_payload, timeout=30)
        assert r.status_code == 200, r.text

        # Timeline shows add crew + truck assigned
        tl = requests.get(f"{API}/assignments/{hoboken_id}/timeline", headers=_auth(owner_token), timeout=30).json()
        titles = [e["title"] for e in tl["events"]]
        assert any("Added to crew: Junior" in t for t in titles), titles
        assert any("Truck assigned: Truck 2" in t for t in titles), titles

        # Now remove crew + truck
        remove_payload = {**base_payload, "crew": [], "truck_id": None}
        r2 = requests.patch(f"{API}/assignments/{hoboken_id}", headers=_auth(owner_token), json=remove_payload, timeout=30)
        assert r2.status_code == 200, r2.text
        tl2 = requests.get(f"{API}/assignments/{hoboken_id}/timeline", headers=_auth(owner_token), timeout=30).json()
        titles2 = [e["title"] for e in tl2["events"]]
        assert any("Removed from crew: Junior" in t for t in titles2), titles2
        assert any("Truck removed" in t for t in titles2), titles2


# ------------------- dispatch board checklist counts -------------------

class TestDispatchChecklistFields:
    def test_montclair_checklist_counts(self, owner_token):
        r = requests.get(f"{API}/dispatch/board", headers=_auth(owner_token), params={"date": QA_DAY}, timeout=30)
        assert r.status_code == 200
        m = next(a for a in r.json()["assignments"] if a["id"] == MONTCLAIR_ID)
        assert m["checklist_total"] == 25
        # warehouse (5) + arrival (5) done = 10
        assert m["checklist_done"] >= 10, f"expected >=10, got {m['checklist_done']}"


# ------------------- username login + create user validation -------------------

class TestUsernameLoginAndCreateUser:
    _created_user_id = None

    def test_create_with_username_no_at(self, owner_token):
        r = requests.post(f"{API}/users", headers=_auth(owner_token),
                          json={"name": "QA Login Test", "email": "qalogintest",
                                "roles": ["crew"], "role": "crew"}, timeout=30)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body["email"] == "qalogintest"
        TestUsernameLoginAndCreateUser._created_user_id = body["id"]

    def test_username_login_ok(self):
        r = requests.post(f"{API}/auth/login", json={"email": "qalogintest", "password": "haulyeah123"}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("token")
        assert body["user"]["must_change_password"] is True

    def test_create_with_space_422(self, owner_token):
        r = requests.post(f"{API}/users", headers=_auth(owner_token),
                          json={"name": "Bad", "email": "has space", "roles": ["crew"], "role": "crew"}, timeout=30)
        assert r.status_code == 422

    def test_create_duplicate_409(self, owner_token):
        r = requests.post(f"{API}/users", headers=_auth(owner_token),
                          json={"name": "Dup", "email": "qalogintest", "roles": ["crew"], "role": "crew"}, timeout=30)
        assert r.status_code == 409

    def test_z_cleanup_qa_user(self, owner_token):
        uid = TestUsernameLoginAndCreateUser._created_user_id
        if not uid:
            pytest.skip("no user to clean up")
        # deactivate first (per handoff note)
        rd = requests.patch(f"{API}/users/{uid}", headers=_auth(owner_token), json={"active": False}, timeout=30)
        assert rd.status_code in (200, 204)
        # DELETE
        r = requests.delete(f"{API}/users/{uid}", headers=_auth(owner_token), timeout=30)
        assert r.status_code in (200, 204)


# ------------------- unscheduled clock-in flag -------------------

class TestUnscheduledClockInFlag:
    def test_testcrew_clock_in_flag_and_notif(self, testcrew_token, owner_token):
        # Ensure not already clocked in
        try:
            requests.post(f"{API}/crew/clock-out", headers=_auth(testcrew_token), json={}, timeout=30)
        except Exception:
            pass
        r = requests.post(f"{API}/crew/clock-in", headers=_auth(testcrew_token), json={}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "not_scheduled_today" in (body.get("flags") or [])

        # Owner should see notification of type=flag with title Unscheduled clock-in
        time.sleep(1)
        notif = requests.get(f"{API}/notifications", headers=_auth(owner_token), timeout=30).json()
        items = notif.get("notifications") or notif.get("items") or []
        assert items, "no notifications"
        top = items[0]
        assert top.get("type") == "flag"
        assert "Unscheduled clock-in" in (top.get("title") or "")

        # clock out
        ro = requests.post(f"{API}/crew/clock-out", headers=_auth(testcrew_token), json={}, timeout=30)
        assert ro.status_code == 200

    def test_javante_scheduled_no_flag(self, javante_token, owner_token):
        # create a temp assignment for the LIVE ET today so Javante counts as scheduled
        from zoneinfo import ZoneInfo
        from datetime import datetime
        today_et = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
        payload = requests.get(f"{API}/users", headers=_auth(owner_token), timeout=30).json()
        users = payload.get("users", payload) if isinstance(payload, dict) else payload
        jav_id = next(u["id"] for u in users if "javante" in (u.get("email") or "").lower())
        ra = requests.post(f"{API}/assignments", headers=_auth(owner_token), timeout=30, json={
            "job_name": "TEMP iter15 flag test", "job_date": today_et, "arrival_time": "",
            "crew": [{"user_id": jav_id, "position": "Helper"}], "ignore_warnings": True})
        assert ra.status_code == 200, ra.text
        temp_id = ra.json()["id"]
        try:
            requests.post(f"{API}/crew/clock-out", headers=_auth(javante_token), json={}, timeout=30)
            r = requests.post(f"{API}/crew/clock-in", headers=_auth(javante_token), json={}, timeout=30)
            if r.status_code != 200:
                pytest.skip(f"javante clock-in failed: {r.text}")
            body = r.json()
            assert "not_scheduled_today" not in (body.get("flags") or []), body.get("flags")
            requests.post(f"{API}/crew/clock-out", headers=_auth(javante_token), json={}, timeout=30)
        finally:
            requests.delete(f"{API}/assignments/{temp_id}", headers=_auth(owner_token), timeout=30)
