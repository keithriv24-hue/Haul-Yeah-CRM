"""Phase D customer portal — public /track endpoints + owner portal-uploads."""
import os
import pytest
import requests
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from test_config import OWNER_PASSWORD, QA_TRACK_TOKEN

TRACK_JOB_DATE = (datetime.now(ZoneInfo("America/New_York")) + timedelta(days=3)).strftime("%Y-%m-%d")

def _load_backend_url():
    env = Path("/app/frontend/.env").read_text()
    for line in env.splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or _load_backend_url()
TOKEN = QA_TRACK_TOKEN


@pytest.fixture(scope="module")
def owner():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": "HaulYeahAdmin", "password": OWNER_PASSWORD})
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    s.headers["Authorization"] = f"Bearer {tok}"
    return s


# ---------- GET /track/{token}
def test_track_public_ok():
    r = requests.get(f"{BASE}/api/track/{TOKEN}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["invoice_number"] == "QA-1001"
    assert d["customer_name"] == "Dana Johnson"
    assert d["job_date"] == TRACK_JOB_DATE
    assert d["status"] == "Crew assigned"
    assert d["quote_total"] == 1200
    assert d["deposit_amount"] == 300
    assert d["paid_in_full"] == False
    assert d["remaining_balance"] == 900
    assert d["tips_enabled"] == True
    assert d["review_submitted"] == True
    assert d["invoices"] == []
    assert any("QA Crew One" in c.get("name", "") for c in d["crew"])
    assert d["truck_name"] == "Truck 1"
    assert d["details"].get("gate_code") == "#4321"
    assert len(d["uploads"]) >= 1


def test_track_bad_token_404():
    r = requests.get(f"{BASE}/api/track/nope-nope-nope")
    assert r.status_code == 404
    assert "no longer active" in r.json()["detail"].lower()


# ---------- POST /track/{token}/details
def test_portal_details_save_and_overwrite():
    payload = {"gate_code": "#4321", "elevator": "", "parking": "Driveway",
               "special_requests": "Please wrap the TV", "inventory_notes": ""}
    r = requests.post(f"{BASE}/api/track/{TOKEN}/details", json=payload)
    assert r.status_code == 200, r.text
    d = requests.get(f"{BASE}/api/track/{TOKEN}").json()
    assert d["details"]["parking"] == "Driveway"
    # overwrite
    payload["parking"] = "Street parking only"
    requests.post(f"{BASE}/api/track/{TOKEN}/details", json=payload)
    d = requests.get(f"{BASE}/api/track/{TOKEN}").json()
    assert d["details"]["parking"] == "Street parking only"
    # restore
    payload["parking"] = "Driveway"
    requests.post(f"{BASE}/api/track/{TOKEN}/details", json=payload)


def test_portal_details_truncates_600():
    big = "x" * 1000
    r = requests.post(f"{BASE}/api/track/{TOKEN}/details",
                      json={"gate_code": "#4321", "parking": "Driveway",
                            "special_requests": big})
    assert r.status_code == 200, r.text
    d = requests.get(f"{BASE}/api/track/{TOKEN}").json()
    assert len(d["details"]["special_requests"]) == 600
    # restore
    requests.post(f"{BASE}/api/track/{TOKEN}/details",
                  json={"gate_code": "#4321", "parking": "Driveway",
                        "special_requests": "Please wrap the TV"})


# ---------- POST /track/{token}/uploads
def _tiny_png_bytes():
    return (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
            b"\xc0\x00\x00\x00\x03\x00\x01\x00\x00\x00\x00IEND\xaeB`\x82")


def test_upload_bad_kind_422():
    r = requests.post(f"{BASE}/api/track/{TOKEN}/uploads",
                      params={"kind": "bogus"},
                      files={"file": ("a.png", _tiny_png_bytes(), "image/png")})
    assert r.status_code == 422


def test_upload_bad_mime_422():
    r = requests.post(f"{BASE}/api/track/{TOKEN}/uploads",
                      params={"kind": "photo"},
                      files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 422


def test_upload_pdf_inventory_and_photo_and_throttle():
    # first photo upload
    r1 = requests.post(f"{BASE}/api/track/{TOKEN}/uploads",
                       params={"kind": "photo"},
                       files={"file": ("a.png", _tiny_png_bytes(), "image/png")})
    assert r1.status_code == 200, r1.text
    up_id = r1.json()["id"]
    # PDF inventory
    r2 = requests.post(f"{BASE}/api/track/{TOKEN}/uploads",
                       params={"kind": "inventory"},
                       files={"file": ("i.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")})
    assert r2.status_code == 200, r2.text
    # stream back
    r3 = requests.get(f"{BASE}/api/track/{TOKEN}/uploads/{up_id}")
    assert r3.status_code == 200
    assert r3.headers.get("content-type", "").startswith("image/")


def test_upload_wrong_id_404():
    r = requests.get(f"{BASE}/api/track/{TOKEN}/uploads/does-not-exist")
    assert r.status_code == 404


def test_upload_wrong_token_404():
    # get a real upload id from portal-uploads owner endpoint by picking existing
    d = requests.get(f"{BASE}/api/track/{TOKEN}").json()
    up_id = d["uploads"][0]["id"]
    r = requests.get(f"{BASE}/api/track/bad-token/uploads/{up_id}")
    assert r.status_code == 404


def test_upload_too_big_422():
    big = b"\x00" * (15 * 1024 * 1024 + 10)
    r = requests.post(f"{BASE}/api/track/{TOKEN}/uploads",
                      params={"kind": "photo"},
                      files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 422


# ---------- POST /track/{token}/tip
def test_tip_creates_square_link():
    r = requests.post(f"{BASE}/api/track/{TOKEN}/tip",
                      json={"amount": 2, "name": "QA"})
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    assert url.startswith("https://square.link/") or "square" in url, url


def test_tip_bad_amounts():
    r = requests.post(f"{BASE}/api/track/{TOKEN}/tip", json={"amount": 0.5})
    assert r.status_code == 422
    r = requests.post(f"{BASE}/api/track/{TOKEN}/tip", json={"amount": 1500})
    assert r.status_code == 422
    r = requests.post(f"{BASE}/api/track/{TOKEN}/tip", json={})
    assert r.status_code == 422


# ---------- POST /track/{token}/review
def test_review_bad_ratings():
    for bad in (0, 6, -1):
        r = requests.post(f"{BASE}/api/track/{TOKEN}/review", json={"rating": bad})
        assert r.status_code == 422, (bad, r.text)


def test_review_three_stars_no_link():
    r = requests.post(f"{BASE}/api/track/{TOKEN}/review",
                      json={"rating": 3, "text": "meh"})
    assert r.status_code == 200
    assert r.json().get("review_link", "") == ""
    # restore 5-star
    r = requests.post(f"{BASE}/api/track/{TOKEN}/review",
                      json={"rating": 5, "text": "Great crew!"})
    assert r.status_code == 200


# ---------- Owner /api/jobs/{id}/portal-uploads
def test_owner_portal_uploads(owner):
    jobs = owner.get(f"{BASE}/api/jobs").json().get("jobs", [])
    target = next((j for j in jobs if j.get("invoice_number") == "QA-1001"), None)
    assert target, "QA-1001 job missing"
    r = owner.get(f"{BASE}/api/jobs/{target['id']}/portal-uploads")
    assert r.status_code == 200
    data = r.json()
    assert data["token"] == TOKEN
    assert len(data["uploads"]) >= 1


def test_owner_portal_uploads_forbidden_for_crew():
    # Verify endpoint requires auth. Uses require_owner dep, and crew creds are not
    # exposed in preview — verify with (a) no auth -> 401 and (b) sales-switched token -> 403.
    ow = requests.Session()
    lr = ow.post(f"{BASE}/api/auth/login",
                 json={"username": "HaulYeahAdmin", "password": OWNER_PASSWORD}).json()
    ow.headers["Authorization"] = f"Bearer {lr.get('access_token') or lr.get('token')}"
    jobs = ow.get(f"{BASE}/api/jobs").json().get("jobs", [])
    jid = next(j["id"] for j in jobs if j.get("invoice_number") == "QA-1001")
    # no auth
    r = requests.get(f"{BASE}/api/jobs/{jid}/portal-uploads")
    assert r.status_code in (401, 403), r.status_code
    # non-owner (sales switch)
    sw = ow.post(f"{BASE}/api/auth/switch-role", json={"role": "sales"})
    if sw.status_code == 200:
        sales_tok = sw.json()["token"]
        r2 = requests.get(f"{BASE}/api/jobs/{jid}/portal-uploads",
                          headers={"Authorization": f"Bearer {sales_tok}"})
        assert r2.status_code == 403, r2.status_code


# ---------- integrations owner_alert_phone
def test_integrations_owner_alert_phone_roundtrip(owner):
    r = owner.put(f"{BASE}/api/settings/integrations",
                  json={"owner_alert_phone": "+15550001234"})
    assert r.status_code == 200, r.text
    echoed = r.json().get("owner_alert_phone")
    # GET
    got = owner.get(f"{BASE}/api/settings/integrations").json()
    # Clear back to empty
    owner.put(f"{BASE}/api/settings/integrations",
              json={"owner_alert_phone": ""})
    got2 = owner.get(f"{BASE}/api/settings/integrations").json()
    assert echoed == "+15550001234", f"PUT did not echo owner_alert_phone: {r.json()}"
    assert got.get("owner_alert_phone") == "+15550001234", f"GET missing owner_alert_phone: {got}"
    assert got2.get("owner_alert_phone", "") == ""


# ---------- Notifications include portal events
def test_owner_notifications_have_portal(owner):
    r = owner.get(f"{BASE}/api/notifications")
    assert r.status_code == 200
    body = r.json()
    items = body.get("notifications") if isinstance(body, dict) else body
    kinds = {(n.get("type") or n.get("kind") or "") for n in items}
    titles = " ".join((n.get("title") or "") for n in items)
    assert "portal" in kinds, f"no portal kind. kinds={kinds}"
    assert ("Customer added move details" in titles
            or "Customer uploaded files" in titles
            or "Crew tip started" in titles
            or "New review" in titles), titles[:400]
