"""Backend tests for the Marketing module (iteration 6).

Covers:
- New user creation without password + login uses default STARTING_PASSWORD
- switch-role to 'marketing' + marketing token permissions matrix
- Ad spend CRUD + validation
- Thresholds get (marketing) / put (owner-only) + non-negative
- Review requests PATCH (review_received, stars 1-5)
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from test_config import OWNER_EMAIL as CONFIG_OWNER_EMAIL, OWNER_PASSWORD, STARTING_PASSWORD

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://haul-yeah-staging.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

OWNER_EMAIL = CONFIG_OWNER_EMAIL
OWNER_PASSWORD = OWNER_PASSWORD
DEFAULT_STARTING = STARTING_PASSWORD


# ---------- Fixtures ----------

@pytest.fixture(scope="session")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="session")
def owner_token():
    r = requests.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}"}


@pytest.fixture(scope="session")
def marketing_token(owner_headers):
    r = requests.post(f"{API}/auth/switch-role", json={"role": "marketing"}, headers=owner_headers, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data
    assert data.get("role") == "marketing"
    return data["token"]


@pytest.fixture(scope="session")
def marketing_headers(marketing_token):
    return {"Authorization": f"Bearer {marketing_token}"}


# ---------- 1. New user creation without password ----------

class TestUserDefaultPassword:
    """POST /api/users without password auto-assigns STARTING_PASSWORD + must_change_password=true."""

    TEST_EMAIL = f"TEST_qamkt_{uuid.uuid4().hex[:8]}@test.com"
    _created_id = None

    def test_create_user_without_password(self, owner_headers, mongo):
        payload = {"name": "TEST QA Marketing", "email": self.TEST_EMAIL, "roles": ["marketing"]}
        r = requests.post(f"{API}/users", json=payload, headers=owner_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("email", "").lower() == self.TEST_EMAIL.lower()
        assert "marketing" in body.get("roles", [])
        assert body.get("must_change_password") == True
        # Save id for cleanup via mongo
        TestUserDefaultPassword._created_id = body.get("id") or body.get("user_id")
        # Verify persisted
        doc = mongo.users.find_one({"email": self.TEST_EMAIL.lower()})
        assert doc is not None
        assert doc.get("must_change_password") == True
        TestUserDefaultPassword._created_id = doc["_id"]

    def test_login_with_default_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": self.TEST_EMAIL, "password": DEFAULT_STARTING}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "token" in body
        assert body.get("user", {}).get("must_change_password") == True

    def test_cleanup_user(self, mongo):
        if TestUserDefaultPassword._created_id:
            mongo.users.delete_one({"_id": TestUserDefaultPassword._created_id})
        # Verify cleaned
        doc = mongo.users.find_one({"email": self.TEST_EMAIL.lower()})
        assert doc is None


# ---------- 2. Marketing token permissions ----------

class TestMarketingPermissions:
    def test_marketing_overview(self, marketing_headers):
        r = requests.get(f"{API}/marketing/overview", params={"start": "2026-01-01", "end": "2026-01-31"},
                         headers=marketing_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "funnel" in data
        assert "totals" in data
        # Airtable is unavailable in preview so airtable_available should be False
        assert data.get("airtable_available") == False

    def test_marketing_ad_spend_list(self, marketing_headers):
        r = requests.get(f"{API}/marketing/ad-spend", headers=marketing_headers, timeout=15)
        assert r.status_code == 200
        assert "entries" in r.json()

    def test_marketing_thresholds_get(self, marketing_headers):
        r = requests.get(f"{API}/marketing/thresholds", headers=marketing_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        for k in ("cplGreen", "cplRed", "bookingGreen", "bookingRed"):
            assert k in data

    def test_marketing_review_requests(self, marketing_headers):
        r = requests.get(f"{API}/review-requests", headers=marketing_headers, timeout=15)
        assert r.status_code == 200
        assert "requests" in r.json()

    def test_marketing_forbidden_margin(self, marketing_headers):
        r = requests.get(f"{API}/marketing/margin", params={"start": "2026-01-01", "end": "2026-01-31"},
                         headers=marketing_headers, timeout=15)
        assert r.status_code == 403

    def test_marketing_forbidden_leads_table(self, marketing_headers):
        r = requests.get(f"{API}/tables/leads", headers=marketing_headers, timeout=15)
        assert r.status_code == 403


# ---------- 3. Ad spend CRUD ----------

class TestAdSpendCRUD:
    _spend_id = None

    def test_create_ad_spend(self, marketing_headers):
        payload = {"platform": "Meta", "campaign": "TEST_Campaign_QA", "date_start": "2026-01-01",
                   "date_end": "2026-01-07", "amount": 250.50}
        r = requests.post(f"{API}/marketing/ad-spend", json=payload, headers=marketing_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["campaign"] == "TEST_Campaign_QA"
        assert data["amount"] == 250.5
        assert "id" in data
        TestAdSpendCRUD._spend_id = data["id"]

    def test_get_after_create(self, marketing_headers):
        r = requests.get(f"{API}/marketing/ad-spend", headers=marketing_headers, timeout=15)
        assert r.status_code == 200
        ids = [e["id"] for e in r.json().get("entries", [])]
        assert TestAdSpendCRUD._spend_id in ids

    def test_create_ad_spend_zero_amount(self, marketing_headers):
        payload = {"platform": "Meta", "campaign": "TEST_Zero", "date_start": "2026-01-01",
                   "date_end": "2026-01-07", "amount": 0}
        r = requests.post(f"{API}/marketing/ad-spend", json=payload, headers=marketing_headers, timeout=15)
        assert r.status_code == 422

    def test_create_ad_spend_missing_campaign(self, marketing_headers):
        payload = {"platform": "Meta", "campaign": "   ", "date_start": "2026-01-01",
                   "date_end": "2026-01-07", "amount": 100}
        r = requests.post(f"{API}/marketing/ad-spend", json=payload, headers=marketing_headers, timeout=15)
        assert r.status_code == 422

    def test_create_ad_spend_bad_date_range(self, marketing_headers):
        payload = {"platform": "Meta", "campaign": "TEST_BadDate", "date_start": "2026-01-10",
                   "date_end": "2026-01-01", "amount": 100}
        r = requests.post(f"{API}/marketing/ad-spend", json=payload, headers=marketing_headers, timeout=15)
        assert r.status_code == 422

    def test_delete_ad_spend(self, marketing_headers):
        assert TestAdSpendCRUD._spend_id, "Need created spend id"
        r = requests.delete(f"{API}/marketing/ad-spend/{TestAdSpendCRUD._spend_id}",
                            headers=marketing_headers, timeout=15)
        assert r.status_code == 200
        # Confirm gone
        r2 = requests.get(f"{API}/marketing/ad-spend", headers=marketing_headers, timeout=15)
        ids = [e["id"] for e in r2.json().get("entries", [])]
        assert TestAdSpendCRUD._spend_id not in ids


# ---------- 4. Thresholds owner-only ----------

class TestThresholds:
    def test_put_thresholds_marketing_forbidden(self, marketing_headers):
        payload = {"cplGreen": 10, "cplRed": 30, "bookingGreen": 0.3, "bookingRed": 0.1}
        r = requests.put(f"{API}/marketing/thresholds", json=payload, headers=marketing_headers, timeout=15)
        assert r.status_code == 403

    def test_put_thresholds_owner_success(self, owner_headers):
        payload = {"cplGreen": 12, "cplRed": 35, "bookingGreen": 0.35, "bookingRed": 0.12}
        r = requests.put(f"{API}/marketing/thresholds", json=payload, headers=owner_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["cplGreen"] == 12
        # Verify via GET
        r2 = requests.get(f"{API}/marketing/thresholds", headers=owner_headers, timeout=15)
        assert r2.json()["cplGreen"] == 12

    def test_put_thresholds_negative_rejected(self, owner_headers):
        payload = {"cplGreen": -1, "cplRed": 30, "bookingGreen": 0.3, "bookingRed": 0.1}
        r = requests.put(f"{API}/marketing/thresholds", json=payload, headers=owner_headers, timeout=15)
        assert r.status_code == 422


# ---------- 5. Review requests PATCH ----------

class TestReviewRequestsPatch:
    def _get_existing(self, headers):
        r = requests.get(f"{API}/review-requests", headers=headers, timeout=15)
        assert r.status_code == 200
        entries = r.json().get("requests", [])
        return entries

    def test_patch_review_received_and_stars(self, marketing_headers):
        entries = self._get_existing(marketing_headers)
        assert len(entries) >= 1, "Need at least 1 existing review request"
        rid = entries[0]["id"]
        # Set received=true
        r1 = requests.patch(f"{API}/review-requests/{rid}", json={"review_received": True},
                            headers=marketing_headers, timeout=15)
        assert r1.status_code == 200, r1.text
        assert r1.json().get("review", {}).get("received") == True
        # Set stars=4
        r2 = requests.patch(f"{API}/review-requests/{rid}", json={"stars": 4},
                            headers=marketing_headers, timeout=15)
        assert r2.status_code == 200, r2.text
        assert r2.json().get("review", {}).get("stars") == 4
        # Verify persisted via GET
        entries2 = self._get_existing(marketing_headers)
        found = next(x for x in entries2 if x["id"] == rid)
        assert found.get("review", {}).get("stars") == 4

    def test_patch_stars_out_of_range(self, marketing_headers):
        entries = self._get_existing(marketing_headers)
        assert entries
        rid = entries[0]["id"]
        r = requests.patch(f"{API}/review-requests/{rid}", json={"stars": 6},
                           headers=marketing_headers, timeout=15)
        assert r.status_code == 422
        r0 = requests.patch(f"{API}/review-requests/{rid}", json={"stars": 0},
                            headers=marketing_headers, timeout=15)
        assert r0.status_code == 422
