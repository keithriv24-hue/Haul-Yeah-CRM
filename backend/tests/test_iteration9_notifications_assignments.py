"""
Iteration 9 backend tests — team_notifications lifecycle + assignments CRUD
for the project-crew scheduling flow.

Covers:
  1. Full notification lifecycle for POST /api/tasks/{recordId}/audience:
     - owner shares with crew → crew GET /api/team-notifications has 1 item, marketing 0
     - dedupe on re-POST same audience
     - adding marketing later → marketing gets 1
     - reset audience:[] → both groups back to 0
     - owner GET → items: []
  2. POST /api/assignments happy path with crew list (Crew1 as Driver) →
     assignment doc has resolved crew name; crew1's GET /api/crew/my-jobs
     includes it; DELETE cleans up.
  3. GET /api/team-notifications works with sales legacy token (password-only).

All test_notifications + task_meta docs for fake record ids are cleaned up.
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
from test_config import CREW1_PASSWORD, OWNER_EMAIL, OWNER_PASSWORD, SALES_LEGACY_PASSWORD as SALES_LEGACY_PW

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

OWNER_USERNAME = OWNER_EMAIL
OWNER_PASSWORD = OWNER_PASSWORD
SALES_LEGACY_PASSWORD = SALES_LEGACY_PW
CREW1_EMAIL = "qa.crew1@haulyeah.test"
CREW1_PASSWORD = CREW1_PASSWORD


def _login(payload):
    return requests.post(f"{BASE_URL}/api/auth/login", json=payload, timeout=15)


@pytest.fixture(scope="module")
def owner_headers():
    r = _login({"email": OWNER_USERNAME, "password": OWNER_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def crew_headers():
    r = _login({"email": CREW1_EMAIL, "password": CREW1_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def sales_legacy_headers():
    r = _login({"password": SALES_LEGACY_PASSWORD})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "sales"
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def marketing_headers(owner_headers):
    r = requests.post(f"{BASE_URL}/api/auth/switch-role", json={"role": "marketing"},
                      headers=owner_headers, timeout=15)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def mongo_client():
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    yield db
    client.close()


def _get_notif_titles(headers, ntype="task"):
    r = requests.get(f"{BASE_URL}/api/team-notifications", headers=headers, timeout=15)
    assert r.status_code == 200, r.text
    return [i["title"] for i in r.json()["items"] if i["type"] == ntype]


# ---------------------------------------------------------------- 1. Lifecycle
class TestTeamNotificationLifecycle:
    def test_full_task_audience_lifecycle(self, owner_headers, crew_headers,
                                          marketing_headers, mongo_client):
        rec = f"recQA1_{uuid.uuid4().hex[:8]}"
        try:
            # Step 1: owner shares with crew, includes title
            r = requests.post(f"{BASE_URL}/api/tasks/{rec}/audience",
                              json={"audience": ["crew"], "title": "QA Task"},
                              headers=owner_headers, timeout=15)
            assert r.status_code == 200, r.text
            assert r.json()["audience"] == ["crew"]

            # crew has 1 task item with title "QA Task"
            crew_r = requests.get(f"{BASE_URL}/api/team-notifications",
                                  headers=crew_headers, timeout=15)
            assert crew_r.status_code == 200, crew_r.text
            crew_items = [i for i in crew_r.json()["items"]
                          if i["type"] == "task" and i["title"] == "QA Task"]
            assert len(crew_items) == 1, crew_r.json()

            # marketing has 0
            mkt_titles = _get_notif_titles(marketing_headers)
            assert "QA Task" not in mkt_titles

            # Step 2: re-POST same audience — dedupe (still 1)
            r2 = requests.post(f"{BASE_URL}/api/tasks/{rec}/audience",
                               json={"audience": ["crew"], "title": "QA Task"},
                               headers=owner_headers, timeout=15)
            assert r2.status_code == 200
            crew_dup = [i for i in requests.get(
                f"{BASE_URL}/api/team-notifications", headers=crew_headers, timeout=15
            ).json()["items"] if i["type"] == "task" and i["title"] == "QA Task"]
            assert len(crew_dup) == 1, "dedupe failed"

            # Step 3: add marketing
            r3 = requests.post(f"{BASE_URL}/api/tasks/{rec}/audience",
                               json={"audience": ["crew", "marketing"], "title": "QA Task"},
                               headers=owner_headers, timeout=15)
            assert r3.status_code == 200
            assert set(r3.json()["audience"]) == {"crew", "marketing"}
            mkt_titles = _get_notif_titles(marketing_headers)
            assert "QA Task" in mkt_titles

            # Step 4: reset to empty — both groups back to 0
            r4 = requests.post(f"{BASE_URL}/api/tasks/{rec}/audience",
                               json={"audience": [], "title": "QA Task"},
                               headers=owner_headers, timeout=15)
            assert r4.status_code == 200
            assert r4.json()["audience"] == []
            crew_after = [i for i in requests.get(
                f"{BASE_URL}/api/team-notifications", headers=crew_headers, timeout=15
            ).json()["items"] if i["type"] == "task" and i["title"] == "QA Task"]
            assert crew_after == []
            mkt_after = [t for t in _get_notif_titles(marketing_headers) if t == "QA Task"]
            assert mkt_after == []

            # Step 5: owner GET returns items:[]
            owner_r = requests.get(f"{BASE_URL}/api/team-notifications",
                                   headers=owner_headers, timeout=15)
            assert owner_r.status_code == 200
            assert owner_r.json() == {"items": []}
        finally:
            # cleanup
            mongo_client.task_meta.delete_one({"_id": rec})
            mongo_client.team_notifications.delete_many(
                {"key": {"$regex": f"^task:{rec}:"}}
            )

    def test_sales_legacy_token_returns_items(self, owner_headers, sales_legacy_headers,
                                              mongo_client):
        rec = f"recQAS_{uuid.uuid4().hex[:8]}"
        try:
            r0 = requests.post(f"{BASE_URL}/api/tasks/{rec}/audience",
                               json={"audience": ["sales"], "title": "QA Sales Legacy"},
                               headers=owner_headers, timeout=15)
            assert r0.status_code == 200

            # sales legacy password-only login should be able to GET team-notifs (200)
            r = requests.get(f"{BASE_URL}/api/team-notifications",
                             headers=sales_legacy_headers, timeout=15)
            assert r.status_code == 200, r.text
            titles = [i["title"] for i in r.json()["items"] if i["type"] == "task"]
            assert "QA Sales Legacy" in titles
        finally:
            requests.post(f"{BASE_URL}/api/tasks/{rec}/audience",
                          json={"audience": []}, headers=owner_headers, timeout=15)
            mongo_client.task_meta.delete_one({"_id": rec})
            mongo_client.team_notifications.delete_many(
                {"key": {"$regex": f"^task:{rec}:"}}
            )


# ---------------------------------------------------------------- 2. Assignments
class TestAssignmentsCrewFlow:
    def test_create_assignment_with_crew_and_delete(self, owner_headers, crew_headers,
                                                    mongo_client):
        # get crew1's user id
        users_r = requests.get(f"{BASE_URL}/api/users", headers=owner_headers, timeout=15)
        assert users_r.status_code == 200
        users = users_r.json().get("users") or users_r.json()
        crew1 = next((u for u in users if u.get("email") == CREW1_EMAIL), None)
        assert crew1 is not None, "crew1 user not found"
        jav_id = crew1.get("id") or crew1.get("_id")

        payload = {
            "project_id": "recQAPROJ",
            "job_name": "QA Schedule Test",
            "job_date": "2026-08-25",
            "arrival_time": "",
            "start_address": "1 QA St, Atlanta GA",
            "end_address": "2 QA Ave, Atlanta GA",
            "truck_id": None,
            "job_size": "",
            "crew": [{"user_id": jav_id, "position": "Driver"}],
            "ignore_warnings": False,
        }
        r = requests.post(f"{BASE_URL}/api/assignments", json=payload,
                          headers=owner_headers, timeout=20)
        assert r.status_code == 200, r.text
        assignment = r.json()
        aid = assignment["id"]
        try:
            # Assignment doc has crew with resolved name
            assert assignment["job_name"] == "QA Schedule Test"
            assert assignment["job_date"] == "2026-08-25"
            assert len(assignment["crew"]) == 1
            assert assignment["crew"][0]["user_id"] == jav_id
            assert assignment["crew"][0]["position"] == "Driver"
            assert assignment["crew"][0].get("name"), "crew name should be resolved"

            # crew1 GET /api/crew/my-jobs includes it
            my_jobs = requests.get(f"{BASE_URL}/api/crew/my-jobs",
                                   headers=crew_headers, timeout=15)
            assert my_jobs.status_code == 200, my_jobs.text
            jobs = my_jobs.json().get("jobs") or my_jobs.json().get("assignments") or []
            assert any(j.get("id") == aid or j.get("_id") == aid for j in jobs), \
                f"assignment {aid} not in crew1's my-jobs: {jobs}"
        finally:
            # DELETE cleanup
            d = requests.delete(f"{BASE_URL}/api/assignments/{aid}",
                                headers=owner_headers, timeout=15)
            assert d.status_code == 200, d.text
            assert d.json().get("deleted") == True

            # Verify crew1 no longer sees it
            my_jobs2 = requests.get(f"{BASE_URL}/api/crew/my-jobs",
                                    headers=crew_headers, timeout=15)
            if my_jobs2.status_code == 200:
                jobs2 = my_jobs2.json().get("jobs") or my_jobs2.json().get("assignments") or []
                assert not any(j.get("id") == aid or j.get("_id") == aid for j in jobs2)
