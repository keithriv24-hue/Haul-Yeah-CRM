"""
Iteration 12 backend tests — Notification Center Alerts module (Phase 2).

Covers:
  1. Role gates on /api/alerts, /api/alerts/unread-count, /api/alerts/read →
     200 for owner/sales/marketing tokens, 403 for crew token.
  2. Owner-only /api/alerts/webhook-info (403 for sales/marketing/crew).
  3. Public /api/webhooks/zapier:
     - 401 with wrong token
     - happy path (review kind) creates zapier-sourced alert
     - new_lead kind pretty-titles via lead_name
     - invalid kind falls back to custom
     - external_id dedupe (send twice → still one)
  4. Per-principal read tracking isolation:
     - fresh webhook alert makes owner+marketing unread ≥ 1
     - owner marks read → owner unread = 0, marketing still ≥ 1
"""
import os
import uuid
import pytest
import requests
from dotenv import load_dotenv
from test_config import OWNER_PASSWORD

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

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
def webhook_url(owner_h):
    r = requests.get(f"{BASE_URL}/api/alerts/webhook-info", headers=owner_h, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("token") and body.get("path") == "/api/webhooks/zapier"
    return f"{BASE_URL}{body['path']}?token={body['token']}"


# --------------------------- role gates ----------------------------

class TestRoleGates:
    def test_owner_can_list_alerts(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/alerts", headers=owner_h, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "alerts" in data and "unread" in data
        assert isinstance(data["alerts"], list)

    def test_sales_can_list_alerts(self, sales_h):
        r = requests.get(f"{BASE_URL}/api/alerts", headers=sales_h, timeout=10)
        assert r.status_code == 200

    def test_marketing_can_list_alerts(self, marketing_h):
        r = requests.get(f"{BASE_URL}/api/alerts", headers=marketing_h, timeout=10)
        assert r.status_code == 200

    def test_crew_forbidden_on_list(self, crew_h):
        r = requests.get(f"{BASE_URL}/api/alerts", headers=crew_h, timeout=10)
        assert r.status_code == 403

    def test_crew_forbidden_on_unread_count(self, crew_h):
        r = requests.get(f"{BASE_URL}/api/alerts/unread-count", headers=crew_h, timeout=10)
        assert r.status_code == 403

    def test_crew_forbidden_on_mark_read(self, crew_h):
        r = requests.post(f"{BASE_URL}/api/alerts/read", headers=crew_h, timeout=10)
        assert r.status_code == 403

    def test_sales_can_mark_read(self, sales_h):
        r = requests.post(f"{BASE_URL}/api/alerts/read", headers=sales_h, timeout=10)
        assert r.status_code == 200
        assert r.json().get("ok") == True

    def test_marketing_can_mark_read(self, marketing_h):
        r = requests.post(f"{BASE_URL}/api/alerts/read", headers=marketing_h, timeout=10)
        assert r.status_code == 200


class TestWebhookInfoAccess:
    def test_owner_gets_webhook_info(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/alerts/webhook-info", headers=owner_h, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("token")
        assert body.get("path") == "/api/webhooks/zapier"
        assert "new_lead" in body.get("kinds", [])

    def test_sales_forbidden_on_webhook_info(self, sales_h):
        r = requests.get(f"{BASE_URL}/api/alerts/webhook-info", headers=sales_h, timeout=10)
        assert r.status_code == 403

    def test_marketing_forbidden_on_webhook_info(self, marketing_h):
        r = requests.get(f"{BASE_URL}/api/alerts/webhook-info", headers=marketing_h, timeout=10)
        assert r.status_code == 403

    def test_crew_forbidden_on_webhook_info(self, crew_h):
        r = requests.get(f"{BASE_URL}/api/alerts/webhook-info", headers=crew_h, timeout=10)
        assert r.status_code == 403


# --------------------------- webhook ----------------------------

class TestZapierWebhook:
    def test_bad_token_401(self):
        r = requests.post(f"{BASE_URL}/api/webhooks/zapier?token=WRONG",
                          json={"kind": "review", "title": "x"}, timeout=10)
        assert r.status_code == 401

    def test_no_token_401(self):
        r = requests.post(f"{BASE_URL}/api/webhooks/zapier",
                          json={"kind": "review", "title": "x"}, timeout=10)
        assert r.status_code == 401

    def test_review_happy_path(self, owner_h, webhook_url):
        title = f"QA Review {uuid.uuid4().hex[:6]}"
        r = requests.post(webhook_url, json={"kind": "review", "title": title, "body": "test-body"}, timeout=10)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") == True

        # Verify it appears in the feed with source=zapier
        r2 = requests.get(f"{BASE_URL}/api/alerts?limit=200", headers=owner_h, timeout=10)
        assert r2.status_code == 200
        alerts = r2.json()["alerts"]
        match = next((a for a in alerts if a["title"] == title), None)
        assert match is not None, f"posted alert '{title}' not found in feed"
        assert match["source"] == "zapier"
        assert match["kind"] == "review"
        assert match["body"] == "test-body"

    def test_new_lead_pretty_title(self, owner_h, webhook_url):
        lead_name = f"QA Lead {uuid.uuid4().hex[:6]}"
        r = requests.post(webhook_url, json={"kind": "new_lead", "lead_name": lead_name}, timeout=10)
        assert r.status_code == 200

        r2 = requests.get(f"{BASE_URL}/api/alerts?limit=200", headers=owner_h, timeout=10)
        alerts = r2.json()["alerts"]
        # title should be "New lead: <lead_name>"
        expected = f"New lead: {lead_name}"
        match = next((a for a in alerts if a["title"] == expected), None)
        assert match is not None, f"expected title '{expected}' not found. sample titles: {[a['title'] for a in alerts[:5]]}"
        assert match["kind"] == "new_lead"
        assert match["lead_name"] == lead_name

    def test_invalid_kind_falls_back_to_custom(self, owner_h, webhook_url):
        title = f"QA Weirdkind {uuid.uuid4().hex[:6]}"
        r = requests.post(webhook_url, json={"kind": "totally_unknown", "title": title}, timeout=10)
        assert r.status_code == 200

        r2 = requests.get(f"{BASE_URL}/api/alerts?limit=200", headers=owner_h, timeout=10)
        match = next((a for a in r2.json()["alerts"] if a["title"] == title), None)
        assert match is not None
        assert match["kind"] == "custom"

    def test_external_id_dedupe(self, owner_h, webhook_url):
        ext_id = f"qa-dedupe-{uuid.uuid4().hex[:8]}"
        title = f"QA Dedupe {ext_id}"
        payload = {"kind": "custom", "title": title, "external_id": ext_id}

        r1 = requests.post(webhook_url, json=payload, timeout=10)
        assert r1.status_code == 200
        r2 = requests.post(webhook_url, json=payload, timeout=10)
        assert r2.status_code == 200

        r3 = requests.get(f"{BASE_URL}/api/alerts?limit=200", headers=owner_h, timeout=10)
        matches = [a for a in r3.json()["alerts"] if a["title"] == title]
        assert len(matches) == 1, f"dedupe failed; got {len(matches)} copies"


# --------------------------- per-principal read tracking ----------------------------

class TestReadTracking:
    def test_read_marker_isolation(self, owner_h, marketing_h, webhook_url):
        """Push a fresh alert; owner marks read → owner unread=0 but marketing still ≥1."""
        # Owner + marketing both mark everything read to reset baseline
        assert requests.post(f"{BASE_URL}/api/alerts/read", headers=owner_h, timeout=10).status_code == 200
        assert requests.post(f"{BASE_URL}/api/alerts/read", headers=marketing_h, timeout=10).status_code == 200

        # Both should now show unread = 0
        u_owner = requests.get(f"{BASE_URL}/api/alerts/unread-count", headers=owner_h, timeout=10).json()["unread"]
        u_mkt = requests.get(f"{BASE_URL}/api/alerts/unread-count", headers=marketing_h, timeout=10).json()["unread"]
        assert u_owner == 0
        assert u_mkt == 0

        # Push one fresh alert via webhook
        title = f"QA Isolation {uuid.uuid4().hex[:6]}"
        r = requests.post(webhook_url, json={"kind": "custom", "title": title}, timeout=10)
        assert r.status_code == 200

        # Both principals should now see unread ≥ 1
        u_owner2 = requests.get(f"{BASE_URL}/api/alerts/unread-count", headers=owner_h, timeout=10).json()["unread"]
        u_mkt2 = requests.get(f"{BASE_URL}/api/alerts/unread-count", headers=marketing_h, timeout=10).json()["unread"]
        assert u_owner2 >= 1, f"owner unread should be ≥1 after new alert, got {u_owner2}"
        assert u_mkt2 >= 1, f"marketing unread should be ≥1 after new alert, got {u_mkt2}"

        # Owner marks read → owner drops to 0, marketing remains ≥ 1 (isolation)
        assert requests.post(f"{BASE_URL}/api/alerts/read", headers=owner_h, timeout=10).status_code == 200
        u_owner3 = requests.get(f"{BASE_URL}/api/alerts/unread-count", headers=owner_h, timeout=10).json()["unread"]
        u_mkt3 = requests.get(f"{BASE_URL}/api/alerts/unread-count", headers=marketing_h, timeout=10).json()["unread"]
        assert u_owner3 == 0, f"owner should be 0 after marking read, got {u_owner3}"
        assert u_mkt3 >= 1, f"marketing should still see the alert as unread, got {u_mkt3} (isolation broken)"

    def test_list_alerts_unread_flag_matches_unread_count(self, sales_h, webhook_url):
        # sales fresh mark-read → all alerts should be flagged unread=false in list
        requests.post(f"{BASE_URL}/api/alerts/read", headers=sales_h, timeout=10)
        data = requests.get(f"{BASE_URL}/api/alerts", headers=sales_h, timeout=10).json()
        unread_from_flags = sum(1 for a in data["alerts"] if a["unread"])
        # Count endpoint
        n = requests.get(f"{BASE_URL}/api/alerts/unread-count", headers=sales_h, timeout=10).json()["unread"]
        # Both should reflect the same baseline (0)
        assert unread_from_flags == 0
        assert n == 0

        # push new alert
        title = f"QA Sales Read Sync {uuid.uuid4().hex[:6]}"
        requests.post(webhook_url, json={"kind": "custom", "title": title}, timeout=10)
        data2 = requests.get(f"{BASE_URL}/api/alerts", headers=sales_h, timeout=10).json()
        n2 = requests.get(f"{BASE_URL}/api/alerts/unread-count", headers=sales_h, timeout=10).json()["unread"]
        unread2 = sum(1 for a in data2["alerts"] if a["unread"])
        assert unread2 >= 1
        assert n2 >= 1
