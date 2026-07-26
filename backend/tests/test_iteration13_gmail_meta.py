"""
Iteration 13 backend tests — Notification Center Phases 3+4
(Gmail inboxes + Meta social feed).

Covers all bullet points from the review-request:
  1. /api/meta/status   — role gates + owner-only redirect_uri
  2. /api/meta/connect  — 422 for owner (unconfigured), 403 for others
  3. /api/meta/feed     — owner+marketing 200; sales+crew 403
  4. /api/meta/refresh  — owner+marketing 404 (no tokens); sales+crew 403
  5. /api/meta/disconnect — owner 404 (nothing); non-owner 403
  6. Public /api/meta/oauth/callback — RedirectResponse to /settings?meta=denied|expired
     (302/307), NOT 401/500
  7. /api/gmail/status  — owner sees both mailboxes + redirect_uri;
     sales/marketing see ONLY contact mailbox, no redirect_uri; crew 403
  8. /api/gmail/connect/contact — owner 422 (Google unconfigured); sales 403
  9. /api/gmail/contact/messages — owner 409 (mailbox not connected), NOT 500
 10. Regression: /api/alerts still works (owner/sales/marketing 200, crew 403)
"""
import os
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


# ================================================================ META STATUS

class TestMetaStatus:
    def test_owner_gets_status_with_redirect_uri(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/meta/status", headers=owner_h, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["configured"] == False
        assert d["connected"] == False
        assert d["pages"] == []
        assert "redirect_uri" in d
        assert d["redirect_uri"].endswith("/api/meta/oauth/callback")

    def test_marketing_gets_status_without_redirect_uri(self, marketing_h):
        r = requests.get(f"{BASE_URL}/api/meta/status", headers=marketing_h, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["configured"] == False
        assert d["connected"] == False
        assert d["pages"] == []
        assert "redirect_uri" not in d, "marketing should NOT see redirect_uri"

    def test_sales_forbidden_on_status(self, sales_h):
        r = requests.get(f"{BASE_URL}/api/meta/status", headers=sales_h, timeout=10)
        assert r.status_code == 403

    def test_crew_forbidden_on_status(self, crew_h):
        r = requests.get(f"{BASE_URL}/api/meta/status", headers=crew_h, timeout=10)
        assert r.status_code == 403


# ================================================================ META CONNECT

class TestMetaConnect:
    def test_owner_unconfigured_returns_422(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/meta/connect", headers=owner_h, timeout=10)
        assert r.status_code == 422
        assert "Meta App ID" in r.json().get("detail", "")

    def test_marketing_forbidden_on_connect(self, marketing_h):
        r = requests.get(f"{BASE_URL}/api/meta/connect", headers=marketing_h, timeout=10)
        assert r.status_code == 403

    def test_sales_forbidden_on_connect(self, sales_h):
        r = requests.get(f"{BASE_URL}/api/meta/connect", headers=sales_h, timeout=10)
        assert r.status_code == 403

    def test_crew_forbidden_on_connect(self, crew_h):
        r = requests.get(f"{BASE_URL}/api/meta/connect", headers=crew_h, timeout=10)
        assert r.status_code == 403


# ================================================================ META FEED

class TestMetaFeed:
    def test_owner_gets_empty_feed(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/meta/feed", headers=owner_h, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d
        assert isinstance(d["items"], list)

    def test_marketing_gets_empty_feed(self, marketing_h):
        r = requests.get(f"{BASE_URL}/api/meta/feed", headers=marketing_h, timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json()["items"], list)

    def test_sales_forbidden_on_feed(self, sales_h):
        r = requests.get(f"{BASE_URL}/api/meta/feed", headers=sales_h, timeout=10)
        assert r.status_code == 403

    def test_crew_forbidden_on_feed(self, crew_h):
        r = requests.get(f"{BASE_URL}/api/meta/feed", headers=crew_h, timeout=10)
        assert r.status_code == 403


# ================================================================ META REFRESH

class TestMetaRefresh:
    def test_owner_no_tokens_returns_404(self, owner_h):
        r = requests.post(f"{BASE_URL}/api/meta/refresh", headers=owner_h, timeout=10)
        assert r.status_code == 404
        assert "Facebook" in r.json().get("detail", "")

    def test_marketing_no_tokens_returns_404(self, marketing_h):
        r = requests.post(f"{BASE_URL}/api/meta/refresh", headers=marketing_h, timeout=10)
        assert r.status_code == 404

    def test_sales_forbidden_on_refresh(self, sales_h):
        r = requests.post(f"{BASE_URL}/api/meta/refresh", headers=sales_h, timeout=10)
        assert r.status_code == 403

    def test_crew_forbidden_on_refresh(self, crew_h):
        r = requests.post(f"{BASE_URL}/api/meta/refresh", headers=crew_h, timeout=10)
        assert r.status_code == 403


# ================================================================ META DISCONNECT

class TestMetaDisconnect:
    def test_owner_nothing_connected_returns_404(self, owner_h):
        r = requests.post(f"{BASE_URL}/api/meta/disconnect", headers=owner_h, timeout=10)
        assert r.status_code == 404

    def test_marketing_forbidden_on_disconnect(self, marketing_h):
        r = requests.post(f"{BASE_URL}/api/meta/disconnect", headers=marketing_h, timeout=10)
        assert r.status_code == 403

    def test_sales_forbidden_on_disconnect(self, sales_h):
        r = requests.post(f"{BASE_URL}/api/meta/disconnect", headers=sales_h, timeout=10)
        assert r.status_code == 403

    def test_crew_forbidden_on_disconnect(self, crew_h):
        r = requests.post(f"{BASE_URL}/api/meta/disconnect", headers=crew_h, timeout=10)
        assert r.status_code == 403


# ================================================================ META OAUTH CALLBACK (public, no auth)

class TestMetaOAuthCallback:
    def test_no_params_redirects_to_denied(self):
        r = requests.get(f"{BASE_URL}/api/meta/oauth/callback", timeout=10, allow_redirects=False)
        assert r.status_code in (302, 307), f"expected redirect, got {r.status_code}"
        loc = r.headers.get("location", "")
        assert "meta=denied" in loc, f"expected meta=denied in location, got {loc}"

    def test_bad_state_redirects_to_expired(self):
        r = requests.get(
            f"{BASE_URL}/api/meta/oauth/callback?code=fake&state=bogus_state_xyz",
            timeout=10, allow_redirects=False,
        )
        assert r.status_code in (302, 307), f"expected redirect, got {r.status_code}"
        loc = r.headers.get("location", "")
        assert "meta=expired" in loc, f"expected meta=expired in location, got {loc}"

    def test_error_param_redirects_to_denied(self):
        r = requests.get(
            f"{BASE_URL}/api/meta/oauth/callback?error=user_denied",
            timeout=10, allow_redirects=False,
        )
        assert r.status_code in (302, 307)
        assert "meta=denied" in r.headers.get("location", "")


# ================================================================ GMAIL STATUS

class TestGmailStatus:
    def test_owner_sees_both_mailboxes_with_redirect_uri(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/gmail/status", headers=owner_h, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["configured"] == False
        assert "redirect_uri" in d
        assert d["redirect_uri"].endswith("/api/gmail/oauth/callback")
        ids = {mb["id"] for mb in d["mailboxes"]}
        assert ids == {"contact", "owner"}, f"owner should see both mailboxes, got {ids}"
        for mb in d["mailboxes"]:
            assert mb["connected"] == False

    def test_sales_sees_only_contact_no_redirect_uri(self, sales_h):
        r = requests.get(f"{BASE_URL}/api/gmail/status", headers=sales_h, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "redirect_uri" not in d
        ids = [mb["id"] for mb in d["mailboxes"]]
        assert ids == ["contact"], f"sales should see only contact mailbox, got {ids}"

    def test_marketing_sees_only_contact_no_redirect_uri(self, marketing_h):
        r = requests.get(f"{BASE_URL}/api/gmail/status", headers=marketing_h, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "redirect_uri" not in d
        ids = [mb["id"] for mb in d["mailboxes"]]
        assert ids == ["contact"]

    def test_crew_forbidden_on_gmail_status(self, crew_h):
        r = requests.get(f"{BASE_URL}/api/gmail/status", headers=crew_h, timeout=10)
        assert r.status_code == 403


# ================================================================ GMAIL CONNECT

class TestGmailConnect:
    def test_owner_connect_contact_unconfigured_422(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/gmail/connect/contact", headers=owner_h, timeout=10)
        assert r.status_code == 422
        assert "Google" in r.json().get("detail", "")

    def test_owner_connect_owner_mailbox_unconfigured_422(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/gmail/connect/owner", headers=owner_h, timeout=10)
        assert r.status_code == 422

    def test_sales_forbidden_on_connect(self, sales_h):
        r = requests.get(f"{BASE_URL}/api/gmail/connect/contact", headers=sales_h, timeout=10)
        assert r.status_code == 403

    def test_marketing_forbidden_on_connect(self, marketing_h):
        r = requests.get(f"{BASE_URL}/api/gmail/connect/contact", headers=marketing_h, timeout=10)
        assert r.status_code == 403

    def test_crew_forbidden_on_connect(self, crew_h):
        r = requests.get(f"{BASE_URL}/api/gmail/connect/contact", headers=crew_h, timeout=10)
        assert r.status_code == 403


# ================================================================ GMAIL MESSAGES (must NOT 500)

class TestGmailMessages:
    def test_owner_contact_messages_not_connected_409(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/gmail/contact/messages", headers=owner_h, timeout=15)
        assert r.status_code == 409, f"expected 409 (mailbox not connected), got {r.status_code} {r.text[:200]}"
        assert "connected" in r.json().get("detail", "").lower()

    def test_owner_owner_mailbox_messages_not_connected_409(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/gmail/owner/messages", headers=owner_h, timeout=15)
        assert r.status_code == 409

    def test_sales_owner_mailbox_returns_404_not_authorized(self, sales_h):
        # sales isn't in the 'owner' mailbox roles list → 404 (per _mailbox_or_404)
        r = requests.get(f"{BASE_URL}/api/gmail/owner/messages", headers=sales_h, timeout=15)
        assert r.status_code == 404


# ================================================================ REGRESSION — alerts still work

class TestAlertsRegression:
    def test_owner_alerts(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/alerts", headers=owner_h, timeout=10)
        assert r.status_code == 200
        assert "alerts" in r.json()

    def test_sales_alerts(self, sales_h):
        r = requests.get(f"{BASE_URL}/api/alerts", headers=sales_h, timeout=10)
        assert r.status_code == 200

    def test_marketing_alerts(self, marketing_h):
        r = requests.get(f"{BASE_URL}/api/alerts", headers=marketing_h, timeout=10)
        assert r.status_code == 200

    def test_crew_forbidden_alerts(self, crew_h):
        r = requests.get(f"{BASE_URL}/api/alerts", headers=crew_h, timeout=10)
        assert r.status_code == 403
