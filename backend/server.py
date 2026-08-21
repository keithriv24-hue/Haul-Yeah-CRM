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
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4
from zoneinfo import ZoneInfo

import bcrypt
import meta_capi
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
BLOG_TITLE_F = "fldKzcIH5j4ZMZQrj"
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
    payload: Dict[str, Any] = {}
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
    payload: Dict[str, Any] = {}
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


async def _login_user_account(payload: LoginPayload, email: str, lock_key: str,
                              fail: Callable[[str], None]) -> Dict[str, Any]:
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


def _login_shared_password(payload: LoginPayload, lock_key: str,
                           fail: Callable[[str], None]) -> Dict[str, Any]:
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


@auth_router.post("/login")
async def login(payload: LoginPayload, request: Request) -> Dict[str, Any]:
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
        return await _login_user_account(payload, email, lock_key, fail)
    return _login_shared_password(payload, lock_key, fail)


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


# ------- Scope calculator pricing (owner-only; consumed by the Job Scope Calculator, NOT the Quote Calculator)

DEFAULT_SCOPE_PRICING = {
    "manHourRate": 65.0,
    "cushionPercent": 10.0,
    "tripFeeTruck": 125.0,
    "tripFeeLabor": 75.0,
    "floorTruck": 650.0,
    "floorLabor": 375.0,
    "roundingIncrement": 25.0,
    "depositPercent": 25.0,
    "manHoursPer100CuFt": 2.10,
}


class ScopePricingPayload(BaseModel):
    manHourRate: float
    cushionPercent: float
    tripFeeTruck: float
    tripFeeLabor: float
    floorTruck: float
    floorLabor: float
    roundingIncrement: float
    depositPercent: float
    manHoursPer100CuFt: float


async def get_scope_pricing_values() -> Dict[str, Any]:
    doc = await mongo_db.settings.find_one({"_id": "calculator_rates"}) or {}
    stored = doc.get("scope_pricing") or {}
    if not stored:
        await mongo_db.settings.update_one(
            {"_id": "calculator_rates"},
            {"$set": {"scope_pricing": dict(DEFAULT_SCOPE_PRICING), "scope_pricing_updated_at": {}}},
            upsert=True)
        stored = dict(DEFAULT_SCOPE_PRICING)
    return {**DEFAULT_SCOPE_PRICING, **{k: v for k, v in stored.items() if k in DEFAULT_SCOPE_PRICING}}


@api_router.get("/settings/scope-pricing")
async def get_scope_pricing(p: Dict[str, Any] = Depends(require_owner)):
    values = await get_scope_pricing_values()
    doc = await mongo_db.settings.find_one({"_id": "calculator_rates"}) or {}
    return {**values, "_updatedAt": doc.get("scope_pricing_updated_at", {})}


@api_router.put("/settings/scope-pricing")
async def save_scope_pricing(payload: ScopePricingPayload, p: Dict[str, Any] = Depends(require_owner)):
    values = payload.model_dump()
    if any(v < 0 for v in values.values()):
        raise HTTPException(status_code=422, detail="Scope pricing values can't be negative.")
    if values["roundingIncrement"] < 1:
        raise HTTPException(status_code=422, detail="The rounding increment must be at least $1.")
    doc = await mongo_db.settings.find_one({"_id": "calculator_rates"}) or {}
    current = {**DEFAULT_SCOPE_PRICING, **(doc.get("scope_pricing") or {})}
    stamps = doc.get("scope_pricing_updated_at", {})
    ts = datetime.now(timezone.utc).isoformat()
    for k, v in values.items():
        if v != current.get(k):
            stamps[k] = ts
    await mongo_db.settings.update_one(
        {"_id": "calculator_rates"},
        {"$set": {"scope_pricing": values, "scope_pricing_updated_at": stamps}}, upsert=True)
    return {**values, "_updatedAt": stamps}


# ------- Saved job scopes (lead_scopes collection; owner-only in step 3, tiers come in step 5)

class ScopeSavePayload(BaseModel):
    lead_id: Optional[str] = None
    label: Optional[str] = None
    inputs: Dict[str, Any]
    pricing: Dict[str, Any]
    result: Dict[str, Any]
    survey_complete: bool = False
    refined_from: Optional[str] = None


@api_router.post("/scopes")
async def save_scope(payload: ScopeSavePayload, p: Dict[str, Any] = Depends(require_owner)):
    pricing = {k: float(payload.pricing.get(k, v)) for k, v in DEFAULT_SCOPE_PRICING.items()}
    doc = {
        "_id": str(uuid4()),
        "lead_id": payload.lead_id or None,
        "label": (payload.label or "").strip(),
        "created_by": p.get("name") or "Owner",
        "created_by_id": p.get("user_id"),
        "tier": "owner",
        "inputs": payload.inputs,
        "pricing": pricing,
        "result": payload.result,
        "survey_complete": bool(payload.survey_complete),
        "refined_from": payload.refined_from or None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await mongo_db.lead_scopes.insert_one(doc)
    return doc


@api_router.get("/scopes")
async def list_scopes(lead_id: Optional[str] = None, p: Dict[str, Any] = Depends(require_owner)):
    query = {"lead_id": lead_id} if lead_id else {}
    docs = await mongo_db.lead_scopes.find(query).sort("created_at", -1).to_list(100)
    return {"scopes": docs}


@api_router.get("/scopes/{scope_id}")
async def get_scope(scope_id: str, p: Dict[str, Any] = Depends(require_owner)):
    doc = await mongo_db.lead_scopes.find_one({"_id": scope_id})
    if not doc:
        raise HTTPException(status_code=404, detail="No such saved scope.")
    return doc


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


def _square_customer_body(payload: SquareInvoicePayload) -> Dict[str, Any]:
    name_parts = payload.name.strip().split(None, 1)
    body: Dict[str, Any] = {
        "idempotency_key": str(uuid4()),
        "given_name": name_parts[0] if name_parts else "Customer",
        "email_address": payload.email.strip(),
    }
    if len(name_parts) > 1:
        body["family_name"] = name_parts[1]
    phone = normalize_phone(payload.phone)
    if phone:
        body["phone_number"] = phone
    return body


def _square_order_lines(payload: SquareInvoicePayload) -> List[Dict[str, Any]]:
    items = [i for i in (payload.line_items or []) if i.name.strip() and i.amount > 0]
    if items and abs(sum(i.amount for i in items) - payload.amount) < 0.01:
        cents = [int(round(i.amount * 100)) for i in items]
        cents[-1] += int(round(payload.amount * 100)) - sum(cents)
        return [{"name": i.name.strip()[:255], "quantity": "1",
                 "base_price_money": {"amount": c, "currency": "USD"}}
                for i, c in zip(items, cents) if c > 0]
    return [{"name": payload.description.strip()[:255] or "Moving services", "quantity": "1",
             "base_price_money": {"amount": int(round(payload.amount * 100)), "currency": "USD"}}]


async def _publish_square_invoice(location_id: str, customer_id: str, order_id: str) -> Dict[str, Any]:
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
    return pub["invoice"]


async def _record_square_invoice(payload: SquareInvoicePayload, published: Dict[str, Any]) -> None:
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


@api_router.post("/square/invoice")
async def send_square_invoice(payload: SquareInvoicePayload, role: str = Depends(require_auth)) -> Dict[str, Any]:
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can send invoices.")
    if payload.amount <= 0:
        raise HTTPException(status_code=422, detail="The invoice amount must be more than $0.")
    if "@" not in payload.email:
        raise HTTPException(status_code=422, detail="This lead needs a valid email before you can send an invoice.")
    location_id = (await square_creds())["location_id"]

    cust = await square_request("POST", "/v2/customers", _square_customer_body(payload))
    customer_id = cust["customer"]["id"]
    order_body = {
        "idempotency_key": str(uuid4()),
        "order": {
            "location_id": location_id,
            "customer_id": customer_id,
            "line_items": _square_order_lines(payload),
        },
    }
    order = await square_request("POST", "/v2/orders", order_body)
    published = await _publish_square_invoice(location_id, customer_id, order["order"]["id"])
    await _record_square_invoice(payload, published)
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
    await mark_lead_commission_payment(lead_id, "deposit")
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


LEAD_CAPI_F = {"fbc": "fld8uG29qAHynjk5S", "fbp": "flddnX9dbcQhmELkJ",
               "fbclid": "fldn7zMBVE1gyXNrp", "event_source_url": "fldlN65ocmrgyks5Z"}


async def fetch_lead_record(lead_id: Optional[str]) -> Dict[str, Any]:
    """Raw Airtable lead record with field-ID keys (empty dict when missing/unavailable)."""
    if not lead_id:
        return {}
    try:
        return await airtable_request("GET", TABLES["leads"], path=f"/{lead_id}",
                                      params={"returnFieldsByFieldId": "true"})
    except HTTPException:
        return {}


def lead_dict_from_airtable(record: Dict[str, Any]) -> Dict[str, Any]:
    """Full match-key lead dict for meta_capi fire_* helpers (email/phone/name/zip/fbc/fbp)."""
    f = record.get("fields") or {}
    name = (f.get(LEAD_F["name"]) or "").strip()
    first, _, last = name.partition(" ")
    return {
        "id": record.get("id"),
        "email": f.get(LEAD_F["email"]),
        "phone": f.get(LEAD_F["phone"]),
        "first_name": first or None,
        "last_name": last or None,
        "zip": f.get(LEAD_F["from"]),
        "fbc": f.get(LEAD_CAPI_F["fbc"]),
        "fbp": f.get(LEAD_CAPI_F["fbp"]),
        "fbclid": f.get(LEAD_CAPI_F["fbclid"]),
        "event_source_url": f.get(LEAD_CAPI_F["event_source_url"]),
    }


async def _capi_log(label: str, coro) -> Dict[str, Any]:
    """Await a meta_capi fire_* call and record the outcome for the Settings counters. Never raises."""
    try:
        result = await coro
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    try:
        if not result.get("skipped"):
            await mongo_db.meta_capi_events.insert_one({
                "_id": str(uuid4()), "label": label,
                "status": "sent" if result.get("ok") else "failed",
                "error": None if result.get("ok") else json.dumps(
                    result.get("response") or {"error": result.get("error")})[:300],
                "sent_at": now_iso() if result.get("ok") else None,
                "created_at": now_iso()})
    except Exception as exc:
        logger.warning("Meta CAPI log write failed: %s", exc)
    return result


def _infer_purpose(inv: Dict[str, Any]) -> str:
    if inv.get("purpose"):
        return inv["purpose"]
    qt = inv.get("quote_total")
    amt = inv.get("amount") or 0
    if qt and amt > qt * 0.5:
        return "balance"
    return "deposit"


async def _sync_existing_deposit_job(existing: Dict[str, Any], inv: Dict[str, Any],
                                     mark_full: bool, paid_at: str) -> None:
    updates: Dict[str, Any] = {}
    if (existing.get("deposit_paid") or {}).get("status") != "paid":
        updates["deposit_paid"] = {"status": "paid", "amount": inv.get("amount"), "paid_at": paid_at}
    if mark_full and (existing.get("paid_in_full") or {}).get("status") != "paid":
        updates["paid_in_full"] = {"status": "paid", "amount": inv.get("amount"), "paid_at": paid_at,
                                   "invoice_number": inv.get("invoice_number")}
    if updates:
        await mongo_db.jobs.update_one({"_id": existing["_id"]}, {"$set": updates})


def _job_customer(inv: Dict[str, Any], lead: Dict[str, Any]) -> Dict[str, Any]:
    customer = inv.get("customer") or {}
    return {
        "name": customer.get("name") or lead.get("name") or "",
        "phone": customer.get("phone") or lead.get("phone") or "",
        "email": customer.get("email") or lead.get("email") or "",
    }


def _job_paid_in_full(inv: Dict[str, Any], paid_at: str, mark_full: bool) -> Dict[str, Any]:
    if mark_full:
        return {"status": "paid", "amount": inv.get("amount"), "paid_at": paid_at,
                "invoice_number": inv.get("invoice_number")}
    return {"status": "unpaid", "amount": None, "paid_at": None}


def _job_doc_from_invoice(inv: Dict[str, Any], lead: Dict[str, Any], integrations: Dict[str, Any],
                          paid_at: str, mark_full: bool) -> Dict[str, Any]:
    return {
        "_id": str(uuid4()),
        "invoice_number": inv.get("invoice_number") or "—",
        "deposit_invoice_id": inv["invoice_id"],
        "lead_id": inv.get("lead_id"),
        "customer": _job_customer(inv, lead),
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
        "paid_in_full": _job_paid_in_full(inv, paid_at, mark_full),
        "tracking": {"token": uuid4().hex, "sms_sent": False, "sms_sent_at": None},
        "created_at": now_iso(), "assigned_at": None,
    }


async def ensure_job_for_deposit(inv: Dict[str, Any], mark_full: bool = False, notify_owner: bool = True) -> None:
    paid_at = inv.get("paid_at") or now_iso()
    existing = await mongo_db.jobs.find_one({"deposit_invoice_id": inv["invoice_id"]})
    if existing:
        await _sync_existing_deposit_job(existing, inv, mark_full, paid_at)
        return
    lead = await fetch_lead_details(inv.get("lead_id"))
    integrations = await get_integrations()
    job = _job_doc_from_invoice(inv, lead, integrations, paid_at, mark_full)
    await mongo_db.jobs.insert_one(job)
    if notify_owner:
        who = job["customer"]["name"] or "the customer"
        await notify(None, "owner", "New job — deposit paid",
                     f"Job #{job['invoice_number']} is live: {who} paid the deposit. Open Jobs to assign a crew.",
                     "success", {"job_id": job["_id"]})


async def _alert_payment_landed(inv: Dict[str, Any], purpose: str) -> None:
    try:
        who = (inv.get("customer") or {}).get("name") or f"invoice #{inv.get('invoice_number') or '?'}"
        stage = {"deposit": "Deposit", "full": "Full payment"}.get(purpose, "Payment")
        await create_alert("payment", f"Money landed: {stage} from {who}",
                           f"${(inv.get('amount') or 0):,.2f} paid on invoice #{inv.get('invoice_number') or '—'}.",
                           lead_id=inv.get("lead_id"), lead_name=who, source="square",
                           dedupe_key=f"payment:{inv['invoice_id']}")
    except Exception as exc:
        logger.warning("payment alert failed: %s", exc)


async def _mark_job_paid_in_full(inv: Dict[str, Any], notify_owner: bool) -> None:
    job = await mongo_db.jobs.find_one({"lead_id": inv["lead_id"]}) if inv.get("lead_id") else None
    if not job or (job.get("paid_in_full") or {}).get("status") == "paid":
        return
    await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {"paid_in_full": {
        "status": "paid", "amount": inv.get("amount"), "paid_at": inv.get("paid_at") or now_iso(),
        "invoice_number": inv.get("invoice_number")}}})
    if notify_owner:
        await notify(None, "owner", "Paid in full",
                     f"Job #{job['invoice_number']} is fully paid (${(inv.get('amount') or 0):,.2f}).",
                     "success", {"job_id": job["_id"]})


async def _mark_job_payment_pending(inv: Dict[str, Any]) -> None:
    job = await mongo_db.jobs.find_one({"lead_id": inv["lead_id"]}) if inv.get("lead_id") else None
    if job and (job.get("paid_in_full") or {}).get("status") == "unpaid":
        await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {"paid_in_full": {
            "status": "pending", "amount": inv.get("amount"), "paid_at": None,
            "invoice_number": inv.get("invoice_number")}}})


def _capi_lead_and_quote(inv: Dict[str, Any], rec_full: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], Any]:
    if rec_full:
        return lead_dict_from_airtable(rec_full), (rec_full.get("fields") or {}).get(LEAD_F["quote"])
    cust = inv.get("customer") or {}
    first, _, last = (cust.get("name") or "").strip().partition(" ")
    lead = {"id": inv.get("lead_id") or inv["invoice_id"],
            "email": cust.get("email"), "phone": cust.get("phone"),
            "first_name": first or None, "last_name": last or None}
    return lead, inv.get("quote_total")


async def _maybe_fire_capi_purchase(inv: Dict[str, Any]) -> None:
    if not meta_capi.capi_enabled() or inv.get("capi_purchase_sent"):
        return
    rec_full = await fetch_lead_record(inv.get("lead_id"))
    capi_lead, quote_amt = _capi_lead_and_quote(inv, rec_full)
    value = inv.get("amount") or quote_amt or 0
    await mongo_db.square_invoices.update_one(
        {"invoice_id": inv["invoice_id"]}, {"$set": {"capi_purchase_sent": True}})
    inv["capi_purchase_sent"] = True
    logger.info("CAPI Purchase firing for invoice %s (lead %s, value %s)",
                inv["invoice_id"], inv.get("lead_id"), value)
    asyncio.create_task(_capi_log("purchase", meta_capi.fire_purchase(
        capi_lead, value=float(value), order_id=inv["invoice_id"])))


async def apply_invoice_to_jobs(inv: Dict[str, Any], notify_owner: bool = True) -> None:
    status = inv.get("status")
    purpose = _infer_purpose(inv)
    if status == "PAYMENT_PENDING":
        if purpose != "deposit":
            await _mark_job_payment_pending(inv)
        return
    if status != "PAID":
        return
    await _alert_payment_landed(inv, purpose)
    await _maybe_fire_capi_purchase(inv)
    if inv.get("lead_id") and purpose != "deposit":
        await mark_lead_commission_payment(inv["lead_id"], "fully")
    if purpose in ("deposit", "full"):
        await ensure_job_for_deposit(inv, mark_full=(purpose == "full"), notify_owner=notify_owner)
        return
    await _mark_job_paid_in_full(inv, notify_owner)


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


async def _update_known_invoice_from_webhook(d: Dict[str, Any], invoice: Dict[str, Any],
                                             new_status: Optional[str], event: Dict[str, Any]) -> None:
    updates: Dict[str, Any] = {"checked_at": time.time()}
    if new_status:
        updates["status"] = new_status
    if new_status == "PAID" and d.get("status") != "PAID":
        updates["paid_at"] = event.get("created_at") or now_iso()
    if new_status == "PAID" and d.get("lead_id") and not d.get("deposit_synced"):
        if await mark_lead_deposit_paid(d["lead_id"]):
            updates["deposit_synced"] = True
    d.update(updates)
    await mongo_db.square_invoices.update_one({"invoice_id": invoice.get("id")}, {"$set": updates})


def _invoice_doc_from_webhook(invoice: Dict[str, Any], new_status: Optional[str],
                              event: Dict[str, Any]) -> Dict[str, Any]:
    amount_cents = ((invoice.get("payment_requests") or [{}])[0].get("computed_amount_money") or {}).get("amount")
    primary = invoice.get("primary_recipient") or {}
    return {
        "lead_id": None,
        "invoice_id": invoice.get("id"),
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


async def _handle_invoice_event(invoice: Dict[str, Any], event: Dict[str, Any]) -> None:
    inv_id = invoice.get("id")
    if not inv_id:
        return
    new_status = invoice.get("status")
    d = await mongo_db.square_invoices.find_one({"invoice_id": inv_id}, {"_id": 0})
    if d:
        await _update_known_invoice_from_webhook(d, invoice, new_status, event)
    else:
        d = _invoice_doc_from_webhook(invoice, new_status, event)
        await mongo_db.square_invoices.insert_one(dict(d))
        d.pop("_id", None)
    if new_status in ("PAID", "PAYMENT_PENDING"):
        await apply_invoice_to_jobs(d)


async def handle_square_event(event: Dict[str, Any]) -> None:
    etype = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}
    if etype.startswith("invoice."):
        await _handle_invoice_event(obj.get("invoice") or obj, event)
    elif etype == "payment.updated":
        docs = await mongo_db.square_invoices.find(
            {"status": {"$nin": list(SQUARE_TERMINAL_STATUSES)}}, {"_id": 0}).to_list(100)
        for d in docs:
            d["checked_at"] = 0
            await refresh_invoice_doc(d, time.time())


@public_router.post("/webhooks/square")
async def square_webhook(request: Request) -> Dict[str, Any]:
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
INTEGRATION_PLAIN = ("square_location_id", "square_notification_url", "openphone_number", "default_truck_pickup",
                     "owner_alert_phone")


class IntegrationsPayload(BaseModel):
    square_access_token: Optional[str] = None
    square_location_id: Optional[str] = None
    square_webhook_key: Optional[str] = None
    square_notification_url: Optional[str] = None
    openphone_api_key: Optional[str] = None
    openphone_number: Optional[str] = None
    default_truck_pickup: Optional[str] = None
    owner_alert_phone: Optional[str] = None


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
async def list_jobs(p: Dict[str, Any] = Depends(require_owner)) -> Dict[str, Any]:
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


async def _resolve_job_crew(slots: List[JobCrewSlot]) -> List[Dict[str, Any]]:
    ids = [slot.user_id for slot in slots]
    users = {u["_id"]: u async for u in mongo_db.users.find({"_id": {"$in": ids}})}
    crew_list = []
    for slot in slots:
        u = users.get(slot.user_id)
        if not u:
            continue
        crew_list.append({"user_id": slot.user_id, "name": u.get("name", ""),
                          "position": (slot.position or "Helper").strip() or "Helper"})
    return crew_list


async def _job_updates_from_payload(payload: JobPatchPayload,
                                    job: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    updates: Dict[str, Any] = {}
    new_crew_ids: List[str] = []
    if payload.crew is not None:
        crew_list = await _resolve_job_crew(payload.crew)
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
    return updates, new_crew_ids


async def _notify_new_crew_members(job: Dict[str, Any], job_id: str, new_crew_ids: List[str]) -> None:
    when = job.get("job_date") or "date TBD"
    if job.get("start_time"):
        when += f" at {job['start_time']}"
    for c in job.get("crew", []):
        if c["user_id"] in new_crew_ids:
            await notify(c["user_id"], None, "You're on a job",
                         f"Job #{job['invoice_number']} — {when}. Your role: {c['position']}. Open Today for details.",
                         "info", {"job_id": job_id})


@api_router.patch("/jobs/{job_id}")
async def patch_job(job_id: str, payload: JobPatchPayload,
                    p: Dict[str, Any] = Depends(require_owner)) -> Dict[str, Any]:
    job = await mongo_db.jobs.find_one({"_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    updates, new_crew_ids = await _job_updates_from_payload(payload, job)
    if updates:
        updates["assigned_at"] = now_iso()
        await mongo_db.jobs.update_one({"_id": job_id}, {"$set": updates})
        job.update(updates)
        await _notify_new_crew_members(job, job_id, new_crew_ids)
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
    crew_ids = [c["user_id"] for c in job.get("crew", [])]
    users = {u["_id"]: u async for u in mongo_db.users.find({"_id": {"$in": crew_ids}})}
    for c in job.get("crew", []):
        u = users.get(c["user_id"]) or {}
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
async def track_job(token: str) -> Dict[str, Any]:
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
    status = await _track_status(job, crew_ids)
    money = _track_money(job)
    portal = await _track_portal_bits(job)
    return {"invoice_number": job.get("invoice_number"), "job_date": job.get("job_date"),
            "start_time": job.get("start_time"), "live": live, "position": position,
            "updated_minutes_ago": minutes_ago,
            "customer_name": (job.get("customer") or {}).get("name", ""),
            "status": status,
            "pickup_address": job.get("pickup_address"), "dropoff_address": job.get("dropoff_address"),
            "crew": [{"name": c.get("name", "Crew member"), "position": c.get("position", "Helper")}
                     for c in job.get("crew", [])],
            "truck_name": job.get("truck_name") or "",
            **money, **portal}


# ------- customer portal (phase D — extends the public tracking link)

async def _track_status(job: Dict[str, Any], crew_ids: List[str]) -> str:
    if crew_ids and job.get("job_date"):
        a = await mongo_db.assignments.find_one({"job_date": job["job_date"], "crew.user_id": {"$in": crew_ids}})
        if a and a.get("exec_status") and a["exec_status"] != "Assigned":
            return a["exec_status"]
    return "Crew assigned" if job.get("crew") else "Scheduled"


def _track_money(job: Dict[str, Any]) -> Dict[str, Any]:
    paid_full = (job.get("paid_in_full") or {}).get("status") == "paid"
    quote = job.get("quote_total")
    deposit = (job.get("deposit_paid") or {}).get("amount") or job.get("deposit_amount")
    remaining = None
    if paid_full:
        remaining = 0.0
    elif quote is not None:
        try:
            remaining = max(0.0, round(float(quote) - float(deposit or 0), 2))
        except (TypeError, ValueError):
            remaining = None
    return {"quote_total": quote, "deposit_amount": deposit, "paid_in_full": paid_full,
            "remaining_balance": remaining}


async def _track_portal_bits(job: Dict[str, Any]) -> Dict[str, Any]:
    invoices = []
    if job.get("lead_id"):
        for inv in await mongo_db.square_invoices.find({"lead_id": job["lead_id"]}).to_list(10):
            invoices.append({"invoice_number": inv.get("invoice_number"), "status": inv.get("status"),
                             "amount": inv.get("amount"), "url": inv.get("public_url")})
    uploads = await mongo_db.portal_uploads.find({"job_id": job["_id"]}).sort("created_at", -1).to_list(30)
    business = await mongo_db.settings.find_one({"_id": "business"}) or {}
    creds = await square_creds()
    return {"invoices": invoices,
            "details": {k: v for k, v in (job.get("portal_details") or {}).items() if k != "updated_at"},
            "uploads": [{"id": u["_id"], "kind": u.get("kind"), "filename": u.get("filename"),
                         "content_type": u.get("content_type")} for u in uploads],
            "review_link": business.get("reviewLink", ""),
            "review_submitted": bool(job.get("portal_review")),
            "tips_enabled": bool(creds["token"] and creds["location_id"])}



async def _job_by_token(token: str) -> Dict[str, Any]:
    job = await mongo_db.jobs.find_one({"tracking.token": token})
    if not job:
        raise HTTPException(status_code=404,
                            detail="This link is no longer active. Reply to our text and we'll send a new one.")
    return job


async def _owner_portal_ping(job: Dict[str, Any], title: str, body: str):
    await notify(None, "owner", title, body, "portal", {"job_id": job["_id"]})
    try:
        integ = await get_integrations()
        phone = (integ.get("owner_alert_phone") or "").strip()
        if phone:
            await openphone_send_sms(phone, f"{title} — {body}")
    except Exception as exc:
        logger.warning("owner portal sms failed: %s", exc)


class PortalDetailsPayload(BaseModel):
    gate_code: str = ""
    elevator: str = ""
    parking: str = ""
    special_requests: str = ""
    inventory_notes: str = ""


@public_router.post("/track/{token}/details")
async def portal_save_details(token: str, payload: PortalDetailsPayload) -> Dict[str, Any]:
    job = await _job_by_token(token)
    fields = ("gate_code", "elevator", "parking", "special_requests", "inventory_notes")
    details = {k: (getattr(payload, k) or "").strip()[:600] for k in fields}
    details["updated_at"] = now_iso()
    await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {"portal_details": details}})
    filled = [k.replace("_", " ") for k in fields if details[k]]
    who = (job.get("customer") or {}).get("name") or "The customer"
    await _owner_portal_ping(job, "Customer added move details",
                             f"{who} (Job #{job.get('invoice_number')}) filled in: "
                             + (", ".join(filled) if filled else "their move details") + ".")
    return {"ok": True}


async def _validate_portal_upload(job: Dict[str, Any], kind: str, content_type: str) -> None:
    if kind not in ("photo", "inventory"):
        raise HTTPException(status_code=422, detail="Upload kind must be photo or inventory.")
    if not (content_type.startswith("image/") or content_type == "application/pdf"):
        raise HTTPException(status_code=422, detail="Photos or PDF files only, please.")
    if await mongo_db.portal_uploads.count_documents({"job_id": job["_id"]}) >= 30:
        raise HTTPException(status_code=422, detail="Upload limit reached for this move — text us instead!")


async def _store_portal_upload(job: Dict[str, Any], kind: str, filename: str,
                               content_type: str, data: bytes) -> Dict[str, Any]:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    path = f"haulyeah-crm/portal/{job['_id']}/{uuid4()}.{ext}"
    key = await get_storage_key()
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.put(f"{STORAGE_URL}/objects/{path}",
                             headers={"X-Storage-Key": key, "Content-Type": content_type}, content=data)
    if r.status_code >= 300:
        raise HTTPException(status_code=502, detail="The upload didn't stick. Try again.")
    doc = {"_id": str(uuid4()), "job_id": job["_id"], "kind": kind,
           "filename": filename[:120], "storage_path": r.json()["path"],
           "content_type": content_type, "created_at": now_iso()}
    await mongo_db.portal_uploads.insert_one(doc)
    return doc


async def _notify_portal_upload(job: Dict[str, Any], kind: str) -> None:
    last = job.get("portal_upload_notice_at") or ""
    try:
        if last and (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() < 900:
            return
    except ValueError:
        pass
    await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {"portal_upload_notice_at": now_iso()}})
    who = (job.get("customer") or {}).get("name") or "The customer"
    await _owner_portal_ping(job, "Customer uploaded files",
                             f"{who} (Job #{job.get('invoice_number')}) added "
                             + ("an inventory file" if kind == "inventory" else "photos")
                             + " to their move. Check the Jobs board.")


@public_router.post("/track/{token}/uploads")
async def portal_upload(token: str, kind: str = "photo", file: UploadFile = File(...)) -> Dict[str, Any]:
    job = await _job_by_token(token)
    ct = file.content_type or ""
    await _validate_portal_upload(job, kind, ct)
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="That file is too big (15 MB max).")
    doc = await _store_portal_upload(job, kind, file.filename or "upload", ct, data)
    await _notify_portal_upload(job, kind)
    return {"id": doc["_id"]}


@public_router.get("/track/{token}/uploads/{upload_id}")
async def portal_upload_view(token: str, upload_id: str) -> Response:
    job = await _job_by_token(token)
    doc = await mongo_db.portal_uploads.find_one({"_id": upload_id, "job_id": job["_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="No such file.")
    key = await get_storage_key()
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(f"{STORAGE_URL}/objects/{doc['storage_path']}", headers={"X-Storage-Key": key})
    if r.status_code >= 300:
        raise HTTPException(status_code=404, detail="File missing.")
    return Response(content=r.content, media_type=doc.get("content_type", "application/octet-stream"))


class TipPayload(BaseModel):
    amount: float
    name: str = ""
    note: str = ""


@public_router.post("/track/{token}/tip")
async def portal_tip(token: str, payload: TipPayload):
    job = await _job_by_token(token)
    try:
        amt = round(float(payload.amount), 2)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Enter a tip amount first.")
    if not (1 <= amt <= 1000):
        raise HTTPException(status_code=422, detail="Tips can be $1 to $1,000.")
    creds = await square_creds()
    if not (creds["token"] and creds["location_id"]):
        raise HTTPException(status_code=503, detail="Tipping isn't set up yet — but the crew says thanks anyway!")
    tipper = (payload.name or "").strip()[:80]
    body = {
        "idempotency_key": uuid4().hex,
        "quick_pay": {
            "name": f"Crew tip — Job #{job.get('invoice_number') or ''}".strip(),
            "price_money": {"amount": int(round(amt * 100)), "currency": "USD"},
            "location_id": creds["location_id"],
        },
        "payment_note": f"Crew tip from {tipper or 'a happy customer'} — Job #{job.get('invoice_number')}",
    }
    data = await square_request("POST", "/v2/online-checkout/payment-links", body)
    url = (data.get("payment_link") or {}).get("url")
    if not url:
        raise HTTPException(status_code=502, detail="Square didn't hand back a checkout link. Try again.")
    await mongo_db.portal_tips.insert_one({
        "_id": str(uuid4()), "job_id": job["_id"], "invoice_number": job.get("invoice_number"),
        "amount": amt, "name": tipper, "note": (payload.note or "").strip()[:300],
        "link_url": url, "created_at": now_iso()})
    who = tipper or (job.get("customer") or {}).get("name") or "Someone"
    await _owner_portal_ping(job, "Crew tip started",
                             f"{who} opened a ${amt:,.2f} tip checkout for Job #{job.get('invoice_number')}. "
                             "Watch Square for the payment.")
    return {"url": url}


class PortalReviewPayload(BaseModel):
    rating: int
    text: str = ""


@public_router.post("/track/{token}/review")
async def portal_review(token: str, payload: PortalReviewPayload):
    job = await _job_by_token(token)
    if not (1 <= payload.rating <= 5):
        raise HTTPException(status_code=422, detail="Rating must be 1 to 5 stars.")
    review = {"rating": payload.rating, "text": (payload.text or "").strip()[:600], "at": now_iso()}
    await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {"portal_review": review}})
    who = (job.get("customer") or {}).get("name") or "The customer"
    stars = "★" * payload.rating + "☆" * (5 - payload.rating)
    await _owner_portal_ping(job, f"New review — {payload.rating}/5",
                             f"{who} (Job #{job.get('invoice_number')}) left {stars}"
                             + (f': "{review["text"][:120]}"' if review["text"] else "."))
    business = await mongo_db.settings.find_one({"_id": "business"}) or {}
    return {"ok": True, "review_link": business.get("reviewLink", "") if payload.rating >= 4 else ""}


@api_router.get("/jobs/{job_id}/portal-uploads")
async def job_portal_uploads(job_id: str, p: Dict[str, Any] = Depends(require_owner)):
    job = await mongo_db.jobs.find_one({"_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="No such job.")
    ups = await mongo_db.portal_uploads.find({"job_id": job_id}).sort("created_at", -1).to_list(50)
    return {"token": (job.get("tracking") or {}).get("token"),
            "uploads": [{"id": u["_id"], "kind": u.get("kind"), "filename": u.get("filename"),
                         "content_type": u.get("content_type"), "created_at": u.get("created_at")} for u in ups]}


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


_PDF_NAVY = HexColor("#1B2A4A")
_PDF_ORANGE = HexColor("#E8743B")
_PDF_SLATE = HexColor("#64748B")
_PDF_LIGHT = HexColor("#F2F4F8")
_PDF_WHITE = HexColor("#FFFFFF")


def _money(v: float) -> str:
    return f"${v:,.2f}"


def _pdf_amounts(b: Dict[str, Any]) -> Dict[str, Any]:
    final = round(float(b.get("finalQuote") or 0), 2)
    lines = [dict(l) for l in (b.get("lines") or []) if float(l.get("amount") or 0) > 0]
    if lines:
        drift = round(final - sum(round(float(l["amount"]), 2) for l in lines), 2)
        if abs(drift) >= 0.01:
            lines[-1]["amount"] = round(float(lines[-1]["amount"]) + drift, 2)
    else:
        lines = [{"name": "Local Moving Service — flat rate", "amount": final}]
    deposit = round(float(b.get("deposit") or final * 0.25), 2)
    return {"final": final, "lines": lines, "deposit": deposit,
            "balance": round(final - deposit, 2),
            "dep_pct": round(deposit / final * 100) if final else 25}


def _pdf_header(c: "PDFCanvas", W: float, H: float) -> None:
    c.setFillColor(_PDF_NAVY)
    c.rect(0, H - 130, W, 130, stroke=0, fill=1)
    try:
        c.drawImage(ImageReader("/app/frontend/public/logo.png"), 40, H - 116, width=160, height=100,
                    preserveAspectRatio=True, anchor="w", mask="auto")
    except Exception:
        c.setFillColor(_PDF_WHITE)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(40, H - 75, "HAUL YEAH MOVING")
    c.setFillColor(_PDF_WHITE)
    c.setFont("Helvetica-Bold", 25)
    c.drawRightString(W - 40, H - 68, "MOVING QUOTE")
    c.setFillColor(_PDF_ORANGE)
    c.setFont("Helvetica-Oblique", 11)
    c.drawRightString(W - 40, H - 88, "Weekend moves, flat price, no surprises.")


def _pdf_customer_block(c: "PDFCanvas", b: Dict[str, Any], H: float) -> float:
    y = H - 168
    c.setFillColor(_PDF_NAVY)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(40, y, f"Prepared for {b.get('customerName') or 'you'}")
    c.setFillColor(_PDF_SLATE)
    c.setFont("Helvetica", 10)
    y -= 17
    c.drawString(40, y, f"Quote date: {datetime.now(ZoneInfo('America/New_York')).strftime('%B %-d, %Y')}")
    for label, key in (("Move date", "moveDate"), ("From", "fromAddress"), ("To", "toAddress")):
        val = (str(b.get(key) or "")).strip()
        if val:
            y -= 14
            c.drawString(40, y, f"{label}: {_pdf_move_date(val) if key == 'moveDate' else val}")
    return y


def _pdf_line_items(c: "PDFCanvas", W: float, y: float, lines: List[Dict[str, Any]]) -> float:
    y -= 34
    c.setFillColor(_PDF_NAVY)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(48, y, "WHAT'S INCLUDED")
    c.drawRightString(W - 48, y, "PRICE")
    y -= 8
    c.setStrokeColor(_PDF_NAVY)
    c.setLineWidth(1.2)
    c.line(40, y, W - 40, y)
    c.setFont("Helvetica", 11)
    for i, l in enumerate(lines[:12]):
        y -= 27
        if i % 2 == 0:
            c.setFillColor(_PDF_LIGHT)
            c.rect(40, y - 9, W - 80, 27, stroke=0, fill=1)
        c.setFillColor(_PDF_NAVY)
        c.drawString(48, y, str(l.get("name") or "")[:72])
        c.drawRightString(W - 48, y, _money(round(float(l["amount"]), 2)))
    return y


def _pdf_totals(c: "PDFCanvas", W: float, y: float, amounts: Dict[str, Any]) -> None:
    y -= 48
    c.setFillColor(_PDF_NAVY)
    c.rect(40, y - 12, W - 80, 40, stroke=0, fill=1)
    c.setFillColor(_PDF_WHITE)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(48, y, "YOUR FLAT TOTAL")
    c.setFillColor(_PDF_ORANGE)
    c.setFont("Helvetica-Bold", 17)
    c.drawRightString(W - 48, y, _money(amounts["final"]))

    y -= 46
    c.setFillColor(_PDF_NAVY)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(48, y, f"Deposit to lock in your date ({amounts['dep_pct']}%):")
    c.drawRightString(W - 48, y, _money(amounts["deposit"]))
    y -= 19
    c.setFont("Helvetica", 11)
    c.drawString(48, y, "Balance due on move day:")
    c.drawRightString(W - 48, y, _money(amounts["balance"]))


def _pdf_footer(c: "PDFCanvas", W: float) -> None:
    c.setFillColor(_PDF_SLATE)
    c.setFont("Helvetica", 9)
    c.drawCentredString(W / 2, 62, "One flat price — crew, truck, travel, and care all included. No hourly surprises.")
    c.setFillColor(_PDF_ORANGE)
    c.setFont("Helvetica-BoldOblique", 10)
    c.drawCentredString(W / 2, 46, "Haul Yeah Moving — Weekend moves, flat price, no surprises.")


def build_quote_pdf(b: Dict[str, Any]) -> bytes:
    amounts = _pdf_amounts(b)
    buf = io.BytesIO()
    c = PDFCanvas(buf, pagesize=PDF_LETTER)
    W, H = PDF_LETTER
    _pdf_header(c, W, H)
    y = _pdf_customer_block(c, b, H)
    y = _pdf_line_items(c, W, y, amounts["lines"])
    _pdf_totals(c, W, y, amounts)
    _pdf_footer(c, W)
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
LEAD_NAME_F = "fldsBIJdaasQ9fh9a"
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
    if table_key == "blog" and payload.fields.get(BLOG_STATUS_F) == "Published":
        await notify_blog_published(data["records"][0])
    return rec


@api_router.patch("/tables/{table_key}/{record_id}")
async def update_record(table_key: str, record_id: str, request: Request, payload: RecordPayload = Body(...), role: str = Depends(require_auth)):
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
    prev_lead_status: Optional[str] = None
    if table_key == "leads" and payload.fields.get(LEAD_STATUS_F) == "Booked":
        try:
            prev = await airtable_request("GET", table_id, path=f"/{record_id}",
                                          params={"returnFieldsByFieldId": "true"})
            prev_lead_status = (prev.get("fields") or {}).get(LEAD_STATUS_F)
        except HTTPException:
            prev_lead_status = None
    body = {"records": [{"id": record_id, "fields": clean_write_fields(payload.fields, role, table_key)}], "typecast": True}
    data = await airtable_request("PATCH", table_id, json_body=body)
    if table_key == "leads" and payload.fields.get(LEAD_STATUS_F) in ("Contacted", "Quoted", "Booked", "Completed"):
        existing = await mongo_db.lead_meta.find_one({"_id": record_id})
        if not existing or not existing.get("contacted_at"):
            await mongo_db.lead_meta.update_one({"_id": record_id}, {"$set": {"contacted_at": now_iso()}}, upsert=True)
    if table_key == "leads" and payload.fields.get(LEAD_STATUS_F) == "Booked":
        if prev_lead_status != "Booked":
            rec_full = await fetch_lead_record(record_id)
            capi_lead = lead_dict_from_airtable(rec_full) if rec_full else {"id": record_id}
            logger.info("CAPI Schedule firing for lead %s (prev status: %s)", record_id, prev_lead_status)
            asyncio.create_task(_capi_log("schedule", meta_capi.fire_schedule(capi_lead)))
        try:
            lead_name0 = (data["records"][0].get("fields") or {}).get(LEAD_NAME_F) or "a lead"
            await create_alert("booked", f"Move booked: {lead_name0}", "Another one on the calendar.",
                               lead_id=record_id, lead_name=lead_name0, source="app",
                               dedupe_key=f"booked:{record_id}")
        except Exception as exc:
            logger.warning("booked alert failed: %s", exc)
        try:
            p = await current_principal(request)
            if p.get("user_id") and p["role"] != "owner" and "sales" in (p.get("roles") or []):
                u = await mongo_db.users.find_one({"_id": p["user_id"], "ghost": {"$ne": True}})
                if u:
                    lead_name = (data["records"][0].get("fields") or {}).get(LEAD_NAME_F) or "a lead"
                    await create_credit_prompt("sales_booked", u, None, lead_name, record_id, _et_today())
                    await notify(None, "owner", "Close credit waiting on you",
                                 f"{u['name']} moved \u201c{lead_name}\u201d to Booked. Approve their Close tally on your Dashboard or in Team HQ.",
                                 "credit_prompt", {"lead_id": record_id})
        except Exception as exc:
            logger.warning("sales credit prompt failed: %s", exc)
    rec = filter_record(data["records"][0], role, table_key)
    if table_key == "tasks" and role == "owner":
        meta = await mongo_db.task_meta.find_one({"_id": record_id}) or {}
        rec["audience"] = meta.get("audience", [])
    if table_key == "blog" and payload.fields.get(BLOG_STATUS_F) == "Published":
        await notify_blog_published(data["records"][0])
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
    title: str = ""


async def _team_notify(key: str, doc: Dict[str, Any]):
    await mongo_db.team_notifications.update_one({"key": key}, {"$setOnInsert": {"key": key, **doc}}, upsert=True)


async def notify_blog_published(record: Dict[str, Any]):
    rid = record.get("id")
    title = (record.get("fields") or {}).get(BLOG_TITLE_F) or ""
    for g in TASK_GROUPS:
        await _team_notify(f"blog:{rid}:{g}", {"_id": str(uuid4()), "type": "blog", "group": g,
                                               "record_id": rid, "title": title, "created_at": now_iso()})


@api_router.post("/tasks/{record_id}/audience")
async def set_task_audience(record_id: str, payload: TaskAudiencePayload = Body(...), p: Dict[str, Any] = Depends(require_owner)):
    audience = sorted({g for g in payload.audience if g in TASK_GROUPS})
    prev_doc = await mongo_db.task_meta.find_one({"_id": record_id}) or {}
    prev = set(prev_doc.get("audience") or [])
    await mongo_db.task_meta.update_one({"_id": record_id}, {"$set": {"audience": audience}}, upsert=True)
    for g in set(audience) - prev:
        await _team_notify(f"task:{record_id}:{g}", {"_id": str(uuid4()), "type": "task", "group": g,
                                                     "record_id": record_id, "title": payload.title.strip(), "created_at": now_iso()})
    removed = prev - set(audience)
    if removed:
        await mongo_db.team_notifications.delete_many({"key": {"$in": [f"task:{record_id}:{g}" for g in removed]}})
    return {"id": record_id, "audience": audience}


@api_router.get("/team-notifications")
async def team_notifications(role: str = Depends(require_auth)):
    grp = TASK_GROUP_FOR_ROLE.get(role)
    if not grp:
        return {"items": []}
    docs = await mongo_db.team_notifications.find({"group": grp}).sort("created_at", -1).to_list(50)
    return {"items": [{"id": d["_id"], "type": d["type"], "title": d.get("title", ""), "created_at": d["created_at"]} for d in docs]}


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


DEFAULT_STARTING_PASSWORD = os.environ.get("DEFAULT_STARTING_PASSWORD", "").strip() or "haulyeah123"


class UserPatchPayload(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    roles: Optional[List[str]] = None
    active: Optional[bool] = None
    password: Optional[str] = None


@api_router.get("/users")
async def list_users(p: Dict[str, Any] = Depends(require_owner)):
    docs = await mongo_db.users.find({"ghost": {"$ne": True}}).sort("created_at", 1).to_list(200)
    return {"users": [_user_public(u) for u in docs]}


@api_router.post("/users")
async def create_user(payload: UserCreatePayload, p: Dict[str, Any] = Depends(require_owner)):
    roles = [r for r in (payload.roles or [payload.role]) if r]
    if not roles or any(r not in ("crew", "sales", "owner", "marketing") for r in roles):
        raise HTTPException(status_code=422, detail="Roles must be crew, sales, owner, or marketing.")
    email = payload.email.strip().lower()
    if len(email) < 3 or " " in email:
        raise HTTPException(status_code=422, detail="That login doesn't look right — use a username (3+ characters, no spaces) or an email.")
    password = payload.password or DEFAULT_STARTING_PASSWORD
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="The password needs at least 8 characters.")
    if await mongo_db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="A user with that email already exists.")
    doc = {"_id": str(uuid4()), "name": payload.name.strip(), "email": email, "role": roles[0], "roles": roles,
           "password_hash": hash_password(password), "active": True, "must_change_password": True,
           "gps_consent_at": None, "profile_task": "open", "created_at": now_iso()}
    await mongo_db.users.insert_one(doc)
    await notify(doc["_id"], None, "First task: set up your profile",
                 "Welcome aboard! Head to the To-Do page — your first task is adding a photo, a nickname, and a fun fact to your team profile.",
                 "task")
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
        if not email or " " in email:
            raise HTTPException(status_code=422, detail="That login doesn't look right — no spaces allowed.")
        clash = await mongo_db.users.find_one({"email": email, "_id": {"$ne": user_id}})
        if clash:
            raise HTTPException(status_code=409, detail="Another user already has that email.")
        updates["email"] = email
        changes.append("email")
    if payload.roles is not None:
        roles = [r for r in payload.roles if r]
        if not roles or any(r not in ("crew", "sales", "owner", "marketing") for r in roles):
            raise HTTPException(status_code=422, detail="Roles must be crew, sales, owner, or marketing.")
        if p["user_id"] == user_id and "owner" not in roles:
            raise HTTPException(status_code=422, detail="You can't take Owner off your own account — you'd lock yourself out.")
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
    mileage: Optional[float] = None
    fleet_status: Optional[str] = None
    registration: Optional[Dict[str, Any]] = None
    insurance: Optional[Dict[str, Any]] = None
    reminders: Optional[List[Dict[str, Any]]] = None


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
    if payload.mileage is not None:
        updates["mileage"] = max(0.0, float(payload.mileage))
    if payload.fleet_status is not None:
        if payload.fleet_status not in FLEET_STATUSES:
            raise HTTPException(status_code=422, detail="Status must be in_service, needs_attention, or in_shop.")
        updates["fleet_status"] = payload.fleet_status
    if payload.registration is not None:
        updates["registration"] = {"number": str(payload.registration.get("number", ""))[:60],
                                   "expires": str(payload.registration.get("expires", ""))[:10]}
    if payload.insurance is not None:
        updates["insurance"] = {"carrier": str(payload.insurance.get("carrier", ""))[:80],
                                "policy": str(payload.insurance.get("policy", ""))[:60],
                                "expires": str(payload.insurance.get("expires", ""))[:10]}
    if payload.reminders is not None:
        updates["reminders"] = [{"id": str(r.get("id") or uuid4()), "title": str(r.get("title", "")).strip()[:120],
                                 "due_date": str(r.get("due_date", ""))[:10], "done": bool(r.get("done"))}
                                for r in payload.reminders if str(r.get("title", "")).strip()][:30]
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
    if doc["crew"]:
        await log_job_event(doc["_id"], "crew",
                            "Crew assigned: " + ", ".join(f"{c['name']} ({c['position']})" for c in doc["crew"]),
                            by=p["name"])
    if doc["truck_name"]:
        await log_job_event(doc["_id"], "truck", f"Truck assigned: {doc['truck_name']}", by=p["name"])
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
    added_names = [c["name"] for c in updates["crew"] if c["user_id"] not in old_ids]
    new_ids = {c["user_id"] for c in updates["crew"]}
    removed_names = [c["name"] for c in existing.get("crew", []) if c["user_id"] not in new_ids]
    if added_names:
        await log_job_event(assignment_id, "crew", "Added to crew: " + ", ".join(added_names), by=p["name"])
    if removed_names:
        await log_job_event(assignment_id, "crew", "Removed from crew: " + ", ".join(removed_names), by=p["name"])
    if (existing.get("truck_id") or None) != (updates["truck_id"] or None):
        await log_job_event(assignment_id, "truck",
                            f"Truck assigned: {updates['truck_name']}" if updates.get("truck_name") else "Truck removed",
                            by=p["name"])
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


# ------- dispatch board (owner day view over existing assignments)

@api_router.get("/dispatch/board")
async def dispatch_board(date: Optional[str] = None, p: Dict[str, Any] = Depends(require_owner)):
    day = (date or _et_today())[:10]
    docs = await mongo_db.assignments.find({"job_date": day}).to_list(100)
    docs.sort(key=lambda a: (a.get("arrival_time") or "99:99", a.get("job_name") or ""))
    ids = [a["_id"] for a in docs]
    entries = await mongo_db.time_entries.find({"assignment_id": {"$in": ids}}).to_list(500)
    cl_docs = await mongo_db.job_checklists.find({"_id": {"$in": ids}}).to_list(100)
    cl_done = {d["_id"]: _checklist_done_count(d) for d in cl_docs}
    open_by_assignment: Dict[str, int] = {}
    for e in entries:
        if not e.get("clock_out"):
            aid = e.get("assignment_id")
            open_by_assignment[aid] = open_by_assignment.get(aid, 0) + 1
    now_et = datetime.now(ZoneInfo("America/New_York"))
    is_today = day == _et_today()
    out, active, complete, behind_count, needs_crew = [], 0, 0, 0, 0
    for a in docs:
        item = _sanitize_assignment(a)
        item["clocked_in"] = open_by_assignment.get(a["_id"], 0)
        item["checklist_done"] = cl_done.get(a["_id"], 0)
        item["checklist_total"] = CHECKLIST_TOTAL_ITEMS
        behind = False
        if is_today and a.get("arrival_time") and a.get("exec_status") in ("Assigned", "En Route"):
            try:
                hh, mm = a["arrival_time"].split(":")[:2]
                behind = now_et > now_et.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0) + timedelta(minutes=15)
            except ValueError:
                pass
        item["behind"] = behind
        status = a.get("exec_status") or "Assigned"
        if status == "Complete":
            complete += 1
        elif status != "Assigned":
            active += 1
        if behind:
            behind_count += 1
        if not a.get("crew"):
            needs_crew += 1
        out.append(item)
    day_dt = datetime.fromisoformat(day)
    week_start = (day_dt - timedelta(days=day_dt.weekday())).date().isoformat()
    week_end = (day_dt + timedelta(days=6 - day_dt.weekday())).date().isoformat()
    week_docs = await mongo_db.assignments.find(
        {"job_date": {"$gte": week_start, "$lte": week_end}}, {"crew": 1}).to_list(300)
    week_count: Dict[str, int] = {}
    for a in week_docs:
        for c in a.get("crew", []):
            week_count[c["user_id"]] = week_count.get(c["user_id"], 0) + 1
    on_today: Dict[str, int] = {}
    for a in docs:
        for c in a.get("crew", []):
            on_today[c["user_id"]] = on_today.get(c["user_id"], 0) + 1
    crew_users = await mongo_db.users.find(
        {"active": True, "ghost": {"$ne": True}, "$or": [{"roles": "crew"}, {"role": "crew"}]}).sort("name", 1).to_list(100)
    open_entries = await mongo_db.time_entries.find({"clock_out": None}, {"user_id": 1}).to_list(100)
    clocked_ids = {e.get("user_id") for e in open_entries}
    off_docs = await mongo_db.availability.find({"date": day, "available": False}).to_list(100)
    off_ids = {d.get("user_id") for d in off_docs}
    crew_pool = [{"id": u["_id"], "name": u.get("name", ""), "jobs_today": on_today.get(u["_id"], 0),
                  "jobs_week": week_count.get(u["_id"], 0), "clocked_in": u["_id"] in clocked_ids,
                  "off": u["_id"] in off_ids} for u in crew_users]
    trucks = await mongo_db.trucks.find({"active": {"$ne": False}}).sort("name", 1).to_list(100)
    truck_use = {a.get("truck_id"): a.get("job_name") for a in docs if a.get("truck_id")}
    truck_pool = [{"id": t["_id"], "name": t.get("name", ""), "on_job": truck_use.get(t["_id"])} for t in trucks]
    revenue_today = 0.0
    paid = await mongo_db.square_invoices.find(
        {"status": "PAID", "paid_at": {"$ne": None}}, {"_id": 0, "amount": 1, "paid_at": 1}).to_list(1000)
    for inv in paid:
        try:
            et_day = datetime.fromisoformat(str(inv["paid_at"]).replace("Z", "+00:00")).astimezone(
                ZoneInfo("America/New_York")).date().isoformat()
        except ValueError:
            continue
        if et_day == day:
            revenue_today += inv.get("amount") or 0
    return {"date": day, "is_today": is_today, "assignments": out, "crew": crew_pool, "trucks": truck_pool,
            "revenue_today": round(revenue_today, 2),
            "counts": {"total": len(out), "active": active, "complete": complete,
                       "behind": behind_count, "needs_crew": needs_crew}}


# ------- crew: my jobs + execution workflow

EXEC_STATUSES = ["Assigned", "En Route", "Arrived", "In Progress", "Complete"]


def _crew_job_view(a: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    mine = next((c for c in a.get("crew", []) if c["user_id"] == user_id), {})
    return {
        "id": a["_id"], "job_name": a.get("job_name"), "job_date": a.get("job_date"),
        "arrival_time": a.get("arrival_time"), "start_address": a.get("start_address"),
        "truck_name": a.get("truck_name"), "truck_id": a.get("truck_id"), "my_position": mine.get("position"),
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


async def _apply_exec_status(a: Dict[str, Any], status: str, p: Dict[str, Any],
                             notes: Optional[str] = None, delay_factors: Optional[List[str]] = None) -> None:
    assignment_id = a["_id"]
    payload = StatusPayload(status=status, notes=notes, delay_factors=delay_factors)
    event = {"status": payload.status, "at": now_iso(), "by": p["name"], "by_id": p.get("user_id")}
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
    if payload.status == "Complete" and not a.get("credit_prompted"):
        try:
            await mongo_db.assignments.update_one({"_id": assignment_id}, {"$set": {"credit_prompted": True}})
            names = []
            for slot in a.get("crew", []):
                u = await mongo_db.users.find_one({"_id": slot.get("user_id"), "ghost": {"$ne": True}})
                if not u:
                    continue
                tag = "driver" if "driver" in (slot.get("position") or "").lower() else "helper"
                await create_credit_prompt("crew_complete", u, tag, a.get("job_name") or "Job",
                                           assignment_id, a.get("job_date") or _et_today())
                names.append(u["name"])
            if names:
                await notify(None, "owner", "Job credit waiting on you",
                             f"\u201c{a.get('job_name')}\u201d is complete. Approve the job tally for {', '.join(names)} on your Dashboard or in Team HQ.",
                             "credit_prompt", {"assignment_id": assignment_id})
        except Exception as exc:
            logger.warning("crew credit prompt failed: %s", exc)
    if payload.status == "Complete":
        await queue_timelog_sync(assignment_id)


@api_router.post("/crew/jobs/{assignment_id}/status")
async def set_job_status(assignment_id: str, payload: StatusPayload, p: Dict[str, Any] = Depends(require_crew)):
    if payload.status not in EXEC_STATUSES[1:]:
        raise HTTPException(status_code=422, detail="Unknown status.")
    a = await mongo_db.assignments.find_one({"_id": assignment_id, "crew.user_id": p["user_id"]})
    if not a:
        raise HTTPException(status_code=404, detail="That job isn't on your schedule.")
    await _apply_exec_status(a, payload.status, p, payload.notes, payload.delay_factors)
    fresh = await mongo_db.assignments.find_one({"_id": assignment_id})
    return _crew_job_view(fresh, p["user_id"])


# ------- job checklists + operations timeline (phase B — attached to existing assignments)

CHECKLIST_TEMPLATES = [
    ("warehouse_departure", "Warehouse Departure", [
        "Truck inspected (walkaround, lights, tires)",
        "Fuel level checked",
        "Dollies, straps & blankets loaded",
        "Tools & shrink wrap on board",
        "Job details & addresses reviewed",
    ]),
    ("arrival", "Arrival", [
        "Arrived & greeted the customer",
        "Walkthrough done — scope confirmed",
        "Photos of existing damage taken",
        "Floors & doorways protected",
        "Parking / access secured",
    ]),
    ("loading", "Loading", [
        "Furniture wrapped & padded",
        "Boxes staged and labeled",
        "Specialty items secured",
        "Load strapped & balanced",
        "Final sweep of every room",
    ]),
    ("delivery", "Delivery", [
        "Walkthrough at the destination",
        "Floors protected at the destination",
        "Items placed in the right rooms",
        "Furniture reassembled",
        "Blankets & equipment collected",
    ]),
    ("completion", "Completion", [
        "Final walkthrough with the customer",
        "Damage check confirmed with the customer",
        "Balance / payment confirmed",
        "Customer asked for a review",
        "Truck cleaned & ready for return",
    ]),
]
CHECKLIST_STATUS_ADVANCE = {"warehouse_departure": "En Route", "arrival": "Arrived",
                            "loading": "In Progress", "completion": "Complete"}
CHECKLIST_TOTAL_ITEMS = sum(len(items) for _k, _l, items in CHECKLIST_TEMPLATES)


async def log_job_event(assignment_id: str, kind: str, title: str, by: str = "", detail: str = ""):
    try:
        await mongo_db.job_events.insert_one({"_id": str(uuid4()), "assignment_id": assignment_id,
                                              "kind": kind, "title": title[:200], "by": by,
                                              "detail": detail[:300], "at": now_iso()})
    except Exception as exc:
        logger.warning("log_job_event failed: %s", exc)


async def _assignment_for_member_or_owner(assignment_id: str, p: Dict[str, Any]) -> Dict[str, Any]:
    a = await mongo_db.assignments.find_one({"_id": assignment_id})
    if not a:
        raise HTTPException(status_code=404, detail="No such job.")
    if p["role"] != "owner" and not any(c["user_id"] == p["user_id"] for c in a.get("crew", [])):
        raise HTTPException(status_code=403, detail="That job isn't on your schedule.")
    return a


def _checklists_out(state: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    lists = (state or {}).get("lists", {})
    out = []
    for key, label, items in CHECKLIST_TEMPLATES:
        saved = lists.get(key) or {}
        saved_items = saved.get("items", {})
        rows, done_count = [], 0
        for idx, text in enumerate(items):
            st = saved_items.get(str(idx)) or {}
            if st.get("done"):
                done_count += 1
            rows.append({"idx": idx, "label": text, "done": bool(st.get("done")),
                         "by": st.get("by", ""), "at": st.get("at")})
        out.append({"key": key, "label": label, "items": rows, "done_count": done_count,
                    "total": len(items), "completed_at": saved.get("completed_at"),
                    "auto_status": CHECKLIST_STATUS_ADVANCE.get(key)})
    return out


def _checklist_done_count(state: Optional[Dict[str, Any]]) -> int:
    n = 0
    for key, _label, items in CHECKLIST_TEMPLATES:
        saved = (((state or {}).get("lists") or {}).get(key) or {}).get("items", {})
        n += sum(1 for i in range(len(items)) if (saved.get(str(i)) or {}).get("done"))
    return n


async def _maybe_complete_checklist(a: Dict[str, Any], list_key: str, p: Dict[str, Any]) -> Optional[str]:
    template = next((t for t in CHECKLIST_TEMPLATES if t[0] == list_key), None)
    if not template:
        return None
    state = await mongo_db.job_checklists.find_one({"_id": a["_id"]})
    saved = (((state or {}).get("lists") or {}).get(list_key) or {})
    saved_items = saved.get("items", {})
    all_done = all((saved_items.get(str(i)) or {}).get("done") for i in range(len(template[2])))
    if all_done and not saved.get("completed_at"):
        await mongo_db.job_checklists.update_one(
            {"_id": a["_id"]}, {"$set": {f"lists.{list_key}.completed_at": now_iso()}})
        await log_job_event(a["_id"], "checklist", f"{template[1]} checklist completed", by=p["name"])
        target = CHECKLIST_STATUS_ADVANCE.get(list_key)
        if target and EXEC_STATUSES.index(target) > EXEC_STATUSES.index(a.get("exec_status") or "Assigned"):
            await _apply_exec_status(a, target, p)
            return target
    elif not all_done and saved.get("completed_at"):
        await mongo_db.job_checklists.update_one(
            {"_id": a["_id"]}, {"$unset": {f"lists.{list_key}.completed_at": ""}})
    return None


@api_router.get("/assignments/{assignment_id}/checklists")
async def get_job_checklists(assignment_id: str, request: Request):
    p = await current_principal(request)
    await _assignment_for_member_or_owner(assignment_id, p)
    state = await mongo_db.job_checklists.find_one({"_id": assignment_id})
    return {"checklists": _checklists_out(state)}


class ChecklistItemPayload(BaseModel):
    done: bool


@api_router.post("/assignments/{assignment_id}/checklists/{list_key}/items/{idx}")
async def toggle_checklist_item(assignment_id: str, list_key: str, idx: int, payload: ChecklistItemPayload,
                                request: Request):
    p = await current_principal(request)
    a = await _assignment_for_member_or_owner(assignment_id, p)
    if p["role"] != "owner":
        on_clock = await mongo_db.time_entries.find_one({"user_id": p["user_id"], "clock_out": None})
        if not on_clock:
            raise HTTPException(status_code=403, detail="Clock in first — checklists unlock once you're on the clock.")
    template = next((t for t in CHECKLIST_TEMPLATES if t[0] == list_key), None)
    if not template or not (0 <= idx < len(template[2])):
        raise HTTPException(status_code=404, detail="No such checklist item.")
    field = f"lists.{list_key}.items.{idx}"
    item_state = {"done": True, "by": p["name"], "at": now_iso()} if payload.done else {"done": False}
    await mongo_db.job_checklists.update_one({"_id": assignment_id}, {"$set": {field: item_state}}, upsert=True)
    advanced_to = await _maybe_complete_checklist(a, list_key, p)
    fresh = await mongo_db.job_checklists.find_one({"_id": assignment_id})
    return {"checklists": _checklists_out(fresh), "advanced_to": advanced_to}


@api_router.get("/assignments/{assignment_id}/timeline")
async def job_timeline(assignment_id: str, request: Request):
    p = await current_principal(request)
    a = await _assignment_for_member_or_owner(assignment_id, p)
    events = []
    for ev in a.get("status_history", []):
        events.append({"at": ev.get("at"), "kind": "status", "title": f"Status: {ev.get('status')}",
                       "by": ev.get("by", "")})
    for d in await mongo_db.job_events.find({"assignment_id": assignment_id}).to_list(200):
        events.append({"at": d.get("at"), "kind": d.get("kind", "event"), "title": d.get("title", ""),
                       "by": d.get("by", ""), "detail": d.get("detail", "")})
    for e in await mongo_db.time_entries.find({"assignment_id": assignment_id}).to_list(100):
        if e.get("clock_in"):
            title = f"{e.get('user_name')} clocked in"
            if "not_scheduled_today" in (e.get("flags") or []):
                title += " (wasn't scheduled)"
            events.append({"at": e["clock_in"]["at"], "kind": "clock", "title": title, "by": e.get("user_name", "")})
        if e.get("clock_out"):
            hrs = e.get("hours")
            events.append({"at": e["clock_out"]["at"], "kind": "clock",
                           "title": f"{e.get('user_name')} clocked out" + (f" — {hrs:.1f}h" if hrs else ""),
                           "by": e.get("user_name", "")})
    for ph in await mongo_db.job_photos.find({"assignment_id": assignment_id}).to_list(100):
        events.append({"at": ph.get("created_at"), "kind": "photo",
                       "title": f"Photo added by {ph.get('user_name')}", "by": ph.get("user_name", "")})
    events = [e for e in events if e.get("at")]
    events.sort(key=lambda e: e["at"], reverse=True)
    events = events[:199]
    if a.get("created_at"):
        events.append({"at": a["created_at"], "kind": "created", "title": "Job put on the schedule", "by": ""})
    return {"events": events}


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


# ------- fleet management (phase C — extends existing trucks)

INSPECTION_ITEMS = [
    ("lights", "Lights & signals working"),
    ("tires", "Tires — pressure & tread OK"),
    ("brakes", "Brakes feel right"),
    ("fluids", "No leaks — oil / coolant OK"),
    ("glass", "Mirrors & windshield clean, no cracks"),
    ("wipers", "Horn & wipers working"),
    ("equipment", "Straps, dollies & pads on board"),
    ("interior", "Cab & box clean and secure"),
]
INSPECTION_LABELS = dict(INSPECTION_ITEMS)
FLEET_STATUSES = ("in_service", "needs_attention", "in_shop")


async def _truck_or_404(truck_id: str) -> Dict[str, Any]:
    t = await mongo_db.trucks.find_one({"_id": truck_id})
    if not t:
        raise HTTPException(status_code=404, detail="No such truck.")
    return t


def _require_fleet_actor(p: Dict[str, Any]):
    if p["role"] not in ("owner", "crew"):
        raise HTTPException(status_code=403, detail="Only crew and the owner can do that.")


def _expiry_state(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    try:
        d = datetime.fromisoformat(date_str[:10]).date()
    except ValueError:
        return None
    today = datetime.now(ZoneInfo("America/New_York")).date()
    if d < today:
        return "expired"
    if (d - today).days <= 30:
        return "soon"
    return "ok"


@api_router.get("/fleet")
async def fleet_overview(p: Dict[str, Any] = Depends(require_owner)):
    trucks = await mongo_db.trucks.find({}).sort("name", 1).to_list(100)
    ids = [t["_id"] for t in trucks]
    today_et = _et_today()
    latest: Dict[str, Dict[str, Any]] = {}
    for i in await mongo_db.truck_inspections.find({"truck_id": {"$in": ids}}).sort("created_at", -1).to_list(500):
        latest.setdefault(i["truck_id"], i)
    damage_open: Dict[str, int] = {}
    for d in await mongo_db.truck_damage.find({"truck_id": {"$in": ids}, "resolved": {"$ne": True}}).to_list(200):
        damage_open[d["truck_id"]] = damage_open.get(d["truck_id"], 0) + 1
    soon_cut = (datetime.fromisoformat(today_et) + timedelta(days=14)).date().isoformat()
    out = []
    for t in trucks:
        li = latest.get(t["_id"])
        reminders = t.get("reminders", [])
        due = sum(1 for r in reminders if not r.get("done") and r.get("due_date") and r["due_date"] <= today_et)
        upcoming = sum(1 for r in reminders if not r.get("done") and r.get("due_date") and today_et < r["due_date"] <= soon_cut)
        out.append({
            "id": t["_id"], "name": t["name"], "plate": t.get("plate", ""), "active": t.get("active", True),
            "fleet_status": t.get("fleet_status", "in_service"), "mileage": t.get("mileage"),
            "registration": t.get("registration") or {}, "insurance": t.get("insurance") or {},
            "registration_state": _expiry_state((t.get("registration") or {}).get("expires")),
            "insurance_state": _expiry_state((t.get("insurance") or {}).get("expires")),
            "reminders": reminders, "reminders_due": due, "reminders_upcoming": upcoming,
            "open_damage": damage_open.get(t["_id"], 0),
            "last_inspection": {"date": li.get("date"), "passed": li.get("passed"), "by": li.get("by"),
                                "inspected_today": li.get("date") == today_et} if li else None,
        })
    return {"trucks": out, "inspection_items": [{"key": k, "label": v} for k, v in INSPECTION_ITEMS]}


class InspectionPayload(BaseModel):
    items: Dict[str, bool]
    odometer: Optional[float] = None
    notes: Optional[str] = ""
    assignment_id: Optional[str] = None


@api_router.post("/trucks/{truck_id}/inspections")
async def create_inspection(truck_id: str, payload: InspectionPayload, request: Request):
    p = await current_principal(request)
    _require_fleet_actor(p)
    t = await _truck_or_404(truck_id)
    items = {k: bool(payload.items.get(k, False)) for k, _ in INSPECTION_ITEMS}
    failed = [k for k, _ in INSPECTION_ITEMS if not items[k]]
    passed = not failed
    doc = {"_id": str(uuid4()), "truck_id": truck_id, "truck_name": t["name"],
           "date": _et_today(), "by": p["name"], "by_id": p["user_id"],
           "items": items, "failed": failed, "passed": passed,
           "odometer": payload.odometer, "notes": (payload.notes or "").strip()[:500],
           "assignment_id": payload.assignment_id, "created_at": now_iso()}
    await mongo_db.truck_inspections.insert_one(doc)
    truck_updates: Dict[str, Any] = {}
    if payload.odometer and (not t.get("mileage") or payload.odometer > t["mileage"]):
        truck_updates["mileage"] = payload.odometer
    if not passed and t.get("fleet_status", "in_service") == "in_service":
        truck_updates["fleet_status"] = "needs_attention"
    if truck_updates:
        await mongo_db.trucks.update_one({"_id": truck_id}, {"$set": truck_updates})
    if not passed:
        await notify(None, "owner", f"Inspection flagged {t['name']}",
                     f"{p['name']}'s daily inspection found issues: "
                     + ", ".join(INSPECTION_LABELS[k] for k in failed)
                     + ". The truck is marked needs-attention on the Fleet page.",
                     "flag", {"truck_id": truck_id, "inspection_id": doc["_id"]})
    if payload.assignment_id:
        a = await mongo_db.assignments.find_one({"_id": payload.assignment_id})
        if a and (p["role"] == "owner" or any(c["user_id"] == p["user_id"] for c in a.get("crew", []))):
            await log_job_event(a["_id"], "checklist",
                                f"Daily inspection filed for {t['name']}" + ("" if passed else " — issues flagged"),
                                by=p["name"])
            await mongo_db.job_checklists.update_one(
                {"_id": a["_id"]},
                {"$set": {"lists.warehouse_departure.items.0": {"done": True, "by": p["name"], "at": now_iso()}}},
                upsert=True)
            await _maybe_complete_checklist(a, "warehouse_departure", p)
    await audit(p, "filed a truck inspection", t["name"], {"passed": passed, "failed": failed})
    return {"id": doc["_id"], "passed": passed, "failed": failed, "date": doc["date"]}


@api_router.get("/trucks/{truck_id}/inspections")
async def list_inspections(truck_id: str, request: Request):
    p = await current_principal(request)
    _require_fleet_actor(p)
    await _truck_or_404(truck_id)
    limit = 50 if p["role"] == "owner" else 5
    docs = await mongo_db.truck_inspections.find({"truck_id": truck_id}).sort("created_at", -1).to_list(limit)
    photo_map: Dict[str, List[str]] = {}
    for ph in await mongo_db.truck_photos.find({"ref_id": {"$in": [d["_id"] for d in docs]}}).to_list(200):
        photo_map.setdefault(ph["ref_id"], []).append(ph["_id"])
    return {"inspections": [{
        "id": d["_id"], "date": d.get("date"), "by": d.get("by"), "passed": d.get("passed"),
        "failed": [INSPECTION_LABELS.get(k, k) for k in d.get("failed", [])],
        "odometer": d.get("odometer"), "notes": d.get("notes", ""),
        "photos": photo_map.get(d["_id"], []), "created_at": d.get("created_at"),
    } for d in docs]}


class TruckLogPayload(BaseModel):
    kind: str
    date: Optional[str] = None
    odometer: Optional[float] = None
    cost: Optional[float] = None
    gallons: Optional[float] = None
    notes: str = ""


@api_router.post("/trucks/{truck_id}/logs")
async def add_truck_log(truck_id: str, payload: TruckLogPayload, p: Dict[str, Any] = Depends(require_owner)):
    if payload.kind not in ("maintenance", "fuel"):
        raise HTTPException(status_code=422, detail="Log kind must be maintenance or fuel.")
    t = await _truck_or_404(truck_id)
    doc = {"_id": str(uuid4()), "truck_id": truck_id, "kind": payload.kind,
           "date": (payload.date or _et_today())[:10], "odometer": payload.odometer,
           "cost": payload.cost, "gallons": payload.gallons if payload.kind == "fuel" else None,
           "notes": payload.notes.strip()[:300], "by": p["name"], "created_at": now_iso()}
    await mongo_db.truck_logs.insert_one(doc)
    if payload.odometer and (not t.get("mileage") or payload.odometer > t["mileage"]):
        await mongo_db.trucks.update_one({"_id": truck_id}, {"$set": {"mileage": payload.odometer}})
    await audit(p, f"logged truck {payload.kind}", t["name"], {"cost": payload.cost})
    return {"id": doc["_id"]}


@api_router.get("/trucks/{truck_id}/logs")
async def list_truck_logs(truck_id: str, p: Dict[str, Any] = Depends(require_owner)):
    await _truck_or_404(truck_id)
    docs = await mongo_db.truck_logs.find({"truck_id": truck_id}).sort([("date", -1), ("created_at", -1)]).to_list(200)
    maint_cost = sum(d.get("cost") or 0 for d in docs if d["kind"] == "maintenance")
    fuel_cost = sum(d.get("cost") or 0 for d in docs if d["kind"] == "fuel")
    return {"logs": [{"id": d["_id"], "kind": d["kind"], "date": d.get("date"), "odometer": d.get("odometer"),
                      "cost": d.get("cost"), "gallons": d.get("gallons"), "notes": d.get("notes", ""),
                      "by": d.get("by", "")} for d in docs],
            "totals": {"maintenance": round(maint_cost, 2), "fuel": round(fuel_cost, 2)}}


@api_router.delete("/truck-logs/{log_id}")
async def delete_truck_log(log_id: str, p: Dict[str, Any] = Depends(require_owner)):
    res = await mongo_db.truck_logs.delete_one({"_id": log_id})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="No such log entry.")
    return {"deleted": True}


class DamagePayload(BaseModel):
    description: str
    assignment_id: Optional[str] = None


@api_router.post("/trucks/{truck_id}/damage")
async def report_damage(truck_id: str, payload: DamagePayload, request: Request):
    p = await current_principal(request)
    _require_fleet_actor(p)
    t = await _truck_or_404(truck_id)
    desc = payload.description.strip()
    if not desc:
        raise HTTPException(status_code=422, detail="Describe the damage first.")
    doc = {"_id": str(uuid4()), "truck_id": truck_id, "truck_name": t["name"], "description": desc[:600],
           "by": p["name"], "by_id": p["user_id"], "resolved": False, "assignment_id": payload.assignment_id,
           "created_at": now_iso()}
    await mongo_db.truck_damage.insert_one(doc)
    if p["role"] != "owner":
        await notify(None, "owner", f"Damage reported on {t['name']}",
                     f"{p['name']} reported: {desc[:140]}. Photos and details are on the Fleet page.",
                     "flag", {"truck_id": truck_id, "damage_id": doc["_id"]})
    if payload.assignment_id:
        a = await mongo_db.assignments.find_one({"_id": payload.assignment_id})
        if a and (p["role"] == "owner" or any(c["user_id"] == p["user_id"] for c in a.get("crew", []))):
            await log_job_event(a["_id"], "truck", f"Damage reported on {t['name']}", by=p["name"])
    await audit(p, "reported truck damage", t["name"])
    return {"id": doc["_id"]}


@api_router.get("/trucks/{truck_id}/damage")
async def list_damage(truck_id: str, p: Dict[str, Any] = Depends(require_owner)):
    await _truck_or_404(truck_id)
    docs = await mongo_db.truck_damage.find({"truck_id": truck_id}).sort("created_at", -1).to_list(100)
    photo_map: Dict[str, List[str]] = {}
    for ph in await mongo_db.truck_photos.find({"ref_id": {"$in": [d["_id"] for d in docs]}}).to_list(200):
        photo_map.setdefault(ph["ref_id"], []).append(ph["_id"])
    return {"reports": [{"id": d["_id"], "description": d.get("description", ""), "by": d.get("by", ""),
                         "resolved": d.get("resolved", False), "resolved_at": d.get("resolved_at"),
                         "photos": photo_map.get(d["_id"], []), "created_at": d.get("created_at")}
                        for d in docs]}


class DamagePatchPayload(BaseModel):
    resolved: bool


@api_router.patch("/truck-damage/{damage_id}")
async def patch_damage(damage_id: str, payload: DamagePatchPayload, p: Dict[str, Any] = Depends(require_owner)):
    d = await mongo_db.truck_damage.find_one({"_id": damage_id})
    if not d:
        raise HTTPException(status_code=404, detail="No such damage report.")
    await mongo_db.truck_damage.update_one(
        {"_id": damage_id},
        {"$set": {"resolved": payload.resolved, "resolved_at": now_iso() if payload.resolved else None}})
    await audit(p, "resolved truck damage" if payload.resolved else "reopened truck damage", d.get("truck_name", ""))
    return {"ok": True}


@api_router.post("/trucks/{truck_id}/photos")
async def upload_truck_photo(truck_id: str, request: Request, kind: str = "inspection",
                             ref_id: str = "", file: UploadFile = File(...)):
    p = await current_principal(request)
    _require_fleet_actor(p)
    await _truck_or_404(truck_id)
    if kind not in ("inspection", "damage", "general"):
        raise HTTPException(status_code=422, detail="Photo kind must be inspection, damage, or general.")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=422, detail="Only photos can be uploaded here.")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="That photo is too big (15 MB max).")
    ext = (file.filename or "photo.jpg").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "jpg"
    path = f"haulyeah-crm/trucks/{truck_id}/{uuid4()}.{ext}"
    key = await get_storage_key()
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.put(f"{STORAGE_URL}/objects/{path}",
                             headers={"X-Storage-Key": key, "Content-Type": file.content_type or "image/jpeg"},
                             content=data)
    if r.status_code >= 300:
        raise HTTPException(status_code=502, detail="The photo didn't upload. Try again.")
    doc = {"_id": str(uuid4()), "truck_id": truck_id, "kind": kind, "ref_id": ref_id or None,
           "user_name": p["name"], "storage_path": r.json()["path"],
           "content_type": file.content_type or "image/jpeg", "created_at": now_iso()}
    await mongo_db.truck_photos.insert_one(doc)
    return {"id": doc["_id"]}


@dl_router.get("/truck-photos/{photo_id}")
async def serve_truck_photo(photo_id: str, request: Request, auth: Optional[str] = None):
    if auth:
        p = await principal_from_token_string(auth)
    else:
        p = await current_principal(request)
    _require_fleet_actor(p)
    doc = await mongo_db.truck_photos.find_one({"_id": photo_id})
    if not doc:
        raise HTTPException(status_code=404, detail="No such photo.")
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
    assignment_id: Optional[str] = None


async def _todays_assignment(user_id: str) -> Optional[Dict[str, Any]]:
    return await mongo_db.assignments.find_one({"crew.user_id": user_id, "job_date": _et_today()})


def _punch_flags(punch_at: datetime, coords: Optional[Dict[str, float]], assignment: Optional[Dict[str, Any]],
                 kind: str) -> List[str]:
    flags = []
    if kind == "in" and assignment is None:
        flags.append("not_scheduled_today")
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
    assignment = None
    if payload.assignment_id:
        assignment = await mongo_db.assignments.find_one(
            {"_id": payload.assignment_id, "crew.user_id": p["user_id"]})
    if not assignment:
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
    if "not_scheduled_today" in doc["flags"]:
        await notify(None, "owner", "Unscheduled clock-in",
                     f"{p['name']} just clocked in but isn't on any job today. Check the Time tab on the Crew page.",
                     "flag", {"entry_id": doc["_id"]})
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


# ================================================================ team profiles, badges & challenges

TEAMS = ("crew", "sales")
TEAM_FOR_ROLE_MAP = {"crew": "crew", "employee": "crew", "sales": "sales"}
RARITIES = ("bronze", "silver", "gold")
AUTO_METRICS = ("jobs", "driver", "helper", "closes", "driver_and_helper")
MEMBER_PROFILE_FIELDS = ("display_name", "nickname", "bio", "role_title", "favorite_move", "fun_fact")

BADGE_SEEDS = [
    ("first-haul", "crew", "First Haul", "Completed your first job", "bronze", "Truck", "jobs", 1),
    ("weekend-warrior", "crew", "Weekend Warrior", "10 jobs completed", "silver", "Zap", "jobs", 10),
    ("truck-boss", "crew", "Truck Boss", "25 jobs completed", "gold", "Crown", "jobs", 25),
    ("haul-of-famer", "crew", "Haul of Famer", "50 jobs completed", "gold", "Trophy", "jobs", 50),
    ("behind-the-wheel", "crew", "Behind the Wheel", "First job worked as Driver", "bronze", "CarFront", "driver", 1),
    ("road-captain", "crew", "Road Captain", "10 jobs as Driver", "silver", "Map", "driver", 10),
    ("route-veteran", "crew", "Route Veteran", "25 jobs as Driver", "gold", "Compass", "driver", 25),
    ("helping-hand", "crew", "Helping Hand", "First job worked as Helper", "bronze", "Hand", "helper", 1),
    ("muscle-memory", "crew", "Muscle Memory", "10 jobs as Helper", "silver", "Dumbbell", "helper", 10),
    ("backbone", "crew", "Backbone", "25 jobs as Helper", "gold", "Shield", "helper", 25),
    ("two-way-player", "crew", "Two-Way Player", "5+ jobs as Driver AND 5+ jobs as Helper", "gold", "Repeat", "driver_and_helper", 5),
    ("piano-mover", "crew", "Piano Mover", "Completed a piano job", "silver", "Music", None, None),
    ("five-star-shoutout", "crew", "5-Star Shoutout", "Named in a Google review", "silver", "Star", None, None),
    ("iron-streak", "crew", "Iron Streak", "5 straight weekends worked", "silver", "Flame", None, None),
    ("zero-damage-club", "crew", "Zero Damage Club", "10 jobs with no damage claims", "gold", "ShieldCheck", None, None),
    ("stair-master", "crew", "Stair Master", "Completed a job with 3+ flights of stairs", "silver", "TrendingUp", None, None),
    ("early-bird", "crew", "Early Bird", "10 on-time morning arrivals in a row", "silver", "Sunrise", None, None),
    ("workhorse", "crew", "Workhorse", "Won a monthly jobs challenge", "silver", "Award", None, None),
    ("first-close", "sales", "First Close", "Booked your first move", "bronze", "Handshake", "closes", 1),
    ("deal-dozen", "sales", "Deal Dozen", "12 moves closed", "silver", "Layers", "closes", 12),
    ("quarter-club", "sales", "Quarter Club", "25 moves closed", "gold", "Crown", "closes", 25),
    ("speed-demon", "sales", "Speed Demon", "Fastest lead callback of the week", "silver", "Zap", None, None),
    ("big-closer", "sales", "Big Closer", "Closed a $3,000+ move", "silver", "BadgeDollarSign", None, None),
    ("hat-trick", "sales", "Hat Trick", "3 closes in one day", "silver", "Target", None, None),
    ("deposit-locksmith", "sales", "Deposit Locksmith", "5 deposits locked same-day as first call", "silver", "Lock", None, None),
    ("comeback-kid", "sales", "Comeback Kid", "Revived and closed a lead marked Lost", "silver", "RotateCcw", None, None),
    ("closer", "sales", "Closer", "Won a weekly deposits challenge", "silver", "Award", None, None),
]


def teams_for_roles(roles: Optional[List[str]]) -> List[str]:
    roles = roles or []
    return [t for t in TEAMS if any(TEAM_FOR_ROLE_MAP.get(r) == t for r in roles)]


def _badge_out(b: Dict[str, Any], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out = {"id": b["_id"], "track": b["track"], "name": b["name"], "description": b.get("description", ""),
           "rarity": b.get("rarity", "bronze"), "icon": b.get("icon", "Medal"), "auto": b.get("auto"),
           "active": b.get("active", True)}
    if extra:
        out.update(extra)
    return out


async def _active_members(team: Optional[str] = None) -> List[Dict[str, Any]]:
    docs = await mongo_db.users.find({"ghost": {"$ne": True}, "active": True}).sort("name", 1).to_list(200)
    if team:
        docs = [u for u in docs if team in teams_for_roles(u.get("roles") or [u.get("role")])]
    return docs


async def credit_counts(user_id: str) -> Dict[str, int]:
    docs = await mongo_db.job_credits.find({"user_id": user_id}).to_list(3000)
    month = _et_today()[:7]
    c = {"jobs": 0, "driver": 0, "helper": 0, "closes": 0, "jobs_month": 0, "closes_month": 0}
    for d in docs:
        if d.get("team") == "crew":
            c["jobs"] += 1
            if d.get("role_tag") == "driver":
                c["driver"] += 1
            if d.get("role_tag") == "helper":
                c["helper"] += 1
            if (d.get("date") or "").startswith(month):
                c["jobs_month"] += 1
        else:
            c["closes"] += 1
            if (d.get("date") or "").startswith(month):
                c["closes_month"] += 1
    return c


def _metric_met(counts: Dict[str, int], metric: str, threshold: int) -> bool:
    if metric == "driver_and_helper":
        return counts["driver"] >= threshold and counts["helper"] >= threshold
    return counts.get(metric, 0) >= threshold


async def award_badge(user: Dict[str, Any], badge: Dict[str, Any], by: str) -> bool:
    key = f"{user['_id']}:{badge['_id']}"
    res = await mongo_db.user_badges.update_one(
        {"_id": key},
        {"$setOnInsert": {"_id": key, "user_id": user["_id"], "badge_id": badge["_id"],
                          "awarded_at": now_iso(), "awarded_by": by}},
        upsert=True)
    if res.upserted_id is None:
        return False
    await notify(user["_id"], None, "You unlocked a badge!",
                 f"\u201c{badge['name']}\u201d ({badge.get('rarity', 'bronze').title()}) is yours \u2014 {badge.get('description', '')}",
                 "badge", {"badge_id": badge["_id"]})
    await audit({"name": by, "user_id": None}, "awarded badge", f"{badge['name']} \u2192 {user.get('name', '')}")
    return True


async def check_auto_badges(user: Dict[str, Any]) -> List[str]:
    counts = await credit_counts(user["_id"])
    badges = await mongo_db.badges.find({"active": True, "auto": {"$ne": None}}).to_list(300)
    newly = []
    for b in badges:
        a = b.get("auto") or {}
        if a.get("metric") and _metric_met(counts, a["metric"], a.get("threshold") or 1):
            if await award_badge(user, b, by="auto"):
                newly.append(b["name"])
    return newly


def _next_badge_hint(badges: List[Dict[str, Any]], counts: Dict[str, int], metrics: List[str]) -> str:
    best = None
    for b in badges:
        a = b.get("auto") or {}
        metric, thr = a.get("metric"), a.get("threshold") or 1
        if metric not in metrics or metric == "driver_and_helper":
            continue
        cur = counts.get(metric, 0)
        if cur >= thr:
            continue
        remaining = thr - (cur + 1)
        if best is None or remaining < best[0]:
            best = (remaining, b)
    if not best:
        return ""
    remaining, b = best
    if remaining <= 0:
        return f" That unlocks \u201c{b['name']}\u201d!"
    return f" {remaining} more after this one to \u201c{b['name']}\u201d."


async def create_credit_prompt(kind: str, user: Dict[str, Any], role_tag: Optional[str],
                               job_ref: str, ref_id: str, date_str: str):
    key = f"{kind}:{ref_id}:{user['_id']}"
    counts = await credit_counts(user["_id"])
    badges = await mongo_db.badges.find({"active": True, "auto": {"$ne": None}}).to_list(300)
    if kind == "crew_complete":
        team, metrics = "crew", ["jobs", role_tag]
        msg = f"{user['name']} finished \u201c{job_ref}\u201d as {(role_tag or '').title()} \u2014 give them the job tally?"
    else:
        team, metrics = "sales", ["closes"]
        msg = f"{user['name']} worked a quote that ended up booked \u2014 \u201c{job_ref}\u201d. Give them a Close tally?"
    hint = _next_badge_hint([b for b in badges if b.get("track") == team], counts, metrics)
    await mongo_db.credit_prompts.update_one(
        {"_id": key},
        {"$setOnInsert": {"_id": key, "kind": kind, "user_id": user["_id"], "user_name": user["name"],
                          "team": team, "role_tag": role_tag, "job_ref": job_ref, "ref_id": ref_id,
                          "date": date_str, "message": (msg + hint).strip(), "status": "pending",
                          "created_at": now_iso()}},
        upsert=True)


async def insert_credit(user: Dict[str, Any], team: str, role_tag: Optional[str], job_ref: str,
                        date_str: str, source: str, actor: Dict[str, Any]):
    doc = {"_id": str(uuid4()), "user_id": user["_id"], "user_name": user["name"], "team": team,
           "role_tag": role_tag if team == "crew" else None, "job_ref": job_ref, "date": date_str,
           "source": source, "credited_by": actor.get("name"), "created_at": now_iso()}
    await mongo_db.job_credits.insert_one(doc)
    tag = f", {role_tag}" if team == "crew" and role_tag else ""
    await audit(actor, "credited a job" if team == "crew" else "credited a close",
                f"{user['name']} \u2014 {job_ref} ({date_str}{tag})")
    newly = await check_auto_badges(user)
    return doc, newly


# ------- team directory & profiles

@api_router.get("/team/members")
async def team_members(request: Request):
    p = await current_principal(request)
    users = await mongo_db.users.find({"ghost": {"$ne": True}, "active": True}).sort("name", 1).to_list(200)
    badge_map = {b["_id"]: b for b in await mongo_db.badges.find({}).to_list(300)}
    photos = {d["_id"] for d in await mongo_db.profile_photos.find({}, {"_id": 1}).to_list(500)}
    members = []
    for u in users:
        prof = u.get("member_profile") or {}
        members.append({
            "id": u["_id"], "name": u.get("name", ""), "display_name": prof.get("display_name", ""),
            "nickname": prof.get("nickname", ""), "role_title": prof.get("role_title", ""),
            "teams": teams_for_roles(u.get("roles") or [u.get("role")]),
            "roles": u.get("roles") or ([u.get("role")] if u.get("role") else []),
            "titles": u.get("titles", []), "has_photo": u["_id"] in photos,
            "pinned": [_badge_out(badge_map[bid]) for bid in (u.get("pinned_badges") or []) if bid in badge_map],
        })
    return {"members": members, "me": p.get("user_id")}


@api_router.get("/team/members/{user_id}")
async def member_detail(user_id: str, request: Request):
    p = await current_principal(request)
    u = await mongo_db.users.find_one({"_id": user_id})
    is_self = p.get("user_id") == user_id
    is_owner = p["role"] == "owner"
    if not u or (u.get("ghost") and not (is_self or is_owner)):
        raise HTTPException(status_code=404, detail="No such team member.")
    tms = teams_for_roles(u.get("roles") or [u.get("role")])
    badges = await mongo_db.badges.find({"active": True}).sort("sort", 1).to_list(300)
    badge_map = {b["_id"]: b for b in badges}
    awards = {a["badge_id"]: a for a in await mongo_db.user_badges.find({"user_id": user_id}).to_list(300)}
    gallery = {t: [_badge_out(b, {"unlocked": b["_id"] in awards,
                                  "awarded_at": (awards.get(b["_id"]) or {}).get("awarded_at")})
                   for b in badges if b["track"] == t] for t in tms}
    prof = u.get("member_profile") or {}
    won = await mongo_db.challenges.find({"winners": user_id}).sort("end", -1).to_list(50)
    out = {
        "id": u["_id"], "name": u.get("name", ""), "member_since": u.get("created_at"),
        "teams": tms, "roles": u.get("roles") or ([u.get("role")] if u.get("role") else []),
        "titles": u.get("titles", []),
        "profile": {k: prof.get(k, "") for k in MEMBER_PROFILE_FIELDS},
        "has_photo": bool(await mongo_db.profile_photos.find_one({"_id": user_id}, {"_id": 1})),
        "pinned": [_badge_out(badge_map[bid]) for bid in (u.get("pinned_badges") or []) if bid in badge_map],
        "gallery": gallery,
        "unlocked_count": sum(1 for bid in awards if bid in badge_map),
        "is_self": is_self, "can_edit": is_self or is_owner, "can_see_numbers": is_self or is_owner,
        "challenge_wins": [{"id": c["_id"], "name": c["name"], "team": c["team"], "end": c.get("end"),
                            "reward": c.get("reward", {})} for c in won],
    }
    if is_self or is_owner:
        counts = await credit_counts(user_id)
        out["stats"] = {"jobs_total": counts["jobs"], "jobs_month": counts["jobs_month"],
                        "driver": counts["driver"], "helper": counts["helper"],
                        "closes_total": counts["closes"], "closes_month": counts["closes_month"]}
        progress = []
        for t in tms:
            for b in badges:
                if b["track"] != t or b["_id"] in awards or not b.get("auto"):
                    continue
                a = b["auto"]
                cur = min(counts.get("driver", 0), counts.get("helper", 0)) if a["metric"] == "driver_and_helper" \
                    else counts.get(a["metric"], 0)
                progress.append({"badge_id": b["_id"], "name": b["name"], "track": t,
                                 "metric": a["metric"], "count": cur, "threshold": a.get("threshold") or 1})
        progress.sort(key=lambda x: x["threshold"] - x["count"])
        out["progress"] = progress
    return out


class MemberProfilePayload(BaseModel):
    display_name: str = ""
    nickname: str = ""
    bio: str = ""
    role_title: str = ""
    favorite_move: str = ""
    fun_fact: str = ""


def _clean_profile(payload: MemberProfilePayload) -> Dict[str, str]:
    return {k: (getattr(payload, k) or "").strip()[:500] for k in MEMBER_PROFILE_FIELDS}


@api_router.put("/profile")
async def save_my_member_profile(payload: MemberProfilePayload, request: Request):
    p = await current_principal(request)
    if not p.get("user_id"):
        raise HTTPException(status_code=403, detail="Only user accounts have a profile.")
    prof = _clean_profile(payload)
    updates: Dict[str, Any] = {"member_profile": prof}
    if any(prof.values()):
        updates["profile_task"] = "done"
    await mongo_db.users.update_one({"_id": p["user_id"]}, {"$set": updates})
    await audit(p, "updated their team profile", p.get("name", ""))
    return {"profile": prof}


@api_router.get("/profile-task")
async def get_profile_task(request: Request):
    p = await current_principal(request)
    if not p.get("user_id"):
        return {"status": "none"}
    u = await mongo_db.users.find_one({"_id": p["user_id"]}, {"profile_task": 1})
    return {"status": (u or {}).get("profile_task") or "none", "user_id": p["user_id"]}


@api_router.post("/profile-task/done")
async def complete_profile_task(request: Request):
    p = await current_principal(request)
    if not p.get("user_id"):
        raise HTTPException(status_code=403, detail="Only user accounts have this task.")
    await mongo_db.users.update_one({"_id": p["user_id"]}, {"$set": {"profile_task": "done"}})
    return {"status": "done"}


@api_router.put("/team/members/{user_id}/moderate")
async def moderate_member_profile(user_id: str, payload: MemberProfilePayload, p: Dict[str, Any] = Depends(require_owner)):
    u = await mongo_db.users.find_one({"_id": user_id})
    if not u:
        raise HTTPException(status_code=404, detail="No such team member.")
    prof = _clean_profile(payload)
    await mongo_db.users.update_one({"_id": user_id}, {"$set": {"member_profile": prof}})
    await audit(p, "moderated a team profile", u.get("name", ""))
    return {"profile": prof}


class PinsPayload(BaseModel):
    badge_ids: List[str] = []


@api_router.put("/profile/pins")
async def save_pins(payload: PinsPayload, request: Request):
    p = await current_principal(request)
    if not p.get("user_id"):
        raise HTTPException(status_code=403, detail="Only user accounts can pin badges.")
    ids = list(dict.fromkeys(payload.badge_ids))[:3]
    unlocked = {a["badge_id"] for a in await mongo_db.user_badges.find({"user_id": p["user_id"]}).to_list(300)}
    if any(b not in unlocked for b in ids):
        raise HTTPException(status_code=422, detail="You can only pin badges you've unlocked.")
    await mongo_db.users.update_one({"_id": p["user_id"]}, {"$set": {"pinned_badges": ids}})
    return {"pinned": ids}


@api_router.post("/profile/photo")
async def upload_profile_photo(request: Request, file: UploadFile = File(...)):
    p = await current_principal(request)
    if not p.get("user_id"):
        raise HTTPException(status_code=403, detail="Only user accounts can set a photo.")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=422, detail="Only photos work here.")
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="That photo is too big (8 MB max).")
    ext = (file.filename or "photo.jpg").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "jpg"
    path = f"haulyeah-crm/profile-photos/{p['user_id']}-{uuid4()}.{ext}"
    key = await get_storage_key()
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.put(f"{STORAGE_URL}/objects/{path}",
                             headers={"X-Storage-Key": key, "Content-Type": file.content_type or "image/jpeg"},
                             content=data)
    if r.status_code >= 300:
        raise HTTPException(status_code=502, detail="The photo didn't upload. Try again.")
    await mongo_db.profile_photos.update_one(
        {"_id": p["user_id"]},
        {"$set": {"storage_path": r.json()["path"], "content_type": file.content_type or "image/jpeg",
                  "updated_at": now_iso()}},
        upsert=True)
    return {"ok": True}


@dl_router.get("/profile-photos/{user_id}")
async def serve_profile_photo(user_id: str, request: Request, auth: Optional[str] = None):
    if auth:
        await principal_from_token_string(auth)
    else:
        await current_principal(request)
    doc = await mongo_db.profile_photos.find_one({"_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="No photo.")
    key = await get_storage_key()
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(f"{STORAGE_URL}/objects/{doc['storage_path']}", headers={"X-Storage-Key": key})
    if r.status_code >= 300:
        raise HTTPException(status_code=404, detail="Photo file missing.")
    return Response(content=r.content, media_type=doc.get("content_type", "image/jpeg"))


@api_router.delete("/team/members/{user_id}/photo")
async def delete_profile_photo(user_id: str, request: Request):
    p = await current_principal(request)
    if p["role"] != "owner" and p.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not yours to remove.")
    await mongo_db.profile_photos.delete_one({"_id": user_id})
    if p["role"] == "owner" and p.get("user_id") != user_id:
        u = await mongo_db.users.find_one({"_id": user_id})
        await audit(p, "removed a profile photo", (u or {}).get("name", user_id))
    return {"ok": True}


# ------- badges

class BadgePayload(BaseModel):
    track: str
    name: str
    description: str = ""
    rarity: str = "bronze"
    icon: str = "Medal"
    auto_metric: Optional[str] = None
    auto_threshold: Optional[int] = None


class BadgePatchPayload(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    rarity: Optional[str] = None
    icon: Optional[str] = None
    active: Optional[bool] = None
    auto_metric: Optional[str] = None
    auto_threshold: Optional[int] = None


@api_router.get("/badges")
async def list_badges(role: str = Depends(require_auth)):
    docs = await mongo_db.badges.find({}).sort("sort", 1).to_list(300)
    return {"badges": [_badge_out(b) for b in docs]}


@api_router.post("/badges")
async def create_badge(payload: BadgePayload, p: Dict[str, Any] = Depends(require_owner)):
    if payload.track not in TEAMS:
        raise HTTPException(status_code=422, detail="Track must be crew or sales.")
    if payload.rarity not in RARITIES:
        raise HTTPException(status_code=422, detail="Rarity must be bronze, silver, or gold.")
    auto = None
    if payload.auto_metric:
        if payload.auto_metric not in AUTO_METRICS or not payload.auto_threshold or payload.auto_threshold < 1:
            raise HTTPException(status_code=422, detail="Auto-unlock needs a valid metric and a count of 1 or more.")
        auto = {"metric": payload.auto_metric, "threshold": int(payload.auto_threshold)}
    last = await mongo_db.badges.find_one({}, sort=[("sort", -1)])
    doc = {"_id": str(uuid4()), "track": payload.track, "name": payload.name.strip(),
           "description": payload.description.strip(), "rarity": payload.rarity, "icon": payload.icon or "Medal",
           "auto": auto, "active": True, "seeded": False, "sort": ((last or {}).get("sort") or 0) + 1,
           "created_at": now_iso()}
    await mongo_db.badges.insert_one(doc)
    await audit(p, "created a badge", f"{doc['name']} ({payload.track}, {payload.rarity})")
    return _badge_out(doc)


@api_router.patch("/badges/{badge_id}")
async def patch_badge(badge_id: str, payload: BadgePatchPayload, p: Dict[str, Any] = Depends(require_owner)):
    b = await mongo_db.badges.find_one({"_id": badge_id})
    if not b:
        raise HTTPException(status_code=404, detail="No such badge.")
    updates: Dict[str, Any] = {}
    if payload.name is not None and payload.name.strip():
        updates["name"] = payload.name.strip()
    if payload.description is not None:
        updates["description"] = payload.description.strip()
    if payload.rarity is not None:
        if payload.rarity not in RARITIES:
            raise HTTPException(status_code=422, detail="Rarity must be bronze, silver, or gold.")
        updates["rarity"] = payload.rarity
    if payload.icon is not None:
        updates["icon"] = payload.icon
    if payload.active is not None:
        updates["active"] = payload.active
    if payload.auto_metric is not None:
        if payload.auto_metric == "":
            updates["auto"] = None
        elif payload.auto_metric in AUTO_METRICS and payload.auto_threshold and payload.auto_threshold >= 1:
            updates["auto"] = {"metric": payload.auto_metric, "threshold": int(payload.auto_threshold)}
        else:
            raise HTTPException(status_code=422, detail="Auto-unlock needs a valid metric and a count of 1 or more.")
    if updates:
        await mongo_db.badges.update_one({"_id": badge_id}, {"$set": updates})
        await audit(p, "edited a badge", b["name"], {"changes": list(updates.keys())})
    fresh = await mongo_db.badges.find_one({"_id": badge_id})
    return _badge_out(fresh)


class AwardPayload(BaseModel):
    user_id: str


@api_router.post("/badges/{badge_id}/award")
async def manual_award_badge(badge_id: str, payload: AwardPayload, p: Dict[str, Any] = Depends(require_owner)):
    b = await mongo_db.badges.find_one({"_id": badge_id})
    u = await mongo_db.users.find_one({"_id": payload.user_id})
    if not b or not u:
        raise HTTPException(status_code=404, detail="No such badge or member.")
    awarded = await award_badge(u, b, by=p.get("name") or "owner")
    return {"awarded": awarded, "badge": b["name"], "user": u["name"]}


@api_router.delete("/badges/{badge_id}/award/{user_id}")
async def revoke_badge(badge_id: str, user_id: str, p: Dict[str, Any] = Depends(require_owner)):
    res = await mongo_db.user_badges.delete_one({"_id": f"{user_id}:{badge_id}"})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="They don't have that badge.")
    await mongo_db.users.update_one({"_id": user_id}, {"$pull": {"pinned_badges": badge_id}})
    u = await mongo_db.users.find_one({"_id": user_id})
    b = await mongo_db.badges.find_one({"_id": badge_id})
    await audit(p, "took back a badge", f"{(b or {}).get('name', badge_id)} \u2190 {(u or {}).get('name', user_id)}")
    return {"ok": True}


# ------- job credits & approval prompts

class CreditPayload(BaseModel):
    user_id: str
    team: str
    role_tag: Optional[str] = None
    job_ref: str
    date: str


@api_router.get("/credits")
async def list_credits(user_id: Optional[str] = None, limit: int = 100, p: Dict[str, Any] = Depends(require_owner)):
    q = {"user_id": user_id} if user_id else {}
    docs = await mongo_db.job_credits.find(q).sort("created_at", -1).to_list(min(limit, 500))
    return {"credits": [{"id": d["_id"], "user_id": d["user_id"], "user_name": d.get("user_name", ""),
                         "team": d["team"], "role_tag": d.get("role_tag"), "job_ref": d.get("job_ref", ""),
                         "date": d.get("date"), "source": d.get("source"), "credited_by": d.get("credited_by"),
                         "created_at": d["created_at"]} for d in docs]}


@api_router.post("/credits")
async def add_credit(payload: CreditPayload, p: Dict[str, Any] = Depends(require_owner)):
    if payload.team not in TEAMS:
        raise HTTPException(status_code=422, detail="Team must be crew or sales.")
    if payload.team == "crew" and payload.role_tag not in ("driver", "helper"):
        raise HTTPException(status_code=422, detail="Pick Driver or Helper for crew credits.")
    u = await mongo_db.users.find_one({"_id": payload.user_id})
    if not u:
        raise HTTPException(status_code=404, detail="No such member.")
    doc, newly = await insert_credit(u, payload.team, payload.role_tag, payload.job_ref.strip() or "Job",
                                     payload.date, "manual", p)
    return {"credit": {"id": doc["_id"]}, "newly_unlocked": newly}


@api_router.delete("/credits/{credit_id}")
async def delete_credit(credit_id: str, p: Dict[str, Any] = Depends(require_owner)):
    d = await mongo_db.job_credits.find_one({"_id": credit_id})
    if not d:
        raise HTTPException(status_code=404, detail="No such credit.")
    await mongo_db.job_credits.delete_one({"_id": credit_id})
    await audit(p, "removed a job credit", f"{d.get('user_name', '')} \u2014 {d.get('job_ref', '')} ({d.get('date', '')})")
    return {"ok": True}


@api_router.get("/credit-prompts")
async def list_credit_prompts(p: Dict[str, Any] = Depends(require_owner)):
    docs = await mongo_db.credit_prompts.find({"status": "pending"}).sort("created_at", -1).to_list(100)
    return {"prompts": [{"id": d["_id"], "kind": d["kind"], "user_id": d["user_id"], "user_name": d["user_name"],
                         "team": d["team"], "role_tag": d.get("role_tag"), "job_ref": d.get("job_ref", ""),
                         "date": d.get("date"), "message": d.get("message", ""), "created_at": d["created_at"]}
                        for d in docs]}


class PromptResolvePayload(BaseModel):
    approve: bool


@api_router.post("/credit-prompts/{prompt_id:path}/resolve")
async def resolve_credit_prompt(prompt_id: str, payload: PromptResolvePayload, p: Dict[str, Any] = Depends(require_owner)):
    d = await mongo_db.credit_prompts.find_one({"_id": prompt_id, "status": "pending"})
    if not d:
        raise HTTPException(status_code=404, detail="That one's already handled.")
    newly: List[str] = []
    if payload.approve:
        u = await mongo_db.users.find_one({"_id": d["user_id"]})
        if not u:
            raise HTTPException(status_code=404, detail="That member's account is gone.")
        _, newly = await insert_credit(u, d["team"], d.get("role_tag"), d.get("job_ref", "Job"),
                                       d.get("date") or _et_today(), "prompt", p)
    else:
        await audit(p, "skipped a job credit", f"{d.get('user_name', '')} \u2014 {d.get('job_ref', '')}")
    await mongo_db.credit_prompts.update_one(
        {"_id": prompt_id},
        {"$set": {"status": "approved" if payload.approve else "dismissed", "resolved_at": now_iso()}})
    return {"ok": True, "newly_unlocked": newly}


# ------- leaderboard & hall of fame

def _next_month(m: str) -> str:
    y, mm = int(m[:4]), int(m[5:7])
    mm += 1
    if mm > 12:
        y, mm = y + 1, 1
    return f"{y:04d}-{mm:02d}"


async def ensure_hall_of_fame():
    first = await mongo_db.job_credits.find_one({}, sort=[("date", 1)])
    if not first or not first.get("date"):
        return
    cur = _et_today()[:7]
    m = first["date"][:7]
    while m < cur:
        for team in TEAMS:
            _id = f"{m}:{team}"
            if await mongo_db.hall_of_fame.find_one({"_id": _id}):
                continue
            docs = await mongo_db.job_credits.find({"team": team, "date": {"$regex": f"^{m}"}}).to_list(5000)
            if not docs:
                continue
            counts: Dict[str, int] = {}
            for d in docs:
                counts[d["user_id"]] = counts.get(d["user_id"], 0) + 1
            uid = max(counts, key=lambda k: counts[k])
            name = next((d.get("user_name", "") for d in docs if d["user_id"] == uid), "")
            await mongo_db.hall_of_fame.insert_one({"_id": _id, "month": m, "team": team, "winner_id": uid,
                                                    "winner_name": name, "count": counts[uid],
                                                    "archived_at": now_iso()})
        m = _next_month(m)


@api_router.get("/leaderboard")
async def leaderboard(request: Request, month: Optional[str] = None):
    await current_principal(request)
    await ensure_hall_of_fame()
    month = (month or _et_today()[:7])[:7]
    out: Dict[str, Any] = {"month": month}
    active_ids = {u["_id"] for u in await _active_members()}
    for team in TEAMS:
        docs = await mongo_db.job_credits.find({"team": team, "date": {"$regex": f"^{month}"}}).to_list(5000)
        counts: Dict[str, Dict[str, Any]] = {}
        for d in docs:
            row = counts.setdefault(d["user_id"], {"user_id": d["user_id"], "name": d.get("user_name", ""), "count": 0})
            row["count"] += 1
        rows = [r for r in counts.values() if r["user_id"] in active_ids]
        rows.sort(key=lambda r: (-r["count"], r["name"]))
        out[team] = rows
    return out


@api_router.get("/hall-of-fame")
async def hall_of_fame(request: Request):
    await current_principal(request)
    await ensure_hall_of_fame()
    docs = await mongo_db.hall_of_fame.find({}).sort("month", -1).to_list(200)
    return {"entries": [{"month": d["month"], "team": d["team"], "winner_id": d["winner_id"],
                         "winner_name": d["winner_name"], "count": d["count"]} for d in docs]}


# ------- challenges

class ChallengePayload(BaseModel):
    name: str
    description: str = ""
    team: str
    type: str
    metric: str
    target: Optional[int] = None
    start: str
    end: str
    reward_kind: str
    reward_badge_id: Optional[str] = None
    reward_title: Optional[str] = None


async def challenge_progress(ch: Dict[str, Any]) -> List[Dict[str, Any]]:
    members = await _active_members(ch["team"])
    if ch.get("metric") == "job_credits":
        docs = await mongo_db.job_credits.find(
            {"team": ch["team"], "date": {"$gte": ch["start"], "$lte": ch["end"]}}).to_list(5000)
        counts: Dict[str, int] = {}
        for d in docs:
            counts[d["user_id"]] = counts.get(d["user_id"], 0) + 1
    else:
        counts = {k: int(v) for k, v in (ch.get("verified") or {}).items()}
    rows = [{"user_id": m["_id"], "name": m["name"], "value": counts.get(m["_id"], 0)} for m in members]
    rows.sort(key=lambda r: (-r["value"], r["name"]))
    return rows


async def _award_challenge(ch: Dict[str, Any], winners: List[str], rows: List[Dict[str, Any]], actor: Dict[str, Any]):
    reward = ch.get("reward") or {}
    for uid in winners:
        u = await mongo_db.users.find_one({"_id": uid})
        if not u:
            continue
        if reward.get("kind") == "badge" and reward.get("badge_id"):
            b = await mongo_db.badges.find_one({"_id": reward["badge_id"]})
            if b:
                await award_badge(u, b, by=f"challenge: {ch['name']}")
        elif reward.get("kind") == "title" and reward.get("title"):
            await mongo_db.users.update_one({"_id": uid}, {"$addToSet": {"titles": reward["title"]}})
            await notify(uid, None, "You earned a title!",
                         f"You won \u201c{ch['name']}\u201d \u2014 the \u201c{reward['title']}\u201d title is on your profile now.",
                         "challenge")
    await mongo_db.challenges.update_one(
        {"_id": ch["_id"]},
        {"$set": {"status": "awarded" if winners else "ended", "winners": winners, "final": rows,
                  "awarded_at": now_iso()}})
    await audit(actor, "closed a challenge", f"{ch['name']} \u2014 {len(winners)} winner(s)")


async def finalize_due_challenges():
    today = _et_today()
    due = await mongo_db.challenges.find({"status": "active", "end": {"$lt": today}}).to_list(100)
    for ch in due:
        rows = await challenge_progress(ch)
        if ch.get("metric") == "owner_verified":
            await mongo_db.challenges.update_one({"_id": ch["_id"]}, {"$set": {"status": "needs_verify"}})
            await notify(None, "owner", "Challenge needs your call",
                         f"\u201c{ch['name']}\u201d just ended. Confirm the winner(s) in Team HQ \u2192 Challenges before the reward goes out.",
                         "challenge", {"challenge_id": ch["_id"]})
            continue
        if ch.get("type") == "individual":
            target = ch.get("target") or 0
            winners = [r["user_id"] for r in rows if target and r["value"] >= target]
        else:
            top = rows[0]["value"] if rows else 0
            winners = [r["user_id"] for r in rows if top > 0 and r["value"] == top]
        await _award_challenge(ch, winners, rows, {"name": "auto", "user_id": None})


def _challenge_out(ch: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    name_map = {r["user_id"]: r["name"] for r in rows}
    return {"id": ch["_id"], "name": ch["name"], "description": ch.get("description", ""),
            "team": ch["team"], "type": ch["type"], "metric": ch["metric"], "target": ch.get("target"),
            "start": ch["start"], "end": ch["end"], "reward": ch.get("reward", {}),
            "status": ch.get("status", "active"),
            "winners": [{"user_id": w, "name": name_map.get(w, "")} for w in ch.get("winners", [])],
            "progress": rows}


@api_router.get("/challenges")
async def list_challenges(request: Request):
    p = await current_principal(request)
    await finalize_due_challenges()
    if p["role"] in ("owner", "marketing"):
        visible = list(TEAMS)
    else:
        visible = teams_for_roles(p.get("roles") or [p["role"]])
    docs = await mongo_db.challenges.find({"team": {"$in": visible}}).sort("end", -1).to_list(100)
    out = []
    for ch in docs:
        rows = ch.get("final") if ch.get("status") in ("awarded", "ended") and ch.get("final") else await challenge_progress(ch)
        out.append(_challenge_out(ch, rows))
    return {"challenges": out, "me": p.get("user_id"), "is_owner": p["role"] == "owner"}


def _validate_challenge(payload: ChallengePayload) -> Dict[str, Any]:
    if payload.team not in TEAMS:
        raise HTTPException(status_code=422, detail="Team must be crew or sales.")
    if payload.type not in ("individual", "competition"):
        raise HTTPException(status_code=422, detail="Type must be individual or competition.")
    if payload.metric not in ("job_credits", "owner_verified"):
        raise HTTPException(status_code=422, detail="Metric must be job_credits or owner_verified.")
    if payload.type == "individual" and (not payload.target or payload.target < 1):
        raise HTTPException(status_code=422, detail="Individual challenges need a goal count of 1 or more.")
    if not payload.start or not payload.end or payload.end < payload.start:
        raise HTTPException(status_code=422, detail="Check the start and end dates.")
    if payload.reward_kind == "badge" and not payload.reward_badge_id:
        raise HTTPException(status_code=422, detail="Pick the badge to give out.")
    if payload.reward_kind == "title" and not (payload.reward_title or "").strip():
        raise HTTPException(status_code=422, detail="Type the title to give out.")
    if payload.reward_kind not in ("badge", "title"):
        raise HTTPException(status_code=422, detail="Reward must be a badge or a title.")
    reward = {"kind": payload.reward_kind}
    if payload.reward_kind == "badge":
        reward["badge_id"] = payload.reward_badge_id
    else:
        reward["title"] = payload.reward_title.strip()
    return reward


@api_router.post("/challenges")
async def create_challenge(payload: ChallengePayload, p: Dict[str, Any] = Depends(require_owner)):
    reward = _validate_challenge(payload)
    doc = {"_id": str(uuid4()), "name": payload.name.strip(), "description": payload.description.strip(),
           "team": payload.team, "type": payload.type, "metric": payload.metric,
           "target": payload.target if payload.type == "individual" else None,
           "start": payload.start, "end": payload.end, "reward": reward, "status": "active",
           "verified": {}, "winners": [], "created_by": p.get("name"), "created_at": now_iso()}
    await mongo_db.challenges.insert_one(doc)
    await audit(p, "created a challenge", f"{doc['name']} ({payload.team}, {payload.type})")
    return _challenge_out(doc, await challenge_progress(doc))


@api_router.patch("/challenges/{challenge_id}")
async def patch_challenge(challenge_id: str, payload: ChallengePayload, p: Dict[str, Any] = Depends(require_owner)):
    ch = await mongo_db.challenges.find_one({"_id": challenge_id})
    if not ch:
        raise HTTPException(status_code=404, detail="No such challenge.")
    if ch.get("status") == "awarded":
        raise HTTPException(status_code=422, detail="That challenge already paid out \u2014 make a new one instead.")
    reward = _validate_challenge(payload)
    await mongo_db.challenges.update_one(
        {"_id": challenge_id},
        {"$set": {"name": payload.name.strip(), "description": payload.description.strip(),
                  "team": payload.team, "type": payload.type, "metric": payload.metric,
                  "target": payload.target if payload.type == "individual" else None,
                  "start": payload.start, "end": payload.end, "reward": reward}})
    await audit(p, "edited a challenge", payload.name.strip())
    fresh = await mongo_db.challenges.find_one({"_id": challenge_id})
    return _challenge_out(fresh, await challenge_progress(fresh))


@api_router.delete("/challenges/{challenge_id}")
async def delete_challenge(challenge_id: str, p: Dict[str, Any] = Depends(require_owner)):
    ch = await mongo_db.challenges.find_one({"_id": challenge_id})
    if not ch:
        raise HTTPException(status_code=404, detail="No such challenge.")
    await mongo_db.challenges.delete_one({"_id": challenge_id})
    await audit(p, "deleted a challenge", ch.get("name", challenge_id))
    return {"ok": True}


class VerifyPayload(BaseModel):
    user_id: str
    value: int


@api_router.post("/challenges/{challenge_id}/verify")
async def verify_challenge_progress(challenge_id: str, payload: VerifyPayload, p: Dict[str, Any] = Depends(require_owner)):
    ch = await mongo_db.challenges.find_one({"_id": challenge_id})
    if not ch:
        raise HTTPException(status_code=404, detail="No such challenge.")
    if ch.get("metric") != "owner_verified":
        raise HTTPException(status_code=422, detail="This challenge tracks itself from job credits.")
    if ch.get("status") not in ("active", "needs_verify"):
        raise HTTPException(status_code=422, detail="That challenge is already closed.")
    await mongo_db.challenges.update_one({"_id": challenge_id},
                                         {"$set": {f"verified.{payload.user_id}": max(0, int(payload.value))}})
    u = await mongo_db.users.find_one({"_id": payload.user_id})
    await audit(p, "verified challenge progress", f"{ch['name']} \u2014 {(u or {}).get('name', '')}: {payload.value}")
    fresh = await mongo_db.challenges.find_one({"_id": challenge_id})
    return _challenge_out(fresh, await challenge_progress(fresh))


class AwardChallengePayload(BaseModel):
    winners: List[str] = []


@api_router.post("/challenges/{challenge_id}/award")
async def award_challenge(challenge_id: str, payload: AwardChallengePayload, p: Dict[str, Any] = Depends(require_owner)):
    ch = await mongo_db.challenges.find_one({"_id": challenge_id})
    if not ch:
        raise HTTPException(status_code=404, detail="No such challenge.")
    if ch.get("status") not in ("active", "needs_verify"):
        raise HTTPException(status_code=422, detail="That challenge is already closed.")
    rows = await challenge_progress(ch)
    valid_ids = {r["user_id"] for r in rows}
    winners = [w for w in payload.winners if w in valid_ids]
    await _award_challenge(ch, winners, rows, p)
    fresh = await mongo_db.challenges.find_one({"_id": challenge_id})
    return _challenge_out(fresh, rows)


# ------- owner insights

@api_router.get("/admin/crew-comparison")
async def crew_comparison(p: Dict[str, Any] = Depends(require_owner)):
    members = await _active_members("crew")
    rows = []
    for m in members:
        c = await credit_counts(m["_id"])
        rows.append({"user_id": m["_id"], "name": m["name"], "driver": c["driver"], "helper": c["helper"],
                     "total": c["jobs"]})
    rows.sort(key=lambda r: (-r["total"], r["name"]))
    return {"rows": rows}


async def seed_team_module():
    for i, (slug, track, name, desc, rarity, icon, metric, thr) in enumerate(BADGE_SEEDS):
        await mongo_db.badges.update_one(
            {"_id": slug},
            {"$setOnInsert": {"_id": slug, "track": track, "name": name, "description": desc, "rarity": rarity,
                              "icon": icon, "auto": ({"metric": metric, "threshold": thr} if metric else None),
                              "active": True, "seeded": True, "sort": i, "created_at": now_iso()}},
            upsert=True)
    for u in await mongo_db.users.find({"profile_task": {"$exists": False}}).to_list(300):
        prof = u.get("member_profile") or {}
        done = any((prof.get(k) or "").strip() for k in MEMBER_PROFILE_FIELDS)
        await mongo_db.users.update_one({"_id": u["_id"]}, {"$set": {"profile_task": "done" if done else "open"}})
        if not done:
            await notify(u["_id"], None, "First task: set up your profile",
                         "Head to the To-Do page — your first task is adding a photo, a nickname, and a fun fact to your team profile.",
                         "task")
    if await mongo_db.challenges.count_documents({}) == 0:
        today = datetime.strptime(_et_today(), "%Y-%m-%d").date()
        month_start = today.replace(day=1)
        month_end = datetime.strptime(_next_month(_et_today()[:7]) + "-01", "%Y-%m-%d").date() - timedelta(days=1)
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        month_name = today.strftime("%B")
        seeds = [
            {"name": f"Full House {month_name}", "description": "Complete 6 jobs this month and the Workhorse badge is yours.",
             "team": "crew", "type": "individual", "metric": "job_credits", "target": 6,
             "start": month_start.isoformat(), "end": month_end.isoformat(),
             "reward": {"kind": "badge", "badge_id": "workhorse"}},
            {"name": "King of the Weekend", "description": "Most jobs completed this month takes the Top Hauler title.",
             "team": "crew", "type": "competition", "metric": "job_credits", "target": None,
             "start": month_start.isoformat(), "end": month_end.isoformat(),
             "reward": {"kind": "title", "title": "Top Hauler"}},
            {"name": "Six-Pack Sprint", "description": "Lock 3 deposits this week to unlock the Closer badge. The owner confirms these.",
             "team": "sales", "type": "individual", "metric": "owner_verified", "target": 3,
             "start": week_start.isoformat(), "end": week_end.isoformat(),
             "reward": {"kind": "badge", "badge_id": "closer"}},
            {"name": "Whale Hunt", "description": "Biggest single move closed this month wins the Big Fish title. The owner confirms the winner.",
             "team": "sales", "type": "competition", "metric": "owner_verified", "target": None,
             "start": month_start.isoformat(), "end": month_end.isoformat(),
             "reward": {"kind": "title", "title": "Big Fish"}},
        ]
        for s in seeds:
            await mongo_db.challenges.insert_one({"_id": str(uuid4()), **s, "status": "active", "verified": {},
                                                  "winners": [], "created_by": "seed", "created_at": now_iso()})


# ================================================================ sales commissions

MOVE_TYPES = ("Labor-only", "Studio", "1-bedroom", "2-bedroom", "3-bedroom", "4+")
COMMISSION_RATE_DEFAULTS = {
    "small_flat": {"Labor-only": 25.0, "Studio": 40.0, "1-bedroom": 40.0, "2-bedroom": 60.0, "3-bedroom": 60.0, "4+": 60.0},
    "medium_min": 1500.0, "medium_pct": 10.0, "big_min": 3000.0, "big_pct": 12.0,
}


async def get_commission_rates() -> Dict[str, Any]:
    doc = await mongo_db.settings.find_one({"_id": "commission_rates"}) or {}
    rates = {**COMMISSION_RATE_DEFAULTS, **{k: v for k, v in doc.items() if k in ("medium_min", "medium_pct", "big_min", "big_pct")}}
    rates["small_flat"] = {**COMMISSION_RATE_DEFAULTS["small_flat"], **(doc.get("small_flat") or {})}
    return rates


def commission_amount(quote: Any, move_type: Optional[str], rates: Dict[str, Any]) -> float:
    try:
        q = float(quote or 0)
    except (TypeError, ValueError):
        q = 0.0
    if q <= 0:
        return 0.0
    if q >= rates["big_min"]:
        return round(q * rates["big_pct"] / 100, 2)
    if q >= rates["medium_min"]:
        return round(q * rates["medium_pct"] / 100, 2)
    return float(rates["small_flat"].get(move_type or "", 0) or 0)


def _commission_status(d: Dict[str, Any]) -> Optional[str]:
    if not d.get("closed_by"):
        return None
    if d.get("refunded"):
        return "voided"
    if d.get("fully_paid"):
        return "locked"
    if d.get("deposit_paid"):
        return "pending"
    return "none"


def _require_comm_role(p: Dict[str, Any]):
    if p["role"] not in ("owner", "sales"):
        raise HTTPException(status_code=403, detail="You don't have access to commissions.")


def _attr_out(d: Dict[str, Any]) -> Dict[str, Any]:
    return {"lead_name": d.get("lead_name", ""), "quote_sent_by": d.get("quote_sent_by") or "",
            "closed_by": d.get("closed_by") or "", "move_type": d.get("move_type") or "",
            "quote_amount": d.get("quote_amount"), "job_date": d.get("job_date") or "",
            "deposit_paid": bool(d.get("deposit_paid")), "deposit_paid_at": d.get("deposit_paid_at") or "",
            "fully_paid": bool(d.get("fully_paid")), "fully_paid_at": d.get("fully_paid_at") or "",
            "refunded": bool(d.get("refunded"))}


class AttributionPayload(BaseModel):
    lead_name: Optional[str] = None
    quote_sent_by: Optional[str] = None
    closed_by: Optional[str] = None
    move_type: Optional[str] = None
    quote_amount: Optional[float] = None
    job_date: Optional[str] = None
    deposit_paid: Optional[bool] = None
    deposit_paid_at: Optional[str] = None
    fully_paid: Optional[bool] = None
    fully_paid_at: Optional[str] = None
    refunded: Optional[bool] = None


@api_router.get("/commissions/attribution/{lead_id}")
async def get_attribution(lead_id: str, request: Request):
    p = await current_principal(request)
    _require_comm_role(p)
    d = await mongo_db.lead_commissions.find_one({"_id": lead_id}) or {}
    rates = await get_commission_rates()
    return {"attribution": _attr_out(d), "status": _commission_status(d),
            "commission": commission_amount(d.get("quote_amount"), d.get("move_type"), rates)}


@api_router.put("/commissions/attribution/{lead_id}")
async def save_attribution(lead_id: str, payload: AttributionPayload, request: Request):
    p = await current_principal(request)
    _require_comm_role(p)
    payment_fields = ("deposit_paid", "deposit_paid_at", "fully_paid", "fully_paid_at", "refunded")
    if p["role"] != "owner" and any(getattr(payload, k) is not None for k in payment_fields):
        raise HTTPException(status_code=403, detail="Only the owner can change payment flags.")
    updates: Dict[str, Any] = {}
    if payload.lead_name is not None:
        updates["lead_name"] = payload.lead_name.strip()[:200]
    for k in ("quote_sent_by", "closed_by"):
        v = getattr(payload, k)
        if v is not None:
            if v and not await mongo_db.users.find_one({"_id": v}):
                raise HTTPException(status_code=404, detail="That team member doesn't exist.")
            updates[k] = v or None
    if payload.move_type is not None:
        if payload.move_type and payload.move_type not in MOVE_TYPES:
            raise HTTPException(status_code=422, detail="Pick a real move type.")
        updates["move_type"] = payload.move_type or None
    if payload.quote_amount is not None:
        if payload.quote_amount < 0:
            raise HTTPException(status_code=422, detail="Quote amount can't be negative.")
        updates["quote_amount"] = round(float(payload.quote_amount), 2)
    if payload.job_date is not None:
        updates["job_date"] = payload.job_date
    if p["role"] == "owner":
        d0 = await mongo_db.lead_commissions.find_one({"_id": lead_id}) or {}
        if payload.deposit_paid is not None:
            updates["deposit_paid"] = payload.deposit_paid
            updates["deposit_paid_at"] = (payload.deposit_paid_at or d0.get("deposit_paid_at") or _et_today()) if payload.deposit_paid else None
        if payload.fully_paid is not None:
            updates["fully_paid"] = payload.fully_paid
            updates["fully_paid_at"] = (payload.fully_paid_at or d0.get("fully_paid_at") or _et_today()) if payload.fully_paid else None
        if payload.refunded is not None:
            updates["refunded"] = payload.refunded
    updates["updated_at"] = now_iso()
    updates["updated_by"] = p.get("name")
    await mongo_db.lead_commissions.update_one({"_id": lead_id}, {"$set": updates}, upsert=True)
    d = await mongo_db.lead_commissions.find_one({"_id": lead_id})
    await audit(p, "updated commission info", d.get("lead_name") or lead_id)
    rates = await get_commission_rates()
    return {"attribution": _attr_out(d), "status": _commission_status(d),
            "commission": commission_amount(d.get("quote_amount"), d.get("move_type"), rates)}


@api_router.get("/commissions/rates")
async def commission_rates(request: Request):
    p = await current_principal(request)
    _require_comm_role(p)
    return {"rates": await get_commission_rates(), "move_types": list(MOVE_TYPES)}


class CommissionRatesPayload(BaseModel):
    small_flat: Dict[str, float]
    medium_min: float
    medium_pct: float
    big_min: float
    big_pct: float


@api_router.put("/commissions/rates")
async def save_commission_rates(payload: CommissionRatesPayload, p: Dict[str, Any] = Depends(require_owner)):
    if payload.medium_min <= 0 or payload.big_min <= payload.medium_min:
        raise HTTPException(status_code=422, detail="Big-move minimum must be higher than the medium-move minimum.")
    if not (0 <= payload.medium_pct <= 100) or not (0 <= payload.big_pct <= 100):
        raise HTTPException(status_code=422, detail="Percentages must be between 0 and 100.")
    flat = {k: max(0.0, float(v)) for k, v in payload.small_flat.items() if k in MOVE_TYPES}
    await mongo_db.settings.update_one(
        {"_id": "commission_rates"},
        {"$set": {"small_flat": flat, "medium_min": payload.medium_min, "medium_pct": payload.medium_pct,
                  "big_min": payload.big_min, "big_pct": payload.big_pct, "updated_at": now_iso()}},
        upsert=True)
    await audit(p, "changed the commission rate table", "")
    return {"rates": await get_commission_rates()}


@api_router.get("/commissions/report")
async def commissions_report(request: Request, start: Optional[str] = None, end: Optional[str] = None):
    p = await current_principal(request)
    _require_comm_role(p)
    rates = await get_commission_rates()
    q: Dict[str, Any] = {"closed_by": {"$nin": [None, ""]}}
    if p["role"] != "owner":
        if not p.get("user_id"):
            raise HTTPException(status_code=403, detail="Log in with your own account to see commissions.")
        q["closed_by"] = p["user_id"]
    docs = await mongo_db.lead_commissions.find(q).to_list(3000)
    names = {u["_id"]: u.get("name", "") for u in await mongo_db.users.find({}, {"name": 1}).to_list(300)}
    rows = []
    for d in docs:
        status = _commission_status(d)
        if status in (None, "none"):
            continue
        earn_date = (d.get("deposit_paid_at") or d.get("job_date") or (d.get("updated_at") or "")[:10])[:10]
        if start and earn_date < start:
            continue
        if end and earn_date > end:
            continue
        rows.append({"lead_id": d["_id"], "lead_name": d.get("lead_name", ""), "closed_by": d.get("closed_by"),
                     "closed_by_name": names.get(d.get("closed_by"), ""), "move_type": d.get("move_type") or "",
                     "quote_amount": d.get("quote_amount") or 0,
                     "commission": commission_amount(d.get("quote_amount"), d.get("move_type"), rates),
                     "status": status, "earn_date": earn_date, "job_date": d.get("job_date") or "",
                     "fully_paid_at": d.get("fully_paid_at") or ""})
    rows.sort(key=lambda r: r["earn_date"], reverse=True)
    reps: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        rep = reps.setdefault(r["closed_by"], {"user_id": r["closed_by"], "name": r["closed_by_name"],
                                               "pending": 0.0, "locked": 0.0, "voided": 0.0, "jobs": 0})
        rep["jobs"] += 1
        rep[r["status"]] = round(rep[r["status"]] + r["commission"], 2)
    rep_rows = sorted(reps.values(), key=lambda x: -(x["pending"] + x["locked"]))
    return {"rows": rows, "reps": rep_rows, "is_owner": p["role"] == "owner"}


async def mark_lead_commission_payment(lead_id: str, stage: str):
    try:
        d = await mongo_db.lead_commissions.find_one({"_id": lead_id}) or {}
        upd: Dict[str, Any] = {f"{stage}_paid": True}
        if not d.get(f"{stage}_paid_at"):
            upd[f"{stage}_paid_at"] = _et_today()
        await mongo_db.lead_commissions.update_one({"_id": lead_id}, {"$set": upd}, upsert=True)
    except Exception as exc:
        logger.warning("commission %s flip failed for %s: %s", stage, lead_id, exc)


# ================================================================ availability overview (owner)

class OwnerAvailabilityPayload(BaseModel):
    user_id: str
    date: str
    available: bool


@api_router.post("/availability/set")
async def owner_set_availability(payload: OwnerAvailabilityPayload, p: Dict[str, Any] = Depends(require_owner)):
    u = await mongo_db.users.find_one({"_id": payload.user_id})
    if not u:
        raise HTTPException(status_code=404, detail="No such team member.")
    await mongo_db.availability.update_one(
        {"_id": f"{payload.user_id}:{payload.date}"},
        {"$set": {"user_id": payload.user_id, "name": u.get("name"), "date": payload.date,
                  "available": payload.available, "updated_at": now_iso(), "set_by": p.get("name")}},
        upsert=True)
    return {"ok": True}


@api_router.get("/availability/overview")
async def availability_overview(start: str, end: str, p: Dict[str, Any] = Depends(require_owner)):
    crew = await _active_members("crew")
    off_docs = await mongo_db.availability.find(
        {"date": {"$gte": start, "$lte": end}, "available": False}).to_list(2000)
    off_by_date: Dict[str, List[Dict[str, str]]] = {}
    for d in off_docs:
        off_by_date.setdefault(d["date"], []).append({"user_id": d["user_id"], "name": d.get("name", "")})
    assignments = await mongo_db.assignments.find({"job_date": {"$gte": start, "$lte": end}}).to_list(500)
    needed_by_date: Dict[str, int] = {}
    jobs_by_date: Dict[str, int] = {}
    for a in assignments:
        dt = a.get("job_date")
        jobs_by_date[dt] = jobs_by_date.get(dt, 0) + 1
        needed_by_date[dt] = needed_by_date.get(dt, 0) + max(len(a.get("crew") or []), 2)
    days = []
    cur = datetime.strptime(start, "%Y-%m-%d").date()
    last = datetime.strptime(end, "%Y-%m-%d").date()
    while cur <= last:
        dt = cur.isoformat()
        off = off_by_date.get(dt, [])
        off_ids = {o["user_id"] for o in off}
        available = [{"user_id": u["_id"], "name": u["name"]} for u in crew if u["_id"] not in off_ids]
        needed = needed_by_date.get(dt, 0)
        days.append({"date": dt, "weekend": cur.weekday() >= 5, "off": off, "available": available,
                     "jobs": jobs_by_date.get(dt, 0), "needed": needed,
                     "short": needed > 0 and len(available) < needed})
        cur += timedelta(days=1)
    return {"days": days, "crew_total": len(crew),
            "crew": [{"user_id": u["_id"], "name": u["name"]} for u in crew]}


# ================================================================ notification center: alerts

ALERT_ROLES = ("owner", "sales", "marketing")
ALERT_KINDS = ("new_lead", "booked", "review", "custom")


async def create_alert(kind: str, title: str, body: str = "", lead_id: Optional[str] = None,
                       lead_name: Optional[str] = None, source: str = "app",
                       created_at: Optional[str] = None, dedupe_key: Optional[str] = None):
    _id = dedupe_key or str(uuid4())
    doc = {"_id": _id, "kind": kind, "title": title[:200], "body": (body or "")[:500], "lead_id": lead_id,
           "lead_name": lead_name, "source": source, "created_at": created_at or now_iso()}
    try:
        await mongo_db.alerts.update_one({"_id": _id}, {"$setOnInsert": doc}, upsert=True)
    except Exception as exc:
        logger.warning("create_alert failed: %s", exc)


def _alert_gate(p: Dict[str, Any]):
    if p["role"] not in ALERT_ROLES:
        raise HTTPException(status_code=403, detail="You don't have access to notifications.")


def _read_key(p: Dict[str, Any]) -> str:
    return p.get("user_id") or f"role:{p['role']}"


@api_router.get("/alerts")
async def list_alerts(request: Request, limit: int = 100):
    p = await current_principal(request)
    _alert_gate(p)
    docs = await mongo_db.alerts.find({}).sort("created_at", -1).to_list(min(limit, 200))
    lead_ids = [d["lead_id"] for d in docs if d.get("lead_id")]
    metas = {m["_id"]: m for m in await mongo_db.lead_meta.find({"_id": {"$in": lead_ids}}).to_list(500)} if lead_ids else {}
    marker = await mongo_db.alerts_read.find_one({"_id": _read_key(p)}) or {}
    last_read = marker.get("last_read_at") or ""
    out = []
    for d in docs:
        out.append({"id": d["_id"], "kind": d["kind"], "title": d["title"], "body": d.get("body", ""),
                    "lead_id": d.get("lead_id"), "lead_name": d.get("lead_name"), "source": d.get("source", "app"),
                    "created_at": d["created_at"], "unread": d["created_at"] > last_read,
                    "contacted_at": (metas.get(d.get("lead_id")) or {}).get("contacted_at") if d.get("lead_id") else None})
    return {"alerts": out, "unread": sum(1 for a in out if a["unread"])}


@api_router.post("/alerts/read")
async def mark_alerts_read(request: Request):
    p = await current_principal(request)
    _alert_gate(p)
    await mongo_db.alerts_read.update_one({"_id": _read_key(p)}, {"$set": {"last_read_at": now_iso()}}, upsert=True)
    return {"ok": True}


@api_router.get("/alerts/unread-count")
async def alerts_unread_count(request: Request):
    p = await current_principal(request)
    _alert_gate(p)
    marker = await mongo_db.alerts_read.find_one({"_id": _read_key(p)}) or {}
    last_read = marker.get("last_read_at") or ""
    n = await mongo_db.alerts.count_documents({"created_at": {"$gt": last_read}})
    try:
        gmail = await _gmail_unread_counts()
        n += sum(v for mid, v in gmail.items() if p["role"] in GMAIL_MAILBOXES[mid]["roles"])
    except Exception:
        pass
    return {"unread": min(n, 99)}


@api_router.get("/alerts/webhook-info")
async def alerts_webhook_info(p: Dict[str, Any] = Depends(require_owner)):
    doc = await mongo_db.settings.find_one({"_id": "zapier_webhook"})
    if not doc:
        doc = {"_id": "zapier_webhook", "token": uuid4().hex, "created_at": now_iso()}
        await mongo_db.settings.insert_one(doc)
    return {"token": doc["token"], "path": "/api/webhooks/zapier",
            "kinds": list(ALERT_KINDS),
            "fields": {"kind": "new_lead | booked | review | custom (optional, default custom)",
                       "title": "headline text (optional)", "body": "detail line (optional)",
                       "lead_name": "customer name (optional)"}}


class ZapierAlertPayload(BaseModel):
    kind: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    lead_name: Optional[str] = None
    lead_id: Optional[str] = None
    external_id: Optional[str] = None


@public_router.post("/webhooks/zapier")
async def zapier_webhook(payload: ZapierAlertPayload, token: str = ""):
    doc = await mongo_db.settings.find_one({"_id": "zapier_webhook"})
    if not doc or not token or token != doc.get("token"):
        raise HTTPException(status_code=401, detail="Bad or missing webhook token.")
    kind = payload.kind if payload.kind in ALERT_KINDS else "custom"
    default_titles = {"new_lead": "New lead", "booked": "Move booked", "review": "New Google review", "custom": "Alert"}
    title = (payload.title or "").strip() or default_titles[kind]
    if payload.lead_name and payload.lead_name not in title:
        title = f"{title}: {payload.lead_name}"
    dedupe = f"zap:{payload.external_id}" if payload.external_id else None
    await create_alert(kind, title, payload.body or "", lead_id=payload.lead_id,
                       lead_name=payload.lead_name, source="zapier", dedupe_key=dedupe)
    return {"ok": True}


@public_router.post("/webhooks/tally")
async def tally_webhook(request: Request) -> Dict[str, Any]:
    raw = await request.body()
    secret = os.environ.get("TALLY_WEBHOOK_SIGNING_SECRET", "").encode()
    sig = request.headers.get("Tally-Signature", "")
    expected = base64.b64encode(hmac.new(secret, raw, hashlib.sha256).digest()).decode()
    if not secret or not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=401, detail="bad signature")
    body = json.loads(raw or b"{}")
    fields = {f.get("label", "").strip().lower(): f.get("value")
              for f in body.get("data", {}).get("fields", [])}
    full_name = (fields.get("full name") or "").strip()
    first, _, last = full_name.partition(" ")
    lead = {
        "id": body.get("data", {}).get("submissionId") or body.get("eventId"),
        "email": fields.get("email") or fields.get("email (optional)"),
        "phone": fields.get("phone"),
        "first_name": first or None,
        "last_name": last or None,
        "zip": fields.get("moving from (zip code)"),
        "fbclid": fields.get("fbclid"),
        "fbc": fields.get("fbc"),
        "fbp": fields.get("fbp"),
        "event_source_url": fields.get("event_source_url") or "https://haulyeahmoves.com/",
        "client_ip": (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                      or (request.client.host if request.client else None)),
        "user_agent": request.headers.get("user-agent"),
    }
    asyncio.create_task(_capi_log("lead", meta_capi.fire_lead(lead)))
    return {"ok": True}


async def lead_alert_loop():
    while True:
        try:
            if get_api_key():
                data = await airtable_request(
                    "GET", TABLES["leads"],
                    params={"filterByFormula": "DATETIME_DIFF(NOW(), CREATED_TIME(), 'hours') < 24",
                            "pageSize": 50, "returnFieldsByFieldId": "true"})
                for rec in data.get("records", []):
                    name = (rec.get("fields") or {}).get(LEAD_NAME_F) or "Someone new"
                    await create_alert("new_lead", f"New lead: {name}",
                                       "Call them fast — under 5 minutes wins the job.",
                                       lead_id=rec["id"], lead_name=name, source="airtable",
                                       created_at=rec.get("createdTime"), dedupe_key=f"new_lead:{rec['id']}")
        except HTTPException:
            pass
        except Exception as exc:
            logger.warning("lead alert loop error: %s", exc)
        await asyncio.sleep(120)


# ================================================================ gmail inboxes (notification center phase 3)

from urllib.parse import urlencode

from cryptography.fernet import Fernet
from fastapi.responses import RedirectResponse

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SCOPES = " ".join([
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
])
GMAIL_MAILBOXES = {
    "contact": {"email": "contact@haulyeahmoves.com", "label": "Shared inbox", "roles": ("owner", "sales", "marketing")},
    "owner": {"email": "keithrivera@haulyeahmoves.com", "label": "Owner inbox", "roles": ("owner",)},
}
_gmail_unread_cache: Dict[str, Any] = {"at": 0.0, "counts": {}}


def _google_configured() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID", "").strip() and os.environ.get("GOOGLE_CLIENT_SECRET", "").strip())


def _gmail_fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(os.environ["JWT_SECRET"].encode()).digest())
    return Fernet(key)


def _external_base(request: Request) -> str:
    env = os.environ.get("APP_BASE_URL", "").strip().rstrip("/")
    if env:
        return env
    proto = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return f"{proto}://{host}"


def _gmail_redirect_uri(request: Request) -> str:
    return f"{_external_base(request)}/api/gmail/oauth/callback"


def _mailbox_or_404(p: Dict[str, Any], mailbox_id: str) -> Dict[str, Any]:
    mb = GMAIL_MAILBOXES.get(mailbox_id)
    if not mb or p["role"] not in mb["roles"]:
        raise HTTPException(status_code=404, detail="No such mailbox.")
    return mb


async def _gmail_access_token(mailbox_id: str) -> str:
    doc = await mongo_db.gmail_tokens.find_one({"_id": mailbox_id})
    if not doc:
        raise HTTPException(status_code=409, detail="That mailbox isn't connected yet.")
    f = _gmail_fernet()
    expires_at = doc.get("expires_at") or ""
    if expires_at > (datetime.now(timezone.utc) + timedelta(seconds=90)).isoformat():
        return f.decrypt(doc["access_token"].encode()).decode()
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(GMAIL_TOKEN_URL, data={
            "client_id": os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
            "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
            "refresh_token": f.decrypt(doc["refresh_token"].encode()).decode(),
            "grant_type": "refresh_token",
        })
    if r.status_code >= 300:
        raise HTTPException(status_code=409, detail="Gmail session expired — reconnect the mailbox in Settings.")
    tok = r.json()
    access = tok["access_token"]
    await mongo_db.gmail_tokens.update_one({"_id": mailbox_id}, {"$set": {
        "access_token": f.encrypt(access.encode()).decode(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=int(tok.get("expires_in", 3600)))).isoformat(),
    }})
    return access


async def gmail_request(mailbox_id: str, method: str, path: str,
                        params: Optional[Dict[str, Any]] = None, json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    token = await _gmail_access_token(mailbox_id)
    async with httpx.AsyncClient(timeout=40.0) as client:
        r = await client.request(method, f"{GMAIL_API}{path}", params=params, json=json_body,
                                 headers={"Authorization": f"Bearer {token}"})
    if r.status_code in (401, 403):
        raise HTTPException(status_code=409, detail="Gmail access was revoked — reconnect the mailbox in Settings.")
    if r.status_code >= 300:
        logger.warning("gmail api %s %s -> %s", method, path, r.status_code)
        raise HTTPException(status_code=502, detail="Gmail didn't respond. Try again in a second.")
    return r.json() if r.content else {}


def _gmail_header(payload: Dict[str, Any], name: str) -> str:
    return next((h.get("value", "") for h in payload.get("headers", []) if h.get("name", "").lower() == name.lower()), "")


def _gmail_body(payload: Dict[str, Any]):
    html, text = "", ""
    stack = [payload]
    while stack:
        part = stack.pop()
        data = (part.get("body") or {}).get("data")
        mime = part.get("mimeType", "")
        if data:
            try:
                decoded = base64.urlsafe_b64decode(data + "===").decode("utf-8", "replace")
            except Exception:
                decoded = ""
            if mime == "text/html" and not html:
                html = decoded
            elif mime == "text/plain" and not text:
                text = decoded
        stack.extend(part.get("parts") or [])
    return html, text


def _gmail_msg_summary(msg: Dict[str, Any]) -> Dict[str, Any]:
    payload = msg.get("payload") or {}
    return {"id": msg["id"], "thread_id": msg.get("threadId"),
            "from": _gmail_header(payload, "From"), "subject": _gmail_header(payload, "Subject") or "(no subject)",
            "snippet": msg.get("snippet", ""), "date": msg.get("internalDate"),
            "unread": "UNREAD" in (msg.get("labelIds") or [])}


@api_router.get("/gmail/status")
async def gmail_status(request: Request):
    p = await current_principal(request)
    _alert_gate(p)
    boxes = []
    for mid, mb in GMAIL_MAILBOXES.items():
        if p["role"] not in mb["roles"]:
            continue
        doc = await mongo_db.gmail_tokens.find_one({"_id": mid})
        boxes.append({"id": mid, "email": mb["email"], "label": mb["label"],
                      "connected": bool(doc), "connected_at": (doc or {}).get("connected_at")})
    out = {"configured": _google_configured(), "mailboxes": boxes}
    if p["role"] == "owner":
        out["redirect_uri"] = _gmail_redirect_uri(request)
    return out


@api_router.get("/gmail/connect/{mailbox_id}")
async def gmail_connect(mailbox_id: str, request: Request, p: Dict[str, Any] = Depends(require_owner)):
    mb = GMAIL_MAILBOXES.get(mailbox_id)
    if not mb:
        raise HTTPException(status_code=404, detail="No such mailbox.")
    if not _google_configured():
        raise HTTPException(status_code=422, detail="Add the Google Client ID and Secret in Settings first.")
    state = uuid4().hex
    await mongo_db.oauth_states.insert_one({"_id": state, "mailbox_id": mailbox_id, "created_at": now_iso()})
    params = {"client_id": os.environ["GOOGLE_CLIENT_ID"].strip(), "redirect_uri": _gmail_redirect_uri(request),
              "response_type": "code", "scope": GMAIL_SCOPES, "access_type": "offline", "prompt": "consent",
              "state": state, "login_hint": mb["email"]}
    return {"auth_url": f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"}


@public_router.get("/gmail/oauth/callback")
async def gmail_oauth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    st = await mongo_db.oauth_states.find_one({"_id": state}) if state else None
    if st:
        await mongo_db.oauth_states.delete_one({"_id": state})
    if error or not code or not st:
        return RedirectResponse(url="/settings?gmail=denied")
    if st.get("created_at", "") < (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat():
        return RedirectResponse(url="/settings?gmail=expired")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(GMAIL_TOKEN_URL, data={
            "code": code, "client_id": os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
            "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
            "redirect_uri": _gmail_redirect_uri(request), "grant_type": "authorization_code"})
        if r.status_code >= 300:
            logger.warning("gmail token exchange failed: %s", r.text[:200])
            return RedirectResponse(url="/settings?gmail=error")
        tok = r.json()
        if not tok.get("refresh_token"):
            return RedirectResponse(url="/settings?gmail=error")
        prof = await client.get(f"{GMAIL_API}/profile", headers={"Authorization": f"Bearer {tok['access_token']}"})
    email = (prof.json() or {}).get("emailAddress", "").lower() if prof.status_code < 300 else ""
    mb = GMAIL_MAILBOXES[st["mailbox_id"]]
    if email != mb["email"].lower():
        return RedirectResponse(url=f"/settings?gmail=wrong-account&expected={mb['email']}")
    f = _gmail_fernet()
    await mongo_db.gmail_tokens.update_one(
        {"_id": st["mailbox_id"]},
        {"$set": {"email": email,
                  "access_token": f.encrypt(tok["access_token"].encode()).decode(),
                  "refresh_token": f.encrypt(tok["refresh_token"].encode()).decode(),
                  "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=int(tok.get("expires_in", 3600)))).isoformat(),
                  "connected_at": now_iso()}},
        upsert=True)
    await audit({"name": "owner", "user_id": None}, "connected a Gmail inbox", email)
    _gmail_unread_cache["at"] = 0.0
    return RedirectResponse(url="/settings?gmail=connected")


@api_router.post("/gmail/disconnect/{mailbox_id}")
async def gmail_disconnect(mailbox_id: str, p: Dict[str, Any] = Depends(require_owner)):
    doc = await mongo_db.gmail_tokens.find_one({"_id": mailbox_id})
    if not doc:
        raise HTTPException(status_code=404, detail="That mailbox isn't connected.")
    await mongo_db.gmail_tokens.delete_one({"_id": mailbox_id})
    await audit(p, "disconnected a Gmail inbox", doc.get("email", mailbox_id))
    _gmail_unread_cache["at"] = 0.0
    return {"ok": True}


@api_router.get("/gmail/{mailbox_id}/messages")
async def gmail_list_messages(mailbox_id: str, request: Request, q: str = "", page_token: str = "", limit: int = 25):
    p = await current_principal(request)
    _mailbox_or_404(p, mailbox_id)
    params: Dict[str, Any] = {"maxResults": min(max(limit, 1), 50), "labelIds": "INBOX"}
    if q.strip():
        params["q"] = q.strip()[:200]
    if page_token:
        params["pageToken"] = page_token
    data = await gmail_request(mailbox_id, "GET", "/messages", params=params)
    out = []
    for m in data.get("messages") or []:
        msg = await gmail_request(mailbox_id, "GET", f"/messages/{m['id']}",
                                  params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]})
        out.append(_gmail_msg_summary(msg))
    return {"messages": out, "next_page_token": data.get("nextPageToken")}


@api_router.get("/gmail/{mailbox_id}/messages/{msg_id}")
async def gmail_get_message(mailbox_id: str, msg_id: str, request: Request):
    p = await current_principal(request)
    _mailbox_or_404(p, mailbox_id)
    msg = await gmail_request(mailbox_id, "GET", f"/messages/{msg_id}", params={"format": "full"})
    payload = msg.get("payload") or {}
    html, text = _gmail_body(payload)
    if "UNREAD" in (msg.get("labelIds") or []):
        try:
            await gmail_request(mailbox_id, "POST", f"/messages/{msg_id}/modify",
                                json_body={"removeLabelIds": ["UNREAD"]})
            _gmail_unread_cache["at"] = 0.0
        except HTTPException:
            pass
    return {**_gmail_msg_summary(msg), "to": _gmail_header(payload, "To"),
            "body_html": html, "body_text": text, "unread": False}


class GmailReplyPayload(BaseModel):
    body: str


@api_router.post("/gmail/{mailbox_id}/messages/{msg_id}/reply")
async def gmail_reply(mailbox_id: str, msg_id: str, payload: GmailReplyPayload, request: Request):
    p = await current_principal(request)
    mb = _mailbox_or_404(p, mailbox_id)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Type a reply first.")
    orig = await gmail_request(mailbox_id, "GET", f"/messages/{msg_id}",
                               params={"format": "metadata",
                                       "metadataHeaders": ["From", "Reply-To", "Subject", "Message-ID"]})
    op = orig.get("payload") or {}
    to = _gmail_header(op, "Reply-To") or _gmail_header(op, "From")
    subject = _gmail_header(op, "Subject") or ""
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    ref = _gmail_header(op, "Message-ID")
    mime = (f"From: {mb['email']}\r\nTo: {to}\r\nSubject: {subject}\r\n"
            f"In-Reply-To: {ref}\r\nReferences: {ref}\r\n"
            f"Content-Type: text/plain; charset=UTF-8\r\n\r\n{body}")
    raw = base64.urlsafe_b64encode(mime.encode()).decode()
    await gmail_request(mailbox_id, "POST", "/messages/send",
                        json_body={"raw": raw, "threadId": orig.get("threadId")})
    return {"ok": True}


class GmailModifyPayload(BaseModel):
    action: str


@api_router.post("/gmail/{mailbox_id}/messages/{msg_id}/modify")
async def gmail_modify(mailbox_id: str, msg_id: str, payload: GmailModifyPayload, request: Request):
    p = await current_principal(request)
    _mailbox_or_404(p, mailbox_id)
    actions = {"archive": {"removeLabelIds": ["INBOX"]},
               "read": {"removeLabelIds": ["UNREAD"]},
               "unread": {"addLabelIds": ["UNREAD"]}}
    if payload.action not in actions:
        raise HTTPException(status_code=422, detail="Action must be archive, read, or unread.")
    await gmail_request(mailbox_id, "POST", f"/messages/{msg_id}/modify", json_body=actions[payload.action])
    _gmail_unread_cache["at"] = 0.0
    return {"ok": True}


async def _gmail_unread_counts() -> Dict[str, int]:
    if time.time() - _gmail_unread_cache["at"] < 60:
        return _gmail_unread_cache["counts"]
    counts: Dict[str, int] = {}
    for mid in GMAIL_MAILBOXES:
        if not await mongo_db.gmail_tokens.find_one({"_id": mid}, {"_id": 1}):
            continue
        try:
            data = await gmail_request(mid, "GET", "/messages",
                                       params={"labelIds": "INBOX", "q": "is:unread", "maxResults": 1})
            counts[mid] = int(data.get("resultSizeEstimate") or 0)
        except HTTPException:
            counts[mid] = 0
    _gmail_unread_cache["at"] = time.time()
    _gmail_unread_cache["counts"] = counts
    return counts


# ================================================================ meta (facebook / instagram) social feed (notification center phase 4)

META_GRAPH = "https://graph.facebook.com/v21.0"
META_SCOPES = ",".join([
    "pages_show_list", "pages_read_engagement", "pages_read_user_content", "pages_manage_metadata",
    "instagram_basic", "instagram_manage_comments", "instagram_manage_messages",
])
META_ROLES = ("owner", "marketing")


def _meta_configured() -> bool:
    return bool(os.environ.get("META_APP_ID", "").strip() and os.environ.get("META_APP_SECRET", "").strip())


def meta_capi_config() -> Dict[str, str]:
    """Meta Conversions API settings, all read from the environment (secrets panel)."""
    return {
        "dataset_id": os.environ.get("META_DATASET_ID", "").strip(),
        "access_token": os.environ.get("META_CAPI_ACCESS_TOKEN", "").strip(),
        "app_id": os.environ.get("META_APP_ID", "").strip(),
        "app_secret": os.environ.get("META_APP_SECRET", "").strip(),
        "test_event_code": os.environ.get("META_TEST_EVENT_CODE", "").strip(),
    }


def meta_capi_configured() -> bool:
    cfg = meta_capi_config()
    return bool(cfg["dataset_id"] and cfg["access_token"])


# ------- Meta Conversions API — all sending lives in backend/meta_capi.py.
# Calls are fire-and-forget via asyncio.create_task(_capi_log(...)) and never
# raise into the request path; _capi_log records outcomes for the Settings counters.


@api_router.post("/marketing/capi-test")
async def capi_test(payload: Dict[str, Any] = Body(default={}),
                    p: Dict[str, Any] = Depends(require_owner)) -> Dict[str, Any]:
    """Fire a Lead for a supplied lead_id (or a synthetic lead) and return Meta's raw response."""
    lead_id = (payload.get("lead_id") or "").strip()
    if lead_id:
        rec_full = await fetch_lead_record(lead_id)
        if not rec_full:
            raise HTTPException(status_code=404, detail="Lead not found in Airtable.")
        lead = lead_dict_from_airtable(rec_full)
    else:
        lead = {"id": f"capi-test-{uuid4().hex[:8]}", "email": "test@haulyeahmoves.com",
                "phone": "9735550100", "first_name": "Test", "last_name": "Lead",
                "event_source_url": "https://haulyeahmoves.com/"}
    return await _capi_log("lead-test", meta_capi.fire_lead(lead))


@api_router.get("/meta/capi-status")
async def meta_capi_status(p: Dict[str, Any] = Depends(require_owner)) -> Dict[str, Any]:
    cfg = meta_capi_config()
    sent = await mongo_db.meta_capi_events.count_documents({"status": "sent"})
    pending = await mongo_db.meta_capi_events.count_documents({"status": "pending"})
    failed = await mongo_db.meta_capi_events.count_documents({"status": "failed"})
    last = await mongo_db.meta_capi_events.find({"status": "sent"}).sort("sent_at", -1).limit(1).to_list(1)
    last_failed = await mongo_db.meta_capi_events.find({"status": "failed"}).sort("created_at", -1).limit(1).to_list(1)
    return {"configured": meta_capi.capi_enabled(),
            "dataset_id_set": bool(cfg["dataset_id"]), "access_token_set": bool(cfg["access_token"]),
            "app_secret_set": bool(cfg["app_secret"]), "test_event_code_set": bool(cfg["test_event_code"]),
            "sent": sent, "pending": pending, "failed": failed,
            "last_sent_at": (last[0].get("sent_at") if last else None),
            "last_error": (last_failed[0].get("error") if last_failed else None)}


def _meta_gate(p: Dict[str, Any]):
    if p["role"] not in META_ROLES:
        raise HTTPException(status_code=403, detail="You don't have access to the social feed.")


def _meta_redirect_uri(request: Request) -> str:
    return f"{_external_base(request)}/api/meta/oauth/callback"


async def _meta_get(path: str, token: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{META_GRAPH}{path}", params={"access_token": token, **(params or {})})
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Meta API error {r.status_code}: {r.text[:150]}")
    return r.json()


async def _upsert_social(doc: Dict[str, Any]) -> bool:
    try:
        res = await mongo_db.social_items.update_one({"_id": doc["_id"]}, {"$setOnInsert": doc}, upsert=True)
        return res.upserted_id is not None
    except Exception as exc:
        logger.warning("social upsert failed: %s", exc)
        return False


async def _meta_poll_once() -> int:
    doc = await mongo_db.meta_tokens.find_one({"_id": "meta"})
    if not doc:
        return 0
    f = _gmail_fernet()
    new = 0
    for page in doc.get("pages", []):
        try:
            token = f.decrypt(page["token_enc"].encode()).decode()
        except Exception:
            continue
        pid = page["id"]
        try:
            posts = await _meta_get(f"/{pid}/posts", token, {"fields": "id,permalink_url", "limit": 5})
            for post in posts.get("data", []):
                cs = await _meta_get(f"/{post['id']}/comments", token,
                                     {"fields": "id,message,from{name},created_time,permalink_url",
                                      "order": "reverse_chronological", "limit": 10})
                for c in cs.get("data", []):
                    author = (c.get("from") or {}).get("name") or "Someone"
                    if author == page.get("name"):
                        continue
                    if await _upsert_social({
                            "_id": f"fb_comment:{c['id']}", "platform": "facebook", "type": "comment",
                            "title": f"{author} commented on a Facebook post",
                            "body": (c.get("message") or "")[:300], "author": author,
                            "link": c.get("permalink_url") or post.get("permalink_url") or f"https://www.facebook.com/{pid}",
                            "created_at": c.get("created_time") or now_iso(), "page_id": pid}):
                        new += 1
        except Exception as exc:
            logger.warning("meta poll fb comments: %s", exc)
        for platform, plabel in (("messenger", "Messenger"), ("instagram", "Instagram")):
            try:
                convs = await _meta_get(f"/{pid}/conversations", token,
                                        {"fields": "id,link,updated_time,snippet,senders",
                                         "platform": platform, "limit": 10})
                for cv in convs.get("data", []):
                    sender = (((cv.get("senders") or {}).get("data") or [{}])[0].get("name")) or "Someone"
                    upd = cv.get("updated_time") or now_iso()
                    if await _upsert_social({
                            "_id": f"msg:{cv['id']}:{upd}",
                            "platform": "instagram" if platform == "instagram" else "facebook",
                            "type": "message", "title": f"New {plabel} message from {sender}",
                            "body": (cv.get("snippet") or "")[:300], "author": sender,
                            "link": f"https://www.facebook.com{cv['link']}" if cv.get("link")
                                    else f"https://business.facebook.com/latest/inbox?asset_id={pid}",
                            "created_at": upd, "page_id": pid}):
                        new += 1
            except Exception as exc:
                logger.warning("meta poll %s conversations: %s", platform, exc)
        ig = page.get("ig") or {}
        if ig.get("id"):
            try:
                media = await _meta_get(f"/{ig['id']}/media", token, {"fields": "id,permalink", "limit": 5})
                for m in media.get("data", []):
                    cs = await _meta_get(f"/{m['id']}/comments", token,
                                         {"fields": "id,text,username,timestamp", "limit": 10})
                    for c in cs.get("data", []):
                        if c.get("username") and c["username"] == ig.get("username"):
                            continue
                        if await _upsert_social({
                                "_id": f"ig_comment:{c['id']}", "platform": "instagram", "type": "comment",
                                "title": f"@{c.get('username') or 'someone'} commented on Instagram",
                                "body": (c.get("text") or "")[:300], "author": c.get("username") or "someone",
                                "link": m.get("permalink") or "https://www.instagram.com",
                                "created_at": c.get("timestamp") or now_iso(), "page_id": pid}):
                            new += 1
            except Exception as exc:
                logger.warning("meta poll ig comments: %s", exc)
            try:
                tags = await _meta_get(f"/{ig['id']}/tags", token,
                                       {"fields": "id,permalink,caption,username,timestamp", "limit": 10})
                for t in tags.get("data", []):
                    if await _upsert_social({
                            "_id": f"ig_mention:{t['id']}", "platform": "instagram", "type": "mention",
                            "title": f"@{t.get('username') or 'someone'} tagged you on Instagram",
                            "body": (t.get("caption") or "")[:300], "author": t.get("username") or "someone",
                            "link": t.get("permalink") or "https://www.instagram.com",
                            "created_at": t.get("timestamp") or now_iso(), "page_id": pid}):
                        new += 1
            except Exception as exc:
                logger.warning("meta poll ig mentions: %s", exc)
    await mongo_db.meta_tokens.update_one({"_id": "meta"}, {"$set": {"last_poll": now_iso()}})
    return new


async def _safe_meta_poll():
    try:
        await _meta_poll_once()
    except Exception as exc:
        logger.warning("meta initial poll: %s", exc)


async def meta_poll_loop():
    while True:
        try:
            await _meta_poll_once()
        except Exception as exc:
            logger.warning("meta poll loop: %s", exc)
        await asyncio.sleep(300)


@api_router.get("/meta/status")
async def meta_status(request: Request):
    p = await current_principal(request)
    _meta_gate(p)
    doc = await mongo_db.meta_tokens.find_one({"_id": "meta"})
    pages = [{"id": pg["id"], "name": pg.get("name", ""), "ig_username": (pg.get("ig") or {}).get("username")}
             for pg in (doc or {}).get("pages", [])]
    out = {"configured": _meta_configured(), "connected": bool(doc), "pages": pages,
           "connected_at": (doc or {}).get("connected_at"), "last_poll": (doc or {}).get("last_poll")}
    if p["role"] == "owner":
        out["redirect_uri"] = _meta_redirect_uri(request)
    return out


@api_router.get("/meta/connect")
async def meta_connect(request: Request, p: Dict[str, Any] = Depends(require_owner)):
    if not _meta_configured():
        raise HTTPException(status_code=422, detail="Add the Meta App ID and Secret first.")
    state = uuid4().hex
    await mongo_db.oauth_states.insert_one({"_id": state, "provider": "meta", "created_at": now_iso()})
    params = {"client_id": os.environ["META_APP_ID"].strip(), "redirect_uri": _meta_redirect_uri(request),
              "response_type": "code", "scope": META_SCOPES, "state": state}
    return {"auth_url": f"https://www.facebook.com/v21.0/dialog/oauth?{urlencode(params)}"}


@public_router.get("/meta/oauth/callback")
async def meta_oauth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    st = await mongo_db.oauth_states.find_one_and_delete({"_id": state}) if state else None
    if error or not code:
        return RedirectResponse(url="/settings?meta=denied")
    if not st or st.get("provider") != "meta":
        return RedirectResponse(url="/settings?meta=expired")
    app_id = os.environ.get("META_APP_ID", "").strip()
    app_secret = os.environ.get("META_APP_SECRET", "").strip()
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{META_GRAPH}/oauth/access_token", params={
            "client_id": app_id, "client_secret": app_secret,
            "redirect_uri": _meta_redirect_uri(request), "code": code})
        if r.status_code != 200:
            logger.warning("meta token exchange failed: %s", r.text[:200])
            return RedirectResponse(url="/settings?meta=error")
        short_token = r.json().get("access_token", "")
        r2 = await client.get(f"{META_GRAPH}/oauth/access_token", params={
            "grant_type": "fb_exchange_token", "client_id": app_id,
            "client_secret": app_secret, "fb_exchange_token": short_token})
        user_token = (r2.json().get("access_token") if r2.status_code == 200 else None) or short_token
        r3 = await client.get(f"{META_GRAPH}/me/accounts", params={
            "access_token": user_token,
            "fields": "id,name,access_token,connected_instagram_account{id,username}"})
    if r3.status_code != 200:
        logger.warning("meta pages fetch failed: %s", r3.text[:200])
        return RedirectResponse(url="/settings?meta=error")
    raw_pages = r3.json().get("data") or []
    f = _gmail_fernet()
    pages = []
    for pg in raw_pages:
        if not pg.get("access_token"):
            continue
        ig = pg.get("connected_instagram_account") or {}
        pages.append({"id": pg["id"], "name": pg.get("name", ""),
                      "token_enc": f.encrypt(pg["access_token"].encode()).decode(),
                      "ig": {"id": ig.get("id"), "username": ig.get("username")} if ig else {}})
    if not pages:
        return RedirectResponse(url="/settings?meta=no-pages")
    await mongo_db.meta_tokens.update_one(
        {"_id": "meta"}, {"$set": {"pages": pages, "connected_at": now_iso()}}, upsert=True)
    await audit({"name": "owner", "user_id": None}, "connected Facebook / Instagram",
                ", ".join(pg["name"] for pg in pages))
    asyncio.create_task(_safe_meta_poll())
    return RedirectResponse(url="/settings?meta=connected")


@api_router.post("/meta/disconnect")
async def meta_disconnect(p: Dict[str, Any] = Depends(require_owner)):
    doc = await mongo_db.meta_tokens.find_one_and_delete({"_id": "meta"})
    if not doc:
        raise HTTPException(status_code=404, detail="Facebook isn't connected.")
    await audit(p, "disconnected Facebook / Instagram", ", ".join(pg.get("name", "") for pg in doc.get("pages", [])))
    return {"ok": True}


@api_router.get("/meta/feed")
async def meta_feed(request: Request, limit: int = 100):
    p = await current_principal(request)
    _meta_gate(p)
    items = await mongo_db.social_items.find({}).sort("created_at", -1).to_list(min(max(limit, 1), 200))
    for i in items:
        i["id"] = i.pop("_id")
    return {"items": items}


@api_router.post("/meta/refresh")
async def meta_refresh(request: Request):
    p = await current_principal(request)
    _meta_gate(p)
    if not await mongo_db.meta_tokens.find_one({"_id": "meta"}, {"_id": 1}):
        raise HTTPException(status_code=404, detail="Facebook isn't connected yet.")
    new = await _meta_poll_once()
    return {"ok": True, "new_items": new}


# ------- ai operations brief (phase F — panel on existing owner dashboard)

async def _ops_facts() -> Dict[str, Any]:
    today = _et_today()
    now_et = datetime.now(ZoneInfo("America/New_York"))
    tomorrow = (now_et + timedelta(days=1)).date().isoformat()
    assignments = await mongo_db.assignments.find({"job_date": {"$in": [today, tomorrow]}}).to_list(200)
    todays = [a for a in assignments if a["job_date"] == today]
    behind, needs_crew, late_risk = [], [], []
    active = complete = 0
    open_entries = await mongo_db.time_entries.find({"clock_out": None}).to_list(100)
    open_by_aid: Dict[str, int] = {}
    for e in open_entries:
        if e.get("assignment_id"):
            open_by_aid[e["assignment_id"]] = open_by_aid.get(e["assignment_id"], 0) + 1
    for a in todays:
        status = a.get("exec_status") or "Assigned"
        if status == "Complete":
            complete += 1
        elif status != "Assigned":
            active += 1
        if not a.get("crew"):
            needs_crew.append(a.get("job_name"))
        if a.get("arrival_time") and status in ("Assigned", "En Route"):
            try:
                hh, mm = a["arrival_time"].split(":")[:2]
                sched = now_et.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
                if now_et > sched + timedelta(minutes=15):
                    behind.append(f"{a.get('job_name')} (arrival was {a['arrival_time']})")
                elif timedelta(0) <= sched - now_et <= timedelta(minutes=60) and not open_by_aid.get(a["_id"]):
                    late_risk.append(f"{a.get('job_name')} arrives {a['arrival_time']} and nobody is clocked in yet")
            except ValueError:
                pass
    # revenue today
    revenue_today = 0.0
    for inv in await mongo_db.square_invoices.find(
            {"status": "PAID", "paid_at": {"$ne": None}}, {"_id": 0, "amount": 1, "paid_at": 1}).to_list(1000):
        try:
            d_et = datetime.fromisoformat(str(inv["paid_at"]).replace("Z", "+00:00")).astimezone(
                ZoneInfo("America/New_York")).date().isoformat()
        except ValueError:
            continue
        if d_et == today:
            revenue_today += inv.get("amount") or 0
    # crews working + unscheduled + overtime
    clocked, unscheduled = [], []
    for e in open_entries:
        nm = e.get("user_name", "Someone")
        clocked.append(nm)
        if "not_scheduled_today" in (e.get("flags") or []):
            unscheduled.append(nm)
    hours_today: Dict[str, float] = {}
    for e in await mongo_db.time_entries.find({"clock_in.at": {"$gte": f"{today}T00:00:00"}}).to_list(300):
        nm = e.get("user_name", "Someone")
        if e.get("hours"):
            hours_today[nm] = hours_today.get(nm, 0) + e["hours"]
        elif e.get("clock_in") and not e.get("clock_out"):
            try:
                start = datetime.fromisoformat(e["clock_in"]["at"].replace("Z", "+00:00"))
                hours_today[nm] = hours_today.get(nm, 0) + (datetime.now(timezone.utc) - start).total_seconds() / 3600
            except ValueError:
                pass
    overtime = [f"{nm}: {h:.1f}h today" for nm, h in hours_today.items() if h > 8]
    # fleet flags
    fleet_attention, fleet_shop, reminders_due, expired_docs = [], [], [], []
    trucks = await mongo_db.trucks.find({"active": {"$ne": False}}).to_list(100)
    for t in trucks:
        if t.get("fleet_status") == "needs_attention":
            fleet_attention.append(t["name"])
        if t.get("fleet_status") == "in_shop":
            fleet_shop.append(t["name"])
        for r in t.get("reminders", []):
            if not r.get("done") and r.get("due_date") and r["due_date"] <= today:
                reminders_due.append(f"{t['name']}: {r.get('title')}")
        for label, doc_key in (("registration", "registration"), ("insurance", "insurance")):
            st = _expiry_state((t.get(doc_key) or {}).get("expires"))
            if st in ("expired", "soon"):
                expired_docs.append(f"{t['name']} {label} {'EXPIRED' if st == 'expired' else 'expires soon'}")
    open_damage = await mongo_db.truck_damage.count_documents({"resolved": {"$ne": True}})
    # outstanding balances
    unpaid, outstanding_total = [], 0.0
    async for j in mongo_db.jobs.find({"deposit_paid.status": "paid", "paid_in_full.status": {"$ne": "paid"},
                                       "quote_total": {"$ne": None}}):
        try:
            rem = max(0.0, float(j["quote_total"]) - float((j.get("deposit_paid") or {}).get("amount") or 0))
        except (TypeError, ValueError):
            continue
        if rem > 0:
            outstanding_total += rem
            unpaid.append(f"Job #{j.get('invoice_number')} ({(j.get('customer') or {}).get('name', '?')}): ${rem:,.0f} due")
    # schedule conflicts (today + tomorrow)
    conflicts = []
    for day in (today, tomorrow):
        day_assignments = [a for a in assignments if a["job_date"] == day]
        seen: Dict[str, List[str]] = {}
        for a in day_assignments:
            for c in a.get("crew", []):
                seen.setdefault(c.get("name", "?"), []).append(a.get("job_name", "?"))
        for nm, jobs_list in seen.items():
            if len(jobs_list) > 1:
                conflicts.append(f"{nm} is on {len(jobs_list)} jobs {('today' if day == today else 'tomorrow')}: {', '.join(jobs_list)}")
        crew_ids_by_user = {c["user_id"]: c.get("name", "?") for a in day_assignments for c in a.get("crew", [])}
        if crew_ids_by_user:
            async for off in mongo_db.availability.find({"date": day, "available": False,
                                                         "user_id": {"$in": list(crew_ids_by_user)}}):
                conflicts.append(f"{crew_ids_by_user[off['user_id']]} is scheduled {('today' if day == today else 'tomorrow')} but marked OFF")
    # customer issues
    issues = []
    cutoff = (now_et - timedelta(days=14)).date().isoformat()
    async for j in mongo_db.jobs.find({"portal_review.rating": {"$lte": 3}}):
        rv = j.get("portal_review") or {}
        if (rv.get("at") or "") >= cutoff:
            issues.append(f"Job #{j.get('invoice_number')} left {rv.get('rating')}/5" + (f": \"{(rv.get('text') or '')[:80]}\"" if rv.get("text") else ""))
    if open_damage:
        issues.append(f"{open_damage} unresolved truck damage report{'s' if open_damage > 1 else ''}")
    return {
        "date": today,
        "jobs_today": {"total": len(todays), "active": active, "complete": complete,
                       "names": [a.get("job_name") for a in todays],
                       "behind": behind, "needs_crew": needs_crew},
        "revenue_today": round(revenue_today, 2),
        "crews_working": {"clocked_in": clocked, "unscheduled_clock_ins": unscheduled},
        "fleet": {"needs_attention": fleet_attention, "in_shop": fleet_shop,
                  "maintenance_due": reminders_due, "document_warnings": expired_docs,
                  "open_damage_reports": open_damage},
        "money": {"outstanding_balance_total": round(outstanding_total, 2), "unpaid_jobs": unpaid[:10]},
        "schedule_conflicts": conflicts,
        "overtime_warnings": overtime,
        "late_job_risk": late_risk,
        "customer_issues": issues,
    }


async def _generate_ops_brief(facts: Dict[str, Any]) -> str:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    chat = LlmChat(
        api_key=os.environ.get("EMERGENT_LLM_KEY", "").strip(),
        session_id=f"ops-brief-{uuid4().hex[:8]}",
        system_message=(
            "You are the operations brain for Haul Yeah Moving, a small weekend moving company in New Jersey. "
            "You get a JSON snapshot of today's operations. Write the owner (Keith) a punchy brief: "
            "3 to 6 short bullet lines, plain text, each starting with '- '. Most urgent first. "
            "Use specific names, job names and dollar amounts from the data. "
            "Start a bullet with 'DO:' when it needs action today (behind jobs, no-crew jobs, conflicts, expired docs, unpaid balances). "
            "If it's genuinely a quiet day, say so in one line and point at the best money move. "
            "No headings, no markdown besides the dashes, no fluff, never invent data."
        ),
    ).with_model("openai", "gpt-5.4")
    resp = await chat.send_message(UserMessage(text=json.dumps(facts, default=str)))
    return (str(resp) or "").strip()[:2500]


@api_router.get("/ai/ops-brief")
async def ai_ops_brief(refresh: int = 0, p: Dict[str, Any] = Depends(require_owner)):
    facts = await _ops_facts()
    cached = await mongo_db.ai_briefs.find_one({"_id": "ops"})
    now = datetime.now(timezone.utc)
    text, generated_at, from_cache = "", None, False
    if cached and not refresh:
        try:
            age = (now - datetime.fromisoformat(cached["generated_at"])).total_seconds()
            if cached.get("date") == facts["date"] and age < 1800 and cached.get("text"):
                text, generated_at, from_cache = cached["text"], cached["generated_at"], True
        except (KeyError, ValueError):
            pass
    if not from_cache:
        try:
            text = await _generate_ops_brief(facts)
            generated_at = now.isoformat()
            await mongo_db.ai_briefs.update_one(
                {"_id": "ops"}, {"$set": {"date": facts["date"], "generated_at": generated_at, "text": text}},
                upsert=True)
        except Exception as exc:
            logger.warning("ops brief generation failed: %s", exc)
            text = (cached or {}).get("text", "")
            generated_at = (cached or {}).get("generated_at")
    return {"facts": facts, "brief": text, "generated_at": generated_at, "cached": from_cache}


# ------- startup seeding

@app.on_event("startup")
async def seed_on_startup():
    try:
        await mongo_db.users.create_index("email", unique=True)
        owner_email = os.environ.get("OWNER_EMAIL", "haulyeahadmin").strip().lower()
        owner_pw = os.environ.get("APP_PASSWORD", "")
        for legacy in ("keithriv24@gmail.com", "haulyeahowner"):
            if owner_email != legacy:
                await mongo_db.users.update_one({"email": legacy}, {"$set": {"email": owner_email}})
        seeds = [
            {"name": "Keith (Owner)", "email": owner_email, "role": "owner", "password": owner_pw},
        ]
        # removed former test accounts (2026-08-08, user request) — clean up any existing copies
        await mongo_db.users.delete_many({"email": {"$in": ["javante@haulyeahmoves.com", "junior@haulyeahmoves.com"]}})
        for s in seeds:
            if not s["password"]:
                continue
            existing = await mongo_db.users.find_one({"email": s["email"]})
            if existing is None:
                await mongo_db.users.insert_one({
                    "_id": str(uuid4()), "name": s["name"], "email": s["email"], "role": s["role"],
                    "password_hash": hash_password(s["password"]), "active": True,
                    "must_change_password": s["role"] != "owner", "gps_consent_at": None, "created_at": now_iso()})
        ghost_seeds = [
            {"name": "Test Crew (Ghost)", "email": "testcrewadmin", "role": "crew"},
            {"name": "Test Sales (Ghost)", "email": "testsalesadmin", "role": "sales"},
            {"name": "Test Marketing (Ghost)", "email": "testmarketingadmin", "role": "marketing"},
        ]
        for g in ghost_seeds:
            if await mongo_db.users.find_one({"email": g["email"]}) is None:
                await mongo_db.users.insert_one({
                    "_id": str(uuid4()), "name": g["name"], "email": g["email"], "role": g["role"],
                    "roles": [g["role"]], "ghost": True,
                    "password_hash": hash_password("HaulYeah2026!"), "active": True,
                    "must_change_password": False, "gps_consent_at": None, "created_at": now_iso()})
        if await mongo_db.trucks.count_documents({}) == 0:
            for i in range(1, 6):
                await mongo_db.trucks.insert_one({"_id": str(uuid4()), "name": f"Truck {i}", "plate": "", "active": True})
        await seed_team_module()
    except Exception as exc:
        logger.error("Startup seeding failed: %s", exc)
    asyncio.create_task(timelog_retry_loop())
    asyncio.create_task(late_alert_loop())
    asyncio.create_task(invoice_sync_loop())
    asyncio.create_task(lead_alert_loop())
    asyncio.create_task(meta_poll_loop())
    if not meta_capi.capi_enabled():
        logger.warning("Meta CAPI disabled — set META_DATASET_ID and META_CAPI_ACCESS_TOKEN "
                       "in the secrets panel to send ad conversion events.")
    capi = meta_capi_config()
    logger.info("Meta CAPI env: dataset_id=%s access_token=%s app_id=%s app_secret=%s test_event_code=%s",
                "set" if capi["dataset_id"] else "unset",
                "set" if capi["access_token"] else "unset",
                "set" if capi["app_id"] else "unset",
                "set" if capi["app_secret"] else "unset",
                "set" if capi["test_event_code"] else "unset")
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
