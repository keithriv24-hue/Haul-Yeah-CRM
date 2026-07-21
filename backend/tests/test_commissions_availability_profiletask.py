"""
Iteration 11 backend tests:
- Sales commissions math + lifecycle + role gates + rep scoping
- Owner availability overview
- Profile task (open/done/auto-complete)
- Owner login renaming (HaulYeahAdmin) + old HaulYeahOwner fails
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"

OWNER_CREDS = {"email": "HaulYeahAdmin", "password": "HaulYeah2026!"}
JAVANTE_CREDS = {"email": "javante@haulyeahmoves.com", "password": "JavCrew2026!"}
JUNIOR_CREDS = {"email": "junior@haulyeahmoves.com", "password": "JunCrew2026!"}
GHOST_CREW = {"email": "TestCrewAdmin", "password": "HaulYeah2026!"}
GHOST_SALES = {"email": "TestSalesAdmin", "password": "HaulYeah2026!"}
GHOST_MKT = {"email": "TestMarketingAdmin", "password": "HaulYeah2026!"}

TEST_LEAD_A = "recQATEST1"
TEST_LEAD_B = "recQATEST2"
TEST_LEAD_C = "recQATEST3"
TEST_LEAD_D = "recQATEST4"


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
def javante_crew_tok():
    return _login(JAVANTE_CREDS)


@pytest.fixture(scope="module")
def javante_sales_tok(javante_crew_tok):
    r = requests.post(f"{API}/auth/switch-role", json={"role": "sales"},
                      headers=_hdr(javante_crew_tok), timeout=30)
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
def javante_id(users_map):
    u = users_map.get("javante@haulyeahmoves.com")
    assert u, "Javante user must exist"
    return u["id"]


@pytest.fixture(scope="module")
def junior_id(users_map):
    u = users_map.get("junior@haulyeahmoves.com")
    assert u, "Junior user must exist"
    return u["id"]


# ================================ Login rename check

class TestLoginRename:
    def test_old_owner_username_fails(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": "HaulYeahOwner", "password": "HaulYeah2026!"},
                          timeout=30)
        assert r.status_code == 401, f"expected 401 old username, got {r.status_code}"

    def test_new_owner_username_works(self):
        r = requests.post(f"{API}/auth/login", json=OWNER_CREDS, timeout=30)
        assert r.status_code == 200
        assert r.json().get("role") == "owner"


# ================================ Commission math

class TestCommissionMath:
    def test_big_move_3500_pct12_returns_420(self, owner_tok, javante_id):
        payload = {"lead_name": "QA A", "closed_by": javante_id,
                   "move_type": "4+", "quote_amount": 3500, "job_date": "2026-07-25"}
        r = requests.put(f"{API}/commissions/attribution/{TEST_LEAD_A}",
                         json=payload, headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["commission"] == 420.0
        assert body["status"] == "none"

    def test_medium_2000_2bedroom_returns_200(self, owner_tok, javante_id):
        payload = {"lead_name": "QA B", "closed_by": javante_id,
                   "move_type": "2-bedroom", "quote_amount": 2000, "job_date": "2026-07-25"}
        r = requests.put(f"{API}/commissions/attribution/{TEST_LEAD_B}",
                         json=payload, headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["commission"] == 200.0

    def test_small_studio_900_returns_flat_40(self, owner_tok, javante_id):
        payload = {"lead_name": "QA C", "closed_by": javante_id,
                   "move_type": "Studio", "quote_amount": 900, "job_date": "2026-07-25"}
        r = requests.put(f"{API}/commissions/attribution/{TEST_LEAD_C}",
                         json=payload, headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["commission"] == 40.0

    def test_small_labor_only_900_returns_flat_25(self, owner_tok, javante_id):
        payload = {"lead_name": "QA D", "closed_by": javante_id,
                   "move_type": "Labor-only", "quote_amount": 900, "job_date": "2026-07-25"}
        r = requests.put(f"{API}/commissions/attribution/{TEST_LEAD_D}",
                         json=payload, headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["commission"] == 25.0


# ================================ Lifecycle

class TestCommissionLifecycle:
    def test_deposit_paid_pending(self, owner_tok):
        r = requests.put(f"{API}/commissions/attribution/{TEST_LEAD_A}",
                         json={"deposit_paid": True},
                         headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "pending"
        assert body["attribution"]["deposit_paid_at"], "deposit_paid_at should be auto-set"

    def test_report_shows_pending_total(self, owner_tok, javante_id):
        r = requests.get(f"{API}/commissions/report", headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["is_owner"] is True
        rep = next((x for x in body["reps"] if x["user_id"] == javante_id), None)
        assert rep is not None, "javante should have a rep row"
        assert rep["pending"] >= 420.0

    def test_fully_paid_locks(self, owner_tok):
        r = requests.put(f"{API}/commissions/attribution/{TEST_LEAD_A}",
                         json={"fully_paid": True},
                         headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "locked"

    def test_refunded_voids(self, owner_tok, javante_id):
        r = requests.put(f"{API}/commissions/attribution/{TEST_LEAD_A}",
                         json={"refunded": True},
                         headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "voided"

        # verify report excludes voided from pending/locked
        r2 = requests.get(f"{API}/commissions/report", headers=_hdr(owner_tok), timeout=30)
        assert r2.status_code == 200
        body = r2.json()
        rep = next((x for x in body["reps"] if x["user_id"] == javante_id), None)
        assert rep is not None
        # There should also be TEST_LEAD_B/C/D pending (they still have closed_by but no deposit)
        # But TEST_LEAD_A voided => shouldn't add to pending/locked
        # find the row for lead A
        row_a = next((r for r in body["rows"] if r["lead_id"] == TEST_LEAD_A), None)
        assert row_a is not None and row_a["status"] == "voided"
        # rep.voided should include 420 from the voided lead
        assert rep["voided"] >= 420.0


# ================================ Role gates

class TestCommissionRoleGates:
    def test_sales_cannot_flip_payment_flags(self, sales_ghost_tok, javante_id):
        r = requests.put(f"{API}/commissions/attribution/{TEST_LEAD_B}",
                         json={"deposit_paid": True},
                         headers=_hdr(sales_ghost_tok), timeout=30)
        assert r.status_code == 403
        assert "owner" in (r.json().get("detail") or "").lower()

    def test_sales_can_set_attribution_fields(self, sales_ghost_tok, javante_id):
        # sales sets non-flag fields
        r = requests.put(f"{API}/commissions/attribution/{TEST_LEAD_B}",
                         json={"closed_by": javante_id, "move_type": "2-bedroom", "quote_amount": 2000},
                         headers=_hdr(sales_ghost_tok), timeout=30)
        assert r.status_code == 200, r.text

    def test_crew_ghost_403_on_attribution_get(self, crew_ghost_tok):
        r = requests.get(f"{API}/commissions/attribution/{TEST_LEAD_A}",
                         headers=_hdr(crew_ghost_tok), timeout=30)
        assert r.status_code == 403

    def test_crew_ghost_403_on_attribution_put(self, crew_ghost_tok):
        r = requests.put(f"{API}/commissions/attribution/{TEST_LEAD_A}",
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
                     f"/commissions/attribution/{TEST_LEAD_A}"):
            r = requests.get(f"{API}{path}", headers=_hdr(mkt_ghost_tok), timeout=30)
            assert r.status_code == 403, f"{path}: expected 403 got {r.status_code}"

    def test_sales_cannot_put_rates(self, sales_ghost_tok):
        # first get current rates from owner would be nice but sales get 200 too
        r = requests.get(f"{API}/commissions/rates", headers=_hdr(sales_ghost_tok), timeout=30)
        assert r.status_code == 200  # sales CAN view rates
        rates = r.json()["rates"]
        r2 = requests.put(f"{API}/commissions/rates",
                          json={"small_flat": rates["small_flat"], "medium_min": rates["medium_min"],
                                "medium_pct": rates["medium_pct"], "big_min": rates["big_min"],
                                "big_pct": rates["big_pct"]},
                          headers=_hdr(sales_ghost_tok), timeout=30)
        assert r2.status_code == 403


# ================================ Rates editing math change

class TestCommissionRates:
    def test_owner_edit_big_pct_15_changes_math(self, owner_tok, javante_id):
        r = requests.get(f"{API}/commissions/rates", headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200
        original = r.json()["rates"]

        # bump big_pct to 15
        r2 = requests.put(f"{API}/commissions/rates",
                          json={"small_flat": original["small_flat"],
                                "medium_min": original["medium_min"],
                                "medium_pct": original["medium_pct"],
                                "big_min": original["big_min"],
                                "big_pct": 15.0},
                          headers=_hdr(owner_tok), timeout=30)
        assert r2.status_code == 200, r2.text

        # now check a $3500 4+ quote → should be 525
        r3 = requests.put(f"{API}/commissions/attribution/{TEST_LEAD_A}",
                          json={"quote_amount": 3500, "move_type": "4+"},
                          headers=_hdr(owner_tok), timeout=30)
        assert r3.status_code == 200
        assert r3.json()["commission"] == 525.0, r3.json()

        # RESTORE big_pct to 12
        r4 = requests.put(f"{API}/commissions/rates",
                          json={"small_flat": original["small_flat"],
                                "medium_min": original["medium_min"],
                                "medium_pct": original["medium_pct"],
                                "big_min": original["big_min"],
                                "big_pct": 12.0},
                          headers=_hdr(owner_tok), timeout=30)
        assert r4.status_code == 200


# ================================ Rep scoping (Javante)

class TestRepScoping:
    def test_crew_view_report_403(self, javante_crew_tok):
        r = requests.get(f"{API}/commissions/report",
                         headers=_hdr(javante_crew_tok), timeout=30)
        assert r.status_code == 403

    def test_sales_view_own_only(self, javante_sales_tok, javante_id):
        r = requests.get(f"{API}/commissions/report",
                         headers=_hdr(javante_sales_tok), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_owner"] is False
        # all rows should be javante's
        for row in body["rows"]:
            assert row["closed_by"] == javante_id


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

    def test_owner_mark_junior_off_and_shortage(self, owner_tok, javante_id, junior_id):
        # Mark junior off 2026-07-26
        r = requests.post(f"{API}/availability/set",
                          json={"user_id": junior_id, "date": "2026-07-26", "available": False},
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
        assert junior_id in off_ids, day

        # Create an assignment that needs both javante + junior → shortage
        asn_payload = {
            "job_name": "QA Weekend Job",
            "job_date": "2026-07-26",
            "start_address": "1 Test St, Waterbury CT",
            "end_address": "2 Test Ave, Waterbury CT",
            "crew": [{"user_id": javante_id, "position": "Driver"},
                     {"user_id": junior_id, "position": "Helper"}],
            "ignore_warnings": True,
        }
        r3 = requests.post(f"{API}/assignments", json=asn_payload,
                           headers=_hdr(owner_tok), timeout=30)
        assert r3.status_code == 200, r3.text
        assignment_id = r3.json()["id"]

        try:
            # Also mark javante off on 2026-07-26 so short=True (both off < needed=2)
            r4 = requests.post(f"{API}/availability/set",
                               json={"user_id": javante_id, "date": "2026-07-26", "available": False},
                               headers=_hdr(owner_tok), timeout=30)
            assert r4.status_code == 200

            # Overview: needed>=2, short=True
            r5 = requests.get(f"{API}/availability/overview",
                              params={"start": "2026-07-26", "end": "2026-07-26"},
                              headers=_hdr(owner_tok), timeout=30)
            assert r5.status_code == 200
            day = r5.json()["days"][0]
            assert day["needed"] >= 2, day
            assert day["short"] is True, day
        finally:
            # cleanup: restore availability + delete assignment
            requests.post(f"{API}/availability/set",
                          json={"user_id": junior_id, "date": "2026-07-26", "available": True},
                          headers=_hdr(owner_tok), timeout=30)
            requests.post(f"{API}/availability/set",
                          json={"user_id": javante_id, "date": "2026-07-26", "available": True},
                          headers=_hdr(owner_tok), timeout=30)
            requests.delete(f"{API}/assignments/{assignment_id}",
                            headers=_hdr(owner_tok), timeout=30)


# ================================ Profile task

class TestProfileTask:
    def test_javante_profile_task_flow(self, javante_crew_tok):
        r = requests.get(f"{API}/profile-task", headers=_hdr(javante_crew_tok), timeout=30)
        assert r.status_code == 200
        # javante may already be done from prior tests, but should return open/done not error
        assert r.json()["status"] in ("open", "done", "none")

        # POST /profile-task/done marks done
        r2 = requests.post(f"{API}/profile-task/done",
                           headers=_hdr(javante_crew_tok), timeout=30)
        assert r2.status_code == 200
        assert r2.json()["status"] == "done"

        r3 = requests.get(f"{API}/profile-task", headers=_hdr(javante_crew_tok), timeout=30)
        assert r3.json()["status"] == "done"

    def test_temp_user_auto_complete_via_profile_save(self, owner_tok):
        # Create temp user
        email = f"qa_temp_{int(time.time())}@haulyeahmoves.com"
        create = requests.post(f"{API}/users",
                               json={"name": "QA Temp", "email": email,
                                     "roles": ["crew"], "password": "haulyeah123"},
                               headers=_hdr(owner_tok), timeout=30)
        assert create.status_code == 200, create.text
        temp_id = create.json()["id"]

        try:
            # Login as temp user
            login_r = requests.post(f"{API}/auth/login",
                                    json={"email": email, "password": "haulyeah123"},
                                    timeout=30)
            assert login_r.status_code == 200, login_r.text
            temp_tok = login_r.json()["token"]
            # must_change_password flag exposed
            assert login_r.json()["user"]["must_change_password"] is True

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


# ================================ FINAL cleanup — clear closed_by on all TEST leads

def test_zzz_cleanup_test_attributions(request, owner_tok):
    """Runs last — resets closed_by="" on all fake QA leads so report stays clean."""
    for lead_id in (TEST_LEAD_A, TEST_LEAD_B, TEST_LEAD_C, TEST_LEAD_D):
        requests.put(f"{API}/commissions/attribution/{lead_id}",
                     json={"closed_by": "", "refunded": False, "deposit_paid": False,
                           "fully_paid": False},
                     headers=_hdr(owner_tok), timeout=30)
    # verify: report should have no rows for our fake IDs
    r = requests.get(f"{API}/commissions/report", headers=_hdr(owner_tok), timeout=30)
    assert r.status_code == 200
    row_ids = {row["lead_id"] for row in r.json()["rows"]}
    for lid in (TEST_LEAD_A, TEST_LEAD_B, TEST_LEAD_C, TEST_LEAD_D):
        assert lid not in row_ids, f"leftover row for {lid}"
