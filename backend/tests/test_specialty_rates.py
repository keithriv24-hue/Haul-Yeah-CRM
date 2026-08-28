"""Specialty Item Engine — T9 (rate keys + sales-tier folding) regression.

Four-place rule check on the backend side:
- new keys live in DEFAULT_RATES and survive /settings/rates
- the four surchargeCustomB* dollar keys fold x1.1 for the sales tier
- the ratio keys (multipliers, swap factor, cap pct) are NEVER folded
"""
import os

import requests
from test_config import GHOST_PASSWORD, OWNER_EMAIL, OWNER_PASSWORD

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _token(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_owner_rates_contain_custom_specialty_keys():
    tok = _token(OWNER_EMAIL, OWNER_PASSWORD)
    r = requests.get(f"{BASE_URL}/api/settings/rates", headers=_h(tok), timeout=15)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["surchargeCustomB1"] == 75
    assert v["surchargeCustomB2"] == 150
    assert v["surchargeCustomB3"] == 250
    assert v["surchargeCustomB4"] == 400
    assert v["customBuiltInMultiplier"] == 1.25
    assert v["customDisconnectMultiplier"] == 1.15
    assert v["customSwapFactor"] == 0.6
    assert v["specialtyHandlingCapPct"] == 30
    # nothing removed — the 45+ key contract still holds, and zones stay gone
    assert len([k for k in v if k != "_updatedAt"]) >= 48
    assert "zone1Fee" not in v
    assert v["stairFlightFee"] == 85


def test_t9_sales_tier_folds_band_dollars_not_ratios():
    tok = _token("testsalesadmin", GHOST_PASSWORD)
    r = requests.get(f"{BASE_URL}/api/scopes/pricing-values", headers=_h(tok), timeout=15)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["cushionPercent"] == 0.0
    # dollars fold x1.1
    assert v["surchargeCustomB1"] == 82.5
    assert v["surchargeCustomB2"] == 165.0
    assert v["surchargeCustomB3"] == 275.0
    assert v["surchargeCustomB4"] == 440.0
    # ratios NEVER fold — folding a cushion into a ratio is a compounding bug
    assert v["customBuiltInMultiplier"] == 1.25
    assert v["customDisconnectMultiplier"] == 1.15
    assert v["customSwapFactor"] == 0.6
    assert v["specialtyHandlingCapPct"] == 30


def test_owner_pricing_values_unfolded():
    tok = _token(OWNER_EMAIL, OWNER_PASSWORD)
    r = requests.get(f"{BASE_URL}/api/scopes/pricing-values", headers=_h(tok), timeout=15)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["surchargeCustomB4"] == 400
    assert v["cushionPercent"] == 10
