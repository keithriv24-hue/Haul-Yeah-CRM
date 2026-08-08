"""
Iteration 8 backend tests — To-Do sharing controls + Blog role-gated read access.

Covers:
  1. POST /api/tasks/{recordId}/audience — owner only; input normalisation (filters
     invalid groups, sorts, dedups). Non-owner tokens → 403.
  2. Table-access gating for tasks + blog: non-owner roles no longer 403 at
     ROLE_TABLES check; instead the endpoint hits Airtable → 503 (missing key).
     Marketing still 403 on /api/tables/leads.
  3. Task create/update guards:
       - crew POST /api/tables/tasks → 403 'Only the owner can add these'
       - crew PATCH tasks with a non-status field → 403 'You can only move a task between columns'
       - crew PATCH tasks with only-status on record NOT shared with crew → 403
         'That task isn't shared with your team'
       - After owner shares the record id with crew, same PATCH clears gating
         (then Airtable 503, expected).
  4. Blog update guard: marketing PATCH /api/tables/blog/{id} → 403 'Only the owner can edit blog posts'.

Cleans up any task_meta docs for fake record ids after each test.

Note: AIRTABLE_API_KEY is empty in preview → real Airtable calls return 503; that's expected.
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
from test_config import JAVANTE_PASSWORD, OWNER_EMAIL, OWNER_PASSWORD, SALES_LEGACY_PASSWORD as SALES_LEGACY_PW

# Load env vars from frontend and backend .env files so pytest picks up
# REACT_APP_BACKEND_URL, MONGO_URL, DB_NAME regardless of shell env.
load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

OWNER_USERNAME = OWNER_EMAIL
OWNER_PASSWORD = OWNER_PASSWORD
SALES_LEGACY_PASSWORD = SALES_LEGACY_PW
JAVANTE_EMAIL = "javante@haulyeahmoves.com"
JAVANTE_PASSWORD = JAVANTE_PASSWORD


def _login(payload):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=payload, timeout=15)
    return r


@pytest.fixture(scope="module")
def owner_token():
    r = _login({"email": OWNER_USERNAME, "password": OWNER_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}"}


@pytest.fixture(scope="module")
def sales_headers():
    # Legacy shared-password sales login (no email, password only)
    r = _login({"password": SALES_LEGACY_PASSWORD})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "sales"
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def crew_headers():
    r = _login({"email": JAVANTE_EMAIL, "password": JAVANTE_PASSWORD})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "crew"
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def marketing_headers(owner_token):
    # Owner can switch to marketing view — mints a fresh marketing-role JWT
    r = requests.post(
        f"{BASE_URL}/api/auth/switch-role",
        json={"role": "marketing"},
        headers={"Authorization": f"Bearer {owner_token}"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def mongo_meta():
    """Direct handle to mongo task_meta for cleanup + verification."""
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = MongoClient(mongo_url)
    yield client[db_name].task_meta
    client.close()


# --------------- 1. Audience endpoint ---------------
class TestSetTaskAudience:
    def test_owner_sets_audience_filters_invalid_groups_and_sorts(self, owner_headers, mongo_meta):
        rec = f"recTEST_aud_{uuid.uuid4().hex[:8]}"
        try:
            r = requests.post(
                f"{BASE_URL}/api/tasks/{rec}/audience",
                json={"audience": ["sales", "junk", "crew"]},
                headers=owner_headers, timeout=15,
            )
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["id"] == rec
            # "junk" filtered, sorted alphabetically → ["crew", "sales"]
            assert d["audience"] == ["crew", "sales"], d
            # persistence
            meta = mongo_meta.find_one({"_id": rec})
            assert meta is not None
            assert sorted(meta["audience"]) == ["crew", "sales"]
        finally:
            mongo_meta.delete_one({"_id": rec})

    def test_reset_to_empty_audience(self, owner_headers, mongo_meta):
        rec = f"recTEST_aud_reset_{uuid.uuid4().hex[:8]}"
        try:
            # set
            r1 = requests.post(f"{BASE_URL}/api/tasks/{rec}/audience",
                               json={"audience": ["crew", "sales", "marketing"]},
                               headers=owner_headers, timeout=15)
            assert r1.status_code == 200
            assert set(r1.json()["audience"]) == {"crew", "sales", "marketing"}
            # reset
            r2 = requests.post(f"{BASE_URL}/api/tasks/{rec}/audience",
                               json={"audience": []},
                               headers=owner_headers, timeout=15)
            assert r2.status_code == 200
            assert r2.json()["audience"] == []
            meta = mongo_meta.find_one({"_id": rec})
            assert meta is not None
            assert meta.get("audience") == []
        finally:
            mongo_meta.delete_one({"_id": rec})

    def test_crew_forbidden(self, crew_headers, mongo_meta):
        rec = f"recTEST_aud_fbcrew_{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{BASE_URL}/api/tasks/{rec}/audience",
                          json={"audience": ["crew"]},
                          headers=crew_headers, timeout=15)
        assert r.status_code == 403, r.text
        # No doc should be created for a forbidden call
        assert mongo_meta.find_one({"_id": rec}) is None

    def test_sales_forbidden(self, sales_headers, mongo_meta):
        rec = f"recTEST_aud_fbsales_{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{BASE_URL}/api/tasks/{rec}/audience",
                          json={"audience": ["sales"]},
                          headers=sales_headers, timeout=15)
        assert r.status_code == 403
        assert mongo_meta.find_one({"_id": rec}) is None

    def test_marketing_forbidden(self, marketing_headers, mongo_meta):
        rec = f"recTEST_aud_fbmkt_{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{BASE_URL}/api/tasks/{rec}/audience",
                          json={"audience": ["marketing"]},
                          headers=marketing_headers, timeout=15)
        assert r.status_code == 403
        assert mongo_meta.find_one({"_id": rec}) is None


# --------------- 2. Non-owner table access ---------------
class TestNonOwnerTableAccess:
    @pytest.mark.parametrize("table", ["tasks", "blog"])
    def test_crew_has_table_access_gets_503_no_403(self, crew_headers, table):
        r = requests.get(f"{BASE_URL}/api/tables/{table}", headers=crew_headers, timeout=15)
        # Should NOT be 403 (role has access). Airtable key missing → 503.
        assert r.status_code != 403, r.text
        assert r.status_code == 503, r.text

    @pytest.mark.parametrize("table", ["tasks", "blog"])
    def test_marketing_has_table_access_gets_503_no_403(self, marketing_headers, table):
        r = requests.get(f"{BASE_URL}/api/tables/{table}", headers=marketing_headers, timeout=15)
        assert r.status_code != 403
        assert r.status_code == 503

    @pytest.mark.parametrize("table", ["tasks", "blog"])
    def test_sales_has_table_access_gets_503_no_403(self, sales_headers, table):
        r = requests.get(f"{BASE_URL}/api/tables/{table}", headers=sales_headers, timeout=15)
        assert r.status_code != 403
        assert r.status_code == 503

    def test_marketing_still_403_on_leads(self, marketing_headers):
        r = requests.get(f"{BASE_URL}/api/tables/leads", headers=marketing_headers, timeout=15)
        assert r.status_code == 403, r.text


# --------------- 3. Task create/update guards ---------------
TASK_STATUS_F = "fldIpdRVz51aQaNZh"


class TestTaskGuards:
    def test_crew_cannot_create_task(self, crew_headers):
        r = requests.post(f"{BASE_URL}/api/tables/tasks",
                          json={"fields": {"NAME": "hack"}},
                          headers=crew_headers, timeout=15)
        assert r.status_code == 403, r.text
        assert "owner" in r.text.lower()

    def test_crew_patch_non_status_field_forbidden(self, crew_headers):
        rec = f"recTEST_patch_{uuid.uuid4().hex[:8]}"
        r = requests.patch(f"{BASE_URL}/api/tables/tasks/{rec}",
                           json={"fields": {"fldSOMEOTHER": "x"}},
                           headers=crew_headers, timeout=15)
        assert r.status_code == 403, r.text
        assert "column" in r.text.lower() or "move" in r.text.lower()

    def test_crew_patch_status_only_but_not_shared(self, crew_headers, mongo_meta):
        rec = f"recTEST_notshared_{uuid.uuid4().hex[:8]}"
        # Ensure no meta exists
        mongo_meta.delete_one({"_id": rec})
        try:
            r = requests.patch(f"{BASE_URL}/api/tables/tasks/{rec}",
                               json={"fields": {TASK_STATUS_F: "Done"}},
                               headers=crew_headers, timeout=15)
            assert r.status_code == 403, r.text
            assert "shared" in r.text.lower() or "team" in r.text.lower()
        finally:
            mongo_meta.delete_one({"_id": rec})

    def test_crew_patch_status_after_owner_shares_passes_gating(self, owner_headers, crew_headers, mongo_meta):
        """After owner shares the record with crew, gating passes;
        the downstream Airtable call returns 503 because the key is missing — that's expected."""
        rec = f"recTEST_shared_{uuid.uuid4().hex[:8]}"
        try:
            # Owner shares with crew
            r0 = requests.post(f"{BASE_URL}/api/tasks/{rec}/audience",
                               json={"audience": ["crew"]},
                               headers=owner_headers, timeout=15)
            assert r0.status_code == 200
            assert "crew" in r0.json()["audience"]

            # Crew patches status → gate passes, hits Airtable → 503
            r = requests.patch(f"{BASE_URL}/api/tables/tasks/{rec}",
                               json={"fields": {TASK_STATUS_F: "Done"}},
                               headers=crew_headers, timeout=15)
            # Must NOT be 403 anymore. Airtable returns 503 in preview.
            assert r.status_code != 403, f"Expected gate to pass, got 403: {r.text}"
            assert r.status_code == 503, r.text
        finally:
            # Cleanup: reset audience to []
            requests.post(f"{BASE_URL}/api/tasks/{rec}/audience",
                          json={"audience": []},
                          headers=owner_headers, timeout=15)
            mongo_meta.delete_one({"_id": rec})


# --------------- 4. Blog update guard ---------------
class TestBlogGuard:
    def test_marketing_cannot_patch_blog(self, marketing_headers):
        rec = f"recTEST_blog_{uuid.uuid4().hex[:8]}"
        r = requests.patch(f"{BASE_URL}/api/tables/blog/{rec}",
                           json={"fields": {"anything": "x"}},
                           headers=marketing_headers, timeout=15)
        assert r.status_code == 403, r.text
        assert "owner" in r.text.lower() and "blog" in r.text.lower()

    def test_sales_cannot_patch_blog(self, sales_headers):
        rec = f"recTEST_blog2_{uuid.uuid4().hex[:8]}"
        r = requests.patch(f"{BASE_URL}/api/tables/blog/{rec}",
                           json={"fields": {"anything": "x"}},
                           headers=sales_headers, timeout=15)
        assert r.status_code == 403

    def test_crew_cannot_create_blog(self, crew_headers):
        r = requests.post(f"{BASE_URL}/api/tables/blog",
                          json={"fields": {"anything": "x"}},
                          headers=crew_headers, timeout=15)
        assert r.status_code == 403
