"""Spot regression for PRICING SPEC v2.0 — rates endpoint, pricing-values folding, scope tier gates."""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://haul-yeah-staging.preview.emergentagent.com").rstrip("/")


def _login(username, password, switch_role=None):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"login failed for {username}: {r.status_code} {r.text[:200]}"
    token = r.json().get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    if switch_role:
        r2 = s.post(f"{BASE_URL}/api/auth/switch-role", json={"role": switch_role})
        assert r2.status_code == 200, f"switch to {switch_role} failed: {r2.status_code} {r2.text[:200]}"
        s.headers.update({"Authorization": f"Bearer {r2.json()['token']}"})
    return s


def test_rates_owner_200_and_45_plus_keys():
    s = _login("HaulYeahAdmin", "HaulYeah2026!")
    r = s.get(f"{BASE_URL}/api/settings/rates")
    assert r.status_code == 200, r.text[:200]
    values = r.json()
    keys = [k for k in values.keys() if not k.startswith("_")]
    assert len(keys) >= 40, f"expected >=40 keys, got {len(keys)}: {keys}"
    for k in ["manHourRate", "cushionPercent", "depositPercent", "roundingIncrement",
              "tripFeeTruck", "tripFeeLabor", "floorTruck", "floorLabor",
              "stairFlightFee", "longCarryFee", "disassemblyFee",
              "minHoursTruck", "minHoursLabor"]:
        assert k in values, f"missing key {k}"
    assert values["manHourRate"] == 65
    assert values["cushionPercent"] == 10
    assert values["stairFlightFee"] == 80


def test_rates_sales_403():
    s = _login("TestSalesAdmin", "HaulYeah2026!", switch_role="sales")
    r = s.get(f"{BASE_URL}/api/settings/rates")
    assert r.status_code == 403, f"expected 403 got {r.status_code}"


def test_rates_unauth_401():
    r = requests.get(f"{BASE_URL}/api/settings/rates")
    assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


def test_pricing_values_sales_folding():
    s = _login("TestSalesAdmin", "HaulYeah2026!", switch_role="sales")
    r = s.get(f"{BASE_URL}/api/scopes/pricing-values")
    assert r.status_code == 200, r.text[:200]
    values = r.json()
    assert values["cushionPercent"] == 0, f"expected cushion 0, got {values.get('cushionPercent')}"
    assert values["manHourRate"] == 71.5, f"expected 65*1.1=71.5, got {values.get('manHourRate')}"


def test_pricing_values_owner():
    s = _login("HaulYeahAdmin", "HaulYeah2026!")
    r = s.get(f"{BASE_URL}/api/scopes/pricing-values")
    assert r.status_code == 200
    values = r.json()
    assert values["cushionPercent"] == 10
    assert values["manHourRate"] == 65


def test_save_scope_sales_final_mode_forbidden():
    s = _login("TestSalesAdmin", "HaulYeah2026!", switch_role="sales")
    payload = {
        "lead_id": "TEST_sales_final_block",
        "label": "TEST sales final",
        "inputs": {"bedrooms": 2, "miles": 20},
        "pricing": {},
        "result": {"mode": "final", "finalTotal": 1500, "bandLo": 1400, "bandHi": 1600},
    }
    r = s.post(f"{BASE_URL}/api/scopes", json=payload)
    assert r.status_code == 403, f"expected 403 for sales final, got {r.status_code} {r.text[:200]}"
