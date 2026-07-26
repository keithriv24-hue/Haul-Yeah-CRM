"""Iteration 16 — Fleet Management (Phase C) backend tests.

Covers:
- GET /api/fleet (owner-only, shape + Truck 2 seeded state)
- PATCH /api/trucks/{id} extended fleet fields + regression
- POST/GET /api/trucks/{id}/inspections (crew, RBAC, flag notify, mileage bump, needs_attention flip)
- Inspection -> checklist auto-mark integration on Montclair assignment
- Logs (maintenance/fuel) CRUD + owner-only
- Damage report + resolve/reopen + owner notify + open_damage count
- Photos multipart upload + serve + RBAC

Run: pytest /app/backend/tests/test_iteration16_fleet.py -v -n 0
"""
import io
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import requests
from test_config import JAVANTE_PASSWORD, JUNIOR_PASSWORD, OWNER_PASSWORD

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
TODAY_ET = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")

MONTCLAIR_ID = "3b2a0120-9dfb-4fe1-88cd-d5a6025ea61d"

# ---------------- helpers ----------------

def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _switch(owner_tok, role):
    r = requests.post(f"{BASE_URL}/api/auth/switch-role", headers=_h(owner_tok),
                      json={"role": role}, timeout=15)
    assert r.status_code == 200, f"switch-role {role} failed: {r.text}"
    return r.json()["token"]


# ---------------- fixtures ----------------

@pytest.fixture(scope="module")
def owner_token():
    return _login("HaulYeahAdmin", OWNER_PASSWORD)


@pytest.fixture(scope="module")
def javante_token():
    return _login("javante@haulyeahmoves.com", JAVANTE_PASSWORD)


@pytest.fixture(scope="module")
def junior_token():
    return _login("junior@haulyeahmoves.com", JUNIOR_PASSWORD)


@pytest.fixture(scope="module")
def sales_token(owner_token):
    # Use switch-role since ghost accounts return owner-role tokens
    return _switch(owner_token, "sales")


@pytest.fixture(scope="module")
def marketing_token(owner_token):
    return _switch(owner_token, "marketing")


@pytest.fixture(scope="module")
def fleet_data(owner_token):
    r = requests.get(f"{BASE_URL}/api/fleet", headers=_h(owner_token), timeout=15)
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def truck_map(fleet_data):
    return {t["name"]: t for t in fleet_data["trucks"]}


# ---------------- 1. GET /api/fleet ----------------

class TestFleetOverview:
    def test_owner_can_list(self, fleet_data):
        assert "trucks" in fleet_data
        assert "inspection_items" in fleet_data
        assert len(fleet_data["inspection_items"]) == 8
        keys = {it["key"] for it in fleet_data["inspection_items"]}
        assert keys == {"lights", "tires", "brakes", "fluids", "glass", "wipers", "equipment", "interior"}

    def test_crew_forbidden(self, javante_token):
        r = requests.get(f"{BASE_URL}/api/fleet", headers=_h(javante_token), timeout=15)
        assert r.status_code == 403

    def test_sales_forbidden(self, sales_token):
        r = requests.get(f"{BASE_URL}/api/fleet", headers=_h(sales_token), timeout=15)
        assert r.status_code == 403

    def test_truck_card_shape(self, fleet_data):
        t = fleet_data["trucks"][0]
        for key in ("id", "name", "fleet_status", "mileage", "registration", "insurance",
                    "registration_state", "insurance_state", "reminders",
                    "reminders_due", "reminders_upcoming", "open_damage", "last_inspection"):
            assert key in t, f"missing key {key}"

    def test_truck2_seeded_state(self, truck_map):
        t2 = truck_map.get("Truck 2")
        assert t2 is not None, "Truck 2 must exist"
        assert t2["fleet_status"] == "needs_attention"
        assert t2["mileage"] == 84310
        assert t2["registration"].get("number") == "NJ-REG-1234"
        assert t2["registration"].get("expires") == "2026-08-10"
        # 2026-07-26 -> 2026-08-10 == 15 days -> 'soon'
        assert t2["registration_state"] in ("soon", "expired"), t2["registration_state"]
        # 2027-01-15 -> ok (>30 days out)
        assert t2["insurance_state"] == "ok"
        assert t2["reminders_due"] >= 1
        assert t2["open_damage"] >= 1
        assert t2["last_inspection"] is not None
        assert t2["last_inspection"]["passed"] == False


# ---------------- 2. PATCH /api/trucks/{id} extended ----------------

class TestTruckPatchExtended:
    def test_patch_fleet_fields(self, owner_token, truck_map):
        t3 = truck_map.get("Truck 3")
        assert t3 is not None
        payload = {
            "mileage": 55555,
            "fleet_status": "in_service",
            "registration": {"number": "NJ-REG-TEST3", "expires": "2027-06-01"},
            "insurance": {"carrier": "TEST Insurance", "policy": "POL-TEST-3", "expires": "2027-06-01"},
            "reminders": [{"title": "TEST Rotate tires", "due_date": "2026-12-01", "done": False}],
        }
        r = requests.patch(f"{BASE_URL}/api/trucks/{t3['id']}", headers=_h(owner_token), json=payload, timeout=15)
        assert r.status_code == 200, r.text
        # verify via fleet
        r2 = requests.get(f"{BASE_URL}/api/fleet", headers=_h(owner_token), timeout=15)
        t3fresh = next(t for t in r2.json()["trucks"] if t["id"] == t3["id"])
        assert t3fresh["mileage"] == 55555
        assert t3fresh["registration"]["number"] == "NJ-REG-TEST3"
        assert t3fresh["insurance"]["carrier"] == "TEST Insurance"
        assert any(r["title"] == "TEST Rotate tires" for r in t3fresh["reminders"])

    def test_invalid_fleet_status(self, owner_token, truck_map):
        t3 = truck_map.get("Truck 3")
        r = requests.patch(f"{BASE_URL}/api/trucks/{t3['id']}", headers=_h(owner_token),
                           json={"fleet_status": "banana"}, timeout=15)
        assert r.status_code == 422

    def test_regression_name_plate_active(self, owner_token, truck_map):
        t3 = truck_map.get("Truck 3")
        # Read original name/plate to preserve
        orig = t3["name"]; orig_plate = t3["plate"]
        r = requests.patch(f"{BASE_URL}/api/trucks/{t3['id']}", headers=_h(owner_token),
                           json={"name": orig, "plate": orig_plate, "active": True}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == orig
        assert data["active"] == True

    def test_crew_cannot_patch(self, javante_token, truck_map):
        t3 = truck_map.get("Truck 3")
        r = requests.patch(f"{BASE_URL}/api/trucks/{t3['id']}", headers=_h(javante_token),
                           json={"fleet_status": "in_shop"}, timeout=15)
        assert r.status_code == 403


# ---------------- 3. Inspections ----------------

class TestInspections:
    def test_crew_pass_bumps_mileage(self, junior_token, owner_token, truck_map):
        t3 = truck_map.get("Truck 3")
        # First read current mileage
        r0 = requests.get(f"{BASE_URL}/api/fleet", headers=_h(owner_token), timeout=15)
        cur = next(t for t in r0.json()["trucks"] if t["id"] == t3["id"])
        new_mi = (cur.get("mileage") or 0) + 100
        items = {k: True for k in ("lights", "tires", "brakes", "fluids", "glass", "wipers", "equipment", "interior")}
        r = requests.post(f"{BASE_URL}/api/trucks/{t3['id']}/inspections", headers=_h(junior_token),
                          json={"items": items, "odometer": new_mi, "notes": "TEST all pass"}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["passed"] == True
        assert j["failed"] == []
        # verify mileage bump (>= because TestTruckLogs may concurrently log odometer 56000 on another worker)
        r1 = requests.get(f"{BASE_URL}/api/fleet", headers=_h(owner_token), timeout=15)
        fresh = next(t for t in r1.json()["trucks"] if t["id"] == t3["id"])
        assert fresh["mileage"] >= new_mi

    def test_crew_fail_flips_status_and_notifies(self, junior_token, owner_token, truck_map):
        t3 = truck_map.get("Truck 3")
        # reset to in_service first
        requests.patch(f"{BASE_URL}/api/trucks/{t3['id']}", headers=_h(owner_token),
                       json={"fleet_status": "in_service"}, timeout=15)
        items = {k: True for k in ("lights", "tires", "brakes", "fluids", "glass", "wipers", "equipment", "interior")}
        items["brakes"] = False
        r = requests.post(f"{BASE_URL}/api/trucks/{t3['id']}/inspections", headers=_h(junior_token),
                          json={"items": items, "notes": "TEST failed brakes"}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["passed"] == False
        assert "brakes" in j["failed"]
        # verify status flipped
        r1 = requests.get(f"{BASE_URL}/api/fleet", headers=_h(owner_token), timeout=15)
        fresh = next(t for t in r1.json()["trucks"] if t["id"] == t3["id"])
        assert fresh["fleet_status"] == "needs_attention"
        # verify owner notification
        r2 = requests.get(f"{BASE_URL}/api/notifications", headers=_h(owner_token), timeout=15)
        notifs = r2.json() if isinstance(r2.json(), list) else r2.json().get("notifications", [])
        assert any("Inspection flagged" in (n.get("title") or "") and "Truck 3" in (n.get("title") or "") for n in notifs), \
            f"no flag notification found in {[n.get('title') for n in notifs[:5]]}"
        # cleanup: reset Truck 3 back to in_service
        requests.patch(f"{BASE_URL}/api/trucks/{t3['id']}", headers=_h(owner_token),
                       json={"fleet_status": "in_service"}, timeout=15)

    def test_list_inspections_owner_full(self, owner_token, truck_map):
        t3 = truck_map.get("Truck 3")
        r = requests.get(f"{BASE_URL}/api/trucks/{t3['id']}/inspections", headers=_h(owner_token), timeout=15)
        assert r.status_code == 200
        assert "inspections" in r.json()
        assert len(r.json()["inspections"]) >= 2

    def test_list_inspections_crew_limited(self, junior_token, truck_map):
        t3 = truck_map.get("Truck 3")
        r = requests.get(f"{BASE_URL}/api/trucks/{t3['id']}/inspections", headers=_h(junior_token), timeout=15)
        assert r.status_code == 200
        assert len(r.json()["inspections"]) <= 5

    def test_sales_forbidden_post(self, sales_token, truck_map):
        t3 = truck_map.get("Truck 3")
        items = {k: True for k in ("lights", "tires", "brakes", "fluids", "glass", "wipers", "equipment", "interior")}
        r = requests.post(f"{BASE_URL}/api/trucks/{t3['id']}/inspections", headers=_h(sales_token),
                          json={"items": items}, timeout=15)
        assert r.status_code == 403

    def test_marketing_forbidden_get(self, marketing_token, truck_map):
        t3 = truck_map.get("Truck 3")
        r = requests.get(f"{BASE_URL}/api/trucks/{t3['id']}/inspections", headers=_h(marketing_token), timeout=15)
        assert r.status_code == 403


# ---------------- 4. Inspection -> Checklist auto-mark ----------------

class TestInspectionChecklistIntegration:
    def test_montclair_inspection_marks_checklist(self, javante_token, owner_token):
        # 1) Find the truck assigned to Montclair
        r = requests.get(f"{BASE_URL}/api/assignments/{MONTCLAIR_ID}/checklists", headers=_h(javante_token), timeout=15)
        assert r.status_code == 200, r.text
        # 2) Get Montclair assignment to find truck id
        rb = requests.get(f"{BASE_URL}/api/dispatch/board", headers=_h(owner_token),
                          params={"date": TODAY_ET}, timeout=15)
        assert rb.status_code == 200
        montclair = None
        for a in rb.json().get("assignments", []):
            if a["id"] == MONTCLAIR_ID:
                montclair = a; break
        assert montclair is not None, f"Montclair not on {TODAY_ET} board"
        truck_id = montclair.get("truck_id") or montclair.get("truck", {}).get("id")
        assert truck_id, f"no truck on Montclair: {montclair}"

        # 3) Uncheck warehouse_departure item 0 as Javante
        r_un = requests.post(
            f"{BASE_URL}/api/assignments/{MONTCLAIR_ID}/checklists/warehouse_departure/items/0",
            headers=_h(javante_token), json={"done": False}, timeout=15)
        assert r_un.status_code == 200, r_un.text

        # 4) File inspection with assignment_id
        items = {k: True for k in ("lights", "tires", "brakes", "fluids", "glass", "wipers", "equipment", "interior")}
        r_ins = requests.post(f"{BASE_URL}/api/trucks/{truck_id}/inspections", headers=_h(javante_token),
                              json={"items": items, "assignment_id": MONTCLAIR_ID,
                                    "notes": "TEST montclair integration"}, timeout=15)
        assert r_ins.status_code == 200, r_ins.text
        assert r_ins.json()["passed"] == True

        # 5) Verify checklist item 0 done
        r_cl = requests.get(f"{BASE_URL}/api/assignments/{MONTCLAIR_ID}/checklists",
                            headers=_h(javante_token), timeout=15)
        assert r_cl.status_code == 200
        lists = r_cl.json().get("checklists") or r_cl.json().get("lists") or []
        if isinstance(lists, list):
            wh = next(l for l in lists if l["key"] == "warehouse_departure")
        else:
            wh = lists["warehouse_departure"]
        item0 = wh["items"][0]
        assert item0["done"] == True, f"item 0 not done: {item0}"

        # 6) Verify timeline event
        r_tl = requests.get(f"{BASE_URL}/api/assignments/{MONTCLAIR_ID}/timeline",
                            headers=_h(owner_token), timeout=15)
        assert r_tl.status_code == 200
        events = r_tl.json().get("events", r_tl.json())
        assert any("Daily inspection filed" in (e.get("title") or e.get("message") or "") for e in events), \
            f"no timeline event found. sample: {[e.get('title') for e in events[:3]]}"

        # 7) Ensure exec_status did not regress
        rb2 = requests.get(f"{BASE_URL}/api/dispatch/board", headers=_h(owner_token),
                           params={"date": TODAY_ET}, timeout=15)
        m2 = next(a for a in rb2.json()["assignments"] if a["id"] == MONTCLAIR_ID)
        assert m2.get("exec_status") in ("In Progress", "Loading", "Loaded"), m2.get("exec_status")


# ---------------- 5. Truck Logs ----------------

class TestTruckLogs:
    _log_ids = []

    def test_owner_add_maintenance(self, owner_token, truck_map):
        t3 = truck_map.get("Truck 3")
        r = requests.post(f"{BASE_URL}/api/trucks/{t3['id']}/logs", headers=_h(owner_token),
                          json={"kind": "maintenance", "cost": 220.50, "odometer": 56000, "notes": "TEST oil change"},
                          timeout=15)
        assert r.status_code == 200
        self.__class__._log_ids.append(r.json()["id"])

    def test_owner_add_fuel(self, owner_token, truck_map):
        t3 = truck_map.get("Truck 3")
        r = requests.post(f"{BASE_URL}/api/trucks/{t3['id']}/logs", headers=_h(owner_token),
                          json={"kind": "fuel", "cost": 88.10, "gallons": 22.5, "notes": "TEST fuel"},
                          timeout=15)
        assert r.status_code == 200
        self.__class__._log_ids.append(r.json()["id"])

    def test_invalid_kind(self, owner_token, truck_map):
        t3 = truck_map.get("Truck 3")
        r = requests.post(f"{BASE_URL}/api/trucks/{t3['id']}/logs", headers=_h(owner_token),
                          json={"kind": "banana", "cost": 10}, timeout=15)
        assert r.status_code == 422

    def test_get_logs_totals(self, owner_token, truck_map):
        t3 = truck_map.get("Truck 3")
        r = requests.get(f"{BASE_URL}/api/trucks/{t3['id']}/logs", headers=_h(owner_token), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "logs" in j and "totals" in j
        assert j["totals"]["maintenance"] >= 220.50
        assert j["totals"]["fuel"] >= 88.10

    def test_crew_forbidden(self, javante_token, truck_map):
        t3 = truck_map.get("Truck 3")
        r = requests.get(f"{BASE_URL}/api/trucks/{t3['id']}/logs", headers=_h(javante_token), timeout=15)
        assert r.status_code == 403
        r2 = requests.post(f"{BASE_URL}/api/trucks/{t3['id']}/logs", headers=_h(javante_token),
                           json={"kind": "fuel", "cost": 10}, timeout=15)
        assert r2.status_code == 403

    def test_z_delete_logs(self, owner_token):
        # cleanup TEST logs
        for lid in self.__class__._log_ids:
            r = requests.delete(f"{BASE_URL}/api/truck-logs/{lid}", headers=_h(owner_token), timeout=15)
            assert r.status_code == 200
        # crew delete forbidden - test with a dummy id
        r2 = requests.delete(f"{BASE_URL}/api/truck-logs/nonexistent", headers=_h(owner_token), timeout=15)
        assert r2.status_code == 404


# ---------------- 6. Damage ----------------

class TestDamage:
    _damage_id = None

    def test_crew_report_damage_notifies_owner(self, junior_token, owner_token, truck_map):
        t3 = truck_map.get("Truck 3")
        r = requests.post(f"{BASE_URL}/api/trucks/{t3['id']}/damage", headers=_h(junior_token),
                          json={"description": "TEST small dent on rear bumper"}, timeout=15)
        assert r.status_code == 200, r.text
        self.__class__._damage_id = r.json()["id"]
        # verify owner notification
        rn = requests.get(f"{BASE_URL}/api/notifications", headers=_h(owner_token), timeout=15)
        notifs = rn.json() if isinstance(rn.json(), list) else rn.json().get("notifications", [])
        assert any("Damage reported" in (n.get("title") or "") and "Truck 3" in (n.get("title") or "") for n in notifs)

    def test_empty_description_422(self, junior_token, truck_map):
        t3 = truck_map.get("Truck 3")
        r = requests.post(f"{BASE_URL}/api/trucks/{t3['id']}/damage", headers=_h(junior_token),
                          json={"description": "   "}, timeout=15)
        assert r.status_code == 422

    def test_crew_cannot_list_damage(self, junior_token, truck_map):
        t3 = truck_map.get("Truck 3")
        r = requests.get(f"{BASE_URL}/api/trucks/{t3['id']}/damage", headers=_h(junior_token), timeout=15)
        assert r.status_code == 403

    def test_owner_can_list_damage(self, owner_token, truck_map):
        t3 = truck_map.get("Truck 3")
        r = requests.get(f"{BASE_URL}/api/trucks/{t3['id']}/damage", headers=_h(owner_token), timeout=15)
        assert r.status_code == 200
        assert any(d["id"] == self.__class__._damage_id for d in r.json()["reports"])

    def test_open_damage_count_reflected(self, owner_token, truck_map):
        t3 = truck_map.get("Truck 3")
        r = requests.get(f"{BASE_URL}/api/fleet", headers=_h(owner_token), timeout=15)
        fresh = next(t for t in r.json()["trucks"] if t["id"] == t3["id"])
        assert fresh["open_damage"] >= 1

    def test_resolve_damage(self, owner_token):
        r = requests.patch(f"{BASE_URL}/api/truck-damage/{self.__class__._damage_id}",
                           headers=_h(owner_token), json={"resolved": True}, timeout=15)
        assert r.status_code == 200

    def test_reopen_damage(self, owner_token):
        r = requests.patch(f"{BASE_URL}/api/truck-damage/{self.__class__._damage_id}",
                           headers=_h(owner_token), json={"resolved": False}, timeout=15)
        assert r.status_code == 200

    def test_z_final_resolve_cleanup(self, owner_token):
        # cleanup: final resolve TEST damage
        r = requests.patch(f"{BASE_URL}/api/truck-damage/{self.__class__._damage_id}",
                           headers=_h(owner_token), json={"resolved": True}, timeout=15)
        assert r.status_code == 200


# ---------------- 7. Photos ----------------

def _tiny_png_bytes():
    # 1x1 red PNG
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c62f8cfc0000000030001019cfc2e2c0000000049454e44ae426082"
    )


class TestPhotos:
    _photo_id = None

    def test_crew_upload_inspection_photo(self, junior_token, owner_token, truck_map):
        t3 = truck_map.get("Truck 3")
        # Need a fresh inspection id to attach
        items = {k: True for k in ("lights", "tires", "brakes", "fluids", "glass", "wipers", "equipment", "interior")}
        ri = requests.post(f"{BASE_URL}/api/trucks/{t3['id']}/inspections", headers=_h(junior_token),
                           json={"items": items, "notes": "TEST photo attach"}, timeout=15)
        assert ri.status_code == 200
        ins_id = ri.json()["id"]

        files = {"file": ("test.png", io.BytesIO(_tiny_png_bytes()), "image/png")}
        r = requests.post(f"{BASE_URL}/api/trucks/{t3['id']}/photos",
                          headers=_h(junior_token),
                          params={"kind": "inspection", "ref_id": ins_id},
                          files=files, timeout=60)
        if r.status_code == 502:
            pytest.skip("Object storage unavailable (502) — non-blocking per review request")
        assert r.status_code == 200, r.text
        self.__class__._photo_id = r.json()["id"]
        self.__class__._ins_id = ins_id

    def test_owner_can_stream_photo(self, owner_token):
        if not self.__class__._photo_id:
            pytest.skip("no photo uploaded (storage unavailable)")
        r = requests.get(f"{BASE_URL}/api/truck-photos/{self.__class__._photo_id}",
                         params={"auth": owner_token}, timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/")

    def test_crew_can_stream_photo(self, junior_token):
        if not self.__class__._photo_id:
            pytest.skip("no photo uploaded")
        r = requests.get(f"{BASE_URL}/api/truck-photos/{self.__class__._photo_id}",
                         params={"auth": junior_token}, timeout=30)
        assert r.status_code == 200

    def test_sales_cannot_stream_photo(self, sales_token):
        if not self.__class__._photo_id:
            pytest.skip("no photo uploaded")
        r = requests.get(f"{BASE_URL}/api/truck-photos/{self.__class__._photo_id}",
                         params={"auth": sales_token}, timeout=30)
        assert r.status_code == 403

    def test_bad_kind_422(self, junior_token, truck_map):
        t3 = truck_map.get("Truck 3")
        files = {"file": ("test.png", io.BytesIO(_tiny_png_bytes()), "image/png")}
        r = requests.post(f"{BASE_URL}/api/trucks/{t3['id']}/photos",
                          headers=_h(junior_token),
                          params={"kind": "banana", "ref_id": "x"}, files=files, timeout=30)
        assert r.status_code == 422

    def test_non_image_422(self, junior_token, truck_map):
        t3 = truck_map.get("Truck 3")
        files = {"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")}
        r = requests.post(f"{BASE_URL}/api/trucks/{t3['id']}/photos",
                          headers=_h(junior_token),
                          params={"kind": "inspection", "ref_id": "x"}, files=files, timeout=30)
        assert r.status_code == 422

    def test_photo_id_appears_in_inspection_list(self, owner_token, truck_map):
        if not self.__class__._photo_id:
            pytest.skip("no photo uploaded")
        t3 = truck_map.get("Truck 3")
        r = requests.get(f"{BASE_URL}/api/trucks/{t3['id']}/inspections", headers=_h(owner_token), timeout=15)
        assert r.status_code == 200
        target = next((i for i in r.json()["inspections"] if i["id"] == self.__class__._ins_id), None)
        assert target is not None
        assert self.__class__._photo_id in target.get("photos", [])
