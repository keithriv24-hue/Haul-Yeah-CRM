"""Iteration 18 — regression checks after refactor of login/patch_job/portal_upload/
send_square_invoice/handle_square_event/clock_in etc. Behavior must be identical.
Square is LIVE — never create/send real invoices."""
import base64
import io
import os
import struct
import zlib

import pytest
import requests

from test_config import CREW1_EMAIL, CREW1_PASSWORD, OWNER_EMAIL, OWNER_PASSWORD, QA_TRACK_TOKEN

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = BASE_URL + "/api"

OWNER_U = OWNER_EMAIL
OWNER_P = OWNER_PASSWORD
CREW_U = CREW1_EMAIL
CREW_P = CREW1_PASSWORD
QA_TOKEN = QA_TRACK_TOKEN


def _tiny_png_bytes() -> bytes:
    # Minimal 1x1 PNG
    sig = b"\x89PNG\r\n\x1a\n"
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{API}/auth/login", json={"email": OWNER_U, "password": OWNER_P})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("role") in ("owner", "admin")
    return d["token"]


@pytest.fixture(scope="module")
def crew_token():
    r = requests.post(f"{API}/auth/login", json={"email": CREW_U, "password": CREW_P})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# --- Login regression ---
class TestLogin:
    def test_owner_login(self, owner_token):
        assert isinstance(owner_token, str) and len(owner_token) > 10

    def test_crew_login(self, crew_token):
        assert isinstance(crew_token, str) and len(crew_token) > 10

    def test_wrong_password_401(self):
        r = requests.post(f"{API}/auth/login", json={"email": OWNER_U, "password": "WRONG_PW_x"})
        # do not spam — single negative attempt
        assert r.status_code == 401

    def test_legacy_blank_username_owner_password(self):
        # Legacy behavior: blank email + shared owner env password -> owner/sales role
        r = requests.post(f"{API}/auth/login", json={"email": "", "password": OWNER_P})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("role") in ("owner", "sales", "admin"), d

    def test_auth_me(self, owner_token):
        r = requests.get(f"{API}/auth/me", headers=_h(owner_token))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("role") in ("owner", "admin")
        assert "can_switch" in d


# --- Jobs board / patch_job refactor ---
class TestJobsPatch:
    def test_list_jobs(self, owner_token):
        r = requests.get(f"{API}/jobs", headers=_h(owner_token))
        assert r.status_code == 200, r.text
        d = r.json()
        jobs = d if isinstance(d, list) else d.get("jobs") or d.get("items")
        assert isinstance(jobs, list) and len(jobs) > 0
        # attach a job_id fixture value for the next test
        pytest.jobs_cache = jobs

    def test_patch_job_updates(self, owner_token):
        jobs = getattr(pytest, "jobs_cache", None) or []
        assert jobs, "need jobs from previous test"
        target = jobs[0]
        jid = target.get("id") or target.get("job_id") or target.get("_id")
        assert jid, target
        orig_pickup = target.get("pickup_address") or ""
        orig_start = target.get("start_time") or ""
        new_pickup = "TEST_123 QA Regression Rd, Newark, NJ"
        new_start = "09:15"
        r = requests.patch(
            f"{API}/jobs/{jid}",
            headers=_h(owner_token),
            json={"pickup_address": new_pickup, "start_time": new_start},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # response may be the job or {job:...}
        job = d.get("job") if isinstance(d, dict) and "job" in d else d
        assert job.get("pickup_address") == new_pickup
        assert job.get("start_time") == new_start
        # restore
        requests.patch(
            f"{API}/jobs/{jid}",
            headers=_h(owner_token),
            json={"pickup_address": orig_pickup, "start_time": orig_start},
        )


# --- Public tracking portal refactor ---
class TestTrackPortal:
    def test_public_track_ok(self):
        r = requests.get(f"{API}/track/{QA_TOKEN}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("invoice_number") == "QA-1001"
        cust = d.get("customer") or d.get("customer_name")
        if isinstance(cust, dict):
            cust = cust.get("name")
        assert cust == "Dana Johnson", d
        assert d.get("remaining_balance") == 900

    def test_track_bad_token_404(self):
        r = requests.get(f"{API}/track/deadbeef" + "0" * 24)
        assert r.status_code == 404


# --- Portal upload refactor ---
class TestPortalUpload:
    def test_upload_png_ok(self):
        files = {"file": ("qa_regress.png", _tiny_png_bytes(), "image/png")}
        r = requests.post(
            f"{API}/track/{QA_TOKEN}/uploads",
            params={"kind": "photo"},
            files=files,
        )
        assert r.status_code in (200, 201), r.text
        d = r.json()
        upid = d.get("id") or (d.get("upload") or {}).get("id")
        assert upid, d
        # cleanup to keep upload quota clean for next runs
        pytest.last_upload_id = upid

    def test_upload_invalid_kind_422(self):
        files = {"file": ("x.png", _tiny_png_bytes(), "image/png")}
        r = requests.post(
            f"{API}/track/{QA_TOKEN}/uploads",
            params={"kind": "not_a_valid_kind"},
            files=files,
        )
        assert r.status_code == 422, r.text

    def test_upload_non_image_content_type_422(self):
        files = {"file": ("hello.txt", b"hello world", "text/plain")}
        r = requests.post(
            f"{API}/track/{QA_TOKEN}/uploads",
            params={"kind": "photo"},
            files=files,
        )
        assert r.status_code == 422, r.text


# --- Crew clock-in with explicit assignment_id ---
class TestCrewClockInAssignment:
    def test_clock_in_with_assignment_and_out(self, crew_token, owner_token):
        # find an assignment for Crew1 today via dispatch board
        r = requests.get(f"{API}/dispatch/board", headers=_h(owner_token))
        assert r.status_code == 200, r.text
        board = r.json()
        assignments = []
        for section in ("assignments", "cards", "rows", "items"):
            v = board.get(section)
            if isinstance(v, list):
                assignments.extend(v)
        # Try to find Crew1's assignment
        aid = None
        for a in assignments:
            crew = a.get("crew") or a.get("crew_ids") or []
            names = " ".join(str(c) for c in crew) if isinstance(crew, list) else str(crew)
            if "crew1" in names.lower() or "Crew1" in names:
                aid = a.get("id") or a.get("assignment_id") or a.get("_id")
                if aid:
                    break
        if not aid and assignments:
            # fall back to first Montclair assignment id
            for a in assignments:
                if "Montclair" in (a.get("job_name") or ""):
                    aid = a.get("id") or a.get("assignment_id") or a.get("_id")
                    break
        if not aid:
            pytest.skip("No assignment id found on dispatch board to test assignment_id path")

        r_in = requests.post(
            f"{API}/crew/clock-in",
            headers=_h(crew_token),
            json={"assignment_id": aid},
        )
        assert r_in.status_code in (200, 201), r_in.text
        d = r_in.json()
        # should tie punch to that assignment
        got_aid = d.get("assignment_id") or (d.get("punch") or {}).get("assignment_id")
        if got_aid is not None:
            assert got_aid == aid, d

        r_out = requests.post(f"{API}/crew/clock-out", headers=_h(crew_token), json={})
        assert r_out.status_code in (200, 201), r_out.text


# --- Dispatch board refactor smoke ---
class TestDispatchBoard:
    def test_board_today(self, owner_token):
        r = requests.get(f"{API}/dispatch/board", headers=_h(owner_token))
        assert r.status_code == 200, r.text
        d = r.json()
        # date=today ET and is_today true
        from datetime import datetime
        from zoneinfo import ZoneInfo
        today_et = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
        assert d.get("date") == today_et, d.get("date")
        assert d.get("is_today") is True
        blob = str(d)
        assert "QA Dispatch Move — Montclair" in blob
        assert "QA Dispatch Move — Hoboken" in blob


# --- Square status ---
class TestSquareStatus:
    def test_owner_gets_status(self, owner_token):
        r = requests.get(f"{API}/square/status", headers=_h(owner_token))
        assert r.status_code == 200, r.text
        d = r.json()
        assert "configured" in d

    def test_crew_forbidden(self, crew_token):
        r = requests.get(f"{API}/square/status", headers=_h(crew_token))
        assert r.status_code == 403
