"""Iteration 22 regression tests for the pure-refactor changes:
  * auth: decode_token / principal_from_token_string (helper split)
  * server.py: build_quote_pdf split into _pdf_amounts/_pdf_header/_pdf_customer_block/
      _pdf_line_items/_pdf_totals/_pdf_footer
  * server.py: apply_invoice_to_jobs split into _maybe_fire_capi_purchase / _capi_lead_and_quote
      with PAYMENT_PENDING branching inverted (early-return)
  * server.py: _job_doc_from_invoice split into _job_customer / _job_paid_in_full
  * meta_capi.py: build_user_data (hashed + raw sub-helpers) and send_event (payload + auth + post)

All tests are behavioural-parity checks — output/side-effects must match pre-refactor.
"""
import asyncio
import hashlib
import os
import sys
from typing import Dict

import pytest
import requests

# Backend URL from the frontend env, per project rules
from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

sys.path.insert(0, "/app/backend")
from test_config import GHOST_PASSWORD, OWNER_EMAIL, OWNER_PASSWORD  # noqa: E402


def _auth(t: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _login(email: str, pw: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json().get("token")
    assert isinstance(tok, str) and len(tok) > 20
    return tok


@pytest.fixture(scope="module")
def owner_token() -> str:
    return _login(OWNER_EMAIL, OWNER_PASSWORD)


@pytest.fixture(scope="module")
def crew_ghost_token() -> str:
    return _login("TestCrewAdmin", GHOST_PASSWORD)


# ---------------- Auth regression (decode_token / principal_from_token_string) ----------------

class TestAuthRegression:
    def test_owner_login_and_me(self, owner_token):
        r = requests.get(f"{API}/auth/me", headers=_auth(owner_token), timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert j.get("role") == "owner"

    def test_garbage_token_rejected(self):
        r = requests.get(f"{API}/auth/me",
                         headers={"Authorization": "Bearer this.is.not.a.jwt"}, timeout=15)
        assert r.status_code == 401

    def test_wrong_signature_rejected(self):
        # valid header + payload but signature bytes replaced
        import base64
        h = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
        p = base64.urlsafe_b64encode(b'{"sub":"attacker","role":"owner","type":"access","exp":9999999999}'
                                     ).rstrip(b"=").decode()
        forged = f"{h}.{p}.AAAA"
        r = requests.get(f"{API}/auth/me", headers=_auth(forged), timeout=15)
        assert r.status_code == 401

    def test_expired_token_rejected(self):
        # forge an expired token signed with wrong key — must 401 regardless
        import jwt
        expired = jwt.encode({"sub": "x", "role": "owner", "type": "access", "exp": 1},
                             "not-the-real-key", algorithm="HS256")
        r = requests.get(f"{API}/auth/me", headers=_auth(expired), timeout=15)
        assert r.status_code == 401

    def test_no_auth_header_401(self):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401


# ---------------- Role enforcement regression (crew ghost blocked from owner-only) ----------------

class TestRoleEnforcement:
    def test_crew_ghost_login(self, crew_ghost_token):
        r = requests.get(f"{API}/auth/me", headers=_auth(crew_ghost_token), timeout=15)
        assert r.status_code == 200
        assert r.json().get("role") == "crew"

    def test_crew_ghost_blocked_from_meta_status(self, crew_ghost_token):
        # /api/meta/status is owner+sales only
        r = requests.get(f"{API}/meta/status", headers=_auth(crew_ghost_token), timeout=15)
        assert r.status_code == 403

    def test_crew_ghost_blocked_from_owner_users(self, crew_ghost_token):
        # /api/users is owner-only
        r = requests.get(f"{API}/users", headers=_auth(crew_ghost_token), timeout=15)
        assert r.status_code in (401, 403)


# ---------------- Quote PDF regression (build_quote_pdf + helpers) ----------------

class TestQuotePdfRegression:
    def test_save_and_fetch_quote_pdf(self, owner_token):
        # ensure lead_quotes doc exists via the authenticated PUT endpoint
        lead_id = "TEST_iter22_pdf_lead"
        breakdown = {
            "customerName": "Regression Rita",
            "customerPhone": "",  # skip SMS
            "customerEmail": "rita@example.com",
            "fromAddress": "1 Test St",
            "toAddress": "2 Test Ave",
            "moveDate": "2026-02-15",
            "finalQuote": 850.00,
            "quoteLow": 800,
            "quoteHigh": 850,
            "deposit": 212.50,
            "lines": [
                {"name": "Crew Labor", "amount": 585.0},
                {"name": "Travel Fee", "amount": 125.0},
                {"name": "Piano — Upright", "amount": 140.0},
            ],
        }
        r = requests.put(f"{API}/quotes/{lead_id}", headers=_auth(owner_token),
                         json={"breakdown": breakdown}, timeout=15)
        assert r.status_code == 200, r.text
        token = r.json().get("token")
        assert token and isinstance(token, str)

        # fetch the public PDF
        r2 = requests.get(f"{API}/quote-pdf/{token}", timeout=20)
        assert r2.status_code == 200, r2.text[:200]
        assert r2.headers.get("content-type", "").startswith("application/pdf")
        body = r2.content
        assert body[:4] == b"%PDF", f"missing PDF magic: {body[:20]!r}"
        assert len(body) > 1500, f"PDF suspiciously small: {len(body)} bytes"

    def test_pdf_amounts_helper_math(self):
        # direct import to verify pure math helper still balances lines and computes deposit
        from server import _pdf_amounts  # type: ignore
        amt = _pdf_amounts({"finalQuote": 850, "deposit": 212.50,
                            "lines": [{"name": "A", "amount": 400}, {"name": "B", "amount": 449.99}]})
        assert amt["final"] == 850.0
        # lines must sum exactly to final after drift correction
        assert round(sum(l["amount"] for l in amt["lines"]), 2) == 850.0
        assert amt["deposit"] == 212.50
        assert amt["balance"] == round(850 - 212.50, 2)
        assert amt["dep_pct"] == 25

    def test_pdf_amounts_empty_lines_fallback(self):
        from server import _pdf_amounts  # type: ignore
        amt = _pdf_amounts({"finalQuote": 500})
        assert amt["lines"] == [{"name": "Local Moving Service — flat rate", "amount": 500.0}]
        assert amt["deposit"] == 125.0  # 25% default
        assert amt["dep_pct"] == 25

    def test_bad_quote_token_404(self):
        r = requests.get(f"{API}/quote-pdf/deadbeef_no_such_token", timeout=15)
        assert r.status_code == 404


# ---------------- Meta CAPI regression (build_user_data + send_event) ----------------

class TestMetaCapiRegression:
    def test_meta_status_owner_ok(self, owner_token):
        r = requests.get(f"{API}/meta/status", headers=_auth(owner_token), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "configured" in j
        assert "connected" in j
        assert isinstance(j.get("pages", []), list)

    def test_build_user_data_hashes_pii(self):
        from meta_capi import build_user_data  # type: ignore
        ud = build_user_data(
            email="Foo.Bar@Example.COM",
            phone="(212) 555-1234",
            first_name="Foo",
            last_name="Bar",
            zip_code="07001",
            external_id="lead-abc",
            fbc="fb.1.1700000000000.abc",
            fbp="fb.1.1700000000000.999",
            client_ip="1.2.3.4",
            user_agent="Mozilla/5.0",
        )
        # hashed PII
        assert ud["em"] == [hashlib.sha256(b"foo.bar@example.com").hexdigest()]
        assert ud["ph"] == [hashlib.sha256(b"12125551234").hexdigest()]
        assert ud["fn"] == [hashlib.sha256(b"foo").hexdigest()]
        assert ud["ln"] == [hashlib.sha256(b"bar").hexdigest()]
        assert ud["zp"] == [hashlib.sha256(b"07001").hexdigest()]
        assert ud["external_id"] == [hashlib.sha256(b"lead-abc").hexdigest()]
        # raw identifiers preserved
        assert ud["fbc"] == "fb.1.1700000000000.abc"
        assert ud["fbp"] == "fb.1.1700000000000.999"
        assert ud["client_ip_address"] == "1.2.3.4"
        assert ud["client_user_agent"] == "Mozilla/5.0"

    def test_build_user_data_fbclid_reconstruction(self):
        from meta_capi import build_user_data  # type: ignore
        ud = build_user_data(fbclid="IwAR_test")
        assert ud["fbc"].startswith("fb.1.") and ud["fbc"].endswith(".IwAR_test")

    def test_build_user_data_drops_empty_fields(self):
        from meta_capi import build_user_data  # type: ignore
        ud = build_user_data(email=None, phone="", first_name=None)
        assert ud == {}  # nothing to send

    def test_send_event_skips_when_unconfigured(self, monkeypatch):
        # in the preview env META_DATASET_ID/token are unset -> skipped
        monkeypatch.setenv("META_DATASET_ID", "")
        monkeypatch.setenv("META_CAPI_ACCESS_TOKEN", "")
        from meta_capi import send_event  # type: ignore
        out = asyncio.run(send_event("Lead", {"em": ["hashed"]}, event_id="evt1"))
        assert out == {"skipped": True}


# ---------------- Invoice-to-jobs regression (apply_invoice_to_jobs + helpers) ----------------

class TestInvoiceToJobsRegression:
    def test_payment_pending_non_deposit_marks_pending_only(self, monkeypatch):
        """PAYMENT_PENDING + non-deposit purpose -> early return after _mark_job_payment_pending.
        No CAPI, no ensure_job_for_deposit, no _mark_job_paid_in_full."""
        import server as srv  # type: ignore
        calls = []

        async def _fake_mark_pending(inv):
            calls.append(("pending", inv["invoice_id"]))

        async def _fake_capi(inv):
            calls.append(("capi", inv["invoice_id"]))

        async def _fake_ensure(inv, mark_full=False, notify_owner=True):
            calls.append(("ensure", inv["invoice_id"]))

        async def _fake_paid_full(inv, notify_owner):
            calls.append(("paid_full", inv["invoice_id"]))

        async def _fake_alert(inv, purpose):
            calls.append(("alert", inv["invoice_id"]))

        monkeypatch.setattr(srv, "_mark_job_payment_pending", _fake_mark_pending)
        monkeypatch.setattr(srv, "_maybe_fire_capi_purchase", _fake_capi)
        monkeypatch.setattr(srv, "ensure_job_for_deposit", _fake_ensure)
        monkeypatch.setattr(srv, "_mark_job_paid_in_full", _fake_paid_full)
        monkeypatch.setattr(srv, "_alert_payment_landed", _fake_alert)
        # _infer_purpose for a non-deposit final invoice returns "full" or "final";
        # force it to non-deposit for this test:
        monkeypatch.setattr(srv, "_infer_purpose", lambda inv: "final")

        inv = {"invoice_id": "TEST_pending_final", "status": "PAYMENT_PENDING", "amount": 500, "lead_id": None}
        asyncio.run(srv.apply_invoice_to_jobs(inv, notify_owner=False))
        kinds = [c[0] for c in calls]
        assert kinds == ["pending"], f"unexpected side-effects on PAYMENT_PENDING non-deposit: {calls}"

    def test_payment_pending_deposit_no_op(self, monkeypatch):
        """PAYMENT_PENDING + deposit -> pure early return, no calls at all."""
        import server as srv  # type: ignore
        calls = []
        for name in ("_mark_job_payment_pending", "_maybe_fire_capi_purchase",
                     "ensure_job_for_deposit", "_mark_job_paid_in_full", "_alert_payment_landed"):
            async def _rec(*a, __n=name, **kw):
                calls.append(__n)
            monkeypatch.setattr(srv, name, _rec)
        monkeypatch.setattr(srv, "_infer_purpose", lambda inv: "deposit")

        inv = {"invoice_id": "TEST_pending_deposit", "status": "PAYMENT_PENDING", "amount": 200, "lead_id": None}
        asyncio.run(srv.apply_invoice_to_jobs(inv, notify_owner=False))
        assert calls == [], f"PAYMENT_PENDING deposit must be a no-op, got {calls}"

    def test_paid_deposit_calls_ensure_job(self, monkeypatch):
        """PAID + deposit -> alert, capi, ensure_job_for_deposit(mark_full=False)."""
        import server as srv  # type: ignore
        calls = []

        async def _rec_alert(inv, purpose): calls.append(("alert", purpose))
        async def _rec_capi(inv): calls.append(("capi",))
        async def _rec_ensure(inv, mark_full=False, notify_owner=True):
            calls.append(("ensure", mark_full))
        async def _rec_paid(inv, notify_owner): calls.append(("paid_full",))
        async def _rec_pending(inv): calls.append(("pending",))

        monkeypatch.setattr(srv, "_alert_payment_landed", _rec_alert)
        monkeypatch.setattr(srv, "_maybe_fire_capi_purchase", _rec_capi)
        monkeypatch.setattr(srv, "ensure_job_for_deposit", _rec_ensure)
        monkeypatch.setattr(srv, "_mark_job_paid_in_full", _rec_paid)
        monkeypatch.setattr(srv, "_mark_job_payment_pending", _rec_pending)
        monkeypatch.setattr(srv, "_infer_purpose", lambda inv: "deposit")

        inv = {"invoice_id": "TEST_paid_deposit", "status": "PAID", "amount": 200, "lead_id": None}
        asyncio.run(srv.apply_invoice_to_jobs(inv, notify_owner=False))
        assert ("alert", "deposit") in calls
        assert ("capi",) in calls
        assert ("ensure", False) in calls
        assert ("paid_full",) not in calls  # deposit returns early before paid_full

    def test_paid_full_calls_ensure_with_mark_full(self, monkeypatch):
        """PAID + full -> ensure_job_for_deposit(mark_full=True), returns before _mark_job_paid_in_full."""
        import server as srv  # type: ignore
        calls = []
        async def _rec_alert(inv, purpose): calls.append("alert")
        async def _rec_capi(inv): calls.append("capi")
        async def _rec_ensure(inv, mark_full=False, notify_owner=True):
            calls.append(("ensure", mark_full))
        async def _rec_paid(inv, notify_owner): calls.append("paid_full")
        async def _rec_pending(inv): calls.append("pending")
        async def _rec_commission(lid, tag): calls.append(("commission", lid, tag))

        monkeypatch.setattr(srv, "_alert_payment_landed", _rec_alert)
        monkeypatch.setattr(srv, "_maybe_fire_capi_purchase", _rec_capi)
        monkeypatch.setattr(srv, "ensure_job_for_deposit", _rec_ensure)
        monkeypatch.setattr(srv, "_mark_job_paid_in_full", _rec_paid)
        monkeypatch.setattr(srv, "_mark_job_payment_pending", _rec_pending)
        monkeypatch.setattr(srv, "mark_lead_commission_payment", _rec_commission)
        monkeypatch.setattr(srv, "_infer_purpose", lambda inv: "full")

        inv = {"invoice_id": "TEST_paid_full", "status": "PAID", "amount": 800, "lead_id": "LEAD-X"}
        asyncio.run(srv.apply_invoice_to_jobs(inv, notify_owner=False))
        assert ("ensure", True) in calls
        assert "paid_full" not in calls  # 'full' path returns after ensure_job_for_deposit

    def test_paid_non_deposit_non_full_calls_mark_paid_in_full(self, monkeypatch):
        """PAID + purpose='final' (non-deposit/non-full) -> falls through to _mark_job_paid_in_full."""
        import server as srv  # type: ignore
        calls = []
        async def _rec_alert(inv, purpose): calls.append("alert")
        async def _rec_capi(inv): calls.append("capi")
        async def _rec_ensure(inv, mark_full=False, notify_owner=True): calls.append("ensure")
        async def _rec_paid(inv, notify_owner): calls.append("paid_full")
        async def _rec_pending(inv): calls.append("pending")
        async def _rec_commission(lid, tag): calls.append(("commission", tag))

        monkeypatch.setattr(srv, "_alert_payment_landed", _rec_alert)
        monkeypatch.setattr(srv, "_maybe_fire_capi_purchase", _rec_capi)
        monkeypatch.setattr(srv, "ensure_job_for_deposit", _rec_ensure)
        monkeypatch.setattr(srv, "_mark_job_paid_in_full", _rec_paid)
        monkeypatch.setattr(srv, "_mark_job_payment_pending", _rec_pending)
        monkeypatch.setattr(srv, "mark_lead_commission_payment", _rec_commission)
        monkeypatch.setattr(srv, "_infer_purpose", lambda inv: "final")

        inv = {"invoice_id": "TEST_paid_final", "status": "PAID", "amount": 800, "lead_id": "LEAD-Y"}
        asyncio.run(srv.apply_invoice_to_jobs(inv, notify_owner=False))
        assert "ensure" not in calls
        assert "paid_full" in calls
        assert ("commission", "fully") in calls

    def test_status_draft_is_no_op(self, monkeypatch):
        """Any status != PAID/PAYMENT_PENDING should short-circuit."""
        import server as srv  # type: ignore
        calls = []
        for name in ("_mark_job_payment_pending", "_maybe_fire_capi_purchase",
                     "ensure_job_for_deposit", "_mark_job_paid_in_full", "_alert_payment_landed"):
            async def _rec(*a, __n=name, **kw): calls.append(__n)
            monkeypatch.setattr(srv, name, _rec)
        monkeypatch.setattr(srv, "_infer_purpose", lambda inv: "deposit")

        for status in ("DRAFT", "UNPAID", "CANCELED", "SCHEDULED"):
            inv = {"invoice_id": f"TEST_{status}", "status": status, "amount": 100, "lead_id": None}
            asyncio.run(srv.apply_invoice_to_jobs(inv, notify_owner=False))
        assert calls == [], f"non-PAID/non-PENDING statuses must be no-ops, got {calls}"


# ---------------- _job_doc_from_invoice helper split ----------------

class TestJobDocHelpers:
    def test_job_customer_prefers_invoice_customer(self):
        from server import _job_customer  # type: ignore
        cust = _job_customer(
            {"customer": {"name": "Alice", "phone": "212", "email": "a@x"}},
            {"name": "Backup", "phone": "999", "email": "b@x"})
        assert cust == {"name": "Alice", "phone": "212", "email": "a@x"}

    def test_job_customer_falls_back_to_lead(self):
        from server import _job_customer  # type: ignore
        cust = _job_customer({}, {"name": "Bob", "phone": "555", "email": "b@x"})
        assert cust == {"name": "Bob", "phone": "555", "email": "b@x"}

    def test_job_paid_in_full_flag_true(self):
        from server import _job_paid_in_full  # type: ignore
        got = _job_paid_in_full({"amount": 800, "invoice_number": "INV-1"}, "2026-01-01T00:00:00Z", True)
        assert got == {"status": "paid", "amount": 800, "paid_at": "2026-01-01T00:00:00Z",
                       "invoice_number": "INV-1"}

    def test_job_paid_in_full_flag_false(self):
        from server import _job_paid_in_full  # type: ignore
        got = _job_paid_in_full({"amount": 800}, "2026-01-01T00:00:00Z", False)
        assert got == {"status": "unpaid", "amount": None, "paid_at": None}
