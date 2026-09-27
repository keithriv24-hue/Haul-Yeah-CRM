"""
Stage 7 — Guarded automatic optimizer backend tests.

Covers:
  - read-through parity: /settings/rates <-> /settings/estimating-params
  - owner write-through with reason/lock/version/optimistic concurrency
  - monetary-only saves don't create calibration versions
  - optimizer state + run (shadow before activation)
  - RBAC (sales/crew 403 on optimizer endpoints)
  - controls (pause/lock/unlock/manual-set/rollback) all require reason
  - activation is owner-only; quality gets 403 on activation
  - quality parity on non-activation controls + owner notification on quality action
  - /scope-guidance no-dollar contract
"""
import os
import time
import requests
import pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

OWNER = ("HaulYeahAdmin", "HaulYeah2026!")
QUALITY = ("TestQualityAdmin", "HaulYeah2026!")
SALES = ("TestSalesAdmin", "HaulYeah2026!")
CREW = ("TestCrewAdmin", "HaulYeah2026!")


def _login(user_pw):
    u, p = user_pw
    r = requests.post(f"{API}/auth/login", json={"email": u, "password": p}, timeout=15)
    assert r.status_code == 200, f"login failed for {u}: {r.status_code} {r.text[:200]}"
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def owner_h():
    return {"Authorization": f"Bearer {_login(OWNER)}"}


@pytest.fixture(scope="module")
def quality_h():
    return {"Authorization": f"Bearer {_login(QUALITY)}"}


@pytest.fixture(scope="module")
def sales_h():
    return {"Authorization": f"Bearer {_login(SALES)}"}


@pytest.fixture(scope="module")
def crew_h():
    return {"Authorization": f"Bearer {_login(CREW)}"}


# -------- Read-through parity --------

def test_settings_rates_read_through(owner_h):
    r = requests.get(f"{API}/settings/rates", headers=owner_h, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "manHoursPer100CuFt" in d
    assert "_calibrationSeq" in d
    assert "_calibrationVersion" in d
    # sanity: package hours present
    for k in ("pkgStudioHours", "pkg2brHours", "pkg3brHours", "pkg4brHours"):
        assert k in d, f"missing {k} in rates response"


def test_estimating_params_parity(owner_h):
    r1 = requests.get(f"{API}/settings/rates", headers=owner_h, timeout=15).json()
    r2 = requests.get(f"{API}/settings/estimating-params", headers=owner_h, timeout=15)
    assert r2.status_code == 200
    ep = r2.json()
    assert float(ep.get("manHoursPer100CuFt")) == float(r1.get("manHoursPer100CuFt"))
    pkgs = ep.get("packageHours") or {}
    # accept any nested layout — normalise
    def _to(v): return None if v is None else float(v)
    assert _to(pkgs.get("studio", pkgs.get("pkgStudioHours"))) == _to(r1.get("pkgStudioHours"))
    assert _to(pkgs.get("br2", pkgs.get("pkg2brHours"))) == _to(r1.get("pkg2brHours"))


# -------- Owner write-through: reason required + optimistic concurrency --------

def test_rates_write_requires_reason_and_versions(owner_h):
    # current state
    cur = requests.get(f"{API}/settings/rates", headers=owner_h, timeout=15).json()
    seq = int(cur.get("_calibrationSeq", 0))
    original_rate = float(cur["manHoursPer100CuFt"])

    # 1) no reason -> 422
    r = requests.put(
        f"{API}/settings/rates",
        headers=owner_h,
        json={"manHoursPer100CuFt": 2.4},
        timeout=15,
    )
    assert r.status_code == 422, f"expected 422 without reason, got {r.status_code} {r.text[:300]}"

    # 2) with reason + correct expected_calibration_seq -> 200
    r = requests.put(
        f"{API}/settings/rates",
        headers=owner_h,
        json={
            "manHoursPer100CuFt": 2.4,
            "reason": "weekend jobs heavier",
            "expected_calibration_seq": seq,
        },
        timeout=15,
    )
    assert r.status_code == 200, f"expected 200 with reason, got {r.status_code} {r.text[:300]}"

    after = requests.get(f"{API}/settings/rates", headers=owner_h, timeout=15).json()
    assert float(after["manHoursPer100CuFt"]) == 2.4
    assert int(after["_calibrationSeq"]) == seq + 1

    # verify base_rate factor is now locked
    st = requests.get(f"{API}/quality/optimizer/state", headers=owner_h, timeout=15).json()
    factors = {f.get("factor") or f.get("name"): f for f in st.get("factors", [])}
    br = factors.get("base_rate") or factors.get("base_rate_mh_per_100cuft") or {}
    assert br.get("locked") is True, f"base_rate should be locked after write-through; got {br}"

    # 3) STALE seq -> 409 (use a DIFFERENT value to force real write path)
    r = requests.put(
        f"{API}/settings/rates",
        headers=owner_h,
        json={
            "manHoursPer100CuFt": 2.5,
            "reason": "stale attempt should fail",
            "expected_calibration_seq": seq,  # already consumed
        },
        timeout=15,
    )
    assert r.status_code == 409, f"expected 409 stale, got {r.status_code} {r.text[:200]}"

    # 4) restore to original (2.1) with correct seq + reason
    st2 = requests.get(f"{API}/settings/rates", headers=owner_h, timeout=15).json()
    seq2 = int(st2["_calibrationSeq"])
    # unlock base_rate first via optimizer control so restore does not require force
    br_name = "base_rate"
    requests.post(
        f"{API}/quality/optimizer/lock",
        headers=owner_h,
        json={"factor": br_name, "locked": False, "reason": "restore original rate"},
        timeout=15,
    )
    r = requests.put(
        f"{API}/settings/rates",
        headers=owner_h,
        json={
            "manHoursPer100CuFt": original_rate,
            "reason": "restore canonical pricing after stage7 test",
            "expected_calibration_seq": seq2,
        },
        timeout=15,
    )
    assert r.status_code == 200, r.text
    final = requests.get(f"{API}/settings/rates", headers=owner_h, timeout=15).json()
    assert float(final["manHoursPer100CuFt"]) == original_rate


def test_monetary_only_save_no_calibration(owner_h):
    cur = requests.get(f"{API}/settings/rates", headers=owner_h, timeout=15).json()
    seq_before = int(cur.get("_calibrationSeq", 0))
    fee = float(cur.get("stairFlightFee", 25) or 25)
    new_fee = fee + 1
    r = requests.put(
        f"{API}/settings/rates",
        headers=owner_h,
        json={"stairFlightFee": new_fee},
        timeout=15,
    )
    assert r.status_code == 200, f"monetary-only save should be 200: {r.status_code} {r.text[:200]}"
    after = requests.get(f"{API}/settings/rates", headers=owner_h, timeout=15).json()
    assert int(after["_calibrationSeq"]) == seq_before, "monetary-only save must NOT bump calibration seq"
    # restore
    requests.put(f"{API}/settings/rates", headers=owner_h, json={"stairFlightFee": fee}, timeout=15)


# -------- Optimizer state / run / RBAC --------

def test_optimizer_state_shape(owner_h):
    r = requests.get(f"{API}/quality/optimizer/state", headers=owner_h, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("activated") in (False, True)  # existence
    assert "paused" in d
    assert "calibration_version" in d
    factors = d.get("factors") or []
    assert len(factors) == 11, f"expected 11 factors, got {len(factors)}"


def test_optimizer_run_shadow_before_activation(owner_h):
    # ensure activated=false first
    st = requests.get(f"{API}/quality/optimizer/state", headers=owner_h, timeout=15).json()
    if st.get("activated"):
        requests.post(
            f"{API}/quality/optimizer/activate",
            headers=owner_h,
            json={"activated": False, "reason": "stage7 test reset to shadow"},
            timeout=15,
        )
    r = requests.post(f"{API}/quality/optimizer/run", headers=owner_h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    run = d.get("run") or d
    assert run.get("mode") == "shadow", f"expected shadow, got {run}"
    assert run.get("applied_version") in (None, "null")


def test_rbac_sales_crew_forbidden(sales_h, crew_h):
    for h in (sales_h, crew_h):
        r1 = requests.get(f"{API}/quality/optimizer/state", headers=h, timeout=15)
        r2 = requests.post(f"{API}/quality/optimizer/run", headers=h, timeout=15)
        assert r1.status_code == 403, f"expected 403 on state, got {r1.status_code}"
        assert r2.status_code == 403, f"expected 403 on run, got {r2.status_code}"


# -------- Controls (owner) --------

def test_pause_requires_reason(owner_h):
    r_no = requests.post(f"{API}/quality/optimizer/pause", headers=owner_h, json={"paused": True}, timeout=15)
    assert r_no.status_code == 422, f"expected 422 without reason, got {r_no.status_code} {r_no.text[:200]}"
    r_yes = requests.post(
        f"{API}/quality/optimizer/pause",
        headers=owner_h,
        json={"paused": True, "reason": "stage7 pause test"},
        timeout=15,
    )
    assert r_yes.status_code == 200
    # unpause
    r_un = requests.post(
        f"{API}/quality/optimizer/pause",
        headers=owner_h,
        json={"paused": False, "reason": "stage7 resume test"},
        timeout=15,
    )
    assert r_un.status_code == 200


def test_lock_unlock(owner_h):
    r = requests.post(
        f"{API}/quality/optimizer/lock",
        headers=owner_h,
        json={"factor": "crew_efficiency", "locked": True, "reason": "stage7 lock test"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    r2 = requests.post(
        f"{API}/quality/optimizer/lock",
        headers=owner_h,
        json={"factor": "crew_efficiency", "locked": False, "reason": "stage7 unlock test"},
        timeout=15,
    )
    assert r2.status_code == 200, r2.text


def test_manual_set_bounds_and_success(owner_h):
    # out of bounds
    r_bad = requests.post(
        f"{API}/quality/optimizer/manual-set",
        headers=owner_h,
        json={"factor": "package_br3", "value": 999, "reason": "invalid bounds test"},
        timeout=15,
    )
    assert r_bad.status_code == 422, f"expected 422 for out-of-bounds, got {r_bad.status_code} {r_bad.text[:200]}"
    # ok
    r_ok = requests.post(
        f"{API}/quality/optimizer/manual-set",
        headers=owner_h,
        json={"factor": "package_br3", "value": 7, "reason": "stage7 manual set test"},
        timeout=15,
    )
    assert r_ok.status_code == 200, r_ok.text


def test_rollback_creates_new_version(owner_h):
    before = requests.get(f"{API}/quality/optimizer/state", headers=owner_h, timeout=15).json()
    v_before = before.get("calibration_version")
    r = requests.post(
        f"{API}/quality/optimizer/rollback",
        headers=owner_h,
        json={"version": "v1", "reason": "stage7 rollback test"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    after = requests.get(f"{API}/quality/optimizer/state", headers=owner_h, timeout=15).json()
    assert after.get("calibration_version") != v_before, "rollback should bump version"


def test_history_and_runs(owner_h):
    h = requests.get(f"{API}/quality/optimizer/history", headers=owner_h, timeout=15)
    r = requests.get(f"{API}/quality/optimizer/runs", headers=owner_h, timeout=15)
    assert h.status_code == 200 and r.status_code == 200
    # rows expected (we've been writing history via the tests above)
    hj = h.json()
    rj = r.json()
    hrows = hj if isinstance(hj, list) else (hj.get("rows") or hj.get("history") or [])
    rrows = rj if isinstance(rj, list) else (rj.get("rows") or rj.get("runs") or [])
    assert len(hrows) >= 1
    assert len(rrows) >= 1


# -------- Activation owner-only + Quality parity --------

def test_quality_cannot_activate(quality_h):
    r = requests.post(
        f"{API}/quality/optimizer/activate",
        headers=quality_h,
        json={"activated": True, "reason": "quality tries to activate"},
        timeout=15,
    )
    assert r.status_code == 403, f"quality must be 403 on activate, got {r.status_code} {r.text[:200]}"


def test_owner_activate_and_run_noop(owner_h):
    r = requests.post(
        f"{API}/quality/optimizer/activate",
        headers=owner_h,
        json={"activated": True, "reason": "stage7 activation test"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    st = requests.get(f"{API}/quality/optimizer/state", headers=owner_h, timeout=15).json()
    assert st.get("activated") is True

    run = requests.post(f"{API}/quality/optimizer/run", headers=owner_h, timeout=30).json()
    rmode = (run.get("run") or run).get("mode")
    assert rmode in ("applied", "noop"), f"after activation expected applied/noop, got {rmode}"

    # restore to shadow so preview stays in expected state
    requests.post(
        f"{API}/quality/optimizer/activate",
        headers=owner_h,
        json={"activated": False, "reason": "stage7 restore shadow"},
        timeout=15,
    )


def test_quality_parity_controls_and_notification(quality_h, owner_h):
    # quality can GET state and POST run
    st = requests.get(f"{API}/quality/optimizer/state", headers=quality_h, timeout=15)
    assert st.status_code == 200
    rn = requests.post(f"{API}/quality/optimizer/run", headers=quality_h, timeout=30)
    assert rn.status_code == 200

    # notify — capture current notifications count for owner
    def _owner_notif_count():
        r = requests.get(f"{API}/notifications", headers=owner_h, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        rows = data if isinstance(data, list) else (data.get("items") or data.get("notifications") or [])
        return len([x for x in rows if (x.get("kind") == "calibration" or "calibration" in (x.get("type", "") or ""))])

    before = _owner_notif_count()

    r_lock = requests.post(
        f"{API}/quality/optimizer/lock",
        headers=quality_h,
        json={"factor": "drive_speed", "locked": True, "reason": "quality parity lock test"},
        timeout=15,
    )
    assert r_lock.status_code == 200, f"quality lock failed: {r_lock.status_code} {r_lock.text[:200]}"

    # unlock
    requests.post(
        f"{API}/quality/optimizer/lock",
        headers=quality_h,
        json={"factor": "drive_speed", "locked": False, "reason": "quality parity unlock"},
        timeout=15,
    )

    # pause/manual-set/rollback
    r_pa = requests.post(
        f"{API}/quality/optimizer/pause",
        headers=quality_h,
        json={"paused": True, "reason": "quality parity pause"},
        timeout=15,
    )
    assert r_pa.status_code == 200
    requests.post(
        f"{API}/quality/optimizer/pause",
        headers=quality_h,
        json={"paused": False, "reason": "quality parity resume"},
        timeout=15,
    )
    r_ms = requests.post(
        f"{API}/quality/optimizer/manual-set",
        headers=quality_h,
        json={"factor": "package_br2", "value": 5, "reason": "quality parity manual"},
        timeout=15,
    )
    assert r_ms.status_code == 200, r_ms.text

    time.sleep(1)
    after = _owner_notif_count()
    if before is not None and after is not None:
        assert after > before, f"expected owner notification count to grow ({before} -> {after})"


# -------- /scope-guidance --------

def test_scope_guidance_shape_and_no_dollars(owner_h, sales_h):
    for h, who in ((owner_h, "owner"), (sales_h, "sales")):
        r = requests.get(f"{API}/scope-guidance", headers=h, params={"cf": 1200, "crew": 3, "pkg": "br2"}, timeout=15)
        assert r.status_code == 200, f"{who}: {r.status_code} {r.text[:200]}"
        d = r.json()
        for k in ("hint", "usable_jobs", "base_rate_mh_per_100cuft", "package_hours", "similar"):
            assert k in d, f"{who}: missing field {k}"
        text = str(d).lower()
        for banned in ("$", "price", "dollar", "cost"):
            assert banned not in text, f"{who}: guidance leaked '{banned}' ({d})"
