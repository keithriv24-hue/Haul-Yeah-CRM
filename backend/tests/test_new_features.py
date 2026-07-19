"""
Iteration 3 backend tests for the NEW features:
  - Airtable Job Time Log mirror + retry queue (GET /api/timelog/status)
  - Owner Dashboard Work calendar (GET /api/calendar/jobs)
  - Trucks: plate field on POST/PATCH/GET, DELETE endpoint, plate visible on calendar
  - Assignments: job_size accepted & echoed
  - Crew status Complete: delay_factors saved & echoed on calendar
  - Role guards: crew token gets 403 on calendar/jobs and timelog/status
Notes:
  - AIRTABLE_API_KEY is intentionally EMPTY here → syncs must stay pending; that is CORRECT
  - Uses TEST_ prefixed data & cleans up
"""
import os
import time
from datetime import datetime, timezone
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://moving-ops-1.preview.emergentagent.com").rstrip("/")
OWNER_USERNAME = "HaulYeahOwner"
OWNER_PASSWORD = "HaulYeah2026!"
JAVANTE_EMAIL = "javante@haulyeahmoves.com"
JAVANTE_PASSWORD = "JavCrew2026!"


def _login(username, password):
    return requests.post(f"{BASE_URL}/api/auth/login",
                         json={"email": username, "password": password}, timeout=15)


@pytest.fixture(scope="module")
def owner_headers():
    r = _login(OWNER_USERNAME, OWNER_PASSWORD)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def crew_headers():
    r = _login(JAVANTE_EMAIL, JAVANTE_PASSWORD)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# --------- Trucks: plate field on GET, POST(+plate), PATCH(plate), DELETE ---------
class TestTrucksPlateAndDelete:
    def test_list_trucks_exposes_plate(self, owner_headers):
        r = requests.get(f"{BASE_URL}/api/trucks", headers=owner_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "trucks" in d
        for t in d["trucks"]:
            assert "plate" in t, f"truck row missing plate: {t}"

    def test_create_truck_with_plate_then_patch_then_delete(self, owner_headers):
        # CREATE with plate
        payload = {"name": "TEST_QA_Truck_ZZ", "plate": "QAP-9999"}
        r = requests.post(f"{BASE_URL}/api/trucks", json=payload, headers=owner_headers, timeout=15)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        tid = d["id"]
        assert d["name"] == "TEST_QA_Truck_ZZ"
        assert d["plate"] == "QAP-9999"
        assert d["active"] is True

        # VERIFY via list
        r2 = requests.get(f"{BASE_URL}/api/trucks", headers=owner_headers, timeout=15)
        found = [t for t in r2.json()["trucks"] if t["id"] == tid]
        assert found and found[0]["plate"] == "QAP-9999"

        # PATCH plate + rename
        r3 = requests.patch(f"{BASE_URL}/api/trucks/{tid}",
                            json={"name": "TEST_QA_Truck_ZZ_renamed", "plate": "QAP-1111"},
                            headers=owner_headers, timeout=15)
        assert r3.status_code == 200, r3.text
        assert r3.json()["plate"] == "QAP-1111"
        assert r3.json()["name"] == "TEST_QA_Truck_ZZ_renamed"

        # DELETE
        r4 = requests.delete(f"{BASE_URL}/api/trucks/{tid}", headers=owner_headers, timeout=15)
        assert r4.status_code == 200, r4.text
        assert r4.json().get("deleted") is True

        # verify gone
        r5 = requests.get(f"{BASE_URL}/api/trucks", headers=owner_headers, timeout=15)
        assert not [t for t in r5.json()["trucks"] if t["id"] == tid]

    def test_delete_nonexistent_truck_404(self, owner_headers):
        r = requests.delete(f"{BASE_URL}/api/trucks/does-not-exist-{int(time.time())}",
                            headers=owner_headers, timeout=15)
        assert r.status_code == 404


# --------- Timelog sync status (key missing = pending expected) ---------
class TestTimelogStatus:
    def test_owner_can_read_status_and_key_is_missing(self, owner_headers):
        r = requests.get(f"{BASE_URL}/api/timelog/status", headers=owner_headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "configured" in d
        # Preview env has AIRTABLE_API_KEY empty → configured must be False
        assert d["configured"] is False, f"Expected configured=False in preview env, got: {d}"
        assert "pending" in d
        assert isinstance(d["pending"], int)
        assert "pending_jobs" in d
        # pending_jobs[i].error should mention Airtable key missing when any pending exist
        for pj in d["pending_jobs"]:
            assert "error" in pj

    def test_crew_gets_403_on_timelog_status(self, crew_headers):
        r = requests.get(f"{BASE_URL}/api/timelog/status", headers=crew_headers, timeout=15)
        assert r.status_code == 403, r.text


# --------- Calendar jobs endpoint ---------
class TestCalendarJobs:
    def test_owner_can_read_calendar_current_month(self, owner_headers):
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{BASE_URL}/api/calendar/jobs?month={month}",
                         headers=owner_headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["month"] == month
        assert "days" in d
        assert isinstance(d["days"], dict)

    def test_bad_month_param_returns_422(self, owner_headers):
        r = requests.get(f"{BASE_URL}/api/calendar/jobs?month=not-a-month",
                         headers=owner_headers, timeout=15)
        assert r.status_code == 422

    def test_crew_gets_403_on_calendar(self, crew_headers):
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{BASE_URL}/api/calendar/jobs?month={month}",
                         headers=crew_headers, timeout=15)
        assert r.status_code == 403


# --------- Assignment job_size on create/update + calendar echo ---------
class TestAssignmentJobSize:
    def test_create_assignment_with_job_size_and_verify_calendar(self, owner_headers):
        # Get any active truck + Javante id for the assignment
        r = requests.get(f"{BASE_URL}/api/trucks", headers=owner_headers, timeout=15)
        trucks = [t for t in r.json()["trucks"] if t.get("active", True)]
        assert trucks, "need at least one active truck"
        truck_id = trucks[0]["id"]

        users = requests.get(f"{BASE_URL}/api/users", headers=owner_headers, timeout=15).json()["users"]
        javante = next((u for u in users if u["email"].lower() == JAVANTE_EMAIL), None)
        assert javante, "Javante user not found"

        today = datetime.now(timezone.utc).date().isoformat()
        payload = {
            "job_name": "TEST_QA_JobSize_Move",
            "job_date": today,
            "arrival_time": "10:00",
            "start_address": "9 Test Rd, Montclair NJ",
            "end_address": "",
            "truck_id": truck_id,
            "job_size": "3BR",
            "crew": [{"user_id": javante["id"], "position": "Driver"}],
            "ignore_warnings": True,
        }
        r = requests.post(f"{BASE_URL}/api/assignments", json=payload, headers=owner_headers, timeout=20)
        assert r.status_code in (200, 201), r.text
        aid = r.json()["id"]
        assert r.json().get("job_size") == "3BR"

        try:
            # PATCH job_size
            payload["job_size"] = "2BR"
            r2 = requests.patch(f"{BASE_URL}/api/assignments/{aid}", json=payload,
                                headers=owner_headers, timeout=15)
            assert r2.status_code == 200, r2.text
            assert r2.json().get("job_size") == "2BR"

            # Verify on calendar
            month = today[:7]
            r3 = requests.get(f"{BASE_URL}/api/calendar/jobs?month={month}",
                              headers=owner_headers, timeout=15)
            assert r3.status_code == 200
            jobs = r3.json()["days"].get(today, [])
            entry = next((j for j in jobs if j["id"] == aid), None)
            assert entry, f"assignment not found in calendar days[{today}]"
            assert entry["job_size"] == "2BR"
            # Truck plate field should be present (None or string)
            assert "truck_plate" in entry
            # Crew chip carries position
            assert entry["crew"] and entry["crew"][0]["position"] == "Driver"
        finally:
            requests.delete(f"{BASE_URL}/api/assignments/{aid}", headers=owner_headers, timeout=15)

    def test_invalid_job_size_rejected(self, owner_headers):
        r = requests.get(f"{BASE_URL}/api/trucks", headers=owner_headers, timeout=15)
        trucks = [t for t in r.json()["trucks"] if t.get("active", True)]
        truck_id = trucks[0]["id"] if trucks else None
        users = requests.get(f"{BASE_URL}/api/users", headers=owner_headers, timeout=15).json()["users"]
        javante = next((u for u in users if u["email"].lower() == JAVANTE_EMAIL), None)
        payload = {
            "job_name": "TEST_QA_BadSize", "job_date": datetime.now(timezone.utc).date().isoformat(),
            "arrival_time": "10:00", "start_address": "x", "end_address": "", "truck_id": truck_id,
            "job_size": "MegaMansion", "ignore_warnings": True,
            "crew": [{"user_id": javante["id"], "position": "Driver"}] if javante else [],
        }
        r = requests.post(f"{BASE_URL}/api/assignments", json=payload, headers=owner_headers, timeout=15)
        # Backend enforces JOB_SIZES: expect 4xx
        assert r.status_code in (400, 422), r.text


# --------- Crew Complete status accepts delay_factors ---------
class TestDelayFactorsPersist:
    def test_delay_factors_saved_and_shown_on_calendar(self, owner_headers, crew_headers):
        # setup an assignment for Javante today
        r = requests.get(f"{BASE_URL}/api/trucks", headers=owner_headers, timeout=15)
        trucks = [t for t in r.json()["trucks"] if t.get("active", True)]
        truck_id = trucks[0]["id"]
        users = requests.get(f"{BASE_URL}/api/users", headers=owner_headers, timeout=15).json()["users"]
        javante = next(u for u in users if u["email"].lower() == JAVANTE_EMAIL)
        today = datetime.now(timezone.utc).date().isoformat()
        payload = {
            "job_name": "TEST_QA_Delay_Move", "job_date": today, "arrival_time": "09:00",
            "start_address": "1 Test Ln", "end_address": "", "truck_id": truck_id,
            "job_size": "2BR",
            "crew": [{"user_id": javante["id"], "position": "Driver"}],
            "ignore_warnings": True,
        }
        r = requests.post(f"{BASE_URL}/api/assignments", json=payload, headers=owner_headers, timeout=20)
        assert r.status_code in (200, 201), r.text
        aid = r.json()["id"]
        try:
            # Move status through to Complete with delay_factors
            for status in ["En Route", "Arrived", "In Progress"]:
                r = requests.post(f"{BASE_URL}/api/crew/jobs/{aid}/status",
                                  json={"status": status}, headers=crew_headers, timeout=15)
                assert r.status_code == 200, r.text
            r = requests.post(f"{BASE_URL}/api/crew/jobs/{aid}/status",
                              json={"status": "Complete", "notes": "QA delay-factors test",
                                    "delay_factors": ["Stairs", "Traffic", "Bogus_should_drop"]},
                              headers=crew_headers, timeout=15)
            assert r.status_code == 200, r.text

            # verify on calendar
            month = today[:7]
            r3 = requests.get(f"{BASE_URL}/api/calendar/jobs?month={month}",
                              headers=owner_headers, timeout=15)
            entry = next(j for j in r3.json()["days"][today] if j["id"] == aid)
            assert set(entry["delay_factors"]) == {"Stairs", "Traffic"}, entry["delay_factors"]
            assert entry["notes"] == "QA delay-factors test"
        finally:
            requests.delete(f"{BASE_URL}/api/assignments/{aid}", headers=owner_headers, timeout=15)


# --------- Sync queue: after clock-in a pending row appears (key missing) ---------
class TestTimelogQueueAfterPunch:
    def test_pending_grows_after_clock_in_and_clears_on_delete(self, owner_headers, crew_headers):
        # Baseline pending count
        r0 = requests.get(f"{BASE_URL}/api/timelog/status", headers=owner_headers, timeout=15)
        baseline_pending = r0.json()["pending"]

        r = requests.get(f"{BASE_URL}/api/trucks", headers=owner_headers, timeout=15)
        trucks = [t for t in r.json()["trucks"] if t.get("active", True)]
        truck_id = trucks[0]["id"]
        users = requests.get(f"{BASE_URL}/api/users", headers=owner_headers, timeout=15).json()["users"]
        javante = next(u for u in users if u["email"].lower() == JAVANTE_EMAIL)
        today = datetime.now(timezone.utc).date().isoformat()
        payload = {
            "job_name": "TEST_QA_Punch_Move", "job_date": today, "arrival_time": "09:00",
            "start_address": "1 Test Ln", "end_address": "", "truck_id": truck_id,
            "job_size": "2BR",
            "crew": [{"user_id": javante["id"], "position": "Driver"}],
            "ignore_warnings": True,
        }
        r = requests.post(f"{BASE_URL}/api/assignments", json=payload, headers=owner_headers, timeout=20)
        assert r.status_code in (200, 201), r.text
        aid = r.json()["id"]
        try:
            # ensure Javante isn't stuck on the clock from a previous test
            requests.post(f"{BASE_URL}/api/crew/clock-out", json={}, headers=crew_headers, timeout=15)
            # crew clock-in on this assignment (no GPS)
            r = requests.post(f"{BASE_URL}/api/crew/clock-in",
                              json={"assignment_id": aid}, headers=crew_headers, timeout=15)
            assert r.status_code in (200, 201), r.text
            time.sleep(2)  # allow the queued sync_timelog task to run
            r2 = requests.get(f"{BASE_URL}/api/timelog/status", headers=owner_headers, timeout=15)
            d = r2.json()
            assert d["configured"] is False
            assert d["pending"] >= baseline_pending + 1
            # find our pending job (matched by job_name+date since API doesn't return assignment_id)
            ours = [pj for pj in d["pending_jobs"]
                    if pj.get("job_name") == "TEST_QA_Punch_Move" and pj.get("job_date") == today]
            assert ours, f"our assignment not in pending_jobs: {d['pending_jobs']}"
            err = (ours[0].get("error") or "").lower()
            assert ("airtable" in err) or ("key" in err) or ("api_key" in err), \
                f"expected Airtable/key error, got: {ours[0]}"

            # clock out (cleanly close the punch)
            requests.post(f"{BASE_URL}/api/crew/clock-out",
                          json={"assignment_id": aid}, headers=crew_headers, timeout=15)
        finally:
            requests.delete(f"{BASE_URL}/api/assignments/{aid}", headers=owner_headers, timeout=15)

        # After deletion pending count for OUR assignment should be gone
        time.sleep(1)
        r3 = requests.get(f"{BASE_URL}/api/timelog/status", headers=owner_headers, timeout=15)
        d3 = r3.json()
        our_after = [pj for pj in d3["pending_jobs"]
                     if pj.get("job_name") == "TEST_QA_Punch_Move"]
        assert not our_after, f"deleted assignment still pending: {our_after}"


# --------- Deleted truck: past assignment keeps truck name in history ---------
class TestDeletedTruckHistoryPreserved:
    def test_deleted_truck_still_named_on_assignment_row(self, owner_headers):
        # create temp truck + assignment + delete truck → assignment should keep truck_name
        r = requests.post(f"{BASE_URL}/api/trucks",
                          json={"name": "TEST_QA_HistoryTruck", "plate": "HST-1"},
                          headers=owner_headers, timeout=15)
        assert r.status_code in (200, 201), r.text
        tid = r.json()["id"]

        users = requests.get(f"{BASE_URL}/api/users", headers=owner_headers, timeout=15).json()["users"]
        javante = next(u for u in users if u["email"].lower() == JAVANTE_EMAIL)
        today = datetime.now(timezone.utc).date().isoformat()
        payload = {
            "job_name": "TEST_QA_History_Move", "job_date": today, "arrival_time": "09:00",
            "start_address": "x", "end_address": "", "truck_id": tid, "job_size": "2BR",
            "crew": [{"user_id": javante["id"], "position": "Driver"}],
            "ignore_warnings": True,
        }
        r = requests.post(f"{BASE_URL}/api/assignments", json=payload,
                          headers=owner_headers, timeout=20)
        assert r.status_code in (200, 201), r.text
        aid = r.json()["id"]
        assert r.json().get("truck_name") == "TEST_QA_HistoryTruck"

        # Delete the truck
        r2 = requests.delete(f"{BASE_URL}/api/trucks/{tid}", headers=owner_headers, timeout=15)
        assert r2.status_code == 200

        # Verify calendar row still has truck_name (from stored assignment.truck_name)
        try:
            r3 = requests.get(f"{BASE_URL}/api/calendar/jobs?month={today[:7]}",
                              headers=owner_headers, timeout=15)
            entry = next(j for j in r3.json()["days"][today] if j["id"] == aid)
            assert entry["truck_name"] == "TEST_QA_HistoryTruck"
            # plate should be None because truck record is gone
            assert entry["truck_plate"] in (None, "")
        finally:
            requests.delete(f"{BASE_URL}/api/assignments/{aid}", headers=owner_headers, timeout=15)
