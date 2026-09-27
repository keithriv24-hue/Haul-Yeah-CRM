"""Stage 4 backend regression: reliable actuals & versioned job outcomes.

Exercises the real endpoints (owner + Quality; crew/sales blocked) against the live preview
backend, seeding disposable jobs straight into Mongo and cleaning them up afterwards. No live
Square, no customer SMS, and no Airtable writes — the seeded projects have fake ids, so the
Airtable-backed final-total lookup simply resolves to "missing", which is the correct preview state.

Covers:
  - Shared actuals: taps window, multi-truck / multi-person man-hours with NO double counting,
    drive-time subtraction (work vs on-site), GPS fallback, clock-only incomplete, open-punch incomplete.
  - Quote-scope matching: explicit committed link wins; ambiguous legacy scopes stay unmatched+excluded.
  - Immutable versioning: first build = v1; a no-op rebuild adds no version; a real data change (a
    late-synced punch) adds exactly one labeled version; a second unchanged run adds none.
  - Corrections: reason required; owner-only final_total (Quality 403); prior value preserved; the
    correction survives the rebuild; final_total is never a Square/deposit substitute.
  - Re-pointing the quote scope: reason required; original quote-time history preserved.
  - RBAC: crew and sales get 403; Quality never sees revenue (final_total/dollar_variance redacted).
"""
import os
import uuid
from datetime import datetime, timezone

import pymongo
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://haul-yeah-staging.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

OWNER = {"email": os.environ.get("OWNER_EMAIL", "HaulYeahAdmin"), "password": os.environ.get("APP_PASSWORD", "HaulYeah2026!")}
DAY = "2026-06-01"


def _iso(hhmm):
    return f"{DAY}T{hhmm}:00"


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _switch(owner_headers, role):
    r = requests.post(f"{API}/auth/switch-role", headers=owner_headers, json={"role": role}, timeout=15)
    assert r.status_code == 200, f"switch to {role} failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def owner_headers():
    return _login(OWNER)


@pytest.fixture(scope="module")
def quality_headers(owner_headers):
    return _switch(owner_headers, "quality")


@pytest.fixture(scope="module")
def sales_headers(owner_headers):
    return _switch(owner_headers, "sales")


@pytest.fixture(scope="module")
def crew_headers(owner_headers):
    return _switch(owner_headers, "employee")


@pytest.fixture(scope="module")
def db():
    client = pymongo.MongoClient(os.environ["MONGO_URL"])
    yield client[os.environ["DB_NAME"]]
    client.close()


def _entry(db, aid, uid, name, cin, cout, approved=True, estimated=False):
    doc = {
        "_id": str(uuid.uuid4()), "assignment_id": aid, "user_id": uid, "user_name": name,
        "clock_in": {"at": _iso(cin)} if cin else None,
        "clock_out": {"at": _iso(cout)} if cout else None,
        "hours": None, "approved": approved, "estimated": estimated, "flags": [],
    }
    db.time_entries.insert_one(doc)
    return doc["_id"]


@pytest.fixture(scope="module")
def seed(db, owner_headers):
    """Seed every disposable Stage 4 job used across the suite; delete it all afterwards."""
    tag = uuid.uuid4().hex[:8]
    U1, U2, U3 = f"s4u1-{tag}", f"s4u2-{tag}", f"s4u3-{tag}"
    ids = {"projects": [], "leads": [], "assignments": [], "users": [U1, U2, U3], "keys": []}

    def project_key(pid):
        ids["projects"].append(pid)
        k = f"project:{pid}"
        ids["keys"].append(k)
        return k

    # ---- MAIN taps job: two trucks, U1 on BOTH crews but one punch (no double count) ----
    main_pid = f"s4-main-{tag}"
    main_lead = f"s4-lead-main-{tag}"
    ids["leads"].append(main_lead)
    main_key = project_key(main_pid)
    a1 = f"s4-a1-{tag}"
    a2 = f"s4-a2-{tag}"
    ids["assignments"] += [a1, a2]
    db.assignments.insert_one({
        "_id": a1, "project_id": main_pid, "lead_id": main_lead, "job_name": "Stage4 Outcome Fixture — Truck A",
        "job_date": DAY, "exec_status": "Complete", "truck_id": f"s4-truck-{tag}", "one_way_miles": 25,
        "crew": [{"user_id": U1, "name": "S4 Driver", "position": "Driver"},
                 {"user_id": U2, "name": "S4 Helper Two", "position": "Helper"}],
        "crew_lead": {"taps": {
            "arrived": {"at": _iso("09:00")}, "loaded": {"at": _iso("10:00")},
            "dropoff": {"at": _iso("11:00")}, "complete": {"at": _iso("12:00")}}},
        "status_history": [],
    })
    db.assignments.insert_one({
        "_id": a2, "project_id": main_pid, "lead_id": main_lead, "job_name": "Stage4 Outcome Fixture — Truck B",
        "job_date": DAY, "exec_status": "Complete", "truck_id": f"s4-truck2-{tag}",
        "crew": [{"user_id": U1, "name": "S4 Driver", "position": "Driver"},
                 {"user_id": U3, "name": "S4 Helper Three", "position": "Helper"}],
        "crew_lead": {}, "status_history": [],
    })
    _entry(db, a1, U1, "S4 Driver", "08:30", "12:30")       # overlap 3h, drive 1h -> work 2h
    _entry(db, a1, U2, "S4 Helper Two", "09:00", "12:00")   # overlap 3h, drive 1h -> work 2h
    u3_entry = _entry(db, a2, U3, "S4 Helper Three", "09:00", "11:00")  # overlap 2h, drive 1h -> work 1h
    ids["u3_entry"] = u3_entry

    # committed quote (S1) + an alternative saved quote (S2) for re-pointing
    s1 = f"s4-scope1-{tag}"
    s2 = f"s4-scope2-{tag}"
    ids["scopes"] = [s1, s2]
    db.lead_scopes.insert_one({
        "_id": s1, "lead_id": main_lead, "status": "saved", "label": "Committed quote",
        "created_by": "QA Seeder", "amount": 1450, "survey_complete": True,
        "inputs": {"crew": 3}, "pricing": {}, "created_at": _iso("07:00"),
        "result": {"mode": "final", "finalTotal": 1450, "bandLo": 1400, "bandHi": 1600,
                   "schedMH": 6, "billMH": 6, "crewRec": 3}})
    db.lead_scopes.insert_one({
        "_id": s2, "lead_id": main_lead, "status": "saved", "label": "Alternate quote",
        "created_by": "QA Seeder", "amount": 1700, "survey_complete": True,
        "inputs": {"crew": 4}, "pricing": {}, "created_at": _iso("06:00"),
        "result": {"mode": "final", "finalTotal": 1700, "bandLo": 1650, "bandHi": 1800,
                   "schedMH": 8, "billMH": 8, "crewRec": 4}})
    db.lead_quote_links.replace_one(
        {"_id": main_lead},
        {"_id": main_lead, "active_quote_scope_id": s1, "amount": 1450, "mode": "final", "updated_at": _iso("07:05")},
        upsert=True)

    # ---- GPS-only job ----
    gps_pid = f"s4-gps-{tag}"
    gps_key = project_key(gps_pid)
    ag = f"s4-ag-{tag}"
    ids["assignments"].append(ag)
    db.assignments.insert_one({
        "_id": ag, "project_id": gps_pid, "job_name": "Stage4 GPS Fixture", "job_date": DAY,
        "exec_status": "Complete", "truck_id": f"s4-gtruck-{tag}",
        "site_coords": {"lat": 40.8, "lng": -74.2},
        "crew": [{"user_id": U2, "name": "S4 Helper Two", "position": "Driver"}],
        "crew_lead": {}, "status_history": []})
    _entry(db, ag, U2, "S4 Helper Two", "09:00", "12:00")
    for hhmm in ("09:15", "10:30", "11:45"):
        db.gps_pings.insert_one({"_id": str(uuid.uuid4()), "user_id": U2, "at": _iso(hhmm),
                                 "lat": 40.8, "lng": -74.2})

    # ---- clock-only job (no taps, no GPS) ----
    clk_pid = f"s4-clk-{tag}"
    clk_key = project_key(clk_pid)
    ac = f"s4-ac-{tag}"
    ids["assignments"].append(ac)
    db.assignments.insert_one({
        "_id": ac, "project_id": clk_pid, "job_name": "Stage4 ClockOnly Fixture", "job_date": DAY,
        "exec_status": "Complete", "truck_id": f"s4-ctruck-{tag}",
        "crew": [{"user_id": U3, "name": "S4 Helper Three", "position": "Driver"}],
        "crew_lead": {}, "status_history": []})
    _entry(db, ac, U3, "S4 Helper Three", "09:00", "12:00")

    # ---- open-punch job (taps present, but a punch never clocked out) ----
    op_pid = f"s4-open-{tag}"
    op_key = project_key(op_pid)
    ao = f"s4-ao-{tag}"
    ids["assignments"].append(ao)
    db.assignments.insert_one({
        "_id": ao, "project_id": op_pid, "job_name": "Stage4 OpenPunch Fixture", "job_date": DAY,
        "exec_status": "Complete", "truck_id": f"s4-otruck-{tag}",
        "crew": [{"user_id": U1, "name": "S4 Driver", "position": "Driver"}],
        "crew_lead": {"taps": {"arrived": {"at": _iso("09:00")}, "complete": {"at": _iso("12:00")}}},
        "status_history": []})
    _entry(db, ao, U1, "S4 Driver", "09:00", None)  # still on the clock

    # ---- TEST/sample job ----
    ts_pid = f"s4-test-{tag}"
    ts_key = project_key(ts_pid)
    at = f"s4-at-{tag}"
    ids["assignments"].append(at)
    db.assignments.insert_one({
        "_id": at, "project_id": ts_pid, "job_name": "TEST Stage4 sample data", "job_date": DAY,
        "exec_status": "Complete", "truck_id": f"s4-ttruck-{tag}",
        "crew": [{"user_id": U1, "name": "S4 Driver", "position": "Driver"}],
        "crew_lead": {"taps": {"arrived": {"at": _iso("09:00")}, "complete": {"at": _iso("11:00")}}},
        "status_history": []})
    _entry(db, at, U1, "S4 Driver", "09:00", "11:00")

    # ---- ambiguous legacy job: 2 plain saved scopes, no committed link, no amount match ----
    amb_pid = f"s4-amb-{tag}"
    amb_lead = f"s4-lead-amb-{tag}"
    ids["leads"].append(amb_lead)
    amb_key = project_key(amb_pid)
    aa = f"s4-aa-{tag}"
    ids["assignments"].append(aa)
    db.assignments.insert_one({
        "_id": aa, "project_id": amb_pid, "lead_id": amb_lead, "job_name": "Stage4 Ambiguous Fixture",
        "job_date": DAY, "exec_status": "Complete", "truck_id": f"s4-atruck2-{tag}",
        "crew": [{"user_id": U2, "name": "S4 Helper Two", "position": "Driver"}],
        "crew_lead": {"taps": {"arrived": {"at": _iso("09:00")}, "complete": {"at": _iso("12:00")}}},
        "status_history": []})
    _entry(db, aa, U2, "S4 Helper Two", "09:00", "12:00")
    for i in range(2):
        db.lead_scopes.insert_one({
            "_id": f"s4-ambscope-{i}-{tag}", "lead_id": amb_lead, "status": "saved",
            "label": f"legacy {i}", "created_by": "QA Seeder", "amount": 999 + i,
            "survey_complete": False, "inputs": {"crew": 2}, "pricing": {}, "created_at": _iso(f"0{5+i}:00"),
            "result": {"mode": "band", "bandLo": 900, "bandHi": 1100, "crewRec": 2}})
        ids["scopes"].append(f"s4-ambscope-{i}-{tag}")

    ctx = {"main_key": main_key, "main_lead": main_lead, "main_pid": main_pid, "s1": s1, "s2": s2,
           "gps_key": gps_key, "clk_key": clk_key, "op_key": op_key, "ts_key": ts_key,
           "amb_key": amb_key, "u3_entry": u3_entry}
    # Pre-build the main outcome (v1) so /correct and /repoint — which require an existing doc —
    # work regardless of which xdist worker picks up each test.
    requests.get(f"{API}/outcomes/{main_key}?rebuild=1", headers=owner_headers, timeout=25)
    yield ctx

    # ---- teardown ----
    db.assignments.delete_many({"_id": {"$in": ids["assignments"]}})
    db.time_entries.delete_many({"assignment_id": {"$in": ids["assignments"]}})
    db.lead_scopes.delete_many({"lead_id": {"$in": ids["leads"]}})
    db.lead_quote_links.delete_many({"_id": {"$in": ids["leads"]}})
    db.gps_pings.delete_many({"user_id": {"$in": ids["users"]}})
    db.job_outcomes.delete_many({"_id": {"$in": ids["keys"]}})
    db.job_outcome_versions.delete_many({"job_key": {"$in": ids["keys"]}})
    db.outcome_rebuild_queue.delete_many({"_id": {"$in": ids["keys"]}})


def _get(headers, key, rebuild=False):
    url = f"{API}/outcomes/{key}" + ("?rebuild=1" if rebuild else "")
    return requests.get(url, headers=headers, timeout=25)


# ============================ shared actuals =================================

class TestActuals:
    def test_taps_window_and_no_double_count(self, owner_headers, seed):
        r = _get(owner_headers, seed["main_key"], rebuild=True)
        assert r.status_code == 200, r.text
        a = r.json()["actuals"]
        assert a["window_source"] == "taps"
        assert a["on_site_hours"] == 3.0
        # U1 is on BOTH truck crews but punched once -> counted once. 3 + 3 + 2 = 8.
        assert a["actual_man_hours"] == 8.0
        assert a["actual_crew_count"] == 3
        assert a["data_quality"] == "complete"

    def test_drive_time_subtracted_from_work(self, owner_headers, seed):
        a = _get(owner_headers, seed["main_key"]).json()["actuals"]
        # work = on-site minus the loaded->dropoff drive overlap (1h per worker): 2 + 2 + 1 = 5.
        assert a["work_man_hours"] == 5.0
        assert a["work_man_hours"] < a["actual_man_hours"]

    def test_gps_fallback(self, owner_headers, seed):
        a = _get(owner_headers, seed["gps_key"], rebuild=True).json()["actuals"]
        assert a["window_source"] == "gps"
        assert a["on_site_hours"] == 2.5
        assert a["confidence"] == 0.75

    def test_clock_only_is_incomplete(self, owner_headers, seed):
        d = _get(owner_headers, seed["clk_key"], rebuild=True).json()
        a = d["actuals"]
        assert a["window_source"] == "clock_only"
        assert a["on_site_hours"] is None
        assert "no_defensible_window" in a["incomplete_reasons"]
        assert d["data_quality"] == "incomplete"
        assert d["learning_eligible"] is False

    def test_open_punch_is_incomplete(self, owner_headers, seed):
        d = _get(owner_headers, seed["op_key"], rebuild=True).json()
        assert "open_clock_entry" in d["actuals"]["incomplete_reasons"]
        assert d["data_quality"] == "incomplete"
        assert d["exclusion"]["excluded"] is True

    def test_test_sample_job_excluded(self, owner_headers, seed):
        d = _get(owner_headers, seed["ts_key"], rebuild=True).json()
        assert "test_or_sample" in d["exclusion"]["reasons"]
        assert d["exclusion"]["excluded"] is True


# ============================ quote matching =================================

class TestQuoteMatch:
    def test_explicit_committed_quote_wins(self, owner_headers, seed):
        d = _get(owner_headers, seed["main_key"]).json()
        assert d["quote_match"]["rule"] == "explicit_quote_scope_id"
        assert d["quote_match"]["quote_scope_id"] == seed["s1"]
        assert d["quote"]["crew_rec"] == 3

    def test_ambiguous_legacy_stays_unmatched_and_excluded(self, owner_headers, seed):
        d = _get(owner_headers, seed["amb_key"], rebuild=True).json()
        assert d["quote_match"]["rule"] == "ambiguous"
        assert "unmatched_quote" in d["exclusion"]["reasons"]
        assert d["exclusion"]["excluded"] is True

    def test_final_total_never_a_square_substitute(self, owner_headers, seed):
        ft = _get(owner_headers, seed["main_key"]).json()["final_total"]
        # No Airtable job-audit for a fake project -> "missing"; a Square deposit is NEVER substituted.
        assert ft["source"] in ("missing", "job_audit", "project_final_revenue", "owner_correction")
        assert ft["source"] not in ("square", "deposit", "paid_to_date")


# ============================ immutable versioning ===========================

class TestVersioning:
    def test_noop_rebuild_creates_no_version(self, owner_headers, seed):
        _get(owner_headers, seed["main_key"], rebuild=True)  # ensure current
        v1 = _get(owner_headers, seed["main_key"]).json()["version"]
        _get(owner_headers, seed["main_key"], rebuild=True)
        _get(owner_headers, seed["main_key"], rebuild=True)
        v2 = _get(owner_headers, seed["main_key"]).json()["version"]
        assert v2 == v1, f"a no-op rebuild inflated the version {v1} -> {v2}"
        hist = requests.get(f"{API}/outcomes/{seed['main_key']}/history", headers=owner_headers, timeout=20).json()["versions"]
        assert len(hist) == v1

    def test_real_change_adds_exactly_one_labeled_version(self, owner_headers, seed, db):
        before = _get(owner_headers, seed["main_key"]).json()["version"]
        # Simulate a late-synced / reconciled punch: extend U3's clock-out by 30 min.
        db.time_entries.update_one({"_id": seed["u3_entry"]}, {"$set": {"clock_out": {"at": _iso("11:30")}}})
        try:
            after = _get(owner_headers, seed["main_key"], rebuild=True).json()["version"]
            assert after == before + 1
            # a second, unchanged run adds nothing more
            again = _get(owner_headers, seed["main_key"], rebuild=True).json()["version"]
            assert again == after
            hist = requests.get(f"{API}/outcomes/{seed['main_key']}/history", headers=owner_headers, timeout=20).json()["versions"]
            top = hist[0]
            assert top["version"] == after
            assert "actuals" in (top.get("changed_fields") or {})
        finally:
            db.time_entries.update_one({"_id": seed["u3_entry"]}, {"$set": {"clock_out": {"at": _iso("11:00")}}})
            _get(owner_headers, seed["main_key"], rebuild=True)


# ============================ corrections ====================================

class TestCorrections:
    def test_reason_required(self, owner_headers, seed):
        r = requests.post(f"{API}/outcomes/{seed['main_key']}/correct", headers=owner_headers,
                          json={"field": "as_found_note", "value": "x", "reason": "no"}, timeout=20)
        assert r.status_code == 422, r.text

    def test_quality_cannot_correct_final_total(self, quality_headers, seed):
        r = requests.post(f"{API}/outcomes/{seed['main_key']}/correct", headers=quality_headers,
                          json={"field": "final_total", "value": 2500, "reason": "trying as quality"}, timeout=20)
        assert r.status_code == 403, r.text

    def test_owner_corrects_final_total_and_it_survives_rebuild(self, owner_headers, seed):
        r = requests.post(f"{API}/outcomes/{seed['main_key']}/correct", headers=owner_headers,
                          json={"field": "final_total", "value": 2500,
                                "reason": "Final invoice was $2,500 after add-on boxes."}, timeout=25)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["final_total"]["value"] == 2500
        assert d["final_total"]["source"] == "owner_correction"
        assert any(c["field"] == "final_total" and c["value"] == 2500 for c in d.get("corrections", []))
        # a plain rebuild must NOT clobber the correction
        again = _get(owner_headers, seed["main_key"], rebuild=True).json()
        assert again["final_total"]["value"] == 2500
        # dollar variance now derivable (final 2500 - quote 1450)
        assert again["errors"].get("dollar_variance") == 1050.0

    def test_owner_corrects_as_found_note_preserves_prior(self, owner_headers, seed):
        first = requests.post(f"{API}/outcomes/{seed['main_key']}/correct", headers=owner_headers,
                              json={"field": "as_found_note", "value": "Customer not packed.",
                                    "reason": "Crew noted customer was not packed at all."}, timeout=25)
        assert first.status_code == 200, first.text
        second = requests.post(f"{API}/outcomes/{seed['main_key']}/correct", headers=owner_headers,
                               json={"field": "as_found_note", "value": "Partially packed.",
                                     "reason": "Correcting — kitchen was actually done."}, timeout=25)
        assert second.status_code == 200, second.text
        d = second.json()
        assert d["corrections_map"]["as_found_note"] == "Partially packed."
        note_entries = [c for c in d["corrections"] if c["field"] == "as_found_note"]
        assert len(note_entries) >= 2
        assert note_entries[-1]["before"] == "Customer not packed."  # prior value preserved


# ============================ re-point scope =================================

class TestRepoint:
    def test_candidate_scopes_listed(self, owner_headers, seed):
        r = requests.get(f"{API}/outcomes/{seed['main_key']}/scopes", headers=owner_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        ids = {s["id"] for s in data["scopes"]}
        assert seed["s1"] in ids and seed["s2"] in ids
        assert data["active_quote_scope_id"] == seed["s1"]
        assert any(s["amount"] is not None for s in data["scopes"])

    def test_quality_scopes_have_no_amount(self, quality_headers, seed):
        data = requests.get(f"{API}/outcomes/{seed['main_key']}/scopes", headers=quality_headers, timeout=20).json()
        assert all(s["amount"] is None for s in data["scopes"])

    def test_repoint_requires_reason(self, owner_headers, seed):
        r = requests.post(f"{API}/outcomes/{seed['main_key']}/repoint-scope", headers=owner_headers,
                          json={"quote_scope_id": seed["s2"], "reason": "x"}, timeout=20)
        assert r.status_code == 422, r.text

    def test_repoint_preserves_history(self, owner_headers, seed, db):
        before = requests.get(f"{API}/outcomes/{seed['main_key']}/history", headers=owner_headers, timeout=20).json()["versions"]
        old_scope = _get(owner_headers, seed["main_key"]).json()["quote_match"]["quote_scope_id"]
        r = requests.post(f"{API}/outcomes/{seed['main_key']}/repoint-scope", headers=owner_headers,
                          json={"quote_scope_id": seed["s2"],
                                "reason": "This job was actually quoted on the alternate scope."}, timeout=25)
        assert r.status_code == 200, r.text
        assert r.json()["quote_match"]["quote_scope_id"] == seed["s2"]
        assert db.lead_quote_links.find_one({"_id": seed["main_lead"]})["active_quote_scope_id"] == seed["s2"]
        after = requests.get(f"{API}/outcomes/{seed['main_key']}/history", headers=owner_headers, timeout=20).json()["versions"]
        assert len(after) > len(before)
        # an earlier immutable version still references the original committed scope
        assert any((v.get("snapshot", {}).get("quote_match", {}) or {}).get("quote_scope_id") == old_scope
                   for v in after)
        # restore
        requests.post(f"{API}/outcomes/{seed['main_key']}/repoint-scope", headers=owner_headers,
                      json={"quote_scope_id": seed["s1"], "reason": "Restoring the committed quote."}, timeout=25)


# ============================ RBAC + Quality redaction =======================

class TestAccess:
    def test_crew_blocked(self, crew_headers, seed):
        assert _get(crew_headers, seed["main_key"]).status_code == 403

    def test_sales_blocked(self, sales_headers, seed):
        assert _get(sales_headers, seed["main_key"]).status_code == 403

    def test_unauthenticated_blocked(self, seed):
        r = requests.get(f"{API}/outcomes/{seed['main_key']}", timeout=20)
        assert r.status_code in (401, 403)

    def test_quality_never_sees_revenue(self, quality_headers, owner_headers, seed):
        # ensure a real final_total exists (owner correction from earlier), then check redaction
        requests.post(f"{API}/outcomes/{seed['main_key']}/correct", headers=owner_headers,
                      json={"field": "final_total", "value": 2500, "reason": "ensure revenue present for redaction test"}, timeout=25)
        d = _get(quality_headers, seed["main_key"]).json()
        assert d["final_total"]["value"] is None
        assert d["final_total"].get("redacted") is True
        assert "dollar_variance" not in d["errors"]
        assert "in_band" not in d["errors"]
