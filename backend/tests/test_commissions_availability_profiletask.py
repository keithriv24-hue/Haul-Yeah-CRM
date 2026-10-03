"""
Backend tests (originally iteration 11, rewritten for Prompt 4):
- Sales commissions are now driven by the CANONICAL PAYMENT LEDGER: the commission base is the NET
  money actually collected (payments minus refunds), never a sales-typed quote amount. Status
  (pending/locked/voided) is ledger-derived; only the owner can force a manual void or reassign an
  already-credited rep.
- Owner availability overview
- Profile task (open/done/auto-complete)
- Owner login renaming (HaulYeahAdmin) + old HaulYeahOwner fails

Each commission test class seeds its OWN unique lead/job ids in the canonical ledger and tears them
down, so classes stay isolated under the repo's `-n 2 --dist loadscope` xdist config.
"""
import os
import time
import uuid as _uuid

import pymongo as _pymongo
import pytest
import requests

from test_config import CREW1_PASSWORD, CREW2_PASSWORD, OWNER_PASSWORD, STARTING_PASSWORD

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"

OWNER_CREDS = {"email": "HaulYeahAdmin", "password": OWNER_PASSWORD}
CREW1_CREDS = {"email": "qa.crew1@haulyeah.test", "password": CREW1_PASSWORD}
CREW2_CREDS = {"email": "qa.crew2@haulyeah.test", "password": CREW2_PASSWORD}
GHOST_CREW = {"email": "TestCrewAdmin", "password": OWNER_PASSWORD}
GHOST_SALES = {"email": "TestSalesAdmin", "password": OWNER_PASSWORD}
GHOST_MKT = {"email": "TestMarketingAdmin", "password": OWNER_PASSWORD}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed {creds['email']}: {r.status_code} {r.text}"
    return r.json()["token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def owner_tok():
    return _login(OWNER_CREDS)


@pytest.fixture(scope="module")
def crew1_crew_tok():
    return _login(CREW1_CREDS)


@pytest.fixture(scope="module")
def crew1_sales_tok(crew1_crew_tok):
    r = requests.post(f"{API}/auth/switch-role", json={"role": "sales"},
                      headers=_hdr(crew1_crew_tok), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def crew_ghost_tok():
    return _login(GHOST_CREW)


@pytest.fixture(scope="module")
def sales_ghost_tok():
    return _login(GHOST_SALES)


@pytest.fixture(scope="module")
def mkt_ghost_tok():
    return _login(GHOST_MKT)


@pytest.fixture(scope="module")
def users_map(owner_tok):
    r = requests.get(f"{API}/users", headers=_hdr(owner_tok), timeout=30)
    assert r.status_code == 200
    data = r.json()["users"]
    return {u["email"].lower(): u for u in data}


@pytest.fixture(scope="module")
def crew1_id(users_map):
    u = users_map.get("qa.crew1@haulyeah.test")
    assert u, "Crew1 user must exist"
    return u["id"]


@pytest.fixture(scope="module")
def crew2_id(users_map):
    u = users_map.get("qa.crew2@haulyeah.test")
    assert u, "Crew2 user must exist"
    return u["id"]


# ---- canonical-ledger seeding (Prompt 4: commission base = NET collected from the ledger) --------
_DB = _pymongo.MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _seed_job(job_id, lead_id, quote):
    """A Mongo job so the canonical ledger + commission job_total have something to tie to."""
    _DB.jobs.update_one(
        {"_id": job_id},
        {"$set": {"_id": job_id, "invoice_number": f"QA-{job_id}", "lead_id": lead_id,
                  "quote_total": float(quote), "deposit_paid": {"status": "paid", "amount": 1.0},
                  "status": "Scheduled"}},
        upsert=True)


def _set_collected(job_id, lead_id, amount):
    """Force a lead's NET collected by replacing its ledger payment rows (test-only)."""
    _DB.payments.delete_many({"job_id": job_id})
    if amount:
        _DB.payments.insert_one({
            "_id": str(_uuid.uuid4()), "job_id": job_id, "project_record_id": None, "lead_id": lead_id,
            "kind": "payment", "method": "square", "amount": float(amount), "type": "payment",
            "status": "completed", "source": "square_invoice",
            "dedupe_key": f"qacomm:{_uuid.uuid4()}", "occurred_at": "2026-07-25T12:00:00+00:00"})


def _add_refund(job_id, lead_id, amount):
    """Append a refund row — reduces net collected without deleting the payment rows."""
    _DB.payments.insert_one({
        "_id": str(_uuid.uuid4()), "job_id": job_id, "project_record_id": None, "lead_id": lead_id,
        "kind": "refund", "method": "square", "amount": float(amount), "type": "refund",
        "status": "completed", "source": "square_webhook",
        "dedupe_key": f"qacommr:{_uuid.uuid4()}", "occurred_at": "2026-07-26T12:00:00+00:00"})


def _cleanup_comm(job_id, lead_id):
    _DB.payments.delete_many({"job_id": job_id})
    _DB.jobs.delete_one({"_id": job_id})
    _DB.lead_commissions.delete_one({"_id": lead_id})
    _DB.commission_audit.delete_many({"lead_id": lead_id})


# ================================ Login rename check

class TestLoginRename:
    def test_old_owner_username_fails(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": "HaulYeahOwner", "password": OWNER_PASSWORD},
                          timeout=30)
        assert r.status_code == 401, f"expected 401 old username, got {r.status_code}"

    def test_new_owner_username_works(self):
        r = requests.post(f"{API}/auth/login", json=OWNER_CREDS, timeout=30)
        assert r.status_code == 200
        assert r.json().get("role") == "owner"


# ================================ Commission math — base = NET collected from the ledger

class TestCommissionMath:
    """Tiers are unchanged; the base is strictly the net money collected from the canonical ledger
    (not a sales-typed quote). Fully collected => locked."""
    # lead_id -> (job_id, quote/collected, move_type, expected commission)
    JOBS = {
        "recQATESTM_A": ("qa-commM-A", 3500.0, "4+", 420.0),          # 12% big tier
        "recQATESTM_B": ("qa-commM-B", 2000.0, "2-bedroom", 200.0),   # 10% medium tier
        "recQATESTM_C": ("qa-commM-C", 900.0, "Studio", 40.0),        # <1500 flat studio
        "recQATESTM_D": ("qa-commM-D", 900.0, "Labor-only", 25.0),    # <1500 flat labor-only
    }

    @pytest.fixture(scope="class", autouse=True)
    def _seed(self):
        for lead, (jid, amt, _mt, _c) in self.JOBS.items():
            _seed_job(jid, lead, amt)
            _set_collected(jid, lead, amt)   # fully collected => base == quote
        yield
        for lead, (jid, *_rest) in self.JOBS.items():
            _cleanup_comm(jid, lead)

    def _check(self, owner_tok, crew1_id, lead):
        _jid, amt, mt, expected = self.JOBS[lead]
        r = requests.put(f"{API}/commissions/attribution/{lead}",
                         json={"lead_name": f"QA {lead}", "closed_by": crew1_id,
                               "move_type": mt, "job_date": "2026-07-25"},
                         headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["base"] == amt, body                     # base = net collected, not a quote
        assert body["base_label"] == "net collected", body
        assert body["commission"] == expected, body
        assert body["status"] == "locked", body              # fully collected => locked

    def test_big_move_3500_pct12_returns_420(self, owner_tok, crew1_id):
        self._check(owner_tok, crew1_id, "recQATESTM_A")

    def test_medium_2000_2bedroom_returns_200(self, owner_tok, crew1_id):
        self._check(owner_tok, crew1_id, "recQATESTM_B")

    def test_small_studio_900_returns_flat_40(self, owner_tok, crew1_id):
        self._check(owner_tok, crew1_id, "recQATESTM_C")

    def test_small_labor_only_900_returns_flat_25(self, owner_tok, crew1_id):
        self._check(owner_tok, crew1_id, "recQATESTM_D")


# ================================ Lifecycle — status is ledger-derived

class TestCommissionLifecycle:
    """Partial collection => pending; full collection => locked; owner-authorized refund => voided.
    All driven by ledger activity, never by legacy deposit_paid/fully_paid payload flags."""
    LEAD = "recQATESTLIFE"
    JOB = "qa-comm-LIFE"
    QUOTE = 4000.0

    @pytest.fixture(scope="class", autouse=True)
    def _seed(self, owner_tok, crew1_id):
        _seed_job(self.JOB, self.LEAD, self.QUOTE)
        _set_collected(self.JOB, self.LEAD, 0)   # nothing collected yet
        r = requests.put(f"{API}/commissions/attribution/{self.LEAD}",
                         json={"lead_name": "QA Lifecycle", "closed_by": crew1_id,
                               "move_type": "4+", "job_date": "2026-07-25"},
                         headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        yield
        _cleanup_comm(self.JOB, self.LEAD)

    def test_partial_collection_pending(self, owner_tok):
        _set_collected(self.JOB, self.LEAD, 3500)   # < 4000 total, lands in big tier
        r = requests.get(f"{API}/commissions/attribution/{self.LEAD}",
                         headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["base"] == 3500.0, body
        assert body["commission"] == 420.0, body      # 12% of collected 3500
        assert body["status"] == "pending", body

    def test_report_shows_pending_total(self, owner_tok, crew1_id):
        r = requests.get(f"{API}/commissions/report", headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["is_owner"] is True
        rep = next((x for x in body["reps"] if x["user_id"] == crew1_id), None)
        assert rep is not None, "crew1 should have a rep row"
        assert rep["pending"] >= 420.0

    def test_full_collection_locks(self, owner_tok):
        _set_collected(self.JOB, self.LEAD, self.QUOTE)   # == total => locked
        r = requests.get(f"{API}/commissions/attribution/{self.LEAD}",
                         headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["base"] == self.QUOTE, body
        assert body["commission"] == 480.0, body          # 12% of 4000
        assert body["status"] == "locked", body

    def test_owner_refund_voids(self, owner_tok):
        r = requests.put(f"{API}/commissions/attribution/{self.LEAD}",
                         json={"refunded": True}, headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "voided"

        r2 = requests.get(f"{API}/commissions/report", headers=_hdr(owner_tok), timeout=30)
        assert r2.status_code == 200
        row = next((x for x in r2.json()["rows"] if x["lead_id"] == self.LEAD), None)
        assert row is not None and row["status"] == "voided", r2.json()
        # restore so the report/teardown stays clean for anything reusing this rep
        requests.put(f"{API}/commissions/attribution/{self.LEAD}",
                     json={"refunded": False}, headers=_hdr(owner_tok), timeout=30)


# ================================ Role gates

class TestCommissionRoleGates:
    GATE_LEAD = "recQATESTGATE"      # already credited to crew1 (owner-set) in the fixture
    SETTABLE_LEAD = "recQATESTGSET"  # fresh lead for the "sales may set first attribution" case

    @pytest.fixture(scope="class", autouse=True)
    def _gate_data(self, owner_tok, crew1_id):
        r = requests.put(f"{API}/commissions/attribution/{self.GATE_LEAD}",
                         json={"lead_name": "QA Gate", "closed_by": crew1_id, "move_type": "2-bedroom"},
                         headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        yield
        for lid in (self.GATE_LEAD, self.SETTABLE_LEAD):
            _DB.lead_commissions.delete_one({"_id": lid})
            _DB.commission_audit.delete_many({"lead_id": lid})

    def test_sales_cannot_set_refunded(self, sales_ghost_tok):
        # financial state (void/refund) is owner-only now — sales cannot set it directly
        r = requests.put(f"{API}/commissions/attribution/{self.GATE_LEAD}",
                         json={"refunded": True},
                         headers=_hdr(sales_ghost_tok), timeout=30)
        assert r.status_code == 403
        assert "owner" in (r.json().get("detail") or "").lower()

    def test_sales_cannot_reassign_credited_closed_by(self, sales_ghost_tok, crew2_id):
        # GATE_LEAD is already credited to crew1 — sales cannot reassign it to someone else
        r = requests.put(f"{API}/commissions/attribution/{self.GATE_LEAD}",
                         json={"closed_by": crew2_id},
                         headers=_hdr(sales_ghost_tok), timeout=30)
        assert r.status_code == 403
        assert "owner" in (r.json().get("detail") or "").lower()

    def test_sales_can_set_initial_attribution_fields(self, sales_ghost_tok, crew1_id):
        # first-time attribution on a fresh lead is allowed for sales (no quote base involved)
        r = requests.put(f"{API}/commissions/attribution/{self.SETTABLE_LEAD}",
                         json={"closed_by": crew1_id, "move_type": "2-bedroom"},
                         headers=_hdr(sales_ghost_tok), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["attribution"]["closed_by"] == crew1_id

    def test_crew_ghost_403_on_attribution_get(self, crew_ghost_tok):
        r = requests.get(f"{API}/commissions/attribution/{self.GATE_LEAD}",
                         headers=_hdr(crew_ghost_tok), timeout=30)
        assert r.status_code == 403

    def test_crew_ghost_403_on_attribution_put(self, crew_ghost_tok):
        r = requests.put(f"{API}/commissions/attribution/{self.GATE_LEAD}",
                         json={"lead_name": "hack"},
                         headers=_hdr(crew_ghost_tok), timeout=30)
        assert r.status_code == 403

    def test_crew_ghost_403_on_report(self, crew_ghost_tok):
        r = requests.get(f"{API}/commissions/report", headers=_hdr(crew_ghost_tok), timeout=30)
        assert r.status_code == 403

    def test_crew_ghost_403_on_rates(self, crew_ghost_tok):
        r = requests.get(f"{API}/commissions/rates", headers=_hdr(crew_ghost_tok), timeout=30)
        assert r.status_code == 403

    def test_marketing_ghost_403_on_all_commission_endpoints(self, mkt_ghost_tok):
        for path in ("/commissions/report", "/commissions/rates",
                     f"/commissions/attribution/{self.GATE_LEAD}"):
            r = requests.get(f"{API}{path}", headers=_hdr(mkt_ghost_tok), timeout=30)
            assert r.status_code == 403, f"{path}: expected 403 got {r.status_code}"

    def test_sales_cannot_put_rates(self, sales_ghost_tok):
        r = requests.get(f"{API}/commissions/rates", headers=_hdr(sales_ghost_tok), timeout=30)
        assert r.status_code == 200  # sales CAN view rates
        rates = r.json()["rates"]
        r2 = requests.put(f"{API}/commissions/rates",
                          json={"small_flat": rates["small_flat"], "medium_min": rates["medium_min"],
                                "medium_pct": rates["medium_pct"], "big_min": rates["big_min"],
                                "big_pct": rates["big_pct"]},
                          headers=_hdr(sales_ghost_tok), timeout=30)
        assert r2.status_code == 403


# ================================ Owner reassignment of an already-credited commission

class TestCommissionReassign:
    LEAD = "recQATESTREASSIGN"

    @pytest.fixture(scope="class", autouse=True)
    def _seed(self, owner_tok, crew1_id):
        r = requests.put(f"{API}/commissions/attribution/{self.LEAD}",
                         json={"lead_name": "QA Reassign", "closed_by": crew1_id, "move_type": "2-bedroom"},
                         headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        yield
        _DB.lead_commissions.delete_one({"_id": self.LEAD})
        _DB.commission_audit.delete_many({"lead_id": self.LEAD})

    def test_owner_reassign_without_reason_422(self, owner_tok, crew2_id):
        r = requests.put(f"{API}/commissions/attribution/{self.LEAD}",
                         json={"closed_by": crew2_id},
                         headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 422, r.text

    def test_owner_reassign_with_reason_audits(self, owner_tok, crew1_id, crew2_id):
        r = requests.put(f"{API}/commissions/attribution/{self.LEAD}",
                         json={"closed_by": crew2_id, "reason": "crew1 left; crew2 closed it"},
                         headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["attribution"]["closed_by"] == crew2_id
        log = _DB.commission_audit.find_one({"lead_id": self.LEAD, "field": "closed_by"})
        assert log is not None
        assert log["old"] == crew1_id and log["new"] == crew2_id
        assert log["reason"].startswith("crew1 left")


# ================================ Rates editing changes the math (on net collected)

class TestCommissionRates:
    LEAD = "recQATESTRATE"
    JOB = "qa-comm-RATE"

    @pytest.fixture(scope="class", autouse=True)
    def _seed(self, owner_tok, crew1_id):
        _seed_job(self.JOB, self.LEAD, 3500.0)
        _set_collected(self.JOB, self.LEAD, 3500.0)   # net collected 3500 (big tier)
        r = requests.put(f"{API}/commissions/attribution/{self.LEAD}",
                         json={"lead_name": "QA Rate", "closed_by": crew1_id, "move_type": "4+"},
                         headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        yield
        _cleanup_comm(self.JOB, self.LEAD)

    def test_owner_edit_big_pct_15_changes_math(self, owner_tok):
        r = requests.get(f"{API}/commissions/rates", headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200
        original = r.json()["rates"]
        try:
            r2 = requests.put(f"{API}/commissions/rates",
                              json={"small_flat": original["small_flat"],
                                    "medium_min": original["medium_min"],
                                    "medium_pct": original["medium_pct"],
                                    "big_min": original["big_min"],
                                    "big_pct": 15.0},
                              headers=_hdr(owner_tok), timeout=30)
            assert r2.status_code == 200, r2.text
            # commission recomputes live from NET collected 3500 at the new 15% => 525
            r3 = requests.get(f"{API}/commissions/attribution/{self.LEAD}",
                              headers=_hdr(owner_tok), timeout=30)
            assert r3.status_code == 200
            body = r3.json()
            assert body["base"] == 3500.0, body
            assert body["commission"] == 525.0, body
        finally:
            # RESTORE the original rate so this test can't contaminate others
            requests.put(f"{API}/commissions/rates",
                         json={"small_flat": original["small_flat"],
                               "medium_min": original["medium_min"],
                               "medium_pct": original["medium_pct"],
                               "big_min": original["big_min"],
                               "big_pct": original["big_pct"]},
                         headers=_hdr(owner_tok), timeout=30)


# ================================ Rep scoping (Crew1)

class TestRepScoping:
    def test_crew_view_report_403(self, crew1_crew_tok):
        r = requests.get(f"{API}/commissions/report",
                         headers=_hdr(crew1_crew_tok), timeout=30)
        assert r.status_code == 403

    def test_sales_view_own_only(self, crew1_sales_tok, crew1_id):
        r = requests.get(f"{API}/commissions/report",
                         headers=_hdr(crew1_sales_tok), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_owner"] == False
        # all rows should be crew1's
        for row in body["rows"]:
            assert row["closed_by"] == crew1_id


# ================================ Availability overview

class TestAvailability:
    def test_overview_owner_only(self, owner_tok):
        r = requests.get(f"{API}/availability/overview",
                         params={"start": "2026-07-01", "end": "2026-07-31"},
                         headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        days = body["days"]
        assert len(days) == 31
        # weekend flags on Sat/Sun — July 2026: 4,5,11,12,18,19,25,26 are Sat/Sun
        weekends = {d["date"] for d in days if d["weekend"]}
        assert "2026-07-04" in weekends
        assert "2026-07-25" in weekends and "2026-07-26" in weekends
        assert "2026-07-01" not in weekends  # Wed

    def test_overview_crew_403(self, crew_ghost_tok):
        r = requests.get(f"{API}/availability/overview",
                         params={"start": "2026-07-01", "end": "2026-07-31"},
                         headers=_hdr(crew_ghost_tok), timeout=30)
        assert r.status_code == 403

    def test_overview_sales_403(self, sales_ghost_tok):
        r = requests.get(f"{API}/availability/overview",
                         params={"start": "2026-07-01", "end": "2026-07-31"},
                         headers=_hdr(sales_ghost_tok), timeout=30)
        assert r.status_code == 403

    def test_owner_mark_crew2_off_and_shortage(self, owner_tok, crew1_id, crew2_id):
        # Mark crew2 off 2026-07-26
        r = requests.post(f"{API}/availability/set",
                          json={"user_id": crew2_id, "date": "2026-07-26", "available": False},
                          headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200

        # Verify overview shows him off on that date
        r2 = requests.get(f"{API}/availability/overview",
                          params={"start": "2026-07-26", "end": "2026-07-26"},
                          headers=_hdr(owner_tok), timeout=30)
        assert r2.status_code == 200
        days = r2.json()["days"]
        assert len(days) == 1
        day = days[0]
        off_ids = {o["user_id"] for o in day["off"]}
        assert crew2_id in off_ids, day

        # Create an assignment that needs both crew1 + crew2 → shortage
        asn_payload = {
            "job_name": "QA Weekend Job",
            "job_date": "2026-07-26",
            "start_address": "1 Test St, Waterbury CT",
            "end_address": "2 Test Ave, Waterbury CT",
            "crew": [{"user_id": crew1_id, "position": "Driver"},
                     {"user_id": crew2_id, "position": "Helper"}],
            "ignore_warnings": True,
        }
        r3 = requests.post(f"{API}/assignments", json=asn_payload,
                           headers=_hdr(owner_tok), timeout=30)
        assert r3.status_code == 200, r3.text
        assignment_id = r3.json()["id"]

        try:
            # Also mark crew1 off on 2026-07-26 so short=True (both off < needed=2)
            r4 = requests.post(f"{API}/availability/set",
                               json={"user_id": crew1_id, "date": "2026-07-26", "available": False},
                               headers=_hdr(owner_tok), timeout=30)
            assert r4.status_code == 200

            # Overview: needed>=2, short=True
            r5 = requests.get(f"{API}/availability/overview",
                              params={"start": "2026-07-26", "end": "2026-07-26"},
                              headers=_hdr(owner_tok), timeout=30)
            assert r5.status_code == 200
            day = r5.json()["days"][0]
            assert day["needed"] >= 2, day
            assert day["short"] == True, day
        finally:
            # cleanup: restore availability + delete assignment
            requests.post(f"{API}/availability/set",
                          json={"user_id": crew2_id, "date": "2026-07-26", "available": True},
                          headers=_hdr(owner_tok), timeout=30)
            requests.post(f"{API}/availability/set",
                          json={"user_id": crew1_id, "date": "2026-07-26", "available": True},
                          headers=_hdr(owner_tok), timeout=30)
            requests.delete(f"{API}/assignments/{assignment_id}",
                            headers=_hdr(owner_tok), timeout=30)


# ================================ Profile task

class TestProfileTask:
    def test_crew1_profile_task_flow(self, crew1_crew_tok):
        r = requests.get(f"{API}/profile-task", headers=_hdr(crew1_crew_tok), timeout=30)
        assert r.status_code == 200
        # crew1 may already be done from prior tests, but should return open/done not error
        assert r.json()["status"] in ("open", "done", "none")

        # POST /profile-task/done marks done
        r2 = requests.post(f"{API}/profile-task/done",
                           headers=_hdr(crew1_crew_tok), timeout=30)
        assert r2.status_code == 200
        assert r2.json()["status"] == "done"

        r3 = requests.get(f"{API}/profile-task", headers=_hdr(crew1_crew_tok), timeout=30)
        assert r3.json()["status"] == "done"

    def test_temp_user_auto_complete_via_profile_save(self, owner_tok):
        # Create temp user
        email = f"qa_temp_{int(time.time())}@haulyeahmoves.com"
        create = requests.post(f"{API}/users",
                               json={"name": "QA Temp", "email": email,
                                     "roles": ["crew"], "password": STARTING_PASSWORD},
                               headers=_hdr(owner_tok), timeout=30)
        assert create.status_code == 200, create.text
        temp_id = create.json()["id"]

        try:
            # Login as temp user
            login_r = requests.post(f"{API}/auth/login",
                                    json={"email": email, "password": STARTING_PASSWORD},
                                    timeout=30)
            assert login_r.status_code == 200, login_r.text
            temp_tok = login_r.json()["token"]
            # must_change_password flag exposed
            assert login_r.json()["user"]["must_change_password"] == True

            # Profile task should be open for a newly created user
            r = requests.get(f"{API}/profile-task", headers=_hdr(temp_tok), timeout=30)
            assert r.status_code == 200
            assert r.json()["status"] == "open", r.json()

            # Save profile with nickname → auto-mark done
            r2 = requests.put(f"{API}/profile",
                              json={"nickname": "QA"},
                              headers=_hdr(temp_tok), timeout=30)
            assert r2.status_code == 200, r2.text

            r3 = requests.get(f"{API}/profile-task", headers=_hdr(temp_tok), timeout=30)
            assert r3.status_code == 200
            assert r3.json()["status"] == "done", r3.json()
        finally:
            # cleanup: deactivate then delete
            requests.patch(f"{API}/users/{temp_id}", json={"active": False},
                           headers=_hdr(owner_tok), timeout=30)
            requests.delete(f"{API}/users/{temp_id}",
                            headers=_hdr(owner_tok), timeout=30)
