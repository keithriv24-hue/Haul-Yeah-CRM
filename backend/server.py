import asyncio
import base64
import csv
import hashlib
import hmac
import io
import json
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
from reportlab.lib.pagesizes import letter as PDF_LETTER
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor
from reportlab.pdfgen.canvas import Canvas as PDFCanvas
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
SWITCH_ROLES = ("owner", "sales", "employee", "marketing")
ALL_ROLES = ("owner", "sales", "employee", "crew", "marketing")
ROLE_ENV = {"owner": "APP_PASSWORD", "sales": "SALES_PASSWORD", "employee": "EMPLOYEE_PASSWORD"}
ROLE_TABLES = {
    "owner": set(TABLES),
    "sales": {"leads", "tasks", "blog"},
    "employee": {"projects", "tasks", "blog"},
    "marketing": {"tasks", "blog"},
    "crew": {"tasks", "blog"},
}

TASK_GROUPS = ("sales", "marketing", "crew")
TASK_GROUP_FOR_ROLE = {"sales": "sales", "marketing": "marketing", "crew": "crew", "employee": "crew"}
TASK_STATUS_F = "fldIpdRVz51aQaNZh"
BLOG_STATUS_F = "fldu92VQBEbkeGhtQ"
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


def make_user_token(user: Dict[str, Any], role: Optional[str] = None) -> str:
    claims = {
        "sub": user["email"],
        "uid": user["_id"],
        "role": role or user["role"],
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
        roles = user.get("roles") or ([user["role"]] if user.get("role") else ["crew"])
        claimed = payload.get("role")
        active = claimed if claimed in roles else user.get("role", roles[0])
        return {"role": active, "roles": roles, "user_id": uid, "name": user.get("name", ""), "email": user.get("email", ""),
                "is_user": True, "must_change_password": bool(user.get("must_change_password")),
                "gps_consent_at": user.get("gps_consent_at")}
    role = payload.get("role") or payload.get("sub") or "owner"
    if role not in ALL_ROLES:
        raise HTTPException(status_code=401, detail="Invalid session. Log in again.")
    return {"role": role, "roles": [role], "user_id": None, "name": role.capitalize(), "email": None, "is_user": False,
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
    "cushionPercent": 10,
    "travelTruck": 125,
    "travelLabor": 75,
    "mileageAllowance": 20,
    "overageRate": 0.85,
    "stairFlight": 85,
    "packingRate": 65,
    "depositPercent": 25,
    "roundingIncrement": 50,
}


class RatesPayload(BaseModel):
    manHour: float
    cushionPercent: float
    travelTruck: float
    travelLabor: float
    mileageAllowance: float
    overageRate: float
    stairFlight: float
    packingRate: float
    depositPercent: float
    roundingIncrement: float


app = FastAPI(title="Haul Yeah Moving CRM Proxy")
api_router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])
auth_router = APIRouter(prefix="/api/auth")


class LoginPayload(BaseModel):
    password: str
    email: Optional[str] = None


def _user_public(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": user["_id"], "name": user.get("name", ""), "email": user.get("email", ""), "role": user.get("role"),
        "roles": user.get("roles") or ([user["role"]] if user.get("role") else []),
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
        user_roles = user.get("roles") or [user["role"]]
        return {
            "token": make_user_token(user), "role": user["role"],
            "can_switch": user["role"] == "owner" or len(user_roles) > 1,
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
    uid = token_payload.get("uid")
    if uid:
        user = await mongo_db.users.find_one({"_id": uid})
        if not user or not user.get("active", True):
            raise HTTPException(status_code=401, detail="This account is turned off. Talk to the owner.")
        roles = user.get("roles") or [user.get("role")]
        if "owner" in roles and payload.role in SWITCH_ROLES:
            return {"token": make_token(payload.role, owner_switch=True), "role": payload.role, "can_switch": True}
        if payload.role not in roles:
            raise HTTPException(status_code=403, detail="You don't have that view.")
        return {"token": make_user_token(user, role=payload.role), "role": payload.role,
                "can_switch": len(roles) > 1, "user": _user_public(user)}
    current = token_payload.get("role") or "owner"
    if current != "owner" and not token_payload.get("owner_switch"):
        raise HTTPException(status_code=403, detail="Only the owner can switch accounts.")
    if payload.role not in SWITCH_ROLES:
        raise HTTPException(status_code=422, detail="Unknown role.")
    return {"token": make_token(payload.role, owner_switch=True), "role": payload.role, "can_switch": True}


@auth_router.get("/me")
async def me(request: Request):
    p = await current_principal(request)
    can_switch = p["role"] == "owner" or bool(decode_token(request).get("owner_switch")) or len(p.get("roles") or []) > 1
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
    return {**DEFAULT_RATES, **{k: v for k, v in doc.items() if k in DEFAULT_RATES}, "_updatedAt": doc.get("_updatedAt", {})}


@api_router.put("/settings/rates")
async def save_rates(payload: RatesPayload, role: str = Depends(require_auth)):
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can change rates.")
    rates = payload.model_dump()
    if any(v < 0 for v in rates.values()):
        raise HTTPException(status_code=422, detail="Rates can't be negative.")
    if rates["roundingIncrement"] < 1:
        raise HTTPException(status_code=422, detail="The rounding increment must be at least $1.")
    doc = await mongo_db.settings.find_one({"_id": "calculator_rates"}) or {}
    current = {**DEFAULT_RATES, **{k: v for k, v in doc.items() if k in DEFAULT_RATES}}
    stamps = doc.get("_updatedAt", {})
    now_iso = datetime.now(timezone.utc).isoformat()
    for k, v in rates.items():
        if v != current.get(k):
            stamps[k] = now_iso
    await mongo_db.settings.update_one({"_id": "calculator_rates"}, {"$set": {**rates, "_updatedAt": stamps}}, upsert=True)
    return {**rates, "_updatedAt": stamps}


DEFAULT_ITEMS = [
    {"id": "piano-upright", "name": "Piano (upright)", "price": 500, "active": True},
    {"id": "piano-grand", "name": "Piano (baby grand)", "price": 800, "active": True},
]


class CalcItemUpsert(BaseModel):
    id: Optional[str] = None
    name: str
    price: float
    active: bool = True


class CalcItemsPayload(BaseModel):
    upserts: list[CalcItemUpsert] = []
    deletes: list[str] = []


async def load_calc_items():
    doc = await mongo_db.settings.find_one({"_id": "calculator_items"})
    if doc is None:
        await mongo_db.settings.insert_one({"_id": "calculator_items", "items": DEFAULT_ITEMS})
        return [dict(i) for i in DEFAULT_ITEMS]
    return doc.get("items", [])


@api_router.get("/settings/items")
async def get_calc_items(role: str = Depends(require_auth)):
    if role not in ("owner", "sales"):
        raise HTTPException(status_code=403, detail="Your role can't open this.")
    return {"items": await load_calc_items()}


@api_router.put("/settings/items")
async def save_calc_items(payload: CalcItemsPayload, role: str = Depends(require_auth)):
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can change the item list.")
    items = await load_calc_items()
    deletes = set(payload.deletes)
    items = [i for i in items if i["id"] not in deletes]
    by_id = {i["id"]: i for i in items}
    for u in payload.upserts:
        name = u.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Every item needs a name.")
        if u.price < 0 or u.price > 100000:
            raise HTTPException(status_code=422, detail=f'"{name}" needs a price between $0 and $100,000.')
        if u.id and u.id in by_id:
            by_id[u.id].update({"name": name, "price": u.price, "active": u.active})
        else:
            items.append({"id": uuid4().hex[:12], "name": name, "price": u.price, "active": u.active})
    await mongo_db.settings.update_one({"_id": "calculator_items"}, {"$set": {"items": items}}, upsert=True)
    return {"items": items}


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
DEFAULT_TRUCK_PICKUP = "3 Slater Dr, Elizabeth, NJ"
OPENPHONE_API_URL = "https://api.openphone.com/v1"


async def get_integrations() -> Dict[str, Any]:
    return await mongo_db.settings.find_one({"_id": "integrations"}) or {}


async def square_creds() -> Dict[str, str]:
    doc = await get_integrations()
    return {
        "token": ((doc.get("square_access_token") or "").strip() or os.environ.get("SQUARE_ACCESS_TOKEN", "").strip()),
        "location_id": ((doc.get("square_location_id") or "").strip() or os.environ.get("SQUARE_LOCATION_ID", "").strip()),
    }


async def square_is_configured() -> bool:
    creds = await square_creds()
    return bool(creds["token"] and creds["location_id"])


async def openphone_config() -> Dict[str, str]:
    doc = await get_integrations()
    return {"api_key": (doc.get("openphone_api_key") or "").strip(),
            "number": (doc.get("openphone_number") or "").strip()}


async def openphone_send_sms(to_phone: Optional[str], text: str) -> None:
    cfg = await openphone_config()
    if not cfg["api_key"] or not cfg["number"]:
        raise HTTPException(status_code=503, detail="OpenPhone is not connected. Add the API key and number in Settings → Integrations.")
    to = normalize_phone(to_phone)
    if not to:
        raise HTTPException(status_code=422, detail="The customer's phone number is missing or looks wrong.")
    from_num = normalize_phone(cfg["number"]) or cfg["number"]
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(f"{OPENPHONE_API_URL}/messages",
                                     headers={"Authorization": cfg["api_key"], "Content-Type": "application/json"},
                                     json={"from": from_num, "to": [to], "text": text})
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach OpenPhone. Try again.")
    if resp.status_code not in (200, 201, 202):
        try:
            body = resp.json()
            msg = body.get("message") or body.get("title") or resp.text[:200]
        except ValueError:
            msg = resp.text[:200]
        logger.error("OpenPhone send failed %s: %s", resp.status_code, msg)
        raise HTTPException(status_code=502, detail=f"OpenPhone couldn't send the text: {msg}")


def square_base_url() -> str:
    env = os.environ.get("SQUARE_ENVIRONMENT", "sandbox").strip().lower()
    return "https://connect.squareup.com" if env == "production" else "https://connect.squareupsandbox.com"


async def square_request(method: str, path: str, json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    creds = await square_creds()
    if not (creds["token"] and creds["location_id"]):
        raise HTTPException(status_code=503, detail={
            "error": "square_missing",
            "message": "Square is not connected. Add the access token in Settings → Integrations."})
    headers = {
        "Authorization": f"Bearer {creds['token']}",
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


class InvoiceLineItem(BaseModel):
    name: str
    amount: float


class SquareInvoicePayload(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    amount: float
    description: str = "Moving services"
    lead_id: Optional[str] = None
    purpose: Optional[str] = None
    quote_total: Optional[float] = None
    line_items: Optional[List[InvoiceLineItem]] = None


@api_router.get("/square/status")
async def square_status(role: str = Depends(require_auth)):
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can see this.")
    return {"configured": await square_is_configured(), "environment": os.environ.get("SQUARE_ENVIRONMENT", "sandbox").strip().lower()}


@api_router.post("/square/invoice")
async def send_square_invoice(payload: SquareInvoicePayload, role: str = Depends(require_auth)):
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can send invoices.")
    if payload.amount <= 0:
        raise HTTPException(status_code=422, detail="The invoice amount must be more than $0.")
    if "@" not in payload.email:
        raise HTTPException(status_code=422, detail="This lead needs a valid email before you can send an invoice.")
    location_id = (await square_creds())["location_id"]

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

    items = [i for i in (payload.line_items or []) if i.name.strip() and i.amount > 0]
    if items and abs(sum(i.amount for i in items) - payload.amount) < 0.01:
        cents = [int(round(i.amount * 100)) for i in items]
        cents[-1] += int(round(payload.amount * 100)) - sum(cents)
        order_lines = [{"name": i.name.strip()[:255], "quantity": "1",
                        "base_price_money": {"amount": c, "currency": "USD"}}
                       for i, c in zip(items, cents) if c > 0]
    else:
        order_lines = [{"name": payload.description.strip()[:255] or "Moving services", "quantity": "1",
                        "base_price_money": {"amount": int(round(payload.amount * 100)), "currency": "USD"}}]

    order_body = {
        "idempotency_key": str(uuid4()),
        "order": {
            "location_id": location_id,
            "customer_id": customer_id,
            "line_items": order_lines,
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
        "purpose": payload.purpose,
        "quote_total": payload.quote_total,
        "customer": {"name": payload.name.strip(), "email": payload.email.strip(), "phone": payload.phone or ""},
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


# ------- Jobs engine (deposit-paid Square invoices become Jobs)

LEAD_F = {
    "name": "fldsBIJdaasQ9fh9a", "phone": "fldQMF5LKSd0yI8Bs", "email": "fldi6lWGr530XQ4YE",
    "move_date": "fldWUAHyvTippkVGd", "from": "fldHysDcz9GAos0zD", "to": "fldIKwCb5ZqAP1fEh",
    "quote": "fldI5HufBfW35A1fD",
}

TRACKING_SMS_TEMPLATE = ("Haul Yeah Moving: Your crew is on the way! Track them here: {link}. "
                         "If the link isn't working, reply to this message and we'll send you a new one. "
                         "— Weekend moves, flat price, no surprises.")


def _et_today() -> str:
    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def _request_base(request: Request) -> str:
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    return f"https://{host}"


def _job_out(job: Dict[str, Any]) -> Dict[str, Any]:
    return {**{k: v for k, v in job.items() if k != "_id"}, "id": job["_id"]}


async def fetch_lead_details(lead_id: Optional[str]) -> Dict[str, Any]:
    if not lead_id:
        return {}
    try:
        data = await airtable_request("GET", TABLES["leads"], path=f"/{lead_id}", params={"returnFieldsByFieldId": "true"})
        f = data.get("fields", {})
        return {k: f.get(fid) for k, fid in LEAD_F.items()}
    except HTTPException:
        return {}


def _infer_purpose(inv: Dict[str, Any]) -> str:
    if inv.get("purpose"):
        return inv["purpose"]
    qt = inv.get("quote_total")
    amt = inv.get("amount") or 0
    if qt and amt > qt * 0.5:
        return "balance"
    return "deposit"


async def ensure_job_for_deposit(inv: Dict[str, Any], mark_full: bool = False, notify_owner: bool = True) -> None:
    paid_at = inv.get("paid_at") or now_iso()
    existing = await mongo_db.jobs.find_one({"deposit_invoice_id": inv["invoice_id"]})
    if existing:
        updates: Dict[str, Any] = {}
        if (existing.get("deposit_paid") or {}).get("status") != "paid":
            updates["deposit_paid"] = {"status": "paid", "amount": inv.get("amount"), "paid_at": paid_at}
        if mark_full and (existing.get("paid_in_full") or {}).get("status") != "paid":
            updates["paid_in_full"] = {"status": "paid", "amount": inv.get("amount"), "paid_at": paid_at,
                                       "invoice_number": inv.get("invoice_number")}
        if updates:
            await mongo_db.jobs.update_one({"_id": existing["_id"]}, {"$set": updates})
        return
    lead = await fetch_lead_details(inv.get("lead_id"))
    integrations = await get_integrations()
    customer = inv.get("customer") or {}
    job = {
        "_id": str(uuid4()),
        "invoice_number": inv.get("invoice_number") or "—",
        "deposit_invoice_id": inv["invoice_id"],
        "lead_id": inv.get("lead_id"),
        "customer": {
            "name": customer.get("name") or lead.get("name") or "",
            "phone": customer.get("phone") or lead.get("phone") or "",
            "email": customer.get("email") or lead.get("email") or "",
        },
        "quote_total": inv.get("quote_total") or lead.get("quote"),
        "deposit_amount": inv.get("amount"),
        "pickup_address": lead.get("from") or "",
        "dropoff_address": lead.get("to") or "",
        "job_date": (lead.get("move_date") or "")[:10] or None,
        "start_time": "",
        "truck_id": None, "truck_name": "",
        "truck_pickup_location": (integrations.get("default_truck_pickup") or "").strip() or DEFAULT_TRUCK_PICKUP,
        "crew": [],
        "deposit_paid": {"status": "paid", "amount": inv.get("amount"), "paid_at": paid_at},
        "paid_in_full": ({"status": "paid", "amount": inv.get("amount"), "paid_at": paid_at,
                          "invoice_number": inv.get("invoice_number")} if mark_full
                         else {"status": "unpaid", "amount": None, "paid_at": None}),
        "tracking": {"token": uuid4().hex, "sms_sent": False, "sms_sent_at": None},
        "created_at": now_iso(), "assigned_at": None,
    }
    await mongo_db.jobs.insert_one(job)
    if notify_owner:
        who = job["customer"]["name"] or "the customer"
        await notify(None, "owner", "New job — deposit paid",
                     f"Job #{job['invoice_number']} is live: {who} paid the deposit. Open Jobs to assign a crew.",
                     "success", {"job_id": job["_id"]})


async def apply_invoice_to_jobs(inv: Dict[str, Any], notify_owner: bool = True) -> None:
    status = inv.get("status")
    purpose = _infer_purpose(inv)
    if status == "PAID":
        if purpose in ("deposit", "full"):
            await ensure_job_for_deposit(inv, mark_full=(purpose == "full"), notify_owner=notify_owner)
            return
        job = await mongo_db.jobs.find_one({"lead_id": inv["lead_id"]}) if inv.get("lead_id") else None
        if job and (job.get("paid_in_full") or {}).get("status") != "paid":
            await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {"paid_in_full": {
                "status": "paid", "amount": inv.get("amount"), "paid_at": inv.get("paid_at") or now_iso(),
                "invoice_number": inv.get("invoice_number")}}})
            if notify_owner:
                await notify(None, "owner", "Paid in full",
                             f"Job #{job['invoice_number']} is fully paid (${(inv.get('amount') or 0):,.2f}).",
                             "success", {"job_id": job["_id"]})
    elif status == "PAYMENT_PENDING" and purpose != "deposit":
        job = await mongo_db.jobs.find_one({"lead_id": inv["lead_id"]}) if inv.get("lead_id") else None
        if job and (job.get("paid_in_full") or {}).get("status") == "unpaid":
            await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {"paid_in_full": {
                "status": "pending", "amount": inv.get("amount"), "paid_at": None,
                "invoice_number": inv.get("invoice_number")}}})


async def refresh_invoice_doc(d: Dict[str, Any], now: float) -> None:
    if d.get("status") in SQUARE_TERMINAL_STATUSES or now - d.get("checked_at", 0) < 60:
        return
    try:
        data = await square_request("GET", f"/v2/invoices/{d['invoice_id']}")
    except HTTPException as exc:
        if exc.status_code == 404:
            await mongo_db.square_invoices.update_one({"invoice_id": d["invoice_id"]}, {"$set": {"checked_at": now}})
        return
    new_status = data.get("invoice", {}).get("status", d.get("status"))
    updates: Dict[str, Any] = {"status": new_status, "checked_at": now}
    if new_status == "PAID" and d.get("status") != "PAID":
        updates["paid_at"] = now_iso()
    if new_status == "PAID" and d.get("lead_id") and not d.get("deposit_synced"):
        if await mark_lead_deposit_paid(d["lead_id"]):
            updates["deposit_synced"] = True
    d.update(updates)
    await mongo_db.square_invoices.update_one({"invoice_id": d["invoice_id"]}, {"$set": updates})
    if new_status in ("PAID", "PAYMENT_PENDING"):
        try:
            await apply_invoice_to_jobs(d)
        except Exception as exc:
            logger.error("Job activation failed for %s: %s", d.get("invoice_number"), exc)


async def invoice_sync_loop():
    while True:
        await asyncio.sleep(120)
        try:
            if not await square_is_configured():
                continue
            docs = await mongo_db.square_invoices.find(
                {"status": {"$nin": list(SQUARE_TERMINAL_STATUSES)}}, {"_id": 0}).to_list(100)
            now = time.time()
            for d in docs:
                await refresh_invoice_doc(d, now)
        except Exception as exc:
            logger.error("Invoice sync loop error: %s", exc)


async def backfill_jobs_from_paid_invoices():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    docs = await mongo_db.square_invoices.find(
        {"status": "PAID", "created_at": {"$gte": cutoff}}, {"_id": 0}).to_list(200)
    for d in docs:
        try:
            await apply_invoice_to_jobs(d, notify_owner=False)
        except Exception as exc:
            logger.error("Job backfill failed for %s: %s", d.get("invoice_number"), exc)


# ------- Square webhook (public, HMAC-verified) + integrations settings

public_router = APIRouter(prefix="/api")


async def handle_square_event(event: Dict[str, Any]) -> None:
    etype = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}
    if etype.startswith("invoice."):
        invoice = obj.get("invoice") or obj
        inv_id = invoice.get("id")
        if not inv_id:
            return
        new_status = invoice.get("status")
        d = await mongo_db.square_invoices.find_one({"invoice_id": inv_id}, {"_id": 0})
        if d:
            updates: Dict[str, Any] = {"checked_at": time.time()}
            if new_status:
                updates["status"] = new_status
            if new_status == "PAID" and d.get("status") != "PAID":
                updates["paid_at"] = event.get("created_at") or now_iso()
            if new_status == "PAID" and d.get("lead_id") and not d.get("deposit_synced"):
                if await mark_lead_deposit_paid(d["lead_id"]):
                    updates["deposit_synced"] = True
            d.update(updates)
            await mongo_db.square_invoices.update_one({"invoice_id": inv_id}, {"$set": updates})
        else:
            amount_cents = ((invoice.get("payment_requests") or [{}])[0].get("computed_amount_money") or {}).get("amount")
            primary = invoice.get("primary_recipient") or {}
            d = {
                "lead_id": None,
                "invoice_id": inv_id,
                "invoice_number": invoice.get("invoice_number"),
                "amount": round(amount_cents / 100, 2) if amount_cents else 0,
                "status": new_status,
                "public_url": invoice.get("public_url"),
                "purpose": None, "quote_total": None,
                "customer": {
                    "name": " ".join(x for x in [primary.get("given_name"), primary.get("family_name")] if x),
                    "email": primary.get("email_address") or "",
                    "phone": primary.get("phone_number") or "",
                },
                "paid_at": (event.get("created_at") or now_iso()) if new_status == "PAID" else None,
                "created_at": invoice.get("created_at") or now_iso(),
                "checked_at": time.time(),
            }
            await mongo_db.square_invoices.insert_one(dict(d))
            d.pop("_id", None)
        if new_status in ("PAID", "PAYMENT_PENDING"):
            await apply_invoice_to_jobs(d)
    elif etype == "payment.updated":
        docs = await mongo_db.square_invoices.find(
            {"status": {"$nin": list(SQUARE_TERMINAL_STATUSES)}}, {"_id": 0}).to_list(100)
        for d in docs:
            d["checked_at"] = 0
            await refresh_invoice_doc(d, time.time())


@public_router.post("/webhooks/square")
async def square_webhook(request: Request):
    raw = await request.body()
    signature = request.headers.get("x-square-hmacsha256-signature", "")
    doc = await get_integrations()
    key = (doc.get("square_webhook_key") or "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="Square webhook key is not set. Add it in Settings → Integrations.")
    candidates = set()
    stored = (doc.get("square_notification_url") or "").strip()
    if stored:
        candidates.add(stored)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    if host:
        candidates.add(f"https://{host}/api/webhooks/square")

    def _sig(url: str) -> str:
        digest = hmac.new(key.encode("utf-8"), url.encode("utf-8") + raw, hashlib.sha256).digest()
        return base64.b64encode(digest).decode("utf-8")

    if not any(hmac.compare_digest(_sig(u), signature) for u in candidates):
        logger.warning("Square webhook signature rejected (urls tried: %s)", candidates)
        raise HTTPException(status_code=403, detail="Bad signature.")
    try:
        event = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Bad JSON.")
    event_id = event.get("event_id")
    if event_id:
        if await mongo_db.square_events.find_one({"_id": event_id}):
            return {"ok": True, "duplicate": True}
        await mongo_db.square_events.insert_one({"_id": event_id, "type": event.get("type"),
                                                 "created_at": event.get("created_at"), "received_at": now_iso()})
    try:
        await handle_square_event(event)
    except Exception as exc:
        logger.error("Square webhook processing error: %s", exc)
    return {"ok": True}


INTEGRATION_SECRETS = ("square_access_token", "square_webhook_key", "openphone_api_key")
INTEGRATION_PLAIN = ("square_location_id", "square_notification_url", "openphone_number", "default_truck_pickup")


class IntegrationsPayload(BaseModel):
    square_access_token: Optional[str] = None
    square_location_id: Optional[str] = None
    square_webhook_key: Optional[str] = None
    square_notification_url: Optional[str] = None
    openphone_api_key: Optional[str] = None
    openphone_number: Optional[str] = None
    default_truck_pickup: Optional[str] = None


async def _integration_settings_out() -> Dict[str, Any]:
    doc = await get_integrations()
    out: Dict[str, Any] = {k: doc.get(k, "") for k in INTEGRATION_PLAIN}
    if not out["default_truck_pickup"]:
        out["default_truck_pickup"] = DEFAULT_TRUCK_PICKUP
    for k in INTEGRATION_SECRETS:
        out[f"{k}_set"] = bool((doc.get(k) or "").strip())
    out["square_env_token_present"] = bool(os.environ.get("SQUARE_ACCESS_TOKEN", "").strip())
    return out


@api_router.get("/settings/integrations")
async def get_integration_settings(p: Dict[str, Any] = Depends(require_owner)):
    return await _integration_settings_out()


@api_router.put("/settings/integrations")
async def save_integration_settings(payload: IntegrationsPayload, p: Dict[str, Any] = Depends(require_owner)):
    updates = {k: v.strip() for k, v in payload.model_dump().items() if v is not None}
    if updates:
        await mongo_db.settings.update_one({"_id": "integrations"}, {"$set": updates}, upsert=True)
        await audit(p, "updated integrations settings", "settings", {"fields": list(updates.keys())})
    return await _integration_settings_out()


@api_router.get("/square/sync-status")
async def square_sync_status(p: Dict[str, Any] = Depends(require_owner)):
    doc = await get_integrations()
    op = await openphone_config()
    return {
        "square_connected": await square_is_configured(),
        "webhook_connected": bool((doc.get("square_webhook_key") or "").strip()),
        "openphone_connected": bool(op["api_key"] and op["number"]),
        "notification_url": (doc.get("square_notification_url") or "").strip(),
    }


# ------- Owner Jobs board

@api_router.get("/jobs")
async def list_jobs(p: Dict[str, Any] = Depends(require_owner)):
    docs = await mongo_db.jobs.find({}).to_list(500)
    docs.sort(key=lambda j: (j.get("job_date") or "9999-12-31", j.get("start_time") or ""))
    return {"jobs": [_job_out(j) for j in docs]}


class JobCrewSlot(BaseModel):
    user_id: str
    position: str = "Helper"


class JobPatchPayload(BaseModel):
    crew: Optional[List[JobCrewSlot]] = None
    truck_id: Optional[str] = None
    pickup_address: Optional[str] = None
    dropoff_address: Optional[str] = None
    job_date: Optional[str] = None
    start_time: Optional[str] = None
    truck_pickup_location: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None


@api_router.patch("/jobs/{job_id}")
async def patch_job(job_id: str, payload: JobPatchPayload, p: Dict[str, Any] = Depends(require_owner)):
    job = await mongo_db.jobs.find_one({"_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    updates: Dict[str, Any] = {}
    new_crew_ids: List[str] = []
    if payload.crew is not None:
        crew_list = []
        for slot in payload.crew:
            u = await mongo_db.users.find_one({"_id": slot.user_id})
            if not u:
                continue
            crew_list.append({"user_id": slot.user_id, "name": u.get("name", ""),
                              "position": (slot.position or "Helper").strip() or "Helper"})
        updates["crew"] = crew_list
        old_ids = {c["user_id"] for c in job.get("crew", [])}
        new_crew_ids = [c["user_id"] for c in crew_list if c["user_id"] not in old_ids]
    if payload.truck_id is not None:
        if payload.truck_id:
            truck = await mongo_db.trucks.find_one({"_id": payload.truck_id})
            updates["truck_id"] = payload.truck_id
            updates["truck_name"] = truck.get("name", "") if truck else ""
        else:
            updates["truck_id"] = None
            updates["truck_name"] = ""
    for field in ("pickup_address", "dropoff_address", "job_date", "start_time", "truck_pickup_location"):
        val = getattr(payload, field)
        if val is not None:
            updates[field] = val.strip()
    if payload.customer_phone is not None or payload.customer_email is not None:
        cust = dict(job.get("customer") or {})
        if payload.customer_phone is not None:
            cust["phone"] = payload.customer_phone.strip()
        if payload.customer_email is not None:
            cust["email"] = payload.customer_email.strip()
        updates["customer"] = cust
    if updates:
        updates["assigned_at"] = now_iso()
        await mongo_db.jobs.update_one({"_id": job_id}, {"$set": updates})
        job.update(updates)
        when = job.get("job_date") or "date TBD"
        if job.get("start_time"):
            when += f" at {job['start_time']}"
        for c in job.get("crew", []):
            if c["user_id"] in new_crew_ids:
                await notify(c["user_id"], None, "You're on a job",
                             f"Job #{job['invoice_number']} — {when}. Your role: {c['position']}. Open Today for details.",
                             "info", {"job_id": job_id})
        await audit(p, "updated job assignment", f"job {job.get('invoice_number')}", {"fields": list(updates.keys())})
    return _job_out(job)


# ------- Crew: active job, tracking link, review requests

@api_router.get("/crew/active-job")
async def crew_active_job(p: Dict[str, Any] = Depends(require_crew)):
    today = _et_today()
    docs = await mongo_db.jobs.find({"crew.user_id": p["user_id"], "job_date": {"$gte": today}}).to_list(20)
    docs.sort(key=lambda j: (j.get("job_date") or "9999", j.get("start_time") or ""))
    if not docs:
        return {"job": None, "upcoming_count": 0}
    job = docs[0]
    mine = next((c for c in job.get("crew", []) if c["user_id"] == p["user_id"]), {})
    teammates = []
    for c in job.get("crew", []):
        u = await mongo_db.users.find_one({"_id": c["user_id"]}) or {}
        teammates.append({"user_id": c["user_id"], "name": c.get("name") or u.get("name", ""),
                          "position": c.get("position", "Helper"),
                          "phone": ((u.get("profile") or {}).get("phone") or "").strip(),
                          "me": c["user_id"] == p["user_id"]})
    business = await mongo_db.settings.find_one({"_id": "business"}) or {}
    return {"job": {
        "job_id": job["_id"], "invoice_number": job.get("invoice_number"),
        "job_date": job.get("job_date"), "start_time": job.get("start_time"),
        "my_position": mine.get("position", "Helper"),
        "truck_name": job.get("truck_name"), "truck_pickup_location": job.get("truck_pickup_location"),
        "pickup_address": job.get("pickup_address"), "dropoff_address": job.get("dropoff_address"),
        "customer": job.get("customer") or {},
        "crew": teammates,
        "tracking_sms_sent": (job.get("tracking") or {}).get("sms_sent", False),
        "review_link": business.get("reviewLink", ""),
        "is_today": job.get("job_date") == today,
    }, "upcoming_count": len(docs) - 1}


async def _send_tracking_sms(job: Dict[str, Any], base_url: str) -> None:
    token = uuid4().hex
    link = f"{base_url}/track/{token}"
    await openphone_send_sms((job.get("customer") or {}).get("phone"), TRACKING_SMS_TEMPLATE.format(link=link))
    await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {
        "tracking": {"token": token, "sms_sent": True, "sms_sent_at": now_iso()}}})


async def maybe_send_tracking_sms(p: Dict[str, Any], request: Request) -> None:
    job = await mongo_db.jobs.find_one({"crew.user_id": p["user_id"], "job_date": _et_today()})
    if not job or (job.get("tracking") or {}).get("sms_sent"):
        return
    try:
        await _send_tracking_sms(job, _request_base(request))
        await notify(None, "owner", "Tracking link sent",
                     f"The customer for Job #{job['invoice_number']} got the tracking text.", "info")
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Could not send the tracking text."
        await notify(None, "owner", "Tracking text NOT sent", f"Job #{job['invoice_number']}: {detail}", "warning")


@api_router.post("/crew/jobs/{job_id}/tracking-link")
async def send_new_tracking_link(job_id: str, request: Request, p: Dict[str, Any] = Depends(require_crew)):
    job = await mongo_db.jobs.find_one({"_id": job_id, "crew.user_id": p["user_id"]})
    if not job:
        raise HTTPException(status_code=404, detail="That job isn't yours.")
    await _send_tracking_sms(job, _request_base(request))
    await audit(p, "sent new tracking link", f"job {job.get('invoice_number')}")
    return {"ok": True, "message": "New tracking link sent to the customer."}


@public_router.get("/track/{token}")
async def track_job(token: str):
    job = await mongo_db.jobs.find_one({"tracking.token": token})
    if not job:
        raise HTTPException(status_code=404, detail="This tracking link is no longer active. Reply to our text and we'll send a new one.")
    crew_ids = [c["user_id"] for c in job.get("crew", [])]
    live = False
    position = None
    minutes_ago = None
    if crew_ids:
        open_entries = await mongo_db.time_entries.find({"user_id": {"$in": crew_ids}, "clock_out": None}).to_list(20)
        live = bool(open_entries)
        pings = await mongo_db.gps_pings.find({"user_id": {"$in": crew_ids}}).sort("at", -1).limit(1).to_list(1)
        if pings:
            try:
                at = datetime.fromisoformat(pings[0]["at"])
                minutes_ago = max(0, int((datetime.now(timezone.utc) - at).total_seconds() // 60))
            except ValueError:
                minutes_ago = None
            if live and minutes_ago is not None and minutes_ago <= 10:
                position = {"lat": pings[0]["lat"], "lng": pings[0]["lng"]}
    return {"invoice_number": job.get("invoice_number"), "job_date": job.get("job_date"),
            "start_time": job.get("start_time"), "live": live, "position": position,
            "updated_minutes_ago": minutes_ago}


class ReviewRequestPayload(BaseModel):
    channel: str
    message: str = ""


@api_router.post("/crew/jobs/{job_id}/review-request")
async def crew_review_request(job_id: str, payload: ReviewRequestPayload, p: Dict[str, Any] = Depends(require_crew)):
    job = await mongo_db.jobs.find_one({"_id": job_id, "crew.user_id": p["user_id"]})
    if not job:
        raise HTTPException(status_code=404, detail="That job isn't yours.")
    channel = payload.channel.lower()
    if channel not in ("sms", "email"):
        raise HTTPException(status_code=422, detail="Channel must be sms or email.")
    if channel == "sms":
        if not payload.message.strip():
            raise HTTPException(status_code=422, detail="Write the message first.")
        await openphone_send_sms((job.get("customer") or {}).get("phone"), payload.message.strip())
    await mongo_db.review_requests.insert_one({
        "_id": str(uuid4()), "job_id": job_id, "invoice_number": job.get("invoice_number"),
        "crew_user_id": p["user_id"], "crew_name": p["name"], "channel": channel,
        "sent_at": now_iso(), "customer": job.get("customer") or {},
    })
    return {"ok": True}


async def require_marketing(request: Request) -> Dict[str, Any]:
    p = await current_principal(request)
    if p["role"] not in ("owner", "marketing"):
        raise HTTPException(status_code=403, detail="Only the owner or marketing can open this.")
    return p


@api_router.get("/review-requests")
async def list_review_requests(p: Dict[str, Any] = Depends(require_marketing)):
    docs = await mongo_db.review_requests.find({}).sort("sent_at", -1).to_list(500)
    return {"requests": [{**{k: v for k, v in d.items() if k != "_id"}, "id": d["_id"]} for d in docs]}


class ReviewStatusPayload(BaseModel):
    review_received: Optional[bool] = None
    stars: Optional[int] = None


@api_router.patch("/review-requests/{request_id}")
async def patch_review_request(request_id: str, payload: ReviewStatusPayload, p: Dict[str, Any] = Depends(require_marketing)):
    doc = await mongo_db.review_requests.find_one({"_id": request_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Review request not found.")
    review = dict(doc.get("review") or {})
    if payload.review_received is not None:
        review["received"] = payload.review_received
        if not payload.review_received:
            review["stars"] = None
    if payload.stars is not None:
        if payload.stars < 1 or payload.stars > 5:
            raise HTTPException(status_code=422, detail="Stars must be 1 to 5.")
        review["stars"] = payload.stars
        review["received"] = True
    review["updated_at"] = now_iso()
    review["updated_by"] = p["name"]
    await mongo_db.review_requests.update_one({"_id": request_id}, {"$set": {"review": review}})
    return {**{k: v for k, v in doc.items() if k != "_id"}, "id": doc["_id"], "review": review}


# ------- Stored quote breakdowns (for itemized Square invoices)

class QuoteBreakdownPayload(BaseModel):
    breakdown: Dict[str, Any]


@api_router.put("/quotes/{lead_id}")
async def save_quote_breakdown(lead_id: str, payload: QuoteBreakdownPayload, request: Request, role: str = Depends(require_auth)):
    if role not in ("owner", "sales"):
        raise HTTPException(status_code=403, detail="Your role can't save quotes.")
    doc = await mongo_db.lead_quotes.find_one({"_id": lead_id}) or {}
    token = doc.get("token") or uuid4().hex
    await mongo_db.lead_quotes.update_one(
        {"_id": lead_id}, {"$set": {"breakdown": payload.breakdown, "updated_at": now_iso(), "token": token}}, upsert=True)
    sms_sent = False
    sms_note = ""
    phone = str(payload.breakdown.get("customerPhone") or "").strip()
    final = payload.breakdown.get("finalQuote")
    cfg = await openphone_config()
    if not (cfg["api_key"] and cfg["number"]):
        sms_note = "Auto-text skipped: OpenPhone isn't connected. Use the Quote PDF button to text it yourself."
    elif not phone:
        sms_note = "Auto-text skipped: this lead has no phone number."
    elif (doc.get("pdf_sms") or {}).get("amount") == final:
        sms_note = "Customer already got this exact quote by text."
    else:
        first = str(payload.breakdown.get("customerName") or "").split(" ")[0] or "there"
        link = f"{_request_base(request)}/api/quote-pdf/{token}"
        try:
            await openphone_send_sms(
                phone,
                f"Hi {first}, here's your Haul Yeah Moving quote — one flat price, no surprises: {link} Reply here with any questions!")
            sms_sent = True
            await mongo_db.lead_quotes.update_one({"_id": lead_id}, {"$set": {"pdf_sms": {"sent_at": now_iso(), "amount": final}}})
        except HTTPException as exc:
            sms_note = exc.detail if isinstance(exc.detail, str) else "Auto-text failed."
    return {"ok": True, "token": token, "sms_sent": sms_sent, "sms_note": sms_note}


@api_router.get("/quotes/{lead_id}")
async def get_quote_breakdown(lead_id: str, role: str = Depends(require_auth)):
    if role not in ("owner", "sales"):
        raise HTTPException(status_code=403, detail="Your role can't see quotes.")
    doc = await mongo_db.lead_quotes.find_one({"_id": lead_id}) or {}
    return {"breakdown": doc.get("breakdown"), "updated_at": doc.get("updated_at"), "token": doc.get("token")}


def _pdf_move_date(v: Any) -> str:
    try:
        return datetime.fromisoformat(str(v)[:10]).strftime("%A, %B %-d, %Y")
    except ValueError:
        return str(v)


def build_quote_pdf(b: Dict[str, Any]) -> bytes:
    navy = HexColor("#1B2A4A")
    orange = HexColor("#E8743B")
    slate = HexColor("#64748B")
    light = HexColor("#F2F4F8")
    white = HexColor("#FFFFFF")
    money = lambda v: f"${v:,.2f}"

    final = round(float(b.get("finalQuote") or 0), 2)
    lines = [dict(l) for l in (b.get("lines") or []) if float(l.get("amount") or 0) > 0]
    if lines:
        drift = round(final - sum(round(float(l["amount"]), 2) for l in lines), 2)
        if abs(drift) >= 0.01:
            lines[-1]["amount"] = round(float(lines[-1]["amount"]) + drift, 2)
    else:
        lines = [{"name": "Local Moving Service — flat rate", "amount": final}]
    deposit = round(float(b.get("deposit") or final * 0.25), 2)
    balance = round(final - deposit, 2)
    dep_pct = round(deposit / final * 100) if final else 25

    buf = io.BytesIO()
    c = PDFCanvas(buf, pagesize=PDF_LETTER)
    W, H = PDF_LETTER

    c.setFillColor(navy)
    c.rect(0, H - 130, W, 130, stroke=0, fill=1)
    try:
        c.drawImage(ImageReader("/app/frontend/public/logo.png"), 40, H - 116, width=160, height=100,
                    preserveAspectRatio=True, anchor="w", mask="auto")
    except Exception:
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(40, H - 75, "HAUL YEAH MOVING")
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 25)
    c.drawRightString(W - 40, H - 68, "MOVING QUOTE")
    c.setFillColor(orange)
    c.setFont("Helvetica-Oblique", 11)
    c.drawRightString(W - 40, H - 88, "Weekend moves, flat price, no surprises.")

    y = H - 168
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(40, y, f"Prepared for {b.get('customerName') or 'you'}")
    c.setFillColor(slate)
    c.setFont("Helvetica", 10)
    y -= 17
    c.drawString(40, y, f"Quote date: {datetime.now(ZoneInfo('America/New_York')).strftime('%B %-d, %Y')}")
    for label, key in (("Move date", "moveDate"), ("From", "fromAddress"), ("To", "toAddress")):
        val = (str(b.get(key) or "")).strip()
        if val:
            y -= 14
            c.drawString(40, y, f"{label}: {_pdf_move_date(val) if key == 'moveDate' else val}")

    y -= 34
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(48, y, "WHAT'S INCLUDED")
    c.drawRightString(W - 48, y, "PRICE")
    y -= 8
    c.setStrokeColor(navy)
    c.setLineWidth(1.2)
    c.line(40, y, W - 40, y)
    c.setFont("Helvetica", 11)
    for i, l in enumerate(lines[:12]):
        y -= 27
        if i % 2 == 0:
            c.setFillColor(light)
            c.rect(40, y - 9, W - 80, 27, stroke=0, fill=1)
        c.setFillColor(navy)
        c.drawString(48, y, str(l.get("name") or "")[:72])
        c.drawRightString(W - 48, y, money(round(float(l["amount"]), 2)))

    y -= 48
    c.setFillColor(navy)
    c.rect(40, y - 12, W - 80, 40, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(48, y, "YOUR FLAT TOTAL")
    c.setFillColor(orange)
    c.setFont("Helvetica-Bold", 17)
    c.drawRightString(W - 48, y, money(final))

    y -= 46
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(48, y, f"Deposit to lock in your date ({dep_pct}%):")
    c.drawRightString(W - 48, y, money(deposit))
    y -= 19
    c.setFont("Helvetica", 11)
    c.drawString(48, y, "Balance due on move day:")
    c.drawRightString(W - 48, y, money(balance))

    c.setFillColor(slate)
    c.setFont("Helvetica", 9)
    c.drawCentredString(W / 2, 62, "One flat price — crew, truck, travel, and care all included. No hourly surprises.")
    c.setFillColor(orange)
    c.setFont("Helvetica-BoldOblique", 10)
    c.drawCentredString(W / 2, 46, "Haul Yeah Moving — Weekend moves, flat price, no surprises.")
    c.showPage()
    c.save()
    return buf.getvalue()


@public_router.get("/quote-pdf/{token}")
async def quote_pdf(token: str):
    doc = await mongo_db.lead_quotes.find_one({"token": token})
    if not doc or not doc.get("breakdown"):
        raise HTTPException(status_code=404, detail="This quote link is no longer active.")
    pdf = build_quote_pdf(doc["breakdown"])
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="haul-yeah-moving-quote.pdf"'})


# ------- Marketing module

MARKETING_SOURCES = ["Meta Ad", "Google Business Profile", "Referral", "Repeat Customer", "Walk-in/Other", "Website — Direct"]
LEAD_STATUS_F = "fldplIOmtbERJFG6X"
LEAD_SOURCE_F = "fldNQ7kAAIcVQbysk"
UTM_FIELD_NAMES = {"utm_source": "UTM Source", "utm_medium": "UTM Medium", "utm_campaign": "UTM Campaign", "ad_name": "Ad Name"}
STAGE_INDEX = {"New": 0, "Contacted": 1, "Quoted": 2, "Booked": 3, "Completed": 4}
DEFAULT_MKT_THRESHOLDS = {"cplGreen": 20.0, "cplRed": 25.0, "bookingGreen": 20.0, "bookingRed": 15.0}
_utm_map_cache: Dict[str, Any] = {"at": 0.0, "map": {}}


async def utm_field_map() -> Dict[str, str]:
    if time.time() - _utm_map_cache["at"] < 600:
        return _utm_map_cache["map"]
    out: Dict[str, str] = {}
    key = get_api_key()
    if key:
        try:
            url = f"{AIRTABLE_API_URL}/meta/bases/{get_base_id()}/tables"
            await limiter.wait()
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers={"Authorization": f"Bearer {key}"})
            if resp.status_code == 200:
                table = next((t for t in resp.json().get("tables", []) if t.get("id") == TABLES["leads"]), None)
                names = {fl["name"].strip().lower(): fl["id"] for fl in (table or {}).get("fields", [])}
                for k, name in UTM_FIELD_NAMES.items():
                    fid = names.get(name.lower())
                    if fid:
                        out[k] = fid
        except httpx.HTTPError:
            pass
    _utm_map_cache.update({"at": time.time(), "map": out})
    return out


def _stage_idx(status: str) -> int:
    return STAGE_INDEX.get(status, 0)


async def _marketing_lead_rows(start: str, end: str) -> Optional[List[Dict[str, Any]]]:
    if not get_api_key():
        return None
    records: List[Dict[str, Any]] = []
    offset = None
    try:
        while True:
            params: Dict[str, Any] = {"pageSize": 100, "returnFieldsByFieldId": "true"}
            if offset:
                params["offset"] = offset
            data = await airtable_request("GET", TABLES["leads"], params=params)
            records.extend(data.get("records", []))
            offset = data.get("offset")
            if not offset or len(records) >= 3000:
                break
    except HTTPException:
        return None
    metas = {m["_id"]: m for m in await mongo_db.lead_meta.find({}).to_list(3000)}
    umap = await utm_field_map()
    rows = []
    for r in records:
        created_day = (r.get("createdTime") or "")[:10]
        if not created_day or not (start <= created_day <= end):
            continue
        fl = r.get("fields", {})
        meta = metas.get(r["id"], {})
        source = str(fl.get(LEAD_SOURCE_F) or meta.get("source") or "").strip() or "Website — Direct"
        rows.append({
            "id": r["id"], "created": r.get("createdTime"), "status": fl.get(LEAD_STATUS_F) or "New",
            "source": source,
            "campaign": str(fl.get(umap.get("utm_campaign", ""), "") or meta.get("utm_campaign") or "").strip(),
            "ad_name": str(fl.get(umap.get("ad_name", ""), "") or meta.get("ad_name") or "").strip(),
            "contacted_at": meta.get("contacted_at"),
        })
    return rows


async def _paid_by_lead() -> Dict[str, float]:
    docs = await mongo_db.square_invoices.find(
        {"status": "PAID", "lead_id": {"$ne": None}}, {"_id": 0, "lead_id": 1, "amount": 1}).to_list(3000)
    out: Dict[str, float] = {}
    for d in docs:
        out[d["lead_id"]] = out.get(d["lead_id"], 0) + (d.get("amount") or 0)
    return out


def _agg_rows(rows: List[Dict[str, Any]], paid: Dict[str, float], keyfn) -> List[Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        k = keyfn(r)
        if not k:
            continue
        g = groups.setdefault(k, {"key": k, "leads": 0, "contacted": 0, "quoted": 0, "booked": 0,
                                  "completed": 0, "revenue": 0.0, "_ss": 0.0, "_sn": 0})
        idx = _stage_idx(r["status"])
        g["leads"] += 1
        if idx >= 1:
            g["contacted"] += 1
        if idx >= 2:
            g["quoted"] += 1
        if idx >= 3:
            g["booked"] += 1
        if idx >= 4:
            g["completed"] += 1
        g["revenue"] += paid.get(r["id"], 0)
        if r.get("contacted_at") and r.get("created"):
            try:
                mins = (datetime.fromisoformat(r["contacted_at"]) -
                        datetime.fromisoformat(r["created"].replace("Z", "+00:00"))).total_seconds() / 60
                if mins >= 0:
                    g["_ss"] += mins
                    g["_sn"] += 1
            except ValueError:
                pass
    out = []
    for g in groups.values():
        g["revenue"] = round(g["revenue"], 2)
        g["avg_speed_minutes"] = round(g["_ss"] / g["_sn"]) if g["_sn"] else None
        g["speed_tracked"] = g.pop("_sn")
        g.pop("_ss")
        out.append(g)
    out.sort(key=lambda x: -x["leads"])
    return out


@api_router.get("/marketing/overview")
async def marketing_overview(start: str, end: str, p: Dict[str, Any] = Depends(require_marketing)):
    rows = await _marketing_lead_rows(start, end)
    available = rows is not None
    rows = rows or []
    paid = await _paid_by_lead()
    sources = _agg_rows(rows, paid, lambda r: r["source"])
    campaigns = _agg_rows(rows, paid, lambda r: r["campaign"] or r["ad_name"])
    total_list = _agg_rows(rows, paid, lambda r: "all")
    totals = total_list[0] if total_list else {"key": "all", "leads": 0, "contacted": 0, "quoted": 0, "booked": 0,
                                              "completed": 0, "revenue": 0, "avg_speed_minutes": None, "speed_tracked": 0}
    daily: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        d = (r["created"] or "")[:10]
        e = daily.setdefault(d, {"date": d, "leads": 0, "booked": 0})
        e["leads"] += 1
        if _stage_idx(r["status"]) >= 3:
            e["booked"] += 1
    funnel = [{"stage": label, "count": totals[k]} for label, k in
              (("Leads", "leads"), ("Contacted", "contacted"), ("Quoted", "quoted"),
               ("Booked", "booked"), ("Completed", "completed"))]
    return {"airtable_available": available, "start": start, "end": end, "totals": totals,
            "funnel": funnel, "sources": sources, "campaigns": campaigns,
            "daily": sorted(daily.values(), key=lambda x: x["date"]),
            "known_campaigns": sorted({c["key"] for c in campaigns})}


class AdSpendPayload(BaseModel):
    platform: str
    campaign: str
    date_start: str
    date_end: str
    amount: float


@api_router.get("/marketing/ad-spend")
async def list_ad_spend(p: Dict[str, Any] = Depends(require_marketing)):
    docs = await mongo_db.ad_spend.find({}).sort("date_start", -1).to_list(500)
    return {"entries": [{**{k: v for k, v in d.items() if k != "_id"}, "id": d["_id"]} for d in docs]}


@api_router.post("/marketing/ad-spend")
async def add_ad_spend(payload: AdSpendPayload, p: Dict[str, Any] = Depends(require_marketing)):
    if payload.amount <= 0:
        raise HTTPException(status_code=422, detail="Spend amount must be more than $0.")
    if not payload.campaign.strip():
        raise HTTPException(status_code=422, detail="Pick or type the campaign name.")
    if not payload.date_start or not payload.date_end or payload.date_end < payload.date_start:
        raise HTTPException(status_code=422, detail="Check the date range.")
    doc = {"_id": str(uuid4()), "platform": payload.platform.strip() or "Other",
           "campaign": payload.campaign.strip(), "date_start": payload.date_start,
           "date_end": payload.date_end, "amount": round(payload.amount, 2),
           "logged_by": p["name"], "created_at": now_iso()}
    await mongo_db.ad_spend.insert_one(doc)
    return {**{k: v for k, v in doc.items() if k != "_id"}, "id": doc["_id"]}


@api_router.delete("/marketing/ad-spend/{spend_id}")
async def delete_ad_spend(spend_id: str, p: Dict[str, Any] = Depends(require_marketing)):
    await mongo_db.ad_spend.delete_one({"_id": spend_id})
    return {"deleted": True}


@api_router.get("/marketing/thresholds")
async def get_marketing_thresholds(p: Dict[str, Any] = Depends(require_marketing)):
    doc = await mongo_db.settings.find_one({"_id": "marketing_thresholds"}) or {}
    return {**DEFAULT_MKT_THRESHOLDS, **{k: v for k, v in doc.items() if k in DEFAULT_MKT_THRESHOLDS}}


class ThresholdsPayload(BaseModel):
    cplGreen: float
    cplRed: float
    bookingGreen: float
    bookingRed: float


@api_router.put("/marketing/thresholds")
async def save_marketing_thresholds(payload: ThresholdsPayload, p: Dict[str, Any] = Depends(require_owner)):
    vals = payload.model_dump()
    if any(v < 0 for v in vals.values()):
        raise HTTPException(status_code=422, detail="Thresholds can't be negative.")
    await mongo_db.settings.update_one({"_id": "marketing_thresholds"}, {"$set": vals}, upsert=True)
    return vals


def _entry_et_date(e: Dict[str, Any]) -> str:
    try:
        return datetime.fromisoformat(e["clock_in"]["at"]).astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except (KeyError, ValueError, TypeError):
        return ""


@api_router.get("/marketing/margin")
async def marketing_margin(start: str, end: str, p: Dict[str, Any] = Depends(require_owner)):
    rows = await _marketing_lead_rows(start, end)
    if rows is None:
        return {"airtable_available": False, "sources": []}
    src_by_lead = {r["id"]: r["source"] for r in rows}
    paid = await _paid_by_lead()
    revenue: Dict[str, float] = {}
    for r in rows:
        revenue[r["source"]] = revenue.get(r["source"], 0) + paid.get(r["id"], 0)
    labor: Dict[str, float] = {}
    if src_by_lead:
        jobs = await mongo_db.jobs.find({"lead_id": {"$in": list(src_by_lead)}}).to_list(500)
        rates = await get_crew_rates()
        for job in jobs:
            crew_ids = [c["user_id"] for c in job.get("crew", [])]
            if not crew_ids or not job.get("job_date"):
                continue
            entries = await mongo_db.time_entries.find({"user_id": {"$in": crew_ids}}).to_list(500)
            cost = sum((e.get("hours") or 0) * position_rate(e.get("position", "Helper"), rates)
                       for e in entries if _entry_et_date(e) == job["job_date"])
            src = src_by_lead.get(job.get("lead_id"))
            if src:
                labor[src] = labor.get(src, 0) + cost
    out = []
    for src in sorted(set(revenue) | set(labor)):
        rev = round(revenue.get(src, 0), 2)
        cost = round(labor.get(src, 0), 2)
        out.append({"source": src, "revenue": rev, "labor_cost": cost, "margin": round(rev - cost, 2),
                    "margin_pct": round((rev - cost) / rev * 100) if rev else None})
    out.sort(key=lambda x: -x["revenue"])
    return {"airtable_available": True, "sources": out}


class LeadMetaPayload(BaseModel):
    source: str
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    ad_name: Optional[str] = None


@api_router.post("/lead-meta/{lead_id}")
async def set_lead_meta(lead_id: str, payload: LeadMetaPayload, role: str = Depends(require_auth)):
    if role not in ("owner", "sales"):
        raise HTTPException(status_code=403, detail="Your role can't set lead sources.")
    if payload.source.strip() not in MARKETING_SOURCES:
        raise HTTPException(status_code=422, detail="Pick a lead source from the list.")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["updated_at"] = now_iso()
    await mongo_db.lead_meta.update_one({"_id": lead_id}, {"$set": updates}, upsert=True)
    return {"ok": True}



@api_router.get("/square/invoices")
async def list_square_invoices(role: str = Depends(require_auth)):
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can see invoices.")
    docs = await mongo_db.square_invoices.find({}, {"_id": 0}).to_list(500)
    now = time.time()
    if await square_is_configured():
        for d in docs:
            await refresh_invoice_doc(d, now)
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
    if table_key == "tasks":
        metas = {m["_id"]: m for m in await mongo_db.task_meta.find({}).to_list(2000)}
        if role == "owner":
            records = [{**r, "audience": (metas.get(r["id"]) or {}).get("audience", [])} for r in records]
        else:
            grp = TASK_GROUP_FOR_ROLE.get(role)
            records = [r for r in records if grp in ((metas.get(r["id"]) or {}).get("audience") or [])]
    elif table_key == "blog" and role != "owner":
        records = [r for r in records if (r.get("fields", {}).get(BLOG_STATUS_F) or "") == "Published"]
    return {"records": [filter_record(r, role, table_key) for r in records]}


@api_router.post("/tables/{table_key}")
async def create_record(table_key: str, payload: RecordPayload = Body(...), role: str = Depends(require_auth)):
    table_id = resolve_table(table_key)
    await check_table_access(role, table_key)
    if table_key in ("tasks", "blog") and role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can add these.")
    body = {"records": [{"fields": clean_write_fields(payload.fields, role, table_key)}], "typecast": True}
    data = await airtable_request("POST", table_id, json_body=body)
    rec = filter_record(data["records"][0], role, table_key)
    if table_key == "tasks":
        rec["audience"] = []
    return rec


@api_router.patch("/tables/{table_key}/{record_id}")
async def update_record(table_key: str, record_id: str, payload: RecordPayload = Body(...), role: str = Depends(require_auth)):
    table_id = resolve_table(table_key)
    await check_table_access(role, table_key)
    if table_key == "blog" and role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can edit blog posts.")
    if table_key == "tasks" and role != "owner":
        if any(k != TASK_STATUS_F for k in payload.fields):
            raise HTTPException(status_code=403, detail="You can only move a task between columns.")
        grp = TASK_GROUP_FOR_ROLE.get(role)
        meta = await mongo_db.task_meta.find_one({"_id": record_id})
        if not meta or grp not in (meta.get("audience") or []):
            raise HTTPException(status_code=403, detail="That task isn't shared with your team.")
    body = {"records": [{"id": record_id, "fields": clean_write_fields(payload.fields, role, table_key)}], "typecast": True}
    data = await airtable_request("PATCH", table_id, json_body=body)
    if table_key == "leads" and payload.fields.get(LEAD_STATUS_F) in ("Contacted", "Quoted", "Booked", "Completed"):
        existing = await mongo_db.lead_meta.find_one({"_id": record_id})
        if not existing or not existing.get("contacted_at"):
            await mongo_db.lead_meta.update_one({"_id": record_id}, {"$set": {"contacted_at": now_iso()}}, upsert=True)
    rec = filter_record(data["records"][0], role, table_key)
    if table_key == "tasks" and role == "owner":
        meta = await mongo_db.task_meta.find_one({"_id": record_id}) or {}
        rec["audience"] = meta.get("audience", [])
    return rec


@api_router.delete("/tables/{table_key}/{record_id}")
async def delete_record(table_key: str, record_id: str, role: str = Depends(require_auth)):
    table_id = resolve_table(table_key)
    await check_table_access(role, table_key)
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can delete records.")
    await airtable_request("DELETE", table_id, path=f"/{record_id}")
    return {"deleted": True, "id": record_id}


class TaskAudiencePayload(BaseModel):
    audience: List[str] = []


@api_router.post("/tasks/{record_id}/audience")
async def set_task_audience(record_id: str, payload: TaskAudiencePayload = Body(...), p: Dict[str, Any] = Depends(require_owner)):
    audience = sorted({g for g in payload.audience if g in TASK_GROUPS})
    await mongo_db.task_meta.update_one({"_id": record_id}, {"$set": {"audience": audience}}, upsert=True)
    return {"id": record_id, "audience": audience}


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
        "pending_jobs": [{"assignment_id": d["_id"], "job_name": d.get("job_name"), "job_date": d.get("job_date"),
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


# ------- Late alerts: warn owners when crew hasn't clocked in by arrival time

LATE_GRACE_MINUTES = 10


def _12h(hhmm: str) -> str:
    try:
        hh, mm = [int(x) for x in hhmm.split(":")[:2]]
        return f"{hh % 12 or 12}:{mm:02d} {'AM' if hh < 12 else 'PM'}"
    except (ValueError, AttributeError):
        return hhmm or ""


async def _late_crew_map() -> Dict[str, Dict[str, Any]]:
    now_et = datetime.now(EASTERN)
    today = now_et.strftime("%Y-%m-%d")
    assignments = await mongo_db.assignments.find(
        {"job_date": today, "arrival_time": {"$nin": [None, ""]}}).to_list(100)
    if not assignments:
        return {}
    day_start_utc = datetime(now_et.year, now_et.month, now_et.day, tzinfo=EASTERN).astimezone(timezone.utc).isoformat()
    late: Dict[str, Dict[str, Any]] = {}
    for a in assignments:
        try:
            hh, mm = [int(x) for x in a["arrival_time"].split(":")[:2]]
        except (ValueError, AttributeError):
            continue
        due = now_et.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if now_et < due + timedelta(minutes=LATE_GRACE_MINUTES):
            continue
        for c in a.get("crew", []):
            uid = c["user_id"]
            if uid in late:
                continue
            entry = await mongo_db.time_entries.find_one({"user_id": uid, "clock_in.at": {"$gte": day_start_utc}})
            if entry:
                continue
            late[uid] = {"assignment_id": a["_id"], "job_name": a.get("job_name"),
                         "arrival_time": a["arrival_time"], "name": c["name"]}
    return late


async def late_alert_loop():
    while True:
        await asyncio.sleep(120)
        try:
            late = await _late_crew_map()
            for uid, info in late.items():
                a = await mongo_db.assignments.find_one({"_id": info["assignment_id"]})
                if not a or uid in a.get("late_alerts", []):
                    continue
                await notify(None, "owner", "Late alert",
                             f"{info['name']} hasn't clocked in for {info['job_name']} — crew was due at {_12h(info['arrival_time'])}.",
                             ntype="late", data={"assignment_id": info["assignment_id"], "user_id": uid})
                await mongo_db.assignments.update_one({"_id": info["assignment_id"]},
                                                      {"$addToSet": {"late_alerts": uid}})
        except Exception as exc:
            logger.warning("Late alert loop error: %s", exc)


class UserProfilePayload(BaseModel):
    legal_name: Optional[str] = None
    phone: Optional[str] = None
    birthday: Optional[str] = None
    ssn: Optional[str] = None
    address: Optional[str] = None
    emergency_name: Optional[str] = None
    emergency_phone: Optional[str] = None
    hire_date: Optional[str] = None
    notes: Optional[str] = None


@api_router.get("/users/{user_id}/profile")
async def get_user_profile(user_id: str, p: Dict[str, Any] = Depends(require_owner)):
    u = await mongo_db.users.find_one({"_id": user_id})
    if not u:
        raise HTTPException(status_code=404, detail="No such user.")
    return {"name": u["name"], "profile": u.get("profile", {})}


@api_router.put("/users/{user_id}/profile")
async def save_user_profile(user_id: str, payload: UserProfilePayload, p: Dict[str, Any] = Depends(require_owner)):
    u = await mongo_db.users.find_one({"_id": user_id})
    if not u:
        raise HTTPException(status_code=404, detail="No such user.")
    profile = {k: (v.strip() if isinstance(v, str) else "") for k, v in payload.model_dump().items()}
    await mongo_db.users.update_one({"_id": user_id}, {"$set": {"profile": profile, "updated_at": now_iso()}})
    await audit(p, "updated employee file", u["name"])
    return {"profile": profile}


@api_router.get("/team/status")
async def team_status(p: Dict[str, Any] = Depends(require_owner)):
    users = await mongo_db.users.find({"role": "crew", "active": True}).to_list(100)
    open_entries = await mongo_db.time_entries.find({"clock_out": None}).to_list(100)
    by_user = {e["user_id"]: e for e in open_entries}
    late = await _late_crew_map()
    crew = []
    for u in users:
        e = by_user.get(u["_id"])
        lt = None if e else late.get(u["_id"])
        crew.append({
            "user_id": u["_id"], "name": u["name"],
            "clocked_in": bool(e),
            "since": e["clock_in"]["at"] if e else None,
            "job_name": (e or {}).get("job_name"),
            "late": bool(lt),
            "late_job": (lt or {}).get("job_name"),
            "due_at": (lt or {}).get("arrival_time"),
        })
    crew.sort(key=lambda c: (not c["clocked_in"], not c["late"], c["name"]))
    return {"crew": crew}


# ------- users management (owner)

class UserCreatePayload(BaseModel):
    name: str
    email: str
    role: str = "crew"
    roles: Optional[List[str]] = None
    password: Optional[str] = None


DEFAULT_STARTING_PASSWORD = "haulyeah123"


class UserPatchPayload(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    roles: Optional[List[str]] = None
    active: Optional[bool] = None
    password: Optional[str] = None


@api_router.get("/users")
async def list_users(p: Dict[str, Any] = Depends(require_owner)):
    docs = await mongo_db.users.find({}).sort("created_at", 1).to_list(200)
    return {"users": [_user_public(u) for u in docs]}


@api_router.post("/users")
async def create_user(payload: UserCreatePayload, p: Dict[str, Any] = Depends(require_owner)):
    roles = [r for r in (payload.roles or [payload.role]) if r]
    if not roles or any(r not in ("crew", "sales", "owner", "marketing") for r in roles):
        raise HTTPException(status_code=422, detail="Roles must be crew, sales, owner, or marketing.")
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="That email doesn't look right.")
    password = payload.password or DEFAULT_STARTING_PASSWORD
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="The password needs at least 8 characters.")
    if await mongo_db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="A user with that email already exists.")
    doc = {"_id": str(uuid4()), "name": payload.name.strip(), "email": email, "role": roles[0], "roles": roles,
           "password_hash": hash_password(password), "active": True, "must_change_password": True,
           "gps_consent_at": None, "created_at": now_iso()}
    await mongo_db.users.insert_one(doc)
    await audit(p, "created user", f"{doc['name']} ({email}, {'+'.join(roles)})")
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
    if payload.roles is not None:
        roles = [r for r in payload.roles if r]
        if not roles or any(r not in ("crew", "sales", "owner", "marketing") for r in roles):
            raise HTTPException(status_code=422, detail="Roles must be crew, sales, owner, or marketing.")
        updates["roles"] = roles
        updates["role"] = roles[0]
        changes.append(f"roles → {'+'.join(roles)}")
    elif payload.role is not None:
        if payload.role not in ("crew", "sales", "owner", "marketing"):
            raise HTTPException(status_code=422, detail="Role must be crew, sales, owner, or marketing.")
        updates["role"] = payload.role
        updates["roles"] = [payload.role]
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


@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str, p: Dict[str, Any] = Depends(require_owner)):
    user = await mongo_db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="No such user.")
    if user.get("active", True):
        raise HTTPException(status_code=422, detail="Deactivate them first, then you can delete the account.")
    await mongo_db.users.delete_one({"_id": user_id})
    await audit(p, "deleted user account", f"{user.get('name', '')} ({user.get('email', '')})")
    return {"deleted": True}


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
async def clock_in(payload: PunchPayload, request: Request, p: Dict[str, Any] = Depends(require_crew)):
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
    try:
        await maybe_send_tracking_sms(p, request)
    except Exception as exc:
        logger.error("Tracking SMS hook failed: %s", exc)
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
    job_today = await mongo_db.jobs.find_one({"crew.user_id": p["user_id"], "job_date": _et_today()})
    return {"entry_id": entry["_id"], "hours": hours, "flags": flags,
            "review_prompt": bool(job_today), "job_id": job_today["_id"] if job_today else None,
            "invoice_number": job_today.get("invoice_number") if job_today else None}


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
    asyncio.create_task(late_alert_loop())
    asyncio.create_task(invoice_sync_loop())
    try:
        await backfill_jobs_from_paid_invoices()
    except Exception as exc:
        logger.error("Job backfill on startup failed: %s", exc)


app.include_router(auth_router)
app.include_router(dl_router)
app.include_router(public_router)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
