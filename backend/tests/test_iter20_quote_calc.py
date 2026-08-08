"""Iteration 20 tests: quote calculator fixes - pricing math, quote breakdown round-trip"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://haul-yeah-staging.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

from test_config import OWNER_EMAIL, OWNER_PASSWORD as OWNER_PW  # noqa: E402

LEAD_ID = "recQATESTLEAD1"


@pytest.fixture(scope="module")
def owner_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PW}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json().get("token")
    assert token
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


class TestQuoteBreakdownRoundTrip:
    def test_put_and_get_quote_breakdown(self, owner_session):
        payload = {
            "breakdown": {
                "finalQuote": 1800,
                "deposit": 450,
                "crew": 4,
                "hours": 6.5,
                "lines": [],
                "customerName": "QA",
                "customerPhone": "",
            }
        }
        r = owner_session.put(f"{API}/quotes/{LEAD_ID}", json=payload, timeout=15)
        assert r.status_code == 200, f"PUT failed: {r.status_code} {r.text}"
        body = r.json()
        assert body.get("ok") is True

        r2 = owner_session.get(f"{API}/quotes/{LEAD_ID}", timeout=15)
        assert r2.status_code == 200, f"GET failed: {r2.status_code} {r2.text}"
        b = r2.json().get("breakdown") or {}
        assert b.get("crew") == 4, f"crew should be 4, got {b.get('crew')}"
        assert b.get("hours") == 6.5, f"hours should be 6.5, got {b.get('hours')}"
        assert b.get("finalQuote") == 1800
        assert b.get("deposit") == 450


def teardown_module(module):
    """Clean up the test doc from mongo directly"""
    try:
        from pymongo import MongoClient
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "test_database")
        client = MongoClient(mongo_url)
        client[db_name].lead_quotes.delete_one({"_id": LEAD_ID})
        client.close()
        print(f"Cleaned up lead_quotes/{LEAD_ID}")
    except Exception as e:
        print(f"Cleanup failed: {e}")
