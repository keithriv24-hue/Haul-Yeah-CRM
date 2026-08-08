"""Crew module backend tests — users, trucks, assignments, timeclock, notifications, photos.

Uses real MongoDB. Cleans up test-created data at end of session.
Uses -p no:xdist implicitly serial (fixtures share state).
"""
import io
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from test_config import (CREW1_PASSWORD, CREW2_INITIAL_PASSWORD, CREW2_PASSWORD,
                         OWNER_EMAIL, OWNER_PASSWORD, SALES_LEGACY_PASSWORD)

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://haul-yeah-staging.preview.emergentagent.com").rstrip("/")

OWNER_USERNAME = OWNER_EMAIL
OWNER_PASSWORD = OWNER_PASSWORD
LEGACY_OWNER_PASSWORD = OWNER_PASSWORD
CREW1_EMAIL = "qa.crew1@haulyeah.test"
CREW1_PASSWORD = CREW1_PASSWORD
CREW2_EMAIL = "qa.crew2@haulyeah.test"


def _login(email, password):
    payload = {"password": password}
    if email:
        payload["email"] = email
    return requests.post(f"{BASE_URL}/api/auth/login", json=payload, timeout=15)


@pytest.fixture(scope="session")
def owner_token():
    r = _login(OWNER_USERNAME, OWNER_PASSWORD)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}"}


@pytest.fixture(scope="session")
def crew1_token():
    r = _login(CREW1_EMAIL, CREW1_PASSWORD)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def crew1_headers(crew1_token):
    return {"Authorization": f"Bearer {crew1_token}"}


@pytest.fixture(scope="session")
def crew1_user_id(owner_headers):
    r = requests.get(f"{BASE_URL}/api/users", headers=owner_headers, timeout=15)
    for u in r.json()["users"]:
        if u.get("email", "").lower() == CREW1_EMAIL:
            return u["id"]
    pytest.skip("Crew1 user not found")


@pytest.fixture(scope="session")
def first_truck_id(owner_headers):
    r = requests.get(f"{BASE_URL}/api/trucks", headers=owner_headers, timeout=15)
    trucks = r.json()["trucks"]
    for t in trucks:
        if t.get("active", True) and not t.get("name", "").startswith("TEST_"):
            return t["id"]
    return trucks[0]["id"] if trucks else None


@pytest.fixture(scope="session")
def qa_assignment(owner_headers, crew1_user_id, first_truck_id):
    # tomorrow keeps this module clear of the QA Dispatch seed jobs pinned to today
    day = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
    payload = {
        "job_name": "TEST QA Move",
        "job_date": day,
        "arrival_time": "09:00",
        "start_address": "123 Main St, Montclair NJ",
        "end_address": "",
        "truck_id": first_truck_id,
        "crew": [{"user_id": crew1_user_id, "position": "Driver"}],
        "ignore_warnings": True,
    }
    r = requests.post(f"{BASE_URL}/api/assignments", json=payload, headers=owner_headers, timeout=20)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    aid = data["id"]
    yield {"id": aid, "date": day, "crew1_id": crew1_user_id, "truck_id": first_truck_id}
    requests.delete(f"{BASE_URL}/api/assignments/{aid}", headers=owner_headers, timeout=15)


# ------------------ auth tests ------------------
class TestAuth:
    def test_owner_login_by_username(self):
        r = _login(OWNER_USERNAME, OWNER_PASSWORD)
        assert r.status_code == 200
        d = r.json()
        assert d["role"] == "owner"
        assert d["user"]["email"].lower() == OWNER_EMAIL.lower()
        assert d["user"].get("must_change_password") == False

    def test_owner_legacy_login_blank_username(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": LEGACY_OWNER_PASSWORD}, timeout=15)
        assert r.status_code == 200
        assert r.json()["role"] == "owner"

    def test_sales_legacy_login_blank_username(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": SALES_LEGACY_PASSWORD}, timeout=15)
        assert r.status_code == 200
        assert r.json()["role"] == "sales"

    def test_crew1_no_force_change(self):
        r = _login(CREW1_EMAIL, CREW1_PASSWORD)
        assert r.status_code == 200
        d = r.json()
        assert d["role"] == "crew"
        assert d["user"].get("must_change_password") == False

    def test_crew2_still_needs_change_or_already_done(self):
        """Crew2 may still be must_change or already reset by prior E2E. We accept either."""
        r = _login(CREW2_EMAIL, CREW2_INITIAL_PASSWORD)
        if r.status_code == 200:
            assert r.json()["user"].get("must_change_password") == True
        else:
            # E2E already ran and the crew2 account switched to its permanent password
            r2 = _login(CREW2_EMAIL, CREW2_PASSWORD)
            assert r2.status_code == 200

    def test_wrong_password_401(self):
        r = _login(CREW1_EMAIL, "definitely-wrong-nonce-xyz")
        assert r.status_code == 401


# ------------------ users / trucks ------------------
class TestUsersTrucks:
    def test_list_users_owner(self, owner_headers):
        r = requests.get(f"{BASE_URL}/api/users", headers=owner_headers, timeout=15)
        assert r.status_code == 200
        users = r.json()["users"]
        emails = {u.get("email", "").lower() for u in users}
        assert OWNER_EMAIL.lower() in emails
        assert CREW1_EMAIL in emails
        for u in users:
            assert "_id" not in u

    def test_users_forbidden_for_crew(self, crew1_headers):
        r = requests.get(f"{BASE_URL}/api/users", headers=crew1_headers, timeout=15)
        assert r.status_code == 403

    def test_create_reset_deactivate_user(self, owner_headers):
        email = "test_qa_crew_temp@haulyeahmoves.com"
        # cleanup pre-existing
        listing = requests.get(f"{BASE_URL}/api/users", headers=owner_headers, timeout=15).json()["users"]
        for u in listing:
            if u.get("email", "").lower() == email.lower():
                requests.patch(f"{BASE_URL}/api/users/{u['id']}",
                               json={"active": False}, headers=owner_headers, timeout=15)
                requests.delete(f"{BASE_URL}/api/users/{u['id']}", headers=owner_headers, timeout=15)

        temp_pw = f"Tmp{uuid.uuid4().hex[:10]}!A"
        temp_pw2 = f"Tmp{uuid.uuid4().hex[:10]}!B"
        r = requests.post(
            f"{BASE_URL}/api/users",
            json={"name": "QA Temp Crew", "email": email, "password": temp_pw, "role": "crew"},
            headers=owner_headers, timeout=15,
        )
        assert r.status_code in (200, 201), r.text
        uid = r.json()["id"]

        lr = _login(email, temp_pw)
        assert lr.status_code == 200

        # reset password
        rr = requests.patch(f"{BASE_URL}/api/users/{uid}",
                            json={"password": temp_pw2}, headers=owner_headers, timeout=15)
        assert rr.status_code == 200
        lr2 = _login(email, temp_pw2)
        assert lr2.status_code == 200

        # deactivate
        dr = requests.patch(f"{BASE_URL}/api/users/{uid}",
                            json={"active": False}, headers=owner_headers, timeout=15)
        assert dr.status_code == 200
        assert dr.json().get("active") == False
        # remove so it never lingers in the team directory
        requests.delete(f"{BASE_URL}/api/users/{uid}", headers=owner_headers, timeout=15)

    def test_crew_rates_roundtrip(self, owner_headers):
        r = requests.get(f"{BASE_URL}/api/settings/crew-rates", headers=owner_headers, timeout=15)
        assert r.status_code == 200
        original = r.json()
        payload = {"driver": float(original.get("driver", 25)), "helper": float(original.get("helper", 20))}
        w = requests.put(f"{BASE_URL}/api/settings/crew-rates", json=payload, headers=owner_headers, timeout=15)
        assert w.status_code == 200
        got = w.json()
        assert float(got["driver"]) == payload["driver"]
        assert float(got["helper"]) == payload["helper"]

    def test_trucks_list_and_toggle(self, owner_headers):
        r = requests.get(f"{BASE_URL}/api/trucks", headers=owner_headers, timeout=15)
        assert r.status_code == 200
        trucks = r.json()["trucks"]
        assert len(trucks) >= 5  # Trucks 1..5
        add = requests.post(f"{BASE_URL}/api/trucks", json={"name": "TEST_QA_Truck_ZZ"},
                           headers=owner_headers, timeout=15)
        assert add.status_code in (200, 201), add.text
        tid = add.json()["id"]
        t = requests.patch(f"{BASE_URL}/api/trucks/{tid}", json={"active": False},
                          headers=owner_headers, timeout=15)
        assert t.status_code == 200
        assert t.json().get("active") == False


# ------------------ assignments / conflicts ------------------
class TestAssignments:
    def test_create_appears_in_list(self, owner_headers, qa_assignment):
        r = requests.get(f"{BASE_URL}/api/assignments",
                         params={"start": qa_assignment["date"], "end": qa_assignment["date"]},
                         headers=owner_headers, timeout=15)
        assert r.status_code == 200
        assignments = r.json()["assignments"]
        ids = [a["id"] for a in assignments]
        assert qa_assignment["id"] in ids

    def test_edit_arrival_time(self, owner_headers, qa_assignment):
        payload = {
            "job_name": "TEST QA Move",
            "job_date": qa_assignment["date"],
            "arrival_time": "10:00",
            "start_address": "123 Main St, Montclair NJ",
            "end_address": "",
            "truck_id": qa_assignment["truck_id"],
            "crew": [{"user_id": qa_assignment["crew1_id"], "position": "Driver"}],
        }
        r = requests.patch(f"{BASE_URL}/api/assignments/{qa_assignment['id']}",
                          json=payload, headers=owner_headers, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("arrival_time") == "10:00"

    def test_conflict_returns_409(self, owner_headers, qa_assignment):
        payload = {
            "job_name": "TEST QA Conflict",
            "job_date": qa_assignment["date"],
            "arrival_time": "10:00",
            "start_address": "999 Conflict Ave",
            "end_address": "",
            "truck_id": qa_assignment["truck_id"],
            "crew": [{"user_id": qa_assignment["crew1_id"], "position": "Driver"}],
        }
        r = requests.post(f"{BASE_URL}/api/assignments", json=payload, headers=owner_headers, timeout=15)
        assert r.status_code == 409, f"expected 409, got {r.status_code}: {r.text}"
        detail = r.json()["detail"]
        assert isinstance(detail, dict)
        assert detail.get("error") == "conflicts"
        assert len(detail.get("warnings", [])) >= 1

    def test_conflict_force_saves(self, owner_headers, qa_assignment):
        payload = {
            "job_name": "TEST QA Forced Conflict",
            "job_date": qa_assignment["date"],
            "arrival_time": "10:00",
            "start_address": "999 Conflict Ave",
            "end_address": "",
            "truck_id": qa_assignment["truck_id"],
            "crew": [{"user_id": qa_assignment["crew1_id"], "position": "Driver"}],
            "ignore_warnings": True,
        }
        r = requests.post(f"{BASE_URL}/api/assignments", json=payload, headers=owner_headers, timeout=15)
        assert r.status_code in (200, 201), r.text
        aid = r.json()["id"]
        # cleanup
        d = requests.delete(f"{BASE_URL}/api/assignments/{aid}", headers=owner_headers, timeout=15)
        assert d.status_code in (200, 204)


# ------------------ crew workflow ------------------
class TestCrewWorkflow:
    def test_my_jobs_shows_assignment(self, crew1_headers, qa_assignment):
        r = requests.get(f"{BASE_URL}/api/crew/my-jobs", headers=crew1_headers, timeout=15)
        assert r.status_code == 200
        jobs = r.json()["jobs"]
        matching = [j for j in jobs if j.get("id") == qa_assignment["id"]]
        assert matching, f"assignment not found in my-jobs; ids={[j.get('id') for j in jobs]}"
        assert matching[0].get("my_position") == "Driver"

    def test_status_workflow(self, crew1_headers, qa_assignment):
        for status in ("En Route", "Arrived", "In Progress"):
            r = requests.post(
                f"{BASE_URL}/api/crew/jobs/{qa_assignment['id']}/status",
                json={"status": status}, headers=crew1_headers, timeout=15,
            )
            assert r.status_code == 200, f"{status}: {r.status_code} {r.text}"
        r = requests.post(
            f"{BASE_URL}/api/crew/jobs/{qa_assignment['id']}/status",
            json={"status": "Complete", "notes": "QA test completion"},
            headers=crew1_headers, timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("exec_status") == "Complete"

    def test_owner_gets_complete_notification(self, owner_headers):
        r = requests.get(f"{BASE_URL}/api/notifications", headers=owner_headers, timeout=15)
        assert r.status_code == 200
        body = r.json()
        items = body.get("notifications") or body.get("items") or (body if isinstance(body, list) else [])
        text = " ".join(str(n) for n in items).lower()
        assert "complete" in text or "review" in text, f"no complete/review notification in {items[:3]}"

    def test_mark_all_read(self, owner_headers):
        r = requests.post(f"{BASE_URL}/api/notifications/read-all", headers=owner_headers, timeout=15)
        assert r.status_code == 200


# ------------------ photos ------------------
class TestPhotos:
    def test_upload_and_download_photo(self, crew1_headers, crew1_token, qa_assignment):
        png_bytes = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c62f8"
            "cf00000000ffff030000060005e5aeb0cd0000000049454e44ae426082"
        )
        files = {"file": ("test.png", io.BytesIO(png_bytes), "image/png")}
        r = requests.post(
            f"{BASE_URL}/api/crew/jobs/{qa_assignment['id']}/photos",
            headers=crew1_headers, files=files, timeout=30,
        )
        assert r.status_code in (200, 201), r.text
        body = r.json()
        pid = body.get("id") or body.get("photo", {}).get("id")
        assert pid, body

        list_r = requests.get(f"{BASE_URL}/api/jobs/{qa_assignment['id']}/photos",
                              headers=crew1_headers, timeout=15)
        assert list_r.status_code == 200
        photos = list_r.json().get("photos", [])
        assert any(p["id"] == pid for p in photos)

        g = requests.get(f"{BASE_URL}/api/photos/{pid}", params={"auth": crew1_token}, timeout=15)
        assert g.status_code == 200
        assert g.headers.get("Content-Type", "").startswith("image/")


# ------------------ timeclock ------------------
class TestTimeclock:
    def test_clock_in_and_out(self, crew1_headers):
        # make sure nothing open
        requests.post(f"{BASE_URL}/api/crew/clock-out", json={}, headers=crew1_headers, timeout=15)
        r = requests.post(f"{BASE_URL}/api/crew/clock-in", json={}, headers=crew1_headers, timeout=15)
        assert r.status_code in (200, 201), r.text
        o = requests.post(f"{BASE_URL}/api/crew/clock-out", json={}, headers=crew1_headers, timeout=15)
        assert o.status_code == 200, o.text

    def test_owner_timeclock_list(self, owner_headers):
        r = requests.get(f"{BASE_URL}/api/timeclock", headers=owner_headers, timeout=15)
        assert r.status_code == 200
        entries = r.json()["entries"]
        assert isinstance(entries, list)

    def test_csv_export(self, owner_token):
        today = datetime.now(timezone.utc).date().isoformat()
        weekago = (datetime.now(timezone.utc).date() - timedelta(days=7)).isoformat()
        r = requests.get(f"{BASE_URL}/api/timeclock/export",
                        params={"start": weekago, "end": today, "auth": owner_token},
                        timeout=20)
        assert r.status_code == 200, r.text
        assert r.headers.get("Content-Type", "").startswith("text/csv")
        assert "WEEKLY TOTALS" in r.text
        assert "Crew member" in r.text


# ------------------ availability ------------------
class TestAvailability:
    def test_crew_mark_day_off(self, crew1_headers):
        next_week = (datetime.now(timezone.utc).date() + timedelta(days=7)).isoformat()
        r = requests.post(f"{BASE_URL}/api/crew/availability",
                        json={"date": next_week, "available": False},
                        headers=crew1_headers, timeout=15)
        assert r.status_code == 200, r.text
        g = requests.get(f"{BASE_URL}/api/crew/availability", headers=crew1_headers, timeout=15)
        assert g.status_code == 200
        assert g.json()["availability"].get(next_week) == False

    def test_owner_availability_visible(self, owner_headers):
        next_week = (datetime.now(timezone.utc).date() + timedelta(days=7)).isoformat()
        r = requests.get(f"{BASE_URL}/api/availability",
                       params={"start": next_week, "end": next_week},
                       headers=owner_headers, timeout=15)
        assert r.status_code == 200
        assert "availability" in r.json()


# ------------------ owner-only endpoints ------------------
class TestOwnerOnly:
    def test_gps_live(self, owner_headers):
        r = requests.get(f"{BASE_URL}/api/gps/live", headers=owner_headers, timeout=15)
        assert r.status_code == 200

    def test_labor_report(self, owner_headers):
        today = datetime.now(timezone.utc).date().isoformat()
        weekago = (datetime.now(timezone.utc).date() - timedelta(days=7)).isoformat()
        r = requests.get(f"{BASE_URL}/api/reports/labor",
                       params={"start": weekago, "end": today},
                       headers=owner_headers, timeout=15)
        assert r.status_code == 200

    def test_crew_blocked_from_owner(self, crew1_headers):
        for path in ("/api/gps/live", "/api/timeclock", "/api/users", "/api/trucks",
                     "/api/reports/labor", "/api/assignments"):
            r = requests.get(f"{BASE_URL}{path}", headers=crew1_headers, timeout=15)
            assert r.status_code == 403, f"{path}: expected 403, got {r.status_code}"


# ------------------ cleanup ------------------
def test_zzz_cleanup():
    tok = _login(OWNER_USERNAME, OWNER_PASSWORD).json()["token"]
    headers = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f"{BASE_URL}/api/trucks", headers=headers, timeout=15)
    for t in r.json()["trucks"]:
        if t.get("name", "").startswith("TEST_QA_"):
            requests.patch(f"{BASE_URL}/api/trucks/{t['id']}", json={"active": False},
                          headers=headers, timeout=15)
