import asyncio
import csv
import hmac
import io
import logging
import math
import os
import re
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

import bcrypt

import httpx
import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Body, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("haulyeah")

AIRTABLE_API_URL = "https://api.airtable.com/v0"

TABLES = {
    "leads": "tblOjXRQNk7R2pEHR",
    "contacts": "tbli70SmKckelxe6W",
    "projects": "tblxTwbD5VnChBuxu",
    "tasks": "tblHf8FhK08TIIEKm",
    "blog": "tblpuaGzlXg75HU6Y",
    "invoices": "tbl9S7qG5vAwzNm5q",
    "subscriptions": "tbl4B0mqVLQPTAK62",
}


def get_api_key() -> str:
    return os.environ.get("AIRTABLE_API_KEY", "").strip()


def get_base_id() -> str:
    return os.environ.get("AIRTABLE_BASE_ID", "").strip()


JWT_ALGORITHM = "HS256"
_login_attempts: Dict[str, Dict[str, float]] = {}

ROLES = ("owner", "sales", "employee")
ALL_ROLES = ("owner", "sales", "employee", "crew")
ROLE_ENV = {"owner": "APP_PASSWORD", "sales": "SALES_PASSWORD", "employee": "EMPLOYEE_PASSWORD"}
ROLE_TABLES = {
    "owner": set(TABLES),
    "sales": {"leads"},
    "employee": {"projects", "tasks"},
}
PROJECT_QUOTE_FIELD = "fldkRQlJvhnUhWoR3"
PROJECT_DEPOSIT_FIELD = "fldpqyinP1L9vZ2UP"
PROJECT_REVENUE_FIELD = "fldvOyVAK9ywo2DNA"
PROJECT_CREW_FIELD = "fldkeeMYBMooCqi7p"
PROJECT_HOURS_FIELD = "fldhVlH3Cu66W5EYo"
PROJECT_NAME_FIELD = "fldcuvCepinGbQbK8"
PROJECT_STATUS_FIELD = "fldMZV9A6p0SJyuM5"
PROJECT_DATE_FIELD = "fldVBgzlG9gUCq5OB"
PROJECT_FROM_FIELD = "fldDf4w5prPb89Q4y"
PROJECT_TO_FIELD = "fldnFH0mMdyQ84hTV"
PROJECT_TRUCK_FIELD = "fldhQpzJrqDE6tPAg"
BLOCKED_FIELDS = {
    ("employee", "projects"): {PROJECT_QUOTE_FIELD, PROJECT_DEPOSIT_FIELD, PROJECT_REVENUE_FIELD},
    ("sales", "projects"): {PROJECT_REVENUE_FIELD, PROJECT_DEPOSIT_FIELD},
}
DRIVER_RATE = 28
HELPER_RATE = 24


def decode_token(request: Request) -> Dict[str, Any]:
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else None
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session. Log in again.")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    return payload


def make_token(role: str, owner_switch: bool = False) -> str:
    claims = {"sub": role, "role": role, "type": "access", "exp": datetime.now(timezone.utc) + timedelta(days=30)}
    if owner_switch:
        claims["owner_switch"] = True
    return jwt.encode(claims, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


def make_user_token(user: Dict[str, Any]) -> str:
    claims = {
        "sub": user["email"],
        "uid": user["_id"],
        "role": user["role"],
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
    }
    return jwt.encode(claims, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def require_auth(request: Request) -> str:
    payload = decode_token(request)
    role = payload.get("role") or payload.get("sub") or "owner"
    if role not in ALL_ROLES:
        raise HTTPException(status_code=401, detail="Invalid session. Log in again.")
    return role


async def principal_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    uid = payload.get("uid")
    if uid:
        user = await mongo_db.users.find_one({"_id": uid})
        if not user or not user.get("active", True):
            raise HTTPException(status_code=401, detail="This account is turned off. Talk to the owner.")
        return {"role": user["role"], "user_id": uid, "name": user.get("name", ""), "email": user.get("email", ""),
                "is_user": True, "must_change_password": bool(user.get("must_change_password")),
                "gps_consent_at": user.get("gps_consent_at")}
    role = payload.get("role") or payload.get("sub") or "owner"
    if role not in ALL_ROLES:
        raise HTTPException(status_code=401, detail="Invalid session. Log in again.")
    return {"role": role, "user_id": None, "name": role.capitalize(), "email": None, "is_user": False,
            "must_change_password": False, "gps_consent_at": None}


async def current_principal(request: Request) -> Dict[str, Any]:
    return await principal_from_payload(decode_token(request))


async def principal_from_token_string(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session. Log in again.")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    return await principal_from_payload(payload)


async def require_owner(request: Request) -> Dict[str, Any]:
    p = await current_principal(request)
    if p["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can do this.")
    return p


async def require_crew(request: Request) -> Dict[str, Any]:
    p = await current_principal(request)
    if p["role"] != "crew" or not p["user_id"]:
        raise HTTPException(status_code=403, detail="Only crew accounts can do this.")
    return p


async def check_table_access(role: str, table_key: str):
    allowed = set(ROLE_TABLES.get(role, set()))
    if role == "sales":
        doc = await mongo_db.settings.find_one({"_id": "sales_access"}) or {}
        if doc.get("booking_calendar"):
            allowed.add("projects")
    if table_key not in allowed:
        raise HTTPException(status_code=403, detail="Your role can't open this.")


def filter_record(record: Dict[str, Any], role: str, table_key: str) -> Dict[str, Any]:
    blocked = BLOCKED_FIELDS.get((role, table_key))
    if blocked:
        record = {**record, "fields": {k: v for k, v in record.get("fields", {}).items() if k not in blocked}}
    if role == "owner" and table_key == "projects":
        fields = record.get("fields", {})
        try:
            crew = int(float(fields.get(PROJECT_CREW_FIELD) or 0))
            hours = float(fields.get(PROJECT_HOURS_FIELD) or 0)
        except (TypeError, ValueError):
            crew, hours = 0, 0
        cost = (DRIVER_RATE + max(0, crew - 1) * HELPER_RATE) * hours if crew and hours else 0
        revenue = float(fields.get(PROJECT_REVENUE_FIELD) or fields.get(PROJECT_QUOTE_FIELD) or 0)
        record = {**record, "internal": {"crew_cost": round(cost), "margin": round(revenue - cost)}}
    return record


def clean_write_fields(fields: Dict[str, Any], role: str, table_key: str) -> Dict[str, Any]:
    blocked = BLOCKED_FIELDS.get((role, table_key))
    if blocked:
        return {k: v for k, v in fields.items() if k not in blocked}
    return fields


class RateLimiter:
    """Keeps outgoing Airtable calls under 5 requests per second."""

    def __init__(self, max_per_sec: int = 5):
        self.max = max_per_sec
        self.calls = deque()
        self.lock = asyncio.Lock()

    async def wait(self):
        while True:
            async with self.lock:
                now = time.monotonic()
                while self.calls and now - self.calls[0] > 1.0:
                    self.calls.popleft()
                if len(self.calls) < self.max:
                    self.calls.append(now)
                    return
                sleep_for = 1.0 - (now - self.calls[0]) + 0.02
            await asyncio.sleep(max(sleep_for, 0.02))


limiter = RateLimiter()


def resolve_table(table_key: str) -> str:
    if table_key not in TABLES:
        raise HTTPException(status_code=404, detail={"error": "unknown_table", "message": f"No table named '{table_key}'."})
    return TABLES[table_key]


async def airtable_request(method: str, table_id: str, path: str = "", params: Optional[Dict[str, Any]] = None,
                           json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    key = get_api_key()
    if not key:
        raise HTTPException(status_code=503, detail={
            "error": "missing_key",
            "message": "Airtable key is not set. Add AIRTABLE_API_KEY in the secrets panel, then press Refresh."})
    base_id = get_base_id()
    if not base_id:
        raise HTTPException(status_code=503, detail={
            "error": "missing_base", "message": "AIRTABLE_BASE_ID is not set on the server."})
    url = f"{AIRTABLE_API_URL}/{base_id}/{table_id}{path}"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    await limiter.wait()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(method, url, headers=headers, params=params, json=json_body)
    except httpx.HTTPError as exc:
        logger.error("Airtable network error: %s", exc)
        raise HTTPException(status_code=502, detail={
            "error": "network", "message": "Could not reach Airtable. Check your internet and try again."})
    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(status_code=502, detail={"error": "bad_response", "message": "Airtable sent an unexpected reply."})
    if 200 <= resp.status_code < 300:
        return data
    err = data.get("error", {})
    if isinstance(err, dict):
        err_type = err.get("type", "airtable_error")
        err_msg = err.get("message", "Airtable returned an error.")
    else:
        err_type = str(err)
        err_msg = data.get("message", "Airtable returned an error.")
    if resp.status_code == 429:
        err_msg = "Airtable is busy right now. Wait 30 seconds, then press Refresh."
    if resp.status_code == 401:
        err_msg = "The Airtable key was rejected. Check AIRTABLE_API_KEY in the secrets panel."
    if resp.status_code == 403:
        err_msg = "The Airtable key does not have access to this base. Check the token's scopes and base access."
    logger.error("Airtable %s %s -> %s %s", method, url, resp.status_code, err_msg)
    raise HTTPException(status_code=resp.status_code, detail={"error": err_type, "message": err_msg})


class RecordPayload(BaseModel):
    fields: Dict[str, Any]


mongo_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
mongo_db = mongo_client[os.environ["DB_NAME"]]

DEFAULT_RATES = {
    "manHour": 65,
    "travelTruck": 125,
    "travelLabor": 75,
    "stairFlight": 85,
    "pianoUpright": 500,
    "pianoGrand": 800,
}


class RatesPayload(BaseModel):
    manHour: float
    travelTruck: float
    travelLabor: float
    stairFlight: float
    pianoUpright: float
    pianoGrand: float


app = FastAPI(title="Haul Yeah Moving CRM Proxy")
api_router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])
auth_router = APIRouter(prefix="/api/auth")


class LoginPayload(BaseModel):
    password: str
    email: Optional[str] = None


def _user_public(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": user["_id"], "name": user.get("name", ""), "email": user.get("email", ""), "role": user.get("role"),
        "active": user.get("active", True), "must_change_password": bool(user.get("must_change_password")),
        "gps_consent": bool(user.get("gps_consent_at")), "created_at": user.get("created_at"),
    }


@auth_router.post("/login")
async def login(payload: LoginPayload, request: Request):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    lock_key = f"{ip}:{(payload.email or '').strip().lower()}"
    rec = _login_attempts.get(lock_key, {})
    if rec.get("locked_until", 0) > now:
        raise HTTPException(status_code=429, detail="Too many tries. Wait 15 minutes and try again.")

    def fail(msg: str):
        r = _login_attempts.setdefault(lock_key, {"count": 0})
        r["count"] = r.get("count", 0) + 1
        if r["count"] >= 5:
            r["locked_until"] = now + 900
            r["count"] = 0
        raise HTTPException(status_code=401, detail=msg)

    email = (payload.email or "").strip().lower()
    if email:
        user = await mongo_db.users.find_one({"email": email})
        if not user or not verify_password(payload.password, user.get("password_hash", "")):
            fail("Wrong email or password. Try again.")
        if not user.get("active", True):
            raise HTTPException(status_code=403, detail="This account is turned off. Talk to the owner.")
        _login_attempts.pop(lock_key, None)
        return {
            "token": make_user_token(user), "role": user["role"], "can_switch": user["role"] == "owner",
            "user": _user_public(user),
        }

    if not any(os.environ.get(v) for v in ROLE_ENV.values()):
        raise HTTPException(status_code=503, detail="No login passwords are set on the server.")
    role = None
    for r in ROLES:
        expected = os.environ.get(ROLE_ENV[r], "")
        if expected and hmac.compare_digest(payload.password, expected):
            role = r
            break
    if role is None:
        fail("Wrong password. Try again.")
    _login_attempts.pop(lock_key, None)
    return {"token": make_token(role), "role": role, "can_switch": role == "owner", "user": None}


class SwitchPayload(BaseModel):
    role: str


@auth_router.post("/switch-role")
async def switch_role(payload: SwitchPayload, request: Request):
    token_payload = decode_token(request)
    current = token_payload.get("role") or "owner"
    if current != "owner" and not token_payload.get("owner_switch"):
        raise HTTPException(status_code=403, detail="Only the owner can switch accounts.")
    if payload.role not in ROLES:
        raise HTTPException(status_code=422, detail="Unknown role.")
    return {"token": make_token(payload.role, owner_switch=True), "role": payload.role, "can_switch": True}


@auth_router.get("/me")
async def me(request: Request):
    p = await current_principal(request)
    can_switch = p["role"] == "owner" or bool(decode_token(request).get("owner_switch"))
    user = None
    if p["is_user"]:
        doc = await mongo_db.users.find_one({"_id": p["user_id"]})
        user = _user_public(doc) if doc else None
    return {"ok": True, "role": p["role"], "can_switch": can_switch, "user": user}


class ChangePasswordPayload(BaseModel):
    current_password: str
    new_password: str


@auth_router.post("/change-password")
async def change_password(payload: ChangePasswordPayload, request: Request):
    p = await current_principal(request)
    if not p["is_user"]:
        raise HTTPException(status_code=403, detail="Shared-password logins can't change passwords here.")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=422, detail="The new password needs at least 8 characters.")
    user = await mongo_db.users.find_one({"_id": p["user_id"]})
    if not user or not verify_password(payload.current_password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Your current password is wrong.")
    await mongo_db.users.update_one(
        {"_id": p["user_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password), "must_change_password": False}})
    await audit(p, "changed their password", p["email"] or "")
    return {"ok": True}


@auth_router.post("/consent")
async def gps_consent(request: Request):
    p = await current_principal(request)
    if not p["is_user"]:
        raise HTTPException(status_code=403, detail="Only user accounts can consent.")
    await mongo_db.users.update_one(
        {"_id": p["user_id"]}, {"$set": {"gps_consent_at": datetime.now(timezone.utc).isoformat()}})
    return {"ok": True}


@api_router.get("/")
async def root():
    return {"message": "Haul Yeah Moving CRM API"}


@api_router.get("/health")
async def health():
    return {"airtable_configured": bool(get_api_key()), "base_id_configured": bool(get_base_id())}


@api_router.get("/settings/rates")
async def get_rates(role: str = Depends(require_auth)):
    if role not in ("owner", "sales"):
        raise HTTPException(status_code=403, detail="Your role can't open this.")
    doc = await mongo_db.settings.find_one({"_id": "calculator_rates"}) or {}
    return {**DEFAULT_RATES, **{k: v for k, v in doc.items() if k in DEFAULT_RATES}}


@api_router.put("/settings/rates")
async def save_rates(payload: RatesPayload, role: str = Depends(require_auth)):
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can change rates.")
    rates = payload.model_dump()
    if any(v < 0 for v in rates.values()):
        raise HTTPException(status_code=422, detail="Rates can't be negative.")
    await mongo_db.settings.update_one({"_id": "calculator_rates"}, {"$set": rates}, upsert=True)
    return rates


class BusinessPayload(BaseModel):
    reviewLink: str = ""


@api_router.get("/settings/business")
async def get_business(role: str = Depends(require_auth)):
    if role != "owner":
        raise HTTPException(status_code=403, detail="Your role can't open this.")
    doc = await mongo_db.settings.find_one({"_id": "business"}) or {}
    return {"reviewLink": doc.get("reviewLink", "")}


@api_router.put("/settings/business")
async def save_business(payload: BusinessPayload, role: str = Depends(require_auth)):
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can change settings.")
    link = payload.reviewLink.strip()
    await mongo_db.settings.update_one({"_id": "business"}, {"$set": {"reviewLink": link}}, upsert=True)
    return {"reviewLink": link}


SQUARE_VERSION = "2024-08-21"


def square_configured() -> bool:
    return bool(os.environ.get("SQUARE_ACCESS_TOKEN", "").strip() and os.environ.get("SQUARE_LOCATION_ID", "").strip())


def square_base_url() -> str:
    env = os.environ.get("SQUARE_ENVIRONMENT", "sandbox").strip().lower()
    return "https://connect.squareup.com" if env == "production" else "https://connect.squareupsandbox.com"


async def square_request(method: str, path: str, json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not square_configured():
        raise HTTPException(status_code=503, detail={
            "error": "square_missing",
            "message": "Square is not connected. Add SQUARE_ACCESS_TOKEN and SQUARE_LOCATION_ID in the secrets panel."})
    headers = {
        "Authorization": f"Bearer {os.environ['SQUARE_ACCESS_TOKEN'].strip()}",
        "Content-Type": "application/json",
        "Square-Version": SQUARE_VERSION,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(method, f"{square_base_url()}{path}", headers=headers, json=json_body)
    except httpx.HTTPError as exc:
        logger.error("Square network error: %s", exc)
        raise HTTPException(status_code=502, detail={"error": "network", "message": "Could not reach Square. Try again."})
    try:
        data = resp.json() if resp.content else {}
    except ValueError:
        raise HTTPException(status_code=502, detail={"error": "bad_response", "message": "Square sent an unexpected reply."})
    if 200 <= resp.status_code < 300:
        return data
    errs = data.get("errors", [])
    msg = errs[0].get("detail") or errs[0].get("code", "Square returned an error.") if errs and isinstance(errs[0], dict) else "Square returned an error."
    if resp.status_code == 401:
        msg = "The Square token was rejected. Check SQUARE_ACCESS_TOKEN in the secrets panel."
    logger.error("Square %s %s -> %s %s", method, path, resp.status_code, msg)
    raise HTTPException(status_code=resp.status_code, detail={"error": "square_error", "message": msg})


def normalize_phone(phone: Optional[str]) -> Optional[str]:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return None


class SquareInvoicePayload(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    amount: float
    description: str = "Moving services"
    lead_id: Optional[str] = None


@api_router.get("/square/status")
async def square_status(role: str = Depends(require_auth)):
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can see this.")
    return {"configured": square_configured(), "environment": os.environ.get("SQUARE_ENVIRONMENT", "sandbox").strip().lower()}


@api_router.post("/square/invoice")
async def send_square_invoice(payload: SquareInvoicePayload, role: str = Depends(require_auth)):
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can send invoices.")
    if payload.amount <= 0:
        raise HTTPException(status_code=422, detail="The invoice amount must be more than $0.")
    if "@" not in payload.email:
        raise HTTPException(status_code=422, detail="This lead needs a valid email before you can send an invoice.")
    location_id = os.environ.get("SQUARE_LOCATION_ID", "").strip()

    name_parts = payload.name.strip().split(None, 1)
    cust_body: Dict[str, Any] = {
        "idempotency_key": str(uuid4()),
        "given_name": name_parts[0] if name_parts else "Customer",
        "email_address": payload.email.strip(),
    }
    if len(name_parts) > 1:
        cust_body["family_name"] = name_parts[1]
    phone = normalize_phone(payload.phone)
    if phone:
        cust_body["phone_number"] = phone
    cust = await square_request("POST", "/v2/customers", cust_body)
    customer_id = cust["customer"]["id"]

    order_body = {
        "idempotency_key": str(uuid4()),
        "order": {
            "location_id": location_id,
            "customer_id": customer_id,
            "line_items": [{
                "name": payload.description.strip()[:255] or "Moving services",
                "quantity": "1",
                "base_price_money": {"amount": int(round(payload.amount * 100)), "currency": "USD"},
            }],
        },
    }
    order = await square_request("POST", "/v2/orders", order_body)
    order_id = order["order"]["id"]

    due_date = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
    inv_body = {
        "idempotency_key": str(uuid4()),
        "invoice": {
            "location_id": location_id,
            "order_id": order_id,
            "primary_recipient": {"customer_id": customer_id},
            "payment_requests": [{"request_type": "BALANCE", "due_date": due_date}],
            "delivery_method": "EMAIL",
            "accepted_payment_methods": {"card": True},
            "title": "Haul Yeah Moving",
        },
    }
    inv = await square_request("POST", "/v2/invoices", inv_body)
    invoice = inv["invoice"]

    pub = await square_request("POST", f"/v2/invoices/{invoice['id']}/publish",
                               {"version": invoice["version"], "idempotency_key": str(uuid4())})
    published = pub["invoice"]
    await mongo_db.square_invoices.insert_one({
        "lead_id": payload.lead_id,
        "invoice_id": published["id"],
        "invoice_number": published.get("invoice_number"),
        "amount": payload.amount,
        "status": published.get("status"),
        "public_url": published.get("public_url"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "checked_at": time.time(),
    })
    return {
        "invoice_id": published["id"],
        "invoice_number": published.get("invoice_number"),
        "status": published.get("status"),
        "public_url": published.get("public_url"),
        "amount": payload.amount,
    }


SQUARE_TERMINAL_STATUSES = {"PAID", "REFUNDED", "CANCELED", "FAILED"}
LEAD_DEPOSIT_PAID_FIELD = "fld7BsZG5A6S1oh7Z"


async def mark_lead_deposit_paid(lead_id: str) -> bool:
    try:
        body = {"records": [{"id": lead_id, "fields": {LEAD_DEPOSIT_PAID_FIELD: True}}], "typecast": True}
        await airtable_request("PATCH", TABLES["leads"], json_body=body)
        return True
    except HTTPException:
        return False


@api_router.get("/square/invoices")
async def list_square_invoices(role: str = Depends(require_auth)):
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can see invoices.")
    docs = await mongo_db.square_invoices.find({}, {"_id": 0}).to_list(500)
    now = time.time()
    if square_configured():
        for d in docs:
            if d.get("status") in SQUARE_TERMINAL_STATUSES or now - d.get("checked_at", 0) < 60:
                continue
            try:
                data = await square_request("GET", f"/v2/invoices/{d['invoice_id']}")
            except HTTPException as exc:
                if exc.status_code == 404:
                    await mongo_db.square_invoices.update_one(
                        {"invoice_id": d["invoice_id"]}, {"$set": {"checked_at": now}})
                continue
            new_status = data.get("invoice", {}).get("status", d.get("status"))
            d["status"] = new_status
            updates: Dict[str, Any] = {"status": new_status, "checked_at": now}
            if new_status == "PAID" and d.get("lead_id") and not d.get("deposit_synced"):
                if await mark_lead_deposit_paid(d["lead_id"]):
                    updates["deposit_synced"] = True
                    d["deposit_synced"] = True
            await mongo_db.square_invoices.update_one({"invoice_id": d["invoice_id"]}, {"$set": updates})
    docs.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    return {"invoices": docs}


@api_router.get("/airtable/verify")
async def verify_connection(role: str = Depends(require_auth)):
    if role != "owner":
        raise HTTPException(status_code=403, detail="Your role can't open this.")
    data = await airtable_request("GET", TABLES["leads"], params={"maxRecords": 1, "returnFieldsByFieldId": "true"})
    return {"ok": True, "records_seen": len(data.get("records", []))}


_schema_cache: Dict[str, Dict[str, Any]] = {}


@api_router.get("/schema/{table_key}")
async def get_table_schema(table_key: str, role: str = Depends(require_auth)):
    table_id = resolve_table(table_key)
    await check_table_access(role, table_key)
    cached = _schema_cache.get(table_key)
    if cached and time.time() - cached["at"] < 600:
        fields = cached["fields"]
    else:
        key = get_api_key()
        if not key:
            raise HTTPException(status_code=503, detail={
                "error": "missing_key",
                "message": "Airtable key is not set. Add AIRTABLE_API_KEY in the secrets panel, then press Refresh."})
        url = f"{AIRTABLE_API_URL}/meta/bases/{get_base_id()}/tables"
        await limiter.wait()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers={"Authorization": f"Bearer {key}"})
        except httpx.HTTPError:
            raise HTTPException(status_code=502, detail="Could not reach Airtable. Check your internet and try again.")
        if resp.status_code == 403:
            raise HTTPException(status_code=403, detail="The Airtable token can't read the table layout. Recreate it with the schema.bases:read scope added.")
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Airtable could not send the table layout.")
        table = next((t for t in resp.json().get("tables", []) if t.get("id") == table_id), None)
        if not table:
            raise HTTPException(status_code=404, detail="Table not found in the base.")
        fields = [{"id": fl["id"], "name": fl["name"], "type": fl.get("type", "")} for fl in table.get("fields", [])]
        _schema_cache[table_key] = {"fields": fields, "at": time.time()}
    blocked = BLOCKED_FIELDS.get((role, table_key), set())
    return {"fields": [fl for fl in fields if fl["id"] not in blocked]}


@api_router.get("/tables/{table_key}")
async def list_records(table_key: str, role: str = Depends(require_auth)):
    table_id = resolve_table(table_key)
    await check_table_access(role, table_key)
    records = []
    offset = None
    while True:
        params: Dict[str, Any] = {"pageSize": 100, "returnFieldsByFieldId": "true"}
        if offset:
            params["offset"] = offset
        data = await airtable_request("GET", table_id, params=params)
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return {"records": [filter_record(r, role, table_key) for r in records]}


@api_router.post("/tables/{table_key}")
async def create_record(table_key: str, payload: RecordPayload = Body(...), role: str = Depends(require_auth)):
    table_id = resolve_table(table_key)
    await check_table_access(role, table_key)
    body = {"records": [{"fields": clean_write_fields(payload.fields, role, table_key)}], "typecast": True}
    data = await airtable_request("POST", table_id, json_body=body)
    return filter_record(data["records"][0], role, table_key)


@api_router.patch("/tables/{table_key}/{record_id}")
async def update_record(table_key: str, record_id: str, payload: RecordPayload = Body(...), role: str = Depends(require_auth)):
    table_id = resolve_table(table_key)
    await check_table_access(role, table_key)
    body = {"records": [{"id": record_id, "fields": clean_write_fields(payload.fields, role, table_key)}], "typecast": True}
    data = await airtable_request("PATCH", table_id, json_body=body)
    return filter_record(data["records"][0], role, table_key)


@api_router.delete("/tables/{table_key}/{record_id}")
async def delete_record(table_key: str, record_id: str, role: str = Depends(require_auth)):
    table_id = resolve_table(table_key)
    await check_table_access(role, table_key)
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can delete records.")
    await airtable_request("DELETE", table_id, path=f"/{record_id}")
    return {"deleted": True, "id": record_id}


# ---------------------------------------------------------------- crew module

dl_router = APIRouter(prefix="/api")

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def audit(actor: Dict[str, Any], action: str, target: str, details: Optional[Dict[str, Any]] = None):
    await mongo_db.audit_log.insert_one({
        "_id": str(uuid4()), "at": now_iso(), "actor": actor.get("name") or actor.get("role") or "unknown",
        "actor_id": actor.get("user_id"), "action": action, "target": target, "details": details or {},
    })


async def notify(user_id: Optional[str], role: Optional[str], title: str, body: str, ntype: str = "info",
                 data: Optional[Dict[str, Any]] = None):
    await mongo_db.notifications.insert_one({
        "_id": str(uuid4()), "user_id": user_id, "role": role, "type": ntype, "title": title, "body": body,
        "data": data or {}, "read": False, "created_at": now_iso(),
    })


async def geocode(address: str) -> Optional[Dict[str, float]]:
    if not address:
        return None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get("https://nominatim.openstreetmap.org/search",
                                 params={"q": address, "format": "json", "limit": 1},
                                 headers={"User-Agent": "HaulYeahCRM/1.0 (contact@haulyeahmoves.com)"})
        results = r.json()
        if results:
            return {"lat": float(results[0]["lat"]), "lng": float(results[0]["lon"])}
    except Exception:
        pass
    return None


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat, dlng = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(a))


async def get_crew_rates() -> Dict[str, float]:
    doc = await mongo_db.settings.find_one({"_id": "crew_rates"}) or {}
    return {"driver": float(doc.get("driver", 28)), "helper": float(doc.get("helper", 24))}


def position_rate(position: str, rates: Dict[str, float]) -> float:
    return rates["driver"] if (position or "").lower() == "driver" else rates["helper"]


def entry_hours(entry: Dict[str, Any]) -> Optional[float]:
    if not entry.get("clock_out"):
        return None
    try:
        start = datetime.fromisoformat(entry["clock_in"]["at"])
        end = datetime.fromisoformat(entry["clock_out"]["at"])
        return max(0.0, round((end - start).total_seconds() / 3600, 2))
    except (KeyError, ValueError, TypeError):
        return None


def week_key(iso_ts: str) -> str:
    try:
        d = datetime.fromisoformat(iso_ts)
    except ValueError:
        return "unknown"
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


# ------- Airtable "Job Time Log" mirror (CRM stays source of truth; never deletes Airtable records)

TIMELOG_TABLE = "tbl6mv59JAOwUyI4Y"
TL_ENTRY = "fld4JCy6E5QIGCEff"
TL_JOB_DATE = "fldXZA65mkdSHAgjc"
TL_CLOCK_IN = "flde2Su0f9dATc1Ql"
TL_CLOCK_OUT = "flddYzKloZk6s8kSt"
TL_CREW = "fldoE0yywtqOUjQ2i"
TL_DRIVER = "fldh7dsS16LVAGiaE"
TL_HELPERS = "fldUG4Lk8PXRz7xWx"
TL_CREW_SIZE = "fldFS3A3c3gPTClVj"
TL_TRUCK = "fldKEgVs6AZX0WSPR"
TL_JOB_SIZE = "fldMqMgGkXeUaNUqa"
TL_DELAY = "flddi4exe4gcay7lM"
TL_NOTES = "fldcZhWqgiiR4odDI"
TL_JOB_LINK = "fldqsqBRkDtUsCqbb"
EASTERN = ZoneInfo("America/New_York")
DELAY_FACTORS = ["Stairs", "Long carry", "Elevator wait", "Customer not packed", "Heavy/specialty items",
                 "Traffic", "Weather", "Customer added items", "None"]
JOB_SIZES = ["Studio/1BR", "2BR", "3BR", "4BR+", "Office/Commercial", "Labor-only (no truck)"]
_timelog_lock = asyncio.Lock()


def et_iso(iso_ts: str) -> str:
    return datetime.fromisoformat(iso_ts).astimezone(EASTERN).isoformat()


def timelog_entry_label(a: Dict[str, Any]) -> str:
    try:
        y, m, d = [int(x) for x in a["job_date"].split("-")]
        short = f"{m}/{d}/{y % 100}"
    except (ValueError, KeyError):
        short = a.get("job_date", "")
    return f"{a.get('job_name', '')} – {short}"


async def find_timelog_project_id(a: Dict[str, Any]) -> Optional[str]:
    if a.get("project_id"):
        return a["project_id"]
    try:
        data = await airtable_request("GET", TABLES["projects"], params={"returnFieldsByFieldId": "true"})
        for rec in data.get("records", []):
            fields = rec.get("fields", {})
            if (str(fields.get(PROJECT_NAME_FIELD) or "").strip().lower() == a.get("job_name", "").strip().lower()
                    and str(fields.get(PROJECT_DATE_FIELD) or "")[:10] == a.get("job_date")):
                return rec["id"]
    except Exception:
        pass
    return None


async def build_timelog_fields(a: Dict[str, Any], entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    ins = sorted(e["clock_in"]["at"] for e in entries if e.get("clock_in"))
    open_left = [e for e in entries if not e.get("clock_out")]
    outs = sorted(e["clock_out"]["at"] for e in entries if e.get("clock_out"))
    crew = a.get("crew", [])
    fields: Dict[str, Any] = {
        TL_ENTRY: timelog_entry_label(a),
        TL_JOB_DATE: a.get("job_date"),
        TL_CLOCK_IN: et_iso(ins[0]),
        TL_CREW: [c["name"] for c in crew],
        TL_HELPERS: [c["name"] for c in crew if c.get("position") != "Driver"],
        TL_CREW_SIZE: len(crew),
    }
    driver = next((c["name"] for c in crew if c.get("position") == "Driver"), None)
    if driver:
        fields[TL_DRIVER] = driver
    if a.get("truck_name"):
        fields[TL_TRUCK] = a["truck_name"]
    if a.get("job_size"):
        fields[TL_JOB_SIZE] = a["job_size"]
    project_id = await find_timelog_project_id(a)
    if project_id:
        fields[TL_JOB_LINK] = [project_id]
    if outs and not open_left:
        fields[TL_CLOCK_OUT] = et_iso(outs[-1])
    if a.get("delay_factors"):
        fields[TL_DELAY] = a["delay_factors"]
    if a.get("completion_notes"):
        fields[TL_NOTES] = a["completion_notes"]
    return fields


async def find_existing_timelog(a: Dict[str, Any]) -> Optional[str]:
    label = timelog_entry_label(a).replace('"', '\\"')
    data = await airtable_request("GET", TIMELOG_TABLE,
                                  params={"filterByFormula": f'{{Entry}}="{label}"', "maxRecords": 1})
    recs = data.get("records", [])
    return recs[0]["id"] if recs else None


async def sync_timelog(assignment_id: str) -> bool:
    async with _timelog_lock:
        a = await mongo_db.assignments.find_one({"_id": assignment_id})
        if not a:
            return True
        entries = await mongo_db.time_entries.find({"assignment_id": assignment_id}).to_list(50)
        if not entries:
            await mongo_db.assignments.update_one({"_id": assignment_id}, {"$unset": {"timelog_sync": ""}})
            return True
        try:
            fields = await build_timelog_fields(a, entries)
            rec_id = a.get("timelog_record_id") or await find_existing_timelog(a)
            if rec_id:
                patch_fields = {k: v for k, v in fields.items() if k != TL_CLOCK_IN}
                await airtable_request("PATCH", TIMELOG_TABLE, f"/{rec_id}",
                                       json_body={"fields": patch_fields, "typecast": True})
            else:
                created = await airtable_request("POST", TIMELOG_TABLE,
                                                 json_body={"fields": fields, "typecast": True})
                rec_id = created["id"]
            await mongo_db.assignments.update_one({"_id": assignment_id}, {"$set": {
                "timelog_record_id": rec_id,
                "timelog_sync": {"status": "synced", "at": now_iso(), "error": None}}})
            return True
        except Exception as exc:
            detail = getattr(exc, "detail", None)
            msg = detail.get("message") if isinstance(detail, dict) else (str(detail) if detail else str(exc))
            await mongo_db.assignments.update_one({"_id": assignment_id}, {"$set": {
                "timelog_sync": {"status": "pending", "at": now_iso(), "error": str(msg)[:300]}}})
            logger.warning("Time log sync pending for %s: %s", a.get("job_name"), msg)
            return False


async def queue_timelog_sync(assignment_id: Optional[str]):
    if not assignment_id:
        return
    await mongo_db.assignments.update_one(
        {"_id": assignment_id},
        {"$set": {"timelog_sync.status": "pending", "timelog_sync.at": now_iso()}})
    asyncio.create_task(sync_timelog(assignment_id))


async def timelog_retry_loop():
    while True:
        await asyncio.sleep(90)
        try:
            docs = await mongo_db.assignments.find({"timelog_sync.status": "pending"}).to_list(50)
            for d in docs:
                await sync_timelog(d["_id"])
        except Exception as exc:
            logger.warning("Time log retry loop error: %s", exc)


@api_router.get("/timelog/status")
async def timelog_status(p: Dict[str, Any] = Depends(require_owner)):
    pending = await mongo_db.assignments.find({"timelog_sync.status": "pending"}).to_list(100)
    last = await mongo_db.assignments.find({"timelog_sync.status": "synced"}).sort("timelog_sync.at", -1).limit(1).to_list(1)
    return {
        "configured": bool(get_api_key()),
        "pending": len(pending),
        "pending_jobs": [{"job_name": d.get("job_name"), "job_date": d.get("job_date"),
                          "error": (d.get("timelog_sync") or {}).get("error")} for d in pending],
        "last_synced_at": ((last[0].get("timelog_sync") or {}).get("at")) if last else None,
    }


@api_router.get("/calendar/jobs")
async def calendar_jobs(month: str, p: Dict[str, Any] = Depends(require_owner)):
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise HTTPException(status_code=422, detail="month must look like 2026-07")
    assignments = await mongo_db.assignments.find(
        {"job_date": {"$gte": f"{month}-01", "$lte": f"{month}-31"}}).sort("job_date", 1).to_list(300)
    ids = [a["_id"] for a in assignments]
    entries = await mongo_db.time_entries.find({"assignment_id": {"$in": ids}}).to_list(1000)
    by_assignment: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        by_assignment.setdefault(e["assignment_id"], []).append(e)
    trucks = {t["_id"]: t for t in await mongo_db.trucks.find({}).to_list(100)}
    days: Dict[str, List[Dict[str, Any]]] = {}
    for a in assignments:
        ent = by_assignment.get(a["_id"], [])
        ins = sorted(e["clock_in"]["at"] for e in ent if e.get("clock_in"))
        outs = sorted(e["clock_out"]["at"] for e in ent if e.get("clock_out"))
        open_count = sum(1 for e in ent if not e.get("clock_out"))
        worked_minutes = None
        if ins and outs and not open_count:
            try:
                worked_minutes = int((datetime.fromisoformat(outs[-1]) - datetime.fromisoformat(ins[0])).total_seconds() // 60)
            except ValueError:
                worked_minutes = None
        truck = trucks.get(a.get("truck_id") or "")
        days.setdefault(a["job_date"], []).append({
            "id": a["_id"], "job_name": a.get("job_name"), "job_size": a.get("job_size") or None,
            "exec_status": a.get("exec_status"),
            "crew": [{"name": c["name"], "position": c.get("position")} for c in a.get("crew", [])],
            "crew_size": len(a.get("crew", [])),
            "truck_name": a.get("truck_name"), "truck_plate": (truck or {}).get("plate") or None,
            "delay_factors": a.get("delay_factors", []), "notes": a.get("completion_notes") or "",
            "first_in": ins[0] if ins else None,
            "last_out": outs[-1] if (outs and not open_count) else None,
            "on_clock": open_count,
            "worked_minutes": worked_minutes,
        })
    return {"month": month, "days": days}


# ------- users management (owner)

class UserCreatePayload(BaseModel):
    name: str
    email: str
    role: str
    password: str


class UserPatchPayload(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None


@api_router.get("/users")
async def list_users(p: Dict[str, Any] = Depends(require_owner)):
    docs = await mongo_db.users.find({}).sort("created_at", 1).to_list(200)
    return {"users": [_user_public(u) for u in docs]}


@api_router.post("/users")
async def create_user(payload: UserCreatePayload, p: Dict[str, Any] = Depends(require_owner)):
    if payload.role not in ("crew", "sales", "owner"):
        raise HTTPException(status_code=422, detail="Role must be crew, sales, or owner.")
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="That email doesn't look right.")
    if len(payload.password) < 8:
        raise HTTPException(status_code=422, detail="The password needs at least 8 characters.")
    if await mongo_db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="A user with that email already exists.")
    doc = {"_id": str(uuid4()), "name": payload.name.strip(), "email": email, "role": payload.role,
           "password_hash": hash_password(payload.password), "active": True, "must_change_password": True,
           "gps_consent_at": None, "created_at": now_iso()}
    await mongo_db.users.insert_one(doc)
    await audit(p, "created user", f"{doc['name']} ({email}, {payload.role})")
    return _user_public(doc)


@api_router.patch("/users/{user_id}")
async def patch_user(user_id: str, payload: UserPatchPayload, p: Dict[str, Any] = Depends(require_owner)):
    user = await mongo_db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="No such user.")
    updates: Dict[str, Any] = {}
    changes = []
    if payload.name is not None and payload.name.strip():
        updates["name"] = payload.name.strip()
        changes.append("name")
    if payload.email is not None:
        email = payload.email.strip().lower()
        if "@" not in email:
            raise HTTPException(status_code=422, detail="That email doesn't look right.")
        clash = await mongo_db.users.find_one({"email": email, "_id": {"$ne": user_id}})
        if clash:
            raise HTTPException(status_code=409, detail="Another user already has that email.")
        updates["email"] = email
        changes.append("email")
    if payload.role is not None:
        if payload.role not in ("crew", "sales", "owner"):
            raise HTTPException(status_code=422, detail="Role must be crew, sales, or owner.")
        updates["role"] = payload.role
        changes.append(f"role → {payload.role}")
    if payload.active is not None:
        if p["user_id"] == user_id and payload.active is False:
            raise HTTPException(status_code=422, detail="You can't deactivate your own account.")
        updates["active"] = payload.active
        changes.append("deactivated" if not payload.active else "reactivated")
    if payload.password is not None:
        if len(payload.password) < 8:
            raise HTTPException(status_code=422, detail="The password needs at least 8 characters.")
        updates["password_hash"] = hash_password(payload.password)
        updates["must_change_password"] = True
        changes.append("password reset")
    if not updates:
        return _user_public(user)
    await mongo_db.users.update_one({"_id": user_id}, {"$set": updates})
    await audit(p, "edited user", f"{user.get('name')} ({user.get('email')})", {"changes": changes})
    fresh = await mongo_db.users.find_one({"_id": user_id})
    return _user_public(fresh)


# ------- trucks (owner)

class TruckPayload(BaseModel):
    name: str
    plate: str = ""


class TruckPatchPayload(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None
    plate: Optional[str] = None


@api_router.get("/trucks")
async def list_trucks(p: Dict[str, Any] = Depends(require_owner)):
    docs = await mongo_db.trucks.find({}).sort("name", 1).to_list(100)
    return {"trucks": [{"id": t["_id"], "name": t["name"], "active": t.get("active", True),
                        "plate": t.get("plate", "")} for t in docs]}


@api_router.post("/trucks")
async def create_truck(payload: TruckPayload, p: Dict[str, Any] = Depends(require_owner)):
    doc = {"_id": str(uuid4()), "name": payload.name.strip(), "plate": payload.plate.strip(), "active": True}
    await mongo_db.trucks.insert_one(doc)
    await audit(p, "added truck", doc["name"])
    return {"id": doc["_id"], "name": doc["name"], "active": True, "plate": doc["plate"]}


@api_router.patch("/trucks/{truck_id}")
async def patch_truck(truck_id: str, payload: TruckPatchPayload, p: Dict[str, Any] = Depends(require_owner)):
    truck = await mongo_db.trucks.find_one({"_id": truck_id})
    if not truck:
        raise HTTPException(status_code=404, detail="No such truck.")
    updates = {}
    if payload.name is not None and payload.name.strip():
        updates["name"] = payload.name.strip()
    if payload.active is not None:
        updates["active"] = payload.active
    if payload.plate is not None:
        updates["plate"] = payload.plate.strip()
    if updates:
        await mongo_db.trucks.update_one({"_id": truck_id}, {"$set": updates})
        await audit(p, "edited truck", truck["name"], {"changes": updates})
    fresh = await mongo_db.trucks.find_one({"_id": truck_id})
    return {"id": fresh["_id"], "name": fresh["name"], "active": fresh.get("active", True), "plate": fresh.get("plate", "")}


@api_router.delete("/trucks/{truck_id}")
async def delete_truck(truck_id: str, p: Dict[str, Any] = Depends(require_owner)):
    truck = await mongo_db.trucks.find_one({"_id": truck_id})
    if not truck:
        raise HTTPException(status_code=404, detail="No such truck.")
    await mongo_db.trucks.delete_one({"_id": truck_id})
    await audit(p, "removed truck", truck["name"])
    return {"deleted": True}


# ------- assignments

class CrewSlot(BaseModel):
    user_id: str
    position: str


class AssignmentPayload(BaseModel):
    project_id: Optional[str] = None
    job_name: str
    job_date: str
    arrival_time: str = ""
    start_address: str = ""
    end_address: str = ""
    truck_id: Optional[str] = None
    job_size: str = ""
    crew: List[CrewSlot] = []
    ignore_warnings: bool = False


async def assignment_warnings(job_date: str, crew_ids: List[str], truck_id: Optional[str],
                              exclude_id: Optional[str] = None) -> List[str]:
    warnings = []
    q: Dict[str, Any] = {"job_date": job_date}
    if exclude_id:
        q["_id"] = {"$ne": exclude_id}
    others = await mongo_db.assignments.find(q).to_list(100)
    for other in others:
        other_crew = {c["user_id"]: c["name"] for c in other.get("crew", [])}
        for uid in crew_ids:
            if uid in other_crew:
                warnings.append(f"{other_crew[uid]} is already on \"{other.get('job_name')}\" that day.")
        if truck_id and other.get("truck_id") == truck_id:
            warnings.append(f"Truck {other.get('truck_name')} is already on \"{other.get('job_name')}\" that day.")
    avail = await mongo_db.availability.find({"date": job_date, "available": False,
                                              "user_id": {"$in": crew_ids}}).to_list(50)
    for a in avail:
        warnings.append(f"{a.get('name')} marked themselves UNAVAILABLE on {job_date}.")
    return warnings


def _sanitize_assignment(a: Dict[str, Any]) -> Dict[str, Any]:
    return {**{k: v for k, v in a.items() if k != "_id"}, "id": a["_id"]}


@api_router.get("/assignments")
async def list_assignments(start: Optional[str] = None, end: Optional[str] = None,
                           p: Dict[str, Any] = Depends(require_owner)):
    q: Dict[str, Any] = {}
    if start or end:
        q["job_date"] = {}
        if start:
            q["job_date"]["$gte"] = start
        if end:
            q["job_date"]["$lte"] = end
    docs = await mongo_db.assignments.find(q).sort("job_date", 1).to_list(300)
    return {"assignments": [_sanitize_assignment(a) for a in docs]}


@api_router.post("/assignments")
async def create_assignment(payload: AssignmentPayload, p: Dict[str, Any] = Depends(require_owner)):
    if not payload.job_date:
        raise HTTPException(status_code=422, detail="Pick a job date.")
    if payload.job_size and payload.job_size not in JOB_SIZES:
        raise HTTPException(status_code=422, detail="Pick a real job size.")
    crew_ids = [c.user_id for c in payload.crew]
    for c in payload.crew:
        if c.position not in ("Driver", "Helper"):
            raise HTTPException(status_code=422, detail="Positions must be Driver or Helper.")
    users = await mongo_db.users.find({"_id": {"$in": crew_ids}, "active": True}).to_list(50)
    users_by_id = {u["_id"]: u for u in users}
    missing = [uid for uid in crew_ids if uid not in users_by_id]
    if missing:
        raise HTTPException(status_code=422, detail="One of those crew members doesn't exist or is deactivated.")
    warnings = await assignment_warnings(payload.job_date, crew_ids, payload.truck_id)
    if warnings and not payload.ignore_warnings:
        raise HTTPException(status_code=409, detail={"error": "conflicts", "warnings": warnings})
    truck = await mongo_db.trucks.find_one({"_id": payload.truck_id}) if payload.truck_id else None
    site_coords = await geocode(payload.start_address)
    doc = {
        "_id": str(uuid4()), "project_id": payload.project_id, "job_name": payload.job_name.strip(),
        "job_date": payload.job_date, "arrival_time": payload.arrival_time,
        "start_address": payload.start_address.strip(), "end_address": payload.end_address.strip(),
        "truck_id": payload.truck_id, "truck_name": truck["name"] if truck else None,
        "job_size": payload.job_size,
        "crew": [{"user_id": c.user_id, "name": users_by_id[c.user_id]["name"], "position": c.position} for c in payload.crew],
        "site_coords": site_coords, "exec_status": "Assigned", "status_history": [],
        "completion_notes": "", "review_prompted": False,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await mongo_db.assignments.insert_one(doc)
    for c in doc["crew"]:
        await notify(c["user_id"], None, "New job assigned",
                     f"{doc['job_name']} on {doc['job_date']}{' at ' + doc['arrival_time'] if doc['arrival_time'] else ''} — you're the {c['position']}.",
                     "assignment", {"assignment_id": doc["_id"]})
    await audit(p, "assigned crew to job", doc["job_name"],
                {"date": doc["job_date"], "crew": [f"{c['name']} ({c['position']})" for c in doc["crew"]],
                 "truck": doc["truck_name"]})
    return {**_sanitize_assignment(doc), "warnings": warnings}


@api_router.patch("/assignments/{assignment_id}")
async def update_assignment(assignment_id: str, payload: AssignmentPayload,
                            p: Dict[str, Any] = Depends(require_owner)):
    existing = await mongo_db.assignments.find_one({"_id": assignment_id})
    if not existing:
        raise HTTPException(status_code=404, detail="No such assignment.")
    if payload.job_size and payload.job_size not in JOB_SIZES:
        raise HTTPException(status_code=422, detail="Pick a real job size.")
    crew_ids = [c.user_id for c in payload.crew]
    users = await mongo_db.users.find({"_id": {"$in": crew_ids}, "active": True}).to_list(50)
    users_by_id = {u["_id"]: u for u in users}
    if any(uid not in users_by_id for uid in crew_ids):
        raise HTTPException(status_code=422, detail="One of those crew members doesn't exist or is deactivated.")
    warnings = await assignment_warnings(payload.job_date, crew_ids, payload.truck_id, exclude_id=assignment_id)
    if warnings and not payload.ignore_warnings:
        raise HTTPException(status_code=409, detail={"error": "conflicts", "warnings": warnings})
    truck = await mongo_db.trucks.find_one({"_id": payload.truck_id}) if payload.truck_id else None
    site_coords = existing.get("site_coords")
    if payload.start_address.strip() != existing.get("start_address"):
        site_coords = await geocode(payload.start_address)
    updates = {
        "job_name": payload.job_name.strip(), "job_date": payload.job_date, "arrival_time": payload.arrival_time,
        "start_address": payload.start_address.strip(), "end_address": payload.end_address.strip(),
        "truck_id": payload.truck_id, "truck_name": truck["name"] if truck else None,
        "job_size": payload.job_size,
        "crew": [{"user_id": c.user_id, "name": users_by_id[c.user_id]["name"], "position": c.position} for c in payload.crew],
        "site_coords": site_coords, "updated_at": now_iso(),
    }
    old_ids = {c["user_id"] for c in existing.get("crew", [])}
    await mongo_db.assignments.update_one({"_id": assignment_id}, {"$set": updates})
    for c in updates["crew"]:
        if c["user_id"] not in old_ids:
            await notify(c["user_id"], None, "New job assigned",
                         f"{updates['job_name']} on {updates['job_date']} — you're the {c['position']}.",
                         "assignment", {"assignment_id": assignment_id})
    for uid in old_ids - {c["user_id"] for c in updates["crew"]}:
        await notify(uid, None, "Taken off a job", f"You're no longer on {existing.get('job_name')} ({existing.get('job_date')}).",
                     "assignment", {"assignment_id": assignment_id})
    await audit(p, "updated job assignment", updates["job_name"],
                {"date": updates["job_date"], "crew": [f"{c['name']} ({c['position']})" for c in updates["crew"]]})
    await queue_timelog_sync(assignment_id)
    fresh = await mongo_db.assignments.find_one({"_id": assignment_id})
    return {**_sanitize_assignment(fresh), "warnings": warnings}


@api_router.delete("/assignments/{assignment_id}")
async def delete_assignment(assignment_id: str, p: Dict[str, Any] = Depends(require_owner)):
    existing = await mongo_db.assignments.find_one({"_id": assignment_id})
    if not existing:
        raise HTTPException(status_code=404, detail="No such assignment.")
    await mongo_db.assignments.delete_one({"_id": assignment_id})
    for c in existing.get("crew", []):
        await notify(c["user_id"], None, "Job removed",
                     f"{existing.get('job_name')} on {existing.get('job_date')} was taken off your schedule.",
                     "assignment", {})
    await audit(p, "deleted job assignment", existing.get("job_name") or assignment_id)
    return {"deleted": True}


# ------- crew: my jobs + execution workflow

EXEC_STATUSES = ["Assigned", "En Route", "Arrived", "In Progress", "Complete"]


def _crew_job_view(a: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    mine = next((c for c in a.get("crew", []) if c["user_id"] == user_id), {})
    return {
        "id": a["_id"], "job_name": a.get("job_name"), "job_date": a.get("job_date"),
        "arrival_time": a.get("arrival_time"), "start_address": a.get("start_address"),
        "truck_name": a.get("truck_name"), "my_position": mine.get("position"),
        "exec_status": a.get("exec_status"), "status_history": a.get("status_history", []),
        "completion_notes": a.get("completion_notes", ""),
    }


@api_router.get("/crew/my-jobs")
async def my_jobs(p: Dict[str, Any] = Depends(require_crew)):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).date().isoformat()
    docs = await mongo_db.assignments.find(
        {"crew.user_id": p["user_id"], "job_date": {"$gte": cutoff}}).sort("job_date", 1).to_list(100)
    return {"jobs": [_crew_job_view(a, p["user_id"]) for a in docs]}


class StatusPayload(BaseModel):
    status: str
    notes: Optional[str] = None
    delay_factors: Optional[List[str]] = None


@api_router.post("/crew/jobs/{assignment_id}/status")
async def set_job_status(assignment_id: str, payload: StatusPayload, p: Dict[str, Any] = Depends(require_crew)):
    if payload.status not in EXEC_STATUSES[1:]:
        raise HTTPException(status_code=422, detail="Unknown status.")
    a = await mongo_db.assignments.find_one({"_id": assignment_id, "crew.user_id": p["user_id"]})
    if not a:
        raise HTTPException(status_code=404, detail="That job isn't on your schedule.")
    event = {"status": payload.status, "at": now_iso(), "by": p["name"], "by_id": p["user_id"]}
    updates: Dict[str, Any] = {"exec_status": payload.status, "updated_at": now_iso()}
    if payload.status == "Complete" and payload.notes:
        updates["completion_notes"] = payload.notes.strip()
    if payload.status == "Complete" and payload.delay_factors is not None:
        updates["delay_factors"] = [d for d in payload.delay_factors if d in DELAY_FACTORS]
    await mongo_db.assignments.update_one({"_id": assignment_id},
                                          {"$set": updates, "$push": {"status_history": event}})
    if payload.status == "Complete" and not a.get("review_prompted"):
        await mongo_db.assignments.update_one({"_id": assignment_id}, {"$set": {"review_prompted": True}})
        await notify(None, "owner", "Job complete — ask for a review",
                     f"{p['name']} marked \"{a.get('job_name')}\" complete. Send the customer a review text from Projects.",
                     "job_complete", {"assignment_id": assignment_id, "project_id": a.get("project_id")})
    await audit(p, f"set job status to {payload.status}", a.get("job_name") or assignment_id)
    if payload.status == "Complete":
        await queue_timelog_sync(assignment_id)
    fresh = await mongo_db.assignments.find_one({"_id": assignment_id})
    return _crew_job_view(fresh, p["user_id"])


# ------- photos (object storage)

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
_storage_key: Optional[str] = None


async def get_storage_key() -> str:
    global _storage_key
    if _storage_key:
        return _storage_key
    emergent_key = os.environ.get("EMERGENT_LLM_KEY", "").strip()
    if not emergent_key:
        raise HTTPException(status_code=503, detail="Photo storage isn't set up (EMERGENT_LLM_KEY missing).")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{STORAGE_URL}/init", json={"emergent_key": emergent_key})
    if r.status_code >= 300:
        raise HTTPException(status_code=502, detail="Photo storage didn't respond. Try again.")
    _storage_key = r.json()["storage_key"]
    return _storage_key


@api_router.post("/crew/jobs/{assignment_id}/photos")
async def upload_job_photo(assignment_id: str, request: Request, file: UploadFile = File(...)):
    p = await current_principal(request)
    a = await mongo_db.assignments.find_one({"_id": assignment_id})
    if not a:
        raise HTTPException(status_code=404, detail="No such job.")
    is_mine = any(c["user_id"] == p["user_id"] for c in a.get("crew", []))
    if p["role"] != "owner" and not is_mine:
        raise HTTPException(status_code=403, detail="That job isn't on your schedule.")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=422, detail="Only photos can be uploaded here.")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="That photo is too big (15 MB max).")
    ext = (file.filename or "photo.jpg").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "jpg"
    path = f"haulyeah-crm/jobs/{assignment_id}/{uuid4()}.{ext}"
    key = await get_storage_key()
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.put(f"{STORAGE_URL}/objects/{path}",
                             headers={"X-Storage-Key": key, "Content-Type": file.content_type or "image/jpeg"},
                             content=data)
    if r.status_code >= 300:
        raise HTTPException(status_code=502, detail="The photo didn't upload. Try again.")
    stored = r.json()
    doc = {"_id": str(uuid4()), "assignment_id": assignment_id, "user_id": p["user_id"], "user_name": p["name"],
           "storage_path": stored["path"], "content_type": file.content_type or "image/jpeg",
           "filename": file.filename, "size": stored.get("size", len(data)), "created_at": now_iso()}
    await mongo_db.job_photos.insert_one(doc)
    await audit(p, "uploaded a job photo", a.get("job_name") or assignment_id)
    return {"id": doc["_id"], "created_at": doc["created_at"]}


@api_router.get("/jobs/{assignment_id}/photos")
async def list_job_photos(assignment_id: str, request: Request):
    p = await current_principal(request)
    a = await mongo_db.assignments.find_one({"_id": assignment_id})
    if not a:
        raise HTTPException(status_code=404, detail="No such job.")
    is_mine = any(c["user_id"] == p["user_id"] for c in a.get("crew", []))
    if p["role"] != "owner" and not is_mine:
        raise HTTPException(status_code=403, detail="That job isn't on your schedule.")
    docs = await mongo_db.job_photos.find({"assignment_id": assignment_id}).sort("created_at", 1).to_list(50)
    return {"photos": [{"id": d["_id"], "by": d.get("user_name"), "created_at": d["created_at"]} for d in docs]}


@dl_router.get("/photos/{photo_id}")
async def serve_photo(photo_id: str, request: Request, auth: Optional[str] = None):
    if auth:
        p = await principal_from_token_string(auth)
    else:
        p = await current_principal(request)
    doc = await mongo_db.job_photos.find_one({"_id": photo_id})
    if not doc:
        raise HTTPException(status_code=404, detail="No such photo.")
    if p["role"] != "owner":
        a = await mongo_db.assignments.find_one({"_id": doc["assignment_id"]})
        if not a or not any(c["user_id"] == p["user_id"] for c in a.get("crew", [])):
            raise HTTPException(status_code=403, detail="Not yours to see.")
    key = await get_storage_key()
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(f"{STORAGE_URL}/objects/{doc['storage_path']}", headers={"X-Storage-Key": key})
    if r.status_code >= 300:
        raise HTTPException(status_code=404, detail="Photo file missing.")
    return Response(content=r.content, media_type=doc.get("content_type", "image/jpeg"))


# ------- time clock

class PunchPayload(BaseModel):
    lat: Optional[float] = None
    lng: Optional[float] = None
    accuracy: Optional[float] = None


async def _todays_assignment(user_id: str) -> Optional[Dict[str, Any]]:
    today = datetime.now(timezone.utc).date().isoformat()
    return await mongo_db.assignments.find_one({"crew.user_id": user_id, "job_date": today})


def _punch_flags(punch_at: datetime, coords: Optional[Dict[str, float]], assignment: Optional[Dict[str, Any]],
                 kind: str) -> List[str]:
    flags = []
    if not coords:
        flags.append(f"no_gps_{kind}")
    if assignment:
        site = assignment.get("site_coords")
        if coords and site:
            dist = haversine_miles(coords["lat"], coords["lng"], site["lat"], site["lng"])
            if dist > 0.75:
                flags.append(f"far_from_site_{kind} ({dist:.1f} mi)")
        arrival = assignment.get("arrival_time")
        if arrival and kind == "in":
            try:
                hh, mm = [int(x) for x in arrival.split(":")]
                sched = datetime.fromisoformat(f"{assignment['job_date']}T{hh:02d}:{mm:02d}:00+00:00")
                delta_h = (punch_at - sched).total_seconds() / 3600
                if delta_h < -2:
                    flags.append(f"clocked_in_{abs(delta_h):.1f}h_early")
                elif delta_h > 6:
                    flags.append(f"clocked_in_{delta_h:.1f}h_late")
            except (ValueError, KeyError):
                pass
    return flags


@api_router.post("/crew/clock-in")
async def clock_in(payload: PunchPayload, p: Dict[str, Any] = Depends(require_crew)):
    open_entry = await mongo_db.time_entries.find_one({"user_id": p["user_id"], "clock_out": None})
    if open_entry:
        raise HTTPException(status_code=409, detail="You're already clocked in.")
    now = datetime.now(timezone.utc)
    coords = {"lat": payload.lat, "lng": payload.lng} if payload.lat is not None and payload.lng is not None else None
    assignment = await _todays_assignment(p["user_id"])
    position = "Helper"
    if assignment:
        mine = next((c for c in assignment.get("crew", []) if c["user_id"] == p["user_id"]), None)
        if mine:
            position = mine.get("position") or "Helper"
    doc = {
        "_id": str(uuid4()), "user_id": p["user_id"], "user_name": p["name"],
        "clock_in": {"at": now.isoformat(), "lat": payload.lat, "lng": payload.lng, "accuracy": payload.accuracy},
        "clock_out": None, "assignment_id": assignment["_id"] if assignment else None,
        "job_name": assignment.get("job_name") if assignment else None, "position": position,
        "hours": None, "flags": _punch_flags(now, coords, assignment, "in"),
        "approved": False, "edited": False, "created_at": now.isoformat(),
    }
    await mongo_db.time_entries.insert_one(doc)
    if coords:
        await mongo_db.gps_pings.insert_one({"_id": str(uuid4()), "user_id": p["user_id"], "user_name": p["name"],
                                             "lat": payload.lat, "lng": payload.lng, "at": now.isoformat()})
    await queue_timelog_sync(doc["assignment_id"])
    return {"entry_id": doc["_id"], "clocked_in_at": doc["clock_in"]["at"], "job_name": doc["job_name"],
            "position": position, "flags": doc["flags"]}


@api_router.post("/crew/clock-out")
async def clock_out(payload: PunchPayload, p: Dict[str, Any] = Depends(require_crew)):
    entry = await mongo_db.time_entries.find_one({"user_id": p["user_id"], "clock_out": None})
    if not entry:
        raise HTTPException(status_code=409, detail="You're not clocked in.")
    now = datetime.now(timezone.utc)
    coords = {"lat": payload.lat, "lng": payload.lng} if payload.lat is not None and payload.lng is not None else None
    assignment = await mongo_db.assignments.find_one({"_id": entry.get("assignment_id")}) if entry.get("assignment_id") else None
    flags = list(entry.get("flags", [])) + _punch_flags(now, coords, assignment, "out")
    clock_out_data = {"at": now.isoformat(), "lat": payload.lat, "lng": payload.lng, "accuracy": payload.accuracy}
    hours = entry_hours({**entry, "clock_out": clock_out_data})
    if hours is not None and hours > 14:
        flags.append(f"long_shift_{hours:.1f}h")
    await mongo_db.time_entries.update_one({"_id": entry["_id"]},
                                           {"$set": {"clock_out": clock_out_data, "hours": hours, "flags": flags}})
    await queue_timelog_sync(entry.get("assignment_id"))
    return {"entry_id": entry["_id"], "hours": hours, "flags": flags}


@api_router.post("/crew/ping")
async def gps_ping(payload: PunchPayload, p: Dict[str, Any] = Depends(require_crew)):
    open_entry = await mongo_db.time_entries.find_one({"user_id": p["user_id"], "clock_out": None})
    if not open_entry:
        raise HTTPException(status_code=409, detail="Not clocked in — location isn't tracked.")
    if payload.lat is None or payload.lng is None:
        raise HTTPException(status_code=422, detail="No location in that ping.")
    await mongo_db.gps_pings.insert_one({"_id": str(uuid4()), "user_id": p["user_id"], "user_name": p["name"],
                                         "lat": payload.lat, "lng": payload.lng, "at": now_iso()})
    return {"ok": True}


@api_router.get("/crew/my-time")
async def my_time(p: Dict[str, Any] = Depends(require_crew)):
    docs = await mongo_db.time_entries.find({"user_id": p["user_id"]}).sort("created_at", -1).to_list(200)
    weeks: Dict[str, float] = {}
    for e in docs:
        h = e.get("hours")
        if h:
            wk = week_key(e["clock_in"]["at"])
            weeks[wk] = round(weeks.get(wk, 0) + h, 2)
    open_entry = next((e for e in docs if not e.get("clock_out")), None)
    return {
        "entries": [{"id": e["_id"], "clock_in": e["clock_in"], "clock_out": e.get("clock_out"),
                     "hours": e.get("hours"), "job_name": e.get("job_name"), "position": e.get("position"),
                     "approved": e.get("approved", False)} for e in docs],
        "weekly_totals": weeks,
        "clocked_in": bool(open_entry),
        "open_entry": {"id": open_entry["_id"], "clocked_in_at": open_entry["clock_in"]["at"],
                       "job_name": open_entry.get("job_name")} if open_entry else None,
    }


# ------- owner: timeclock management, live map

class TimeEntryPatch(BaseModel):
    clock_in_at: Optional[str] = None
    clock_out_at: Optional[str] = None
    position: Optional[str] = None
    approved: Optional[bool] = None


@api_router.get("/timeclock")
async def list_time_entries(start: Optional[str] = None, end: Optional[str] = None,
                            p: Dict[str, Any] = Depends(require_owner)):
    q: Dict[str, Any] = {}
    if start:
        q.setdefault("created_at", {})["$gte"] = start
    if end:
        q.setdefault("created_at", {})["$lte"] = end + "T23:59:59+00:00"
    docs = await mongo_db.time_entries.find(q).sort("created_at", -1).to_list(500)
    rates = await get_crew_rates()
    out = []
    for e in docs:
        h = e.get("hours")
        rate = position_rate(e.get("position", "Helper"), rates)
        out.append({"id": e["_id"], "user_id": e["user_id"], "user_name": e["user_name"],
                    "clock_in": e["clock_in"], "clock_out": e.get("clock_out"), "hours": h,
                    "job_name": e.get("job_name"), "position": e.get("position"), "rate": rate,
                    "pay": round(h * rate, 2) if h else None, "flags": e.get("flags", []),
                    "approved": e.get("approved", False), "edited": e.get("edited", False)})
    return {"entries": out}


@api_router.patch("/timeclock/{entry_id}")
async def patch_time_entry(entry_id: str, payload: TimeEntryPatch, p: Dict[str, Any] = Depends(require_owner)):
    entry = await mongo_db.time_entries.find_one({"_id": entry_id})
    if not entry:
        raise HTTPException(status_code=404, detail="No such time entry.")
    updates: Dict[str, Any] = {}
    changes = []
    if payload.clock_in_at:
        try:
            datetime.fromisoformat(payload.clock_in_at)
        except ValueError:
            raise HTTPException(status_code=422, detail="Bad clock-in time format.")
        updates["clock_in"] = {**entry["clock_in"], "at": payload.clock_in_at}
        changes.append("clock-in time")
    if payload.clock_out_at:
        try:
            datetime.fromisoformat(payload.clock_out_at)
        except ValueError:
            raise HTTPException(status_code=422, detail="Bad clock-out time format.")
        updates["clock_out"] = {**(entry.get("clock_out") or {}), "at": payload.clock_out_at}
        changes.append("clock-out time")
    if payload.position in ("Driver", "Helper"):
        updates["position"] = payload.position
        changes.append(f"position → {payload.position}")
    if payload.approved is not None:
        updates["approved"] = payload.approved
        changes.append("approved" if payload.approved else "unapproved")
    if changes and (payload.clock_in_at or payload.clock_out_at):
        updates["edited"] = True
    if updates:
        merged = {**entry, **updates}
        if merged.get("clock_out"):
            updates["hours"] = entry_hours(merged)
        await mongo_db.time_entries.update_one({"_id": entry_id}, {"$set": updates})
        await audit(p, "edited time entry", f"{entry['user_name']} — {entry['clock_in']['at'][:10]}", {"changes": changes})
        await queue_timelog_sync(entry.get("assignment_id"))
    fresh = await mongo_db.time_entries.find_one({"_id": entry_id})
    return {"id": fresh["_id"], "hours": fresh.get("hours"), "approved": fresh.get("approved", False),
            "edited": fresh.get("edited", False), "clock_in": fresh["clock_in"], "clock_out": fresh.get("clock_out")}


@dl_router.get("/timeclock/export")
async def export_timesheet(start: Optional[str] = None, end: Optional[str] = None, auth: Optional[str] = None,
                           request: Request = None):
    if auth:
        p = await principal_from_token_string(auth)
    else:
        p = await current_principal(request)
    if p["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can export timesheets.")
    q: Dict[str, Any] = {}
    if start:
        q.setdefault("created_at", {})["$gte"] = start
    if end:
        q.setdefault("created_at", {})["$lte"] = end + "T23:59:59+00:00"
    docs = await mongo_db.time_entries.find(q).sort([("user_name", 1), ("created_at", 1)]).to_list(1000)
    rates = await get_crew_rates()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Crew member", "Date", "Clock in", "Clock out", "Hours", "Position", "Rate", "Pay",
                     "Job", "Week", "Approved", "Edited", "Flags"])
    totals: Dict[str, Dict[str, float]] = {}
    for e in docs:
        h = e.get("hours") or 0
        rate = position_rate(e.get("position", "Helper"), rates)
        pay = round(h * rate, 2)
        wk = week_key(e["clock_in"]["at"])
        writer.writerow([e["user_name"], e["clock_in"]["at"][:10], e["clock_in"]["at"][11:16],
                         (e.get("clock_out") or {}).get("at", "")[11:16], h, e.get("position", ""), rate, pay,
                         e.get("job_name") or "", wk, "yes" if e.get("approved") else "no",
                         "yes" if e.get("edited") else "no", "; ".join(e.get("flags", []))])
        key = f"{e['user_name']}|{wk}"
        t = totals.setdefault(key, {"hours": 0, "pay": 0})
        t["hours"] = round(t["hours"] + h, 2)
        t["pay"] = round(t["pay"] + pay, 2)
    writer.writerow([])
    writer.writerow(["WEEKLY TOTALS"])
    writer.writerow(["Crew member", "Week", "Total hours", "Total pay"])
    for key in sorted(totals):
        name, wk = key.split("|")
        writer.writerow([name, wk, totals[key]["hours"], totals[key]["pay"]])
    filename = f"haulyeah-timesheet-{start or 'all'}-to-{end or 'now'}.csv"
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@api_router.get("/gps/live")
async def gps_live(p: Dict[str, Any] = Depends(require_owner)):
    open_entries = await mongo_db.time_entries.find({"clock_out": None}).to_list(50)
    out = []
    for e in open_entries:
        ping = await mongo_db.gps_pings.find({"user_id": e["user_id"]}).sort("at", -1).limit(1).to_list(1)
        loc = ping[0] if ping else None
        out.append({"user_id": e["user_id"], "name": e["user_name"], "job_name": e.get("job_name"),
                    "clocked_in_at": e["clock_in"]["at"],
                    "lat": loc["lat"] if loc else None, "lng": loc["lng"] if loc else None,
                    "last_ping": loc["at"] if loc else None})
    return {"crew": out}


# ------- availability

class AvailabilityPayload(BaseModel):
    date: str
    available: bool


@api_router.get("/crew/availability")
async def my_availability(p: Dict[str, Any] = Depends(require_crew)):
    docs = await mongo_db.availability.find({"user_id": p["user_id"]}).to_list(200)
    return {"availability": {d["date"]: d["available"] for d in docs}}


@api_router.post("/crew/availability")
async def set_availability(payload: AvailabilityPayload, p: Dict[str, Any] = Depends(require_crew)):
    await mongo_db.availability.update_one(
        {"_id": f"{p['user_id']}:{payload.date}"},
        {"$set": {"user_id": p["user_id"], "name": p["name"], "date": payload.date,
                  "available": payload.available, "updated_at": now_iso()}},
        upsert=True)
    return {"ok": True, "date": payload.date, "available": payload.available}


@api_router.get("/availability")
async def all_availability(start: Optional[str] = None, end: Optional[str] = None,
                           p: Dict[str, Any] = Depends(require_owner)):
    q: Dict[str, Any] = {}
    if start or end:
        q["date"] = {}
        if start:
            q["date"]["$gte"] = start
        if end:
            q["date"]["$lte"] = end
    docs = await mongo_db.availability.find(q).to_list(500)
    return {"availability": [{"user_id": d["user_id"], "name": d.get("name"), "date": d["date"],
                              "available": d["available"]} for d in docs]}


# ------- notifications

@api_router.get("/notifications")
async def list_notifications(request: Request):
    p = await current_principal(request)
    q: Dict[str, Any] = {"$or": [{"user_id": p["user_id"]}]} if p["user_id"] else {"$or": []}
    if p["role"] == "owner":
        q["$or"].append({"role": "owner"})
    if not q["$or"]:
        return {"notifications": [], "unread": 0}
    docs = await mongo_db.notifications.find(q).sort("created_at", -1).to_list(50)
    unread = sum(1 for d in docs if not d.get("read"))
    return {"notifications": [{"id": d["_id"], "title": d["title"], "body": d["body"], "type": d.get("type"),
                               "data": d.get("data", {}), "read": d.get("read", False),
                               "created_at": d["created_at"]} for d in docs],
            "unread": unread}


@api_router.post("/notifications/read-all")
async def read_all_notifications(request: Request):
    p = await current_principal(request)
    ors = []
    if p["user_id"]:
        ors.append({"user_id": p["user_id"]})
    if p["role"] == "owner":
        ors.append({"role": "owner"})
    if ors:
        await mongo_db.notifications.update_many({"$or": ors}, {"$set": {"read": True}})
    return {"ok": True}


# ------- crew rates + sales access settings

class CrewRatesPayload(BaseModel):
    driver: float
    helper: float


@api_router.get("/settings/crew-rates")
async def crew_rates(p: Dict[str, Any] = Depends(require_owner)):
    return await get_crew_rates()


@api_router.put("/settings/crew-rates")
async def save_crew_rates(payload: CrewRatesPayload, p: Dict[str, Any] = Depends(require_owner)):
    if payload.driver < 0 or payload.helper < 0:
        raise HTTPException(status_code=422, detail="Rates can't be negative.")
    await mongo_db.settings.update_one({"_id": "crew_rates"},
                                       {"$set": {"driver": payload.driver, "helper": payload.helper}}, upsert=True)
    await audit(p, "changed crew pay rates", f"Driver ${payload.driver}/hr, Helper ${payload.helper}/hr")
    return {"driver": payload.driver, "helper": payload.helper}


class SalesAccessPayload(BaseModel):
    booking_calendar: bool = False
    calculator: bool = True
    script: bool = True


@api_router.get("/settings/sales-access")
async def get_sales_access(role: str = Depends(require_auth)):
    doc = await mongo_db.settings.find_one({"_id": "sales_access"}) or {}
    return {"booking_calendar": bool(doc.get("booking_calendar", False)),
            "calculator": bool(doc.get("calculator", True)), "script": bool(doc.get("script", True))}


@api_router.put("/settings/sales-access")
async def save_sales_access(payload: SalesAccessPayload, p: Dict[str, Any] = Depends(require_owner)):
    await mongo_db.settings.update_one({"_id": "sales_access"}, {"$set": payload.model_dump()}, upsert=True)
    await audit(p, "changed sales role access", str(payload.model_dump()))
    return payload.model_dump()


# ------- reports + audit (owner)

@api_router.get("/reports/labor")
async def labor_report(start: Optional[str] = None, end: Optional[str] = None,
                       p: Dict[str, Any] = Depends(require_owner)):
    if not start:
        start = (datetime.now(timezone.utc) - timedelta(days=28)).date().isoformat()
    if not end:
        end = datetime.now(timezone.utc).date().isoformat()
    entries = await mongo_db.time_entries.find(
        {"created_at": {"$gte": start, "$lte": end + "T23:59:59+00:00"}}).to_list(1000)
    assignments = await mongo_db.assignments.find({"job_date": {"$gte": start, "$lte": end}}).to_list(300)
    rates = await get_crew_rates()

    revenue_by_project: Dict[str, float] = {}
    if get_api_key():
        try:
            data = await airtable_request("GET", TABLES["projects"], params={"returnFieldsByFieldId": "true"})
            for rec in data.get("records", []):
                fields = rec.get("fields", {})
                revenue_by_project[rec["id"]] = float(fields.get(PROJECT_REVENUE_FIELD) or fields.get(PROJECT_QUOTE_FIELD) or 0)
        except HTTPException:
            pass

    by_assignment: Dict[str, Dict[str, float]] = {}
    total_hours = 0.0
    total_cost = 0.0
    for e in entries:
        h = e.get("hours") or 0
        if not h:
            continue
        cost = h * position_rate(e.get("position", "Helper"), rates)
        total_hours = round(total_hours + h, 2)
        total_cost = round(total_cost + cost, 2)
        aid = e.get("assignment_id") or "unassigned"
        agg = by_assignment.setdefault(aid, {"hours": 0, "cost": 0})
        agg["hours"] = round(agg["hours"] + h, 2)
        agg["cost"] = round(agg["cost"] + cost, 2)

    jobs = []
    for a in assignments:
        agg = by_assignment.get(a["_id"], {"hours": 0, "cost": 0})
        revenue = revenue_by_project.get(a.get("project_id") or "", 0)
        jobs.append({"assignment_id": a["_id"], "job_name": a.get("job_name"), "job_date": a.get("job_date"),
                     "exec_status": a.get("exec_status"), "hours": agg["hours"], "labor_cost": agg["cost"],
                     "revenue": revenue or None,
                     "margin": round(revenue - agg["cost"], 2) if revenue else None})
    unassigned = by_assignment.get("unassigned", {"hours": 0, "cost": 0})
    completed = sum(1 for a in assignments if a.get("exec_status") == "Complete")
    return {"start": start, "end": end, "jobs": jobs, "unassigned_hours": unassigned["hours"],
            "unassigned_cost": unassigned["cost"], "totals": {"jobs_completed": completed,
                                                              "total_hours": total_hours,
                                                              "total_labor_cost": total_cost}}


@api_router.get("/audit")
async def audit_log(limit: int = 200, p: Dict[str, Any] = Depends(require_owner)):
    docs = await mongo_db.audit_log.find({}).sort("at", -1).to_list(min(limit, 500))
    return {"entries": [{"at": d["at"], "actor": d["actor"], "action": d["action"], "target": d.get("target"),
                         "details": d.get("details", {})} for d in docs]}


# ------- startup seeding

@app.on_event("startup")
async def seed_on_startup():
    try:
        await mongo_db.users.create_index("email", unique=True)
        owner_email = os.environ.get("OWNER_EMAIL", "haulyeahowner").strip().lower()
        owner_pw = os.environ.get("APP_PASSWORD", "")
        if owner_email != "keithriv24@gmail.com":
            await mongo_db.users.update_one({"email": "keithriv24@gmail.com"}, {"$set": {"email": owner_email}})
        seeds = [
            {"name": "Keith (Owner)", "email": owner_email, "role": "owner", "password": owner_pw},
            {"name": "Javante Brown", "email": "javante@haulyeahmoves.com", "role": "crew", "password": "HaulCrew2026!"},
            {"name": "Junior Santil", "email": "junior@haulyeahmoves.com", "role": "crew", "password": "HaulCrew2026!"},
        ]
        for s in seeds:
            if not s["password"]:
                continue
            existing = await mongo_db.users.find_one({"email": s["email"]})
            if existing is None:
                await mongo_db.users.insert_one({
                    "_id": str(uuid4()), "name": s["name"], "email": s["email"], "role": s["role"],
                    "password_hash": hash_password(s["password"]), "active": True,
                    "must_change_password": s["role"] != "owner", "gps_consent_at": None, "created_at": now_iso()})
        if await mongo_db.trucks.count_documents({}) == 0:
            for i in range(1, 6):
                await mongo_db.trucks.insert_one({"_id": str(uuid4()), "name": f"Truck {i}", "plate": "", "active": True})
    except Exception as exc:
        logger.error("Startup seeding failed: %s", exc)
    asyncio.create_task(timelog_retry_loop())


app.include_router(auth_router)
app.include_router(dl_router)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
