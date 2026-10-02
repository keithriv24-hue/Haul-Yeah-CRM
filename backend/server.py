import asyncio
import base64
import copy
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
import optimizer
import scope_engine
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
    "quality_docs": "tblpsrrkQlfa7BVW5",
    "nonconformances": "tblDYbrboZq9ClrHM",
    "job_audits": "tblVFJSZCgogIpz4V",
}


def get_api_key() -> str:
    return os.environ.get("AIRTABLE_API_KEY", "").strip()


def get_base_id() -> str:
    return os.environ.get("AIRTABLE_BASE_ID", "").strip()


JWT_ALGORITHM = "HS256"
_login_attempts: Dict[str, Dict[str, float]] = {}

SWITCH_ROLES = ("owner", "sales", "employee", "marketing", "quality")
ALL_ROLES = ("owner", "sales", "employee", "crew", "marketing", "quality")
ROLE_TABLES = {
    "owner": set(TABLES),
    "sales": {"leads", "tasks", "blog"},
    "employee": {"projects", "tasks", "blog"},
    "marketing": {"tasks", "blog"},
    "crew": {"tasks", "blog"},
    "quality": {"projects", "contacts", "tasks", "blog", "quality_docs", "nonconformances", "job_audits"},
}

TASK_GROUPS = ("sales", "marketing", "crew")
TASK_GROUP_FOR_ROLE = {"sales": "sales", "marketing": "marketing", "crew": "crew", "employee": "crew", "quality": "crew"}
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
PROJECT_QUOTED_BY_FIELD = "fldAew7uXk5JvBqBw"   # rule 7: who produced the quote (existing on projects)
PROJECT_SURVEYOR_FIELD = "fldFJUFcOLLRWvc60"    # rule 7: who performed the survey (existing on projects)
# ------- Quality prompt 2: compliance gate inputs on Projects (Airtable field IDs; dateTime = America/New_York)
PROJECT_MOVE_CLASS_F = "fldbtB0QewQLHQjLw"        # select: Household Goods | Office Goods Only | Other Commercial
PROJECT_SURVEY_TYPE_F = "fld1l5Bbd8VRpX6pk"      # select: On site | Video | None
PROJECT_SURVEY_DATE_F = "fldsifpgYiCTcJAb3"      # date
PROJECT_INVENTORY_COMPLETE_F = "fldRqpCyDYQrWJiFE"  # checkbox
PROJECT_BROCHURE_SENT_F = "fldatfvXCQJpcKsU0"    # dateTime
PROJECT_ESTIMATE_DELIVERED_F = "fld1kTfUSGYDLB7HM"  # dateTime
PROJECT_OFS_SIGNED_F = "fldvmMp7NBuw5Jb4M"       # dateTime
PROJECT_SHORT_NOTICE_PROOF_F = "fldiseTBH76U5bXbq"  # long text
PROJECT_PROTECTION_OPTION_F = "fldBxR8F0ju95dWjV"   # select: Option 1 | Option 2 | Option 3
PROJECT_DECLARED_VALUE_F = "fldCjcgmTBaNJGP6a"   # currency
PROJECT_DEDUCTIBLE_F = "fldL9XhtIwfiqLdjs"       # currency
PROJECT_OWNER_OP_USED_F = "fldRpTPIT3VjEvaNv"    # checkbox
PROJECT_OWNER_OP_NOTICE_F = "fldH679ulF2rwlsSe"  # dateTime
PROJECT_LABOR_EQUIP_F = "fldHghhcEkZSNR7Qz"      # select: None | Agreed in writing | Not agreed
PROJECT_ONE_WAY_MILES_F = "fld1ADOejPKkHNfbN"    # number
PROJECT_LONG_HAUL_ACK_F = "fldwqdmCOvlNeo1u4"    # checkbox (OWNER-only write)
PROJECT_COMPLETED_STATUS = "Completed"          # exact singleSelect value; NEVER "Complete" (that's TASKS)
BLOCKED_FIELDS = {
    ("employee", "projects"): {PROJECT_QUOTE_FIELD, PROJECT_DEPOSIT_FIELD, PROJECT_REVENUE_FIELD},
    ("sales", "projects"): {PROJECT_REVENUE_FIELD, PROJECT_DEPOSIT_FIELD},
    ("quality", "projects"): {PROJECT_REVENUE_FIELD},   # quality sees the quote, never revenue
}
DRIVER_RATE = 28
HELPER_RATE = 24

# ------- Quality & Compliance module — Airtable field IDs (reference by exact ID; never write AUTONUMBER/FORMULA)
# quality_docs
QD_NAME_F = "fld3W18nU4Io2ZZNV"
QD_VERSION_F = "fldiDIwr9JW8hPCzD"
QD_EFFECTIVE_F = "fldT6Y875tNiquvuX"
QD_OWNER_F = "fldLjP5CWmyqnZ9Mz"
QD_REVIEW_F = "fldJpv1V4gzYMFeDY"
QD_STATUS_F = "fldvFny72rpqL8Gq7"
QD_DRIVE_F = "fldCZuors8kOtxo4Z"
QD_NOTES_F = "fldX9QV8g2HjF5tnQ"
# nonconformances  (NC number fldrmgtcxlPwNdzkw = AUTONUMBER, read-only)
NC_NUMBER_F = "fldrmgtcxlPwNdzkw"
NC_RAISED_BY_F = "fldEImK9opqEgqUlS"
NC_RAISED_DATE_F = "fld0CIIBJ4ONEPB7K"
NC_TYPE_F = "fldJcoMjr8CWfpw89"
NC_SEVERITY_F = "fldZjx6p4spGnJkiV"
NC_WHAT_F = "fldzMOMAv7N762lzo"
NC_IMMEDIATE_F = "fldjUQA70Llyko0pY"
NC_ROOT_F = "fldI1z8PvBXwLwECr"
NC_CORRECTIVE_F = "fldMayZQl7txWLmrZ"
NC_VERIFY_DATE_F = "fldLIfdho83ko7VCw"
NC_STATUS_F = "fldHMZHQBqbI0KOTe"
NC_CLOSED_BY_F = "fldtabcHA42ln02nr"
NC_CLOSED_DATE_F = "fldefdFzqGo7xz153"
NC_LINKED_JOB_F = "fldenMuCifGb9sc5n"
# job_audits  (Audit number fldsa0PZkrqe8029F + Audit due fldQVm8CyjurFAgyJ = read-only)
JA_NUMBER_F = "fldsa0PZkrqe8029F"
JA_COMPLETED_DATE_F = "fldcTXzOnPN4UynoG"
JA_AUDIT_DUE_F = "fldQVm8CyjurFAgyJ"
JA_AUDITOR_F = "fldYOjPbBIkx5Lf9Z"
JA_BOL_F = "fldYXIYUXAmisK4SD"
JA_QUOTED_TOTAL_F = "fldcRVrYi4RvI1f8g"
JA_FINAL_TOTAL_F = "fldopn48enx6Xkg1f"
JA_VARIANCE_EXPLAINED_F = "fldHbvmW6KUNQuyuw"
JA_EST_HOURS_F = "fldmTWweMfFkFdAod"
JA_ACTUAL_HOURS_F = "fldq7VZ4bHyiRpk1W"
JA_GATES_F = "fldlFQ0Ovpe8CYRPs"
JA_RESULT_F = "fldc6beKUsF8nHdWO"
JA_FINDINGS_F = "fldUp6XjCp9kLl00e"
JA_SIGNED_BOL_F = "fld8Hu5BuK7oI6dE1"
JA_LINKED_NC_F = "fldJZDkUMcLRDnx3r"
JA_LINKED_JOB_F = "fldYjt6xsNHq2U2Qn"
# claims  (Prompt 3) — Claim number + Form due + Settlement due are read-only (AUTONUMBER/FORMULA)
CLAIMS_TABLE = "tblsdVcVP6uhtxOrK"
CLAIM_NUMBER_F = "fldz1Ph1KXjZYNUDf"          # AUTONUMBER — read-only, primary
CLAIM_LINKED_JOB_F = "fldW0Uk8sWQVuTVGT"      # link -> projects
CLAIM_NOTICE_DATE_F = "fldvFYGanrCdOqh3H"     # date
CLAIM_FORM_DUE_F = "fldFo2HfKyF0VxeHW"        # FORMULA read-only = Notice received + 7
CLAIM_FORM_SENT_F = "fldVqh1bH658FlBW0"       # date
CLAIM_COMPLETED_RECEIVED_F = "fldQ5QVOaYUPMO8gJ"  # date
CLAIM_SETTLEMENT_DUE_F = "fldRF1W2uYa5G6kFw"  # FORMULA read-only = Completed + 90 (or +120 w/ extension — ALREADY applied)
CLAIM_EXTENSION_F = "fldesCpx3bWzECiqQ"       # checkbox
CLAIM_PROTECTION_F = "fldK3KGRhjpFWtuKn"      # select: Option 1 | Option 2 | Option 3
CLAIM_AMOUNT_CLAIMED_F = "fldWn6i4YVB4FKEeL"  # currency
CLAIM_AMOUNT_SETTLED_F = "fldNyl5TbFysjnpIR"  # currency — OWNER ONLY
CLAIM_STATUS_F = "fldqZeAhghtBQ7TZP"          # select (see CLAIM_STATUSES)
CLAIM_NOTES_F = "fldZwaSbKfoS3LLZl"           # long text
CLAIM_LINKED_NC_F = "fldSaXHJjhPBpiFP0"       # link -> nonconformances
CLAIM_STATUSES = ["Notice received", "Form sent", "Awaiting customer", "Under review", "Settled", "Denied", "Withdrawn"]


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


VIEW_AS_TTL_MINUTES = 120  # owner "View As" sessions are short-lived and cannot self-escalate


def make_view_as_token(view_role: str, owner_uid: Optional[str]) -> str:
    """Short-lived owner impersonation token.

    It presents the view role for RBAC (role-only, no authenticated user identity),
    records the originating owner via as_owner_uid, and is flagged view_as so the
    switch-role endpoint refuses to let it change views or climb back to owner.
    """
    claims = {
        "sub": view_role, "role": view_role, "type": "access",
        "view_as": True, "as_owner_uid": owner_uid,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=VIEW_AS_TTL_MINUTES),
    }
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
        allowed.add("projects")  # read of the job board (compliance panel); writes still blocked below
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

# ------- Pricing Spec v2.0 — the SINGLE source of truth for every dollar the calculator uses.
DEFAULT_RATES = {
    # core
    "manHourRate": 65.0, "cushionPercent": 10.0, "depositPercent": 25.0,
    "roundingIncrement": 25.0, "manHoursPer100CuFt": 2.10,
    # trip fees, price floors, hour minimums
    "tripFeeTruck": 125.0, "tripFeeLabor": 75.0,
    "floorTruck": 650.0, "floorLabor": 375.0,
    "minHoursTruck": 3.0, "minHoursLabor": 2.0,
    # mileage (one-way; the first N miles ride free in the trip fee, then per-mile)
    "mileageFreeMiles": 20.0, "mileageRatePerMile": 8.00,
    # access & handling (flat, never volume-scaled)
    "stairFlightFee": 85.0, "longCarryFee": 100.0, "disassemblyFee": 100.0, "extraStopFee": 125.0,
    # specialty surcharges
    "surchargeUprightPiano": 500.0, "surchargeGrandPiano": 800.0, "surchargePoolTable": 600.0,
    "surchargeSafeT1": 200.0, "surchargeSafeT2": 500.0, "surchargeSafeT3": 800.0,
    "surchargeGymT1": 150.0, "surchargeGymT2": 300.0, "surchargeMotorcycle": 300.0,
    # materials
    "materialMattressBag": 15.0, "materialWardrobeBox": 12.0, "materialTvBox": 25.0,
    # custom specialty items — banded handling dollars + ratio modifiers
    "surchargeCustomB1": 75.0, "surchargeCustomB2": 150.0,
    "surchargeCustomB3": 250.0, "surchargeCustomB4": 400.0,
    "customBuiltInMultiplier": 1.25, "customDisconnectMultiplier": 1.15,
    "customSwapFactor": 0.60, "specialtyHandlingCapPct": 30.0,
    # rules
    "hardFloorBedrooms": 3.0, "hardFloorHours": 6.0,
    # capacity & scheduling (crew counts / hours — never dollar figures, never cushion-folded)
    "maxCrewPerDay": 12.0, "targetHoursOnSite": 8.0, "maxHoursOnSite": 10.0,
    # package defaults (crew / hours-on-site per home size)
    "pkgStudioCrew": 2.0, "pkgStudioHours": 3.5,
    "pkg2brCrew": 3.0, "pkg2brHours": 5.5,
    "pkg3brCrew": 4.0, "pkg3brHours": 6.5,
    "pkg4brCrew": 4.0, "pkg4brHours": 8.0,
}
RATE_STRING_KEYS = {"serviceStates": "NJ"}

# dollar keys that get the cushion folded in for the sales tier, so the payload
# they receive never contains the cushion itself yet prices out identically
CUSHION_FOLDED_KEYS = (
    "manHourRate", "tripFeeTruck", "tripFeeLabor",
    "mileageRatePerMile",
    "stairFlightFee", "longCarryFee", "disassemblyFee", "extraStopFee",
    "surchargeUprightPiano", "surchargeGrandPiano", "surchargePoolTable",
    "surchargeSafeT1", "surchargeSafeT2", "surchargeSafeT3",
    "surchargeGymT1", "surchargeGymT2", "surchargeMotorcycle",
    "surchargeCustomB1", "surchargeCustomB2", "surchargeCustomB3", "surchargeCustomB4",
    "materialMattressBag", "materialWardrobeBox", "materialTvBox",
)


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
        "surveyor_attested": bool(user.get("surveyor_attested")),
        "crew_docs_expiry": user.get("crew_docs_expiry"),
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
    if not email:
        raise HTTPException(status_code=401,
                            detail="Shared passwords are retired. Sign in with your own username or email and password.")
    return await _login_user_account(payload, email, lock_key, fail)


class SwitchPayload(BaseModel):
    role: str


@auth_router.post("/switch-role")
async def switch_role(payload: SwitchPayload, request: Request):
    token_payload = decode_token(request)
    # A View-As (impersonation) session is a dead end: it can never switch again — not
    # to another view, and never back to owner. The owner returns to their own account
    # by restoring their original authenticated session in the browser, not via this API.
    # owner_switch covers any legacy tokens still in the wild from before this change.
    if token_payload.get("view_as") or token_payload.get("owner_switch"):
        raise HTTPException(status_code=403,
                            detail="You're in View As mode. Exit to your owner account to change views.")
    uid = token_payload.get("uid")
    if not uid:
        # Role-only tokens carry no authenticated user — they can never switch.
        raise HTTPException(status_code=403, detail="Only the owner can switch views.")
    user = await mongo_db.users.find_one({"_id": uid})
    if not user or not user.get("active", True):
        raise HTTPException(status_code=401, detail="This account is turned off. Talk to the owner.")
    roles = user.get("roles") or [user.get("role")]
    if payload.role == "owner":
        if "owner" not in roles:
            raise HTTPException(status_code=403, detail="You don't have that view.")
        return {"token": make_user_token(user, role="owner"), "role": "owner",
                "can_switch": True, "user": _user_public(user)}
    if "owner" in roles:
        if payload.role not in SWITCH_ROLES:
            raise HTTPException(status_code=422, detail="Unknown role.")
        # Owner impersonation → short-lived, non-escalating View-As token.
        return {"token": make_view_as_token(payload.role, uid), "role": payload.role,
                "can_switch": False, "view_as": True}
    # Multi-role, non-owner user switching among their own granted roles.
    if payload.role not in roles:
        raise HTTPException(status_code=403, detail="You don't have that view.")
    return {"token": make_user_token(user, role=payload.role), "role": payload.role,
            "can_switch": len(roles) > 1, "user": _user_public(user)}


@auth_router.get("/me")
async def me(request: Request):
    token_payload = decode_token(request)
    p = await principal_from_payload(token_payload)
    view_as = bool(token_payload.get("view_as") or token_payload.get("owner_switch"))
    can_switch = (not view_as) and (p["role"] == "owner" or len(p.get("roles") or []) > 1)
    user = None
    if p["is_user"]:
        doc = await mongo_db.users.find_one({"_id": p["user_id"]})
        user = _user_public(doc) if doc else None
    return {"ok": True, "role": p["role"], "can_switch": can_switch, "view_as": view_as, "user": user}


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


async def get_rates_values() -> Dict[str, Any]:
    """Current pricing config. Seeds from defaults (migrating any legacy scope_pricing keys) on first read."""
    doc = await mongo_db.settings.find_one({"_id": "calculator_rates"}) or {}
    stored = doc.get("pricing_v2")
    if not stored:
        legacy = doc.get("scope_pricing") or {}
        stored = {**DEFAULT_RATES, **{k: v for k, v in legacy.items() if k in DEFAULT_RATES}, **RATE_STRING_KEYS}
        await mongo_db.settings.update_one(
            {"_id": "calculator_rates"},
            {"$set": {"pricing_v2": stored, "pricing_v2_updated_at": {}}}, upsert=True)
    if "mileageRatePerMile" not in stored:
        # 2026-06 migration: zone flat fees → per-mile mileage, stairs $80 → $85
        stored["mileageRatePerMile"] = DEFAULT_RATES["mileageRatePerMile"]
        stored["mileageFreeMiles"] = float(stored.get("zone1MaxMiles") or DEFAULT_RATES["mileageFreeMiles"])
        if float(stored.get("stairFlightFee") or 0) == 80.0:
            stored["stairFlightFee"] = 85.0
        for k in ("zone1MaxMiles", "zone1Fee", "zone2MaxMiles", "zone2Fee", "zone3MaxMiles", "zone3Fee"):
            stored.pop(k, None)
        await mongo_db.settings.update_one(
            {"_id": "calculator_rates"}, {"$set": {"pricing_v2": stored}}, upsert=True)
    out: Dict[str, Any] = {**DEFAULT_RATES, **RATE_STRING_KEYS}
    out.update({k: v for k, v in stored.items() if k in DEFAULT_RATES or k in RATE_STRING_KEYS})
    # Stage 7 read-through: the base labor rate (mh/100 cu ft) and package HOURS are authoritative in
    # the estimating_params record — legacy rate consumers read those values through here so a learned
    # calibration flows into every calculator tier. (Monetary manHourRate/fees/crew counts stay in rates.)
    est = await _estimating_active()
    ep = est["params"]
    out["manHoursPer100CuFt"] = float(ep.get("manHoursPer100CuFt", out["manHoursPer100CuFt"]))
    ph = ep.get("packageHours") or {}
    for rate_key, size in (("pkgStudioHours", "studio"), ("pkg2brHours", "br2"),
                           ("pkg3brHours", "br3"), ("pkg4brHours", "br4")):
        if ph.get(size) is not None:
            out[rate_key] = float(ph[size])
    return out


@api_router.get("/settings/rates")
async def get_rates(p: Dict[str, Any] = Depends(require_owner)):
    values = await get_rates_values()
    doc = await mongo_db.settings.find_one({"_id": "calculator_rates"}) or {}
    est = await _estimating_active()
    return {**values, "_updatedAt": doc.get("pricing_v2_updated_at", {}),
            "_calibrationSeq": est["calibration_seq"], "_calibrationVersion": est["calibration_version"]}


@api_router.put("/settings/rates")
async def save_rates(payload: Dict[str, Any], p: Dict[str, Any] = Depends(require_owner)):
    est = await _estimating_active()
    est_params = est["params"]
    current = await get_rates_values()
    reason = str(payload.get("reason") or "").strip()
    expected_seq = payload.get("expected_calibration_seq")

    est_changes: List[Tuple[str, str, Any, float, Optional[float]]] = []
    values = dict(current)
    for k, v in payload.items():
        if k in EST_RATE_KEYS:
            try:
                n = float(v)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail=f"'{k}' must be a number.")
            if n < 0:
                raise HTTPException(status_code=422, detail="Values can't be negative.")
            factor, size = EST_RATE_KEYS[k]
            path, _grp, bounds, label = CALIB_SCALARS[factor]
            authoritative = _get_path(est_params, path)
            if authoritative is None or abs(n - float(authoritative)) > 1e-9:
                if not (bounds[0] <= n <= bounds[1]):
                    raise HTTPException(status_code=422,
                                        detail=f"{label} must be between {bounds[0]} and {bounds[1]}.")
                est_changes.append((k, factor, size, n,
                                    float(authoritative) if authoritative is not None else None))
            values[k] = n
        elif k in DEFAULT_RATES:
            try:
                n = float(v)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail=f"'{k}' must be a number.")
            if n < 0:
                raise HTTPException(status_code=422, detail="Rates can't be negative.")
            values[k] = n
        elif k in RATE_STRING_KEYS:
            values[k] = (str(v or "").strip().upper()[:100]) or RATE_STRING_KEYS[k]
    if values["roundingIncrement"] < 1:
        raise HTTPException(status_code=422, detail="The rounding increment must be at least $1.")

    # A change to the base labor rate or package HOURS is a calibration change: reason + audit version,
    # auto-lock so the optimizer can't undo it, applied to NEW calculations only (snapshots preserved).
    if est_changes:
        if len(reason) < 5:
            raise HTTPException(status_code=422,
                                detail="A reason (5+ characters) is required to change the base labor rate or package hours.")
        new_params = copy.deepcopy(est_params)
        new_locks = dict(est["locks"])
        changes_rec: List[Dict[str, Any]] = []
        for (k, factor, size, n, before) in est_changes:
            path, group, _b, label = CALIB_SCALARS[factor]
            _set_path(new_params, path, n)
            new_locks[group] = {"locked": True, "by": p.get("name"), "at": now_iso(),
                                "reason": f"Owner manually set {label} to {n}"}
            changes_rec.append({"factor": factor, "key": ".".join(path), "before": before,
                                "after": n, "locked": True})
        await _apply_calibration(new_params, trigger="manual_edit", actor=p, reason=reason,
                                 changes=changes_rec, locks=new_locks,
                                 expected_seq=int(expected_seq) if expected_seq is not None else None)
        await audit(p, "edited estimating parameters via rates", "estimating_params",
                    {"changes": changes_rec, "reason": reason})

    # Estimating keys read through from estimating_params — keep only the monetary keys in pricing_v2.
    monetary = {k: v for k, v in values.items() if k not in EST_RATE_KEYS}
    doc = await mongo_db.settings.find_one({"_id": "calculator_rates"}) or {}
    stamps = doc.get("pricing_v2_updated_at", {})
    ts = datetime.now(timezone.utc).isoformat()
    for k, v in monetary.items():
        if v != current.get(k):
            stamps[k] = ts
    for (k, *_rest) in est_changes:
        stamps[k] = ts
    await mongo_db.settings.update_one(
        {"_id": "calculator_rates"},
        {"$set": {"pricing_v2": monetary, "pricing_v2_updated_at": stamps}}, upsert=True)
    out = await get_rates_values()
    est2 = await _estimating_active()
    return {**out, "_updatedAt": stamps, "_calibrationSeq": est2["calibration_seq"],
            "_calibrationVersion": est2["calibration_version"]}


# ------- Stage 5: learnable estimating parameters (non-monetary) -------
# ONE record (_id="estimating_params") holds the engine's learnable WORK-MODEL knobs at today's
# exact values. Seeded once; manHoursPer100CuFt + packageHours mirror live rates so nothing can drift
# out of parity in Stage 5. calibration_version="v0" (the frozen baseline Stage 6 compares against).
# Adding these knobs changes NO quote — the seed reproduces the current engine exactly.
EST_ENGINE_KEYS = ("packingMult", "accessPer", "itemMult", "crewEfficiency",
                   "avgDriveMph", "travelInHours", "travelOutHours")


async def _estimating_engine_doc() -> Dict[str, Any]:
    doc = await mongo_db.settings.find_one({"_id": "estimating_params"})
    if not doc or not doc.get("params"):
        seed = scope_engine.estimating_defaults()
        await mongo_db.settings.update_one(
            {"_id": "estimating_params"},
            {"$set": {"params": seed, "calibration_version": "v0", "calibration_seq": 0,
                      "seeded_at": now_iso(), "updated_at": now_iso()}}, upsert=True)
        return {"params": seed, "calibration_version": "v0"}
    return doc


EST_RATE_KEYS = {
    # legacy /settings/rates key -> (calibration factor, package size or None)
    "manHoursPer100CuFt": ("base_rate", None),
    "pkgStudioHours": ("package_studio", "studio"),
    "pkg2brHours": ("package_br2", "br2"),
    "pkg3brHours": ("package_br3", "br3"),
    "pkg4brHours": ("package_br4", "br4"),
}


def _default_calibration_baselines() -> Dict[str, Any]:
    d = scope_engine.estimating_defaults()
    return {
        "base_rate": float(DEFAULT_RATES["manHoursPer100CuFt"]),
        "package_studio": float(DEFAULT_RATES["pkgStudioHours"]),
        "package_br2": float(DEFAULT_RATES["pkg2brHours"]),
        "package_br3": float(DEFAULT_RATES["pkg3brHours"]),
        "package_br4": float(DEFAULT_RATES["pkg4brHours"]),
        "multipliers": {"packingMult": list(d["packingMult"]),
                        "accessPer": dict(d["accessPer"]), "itemMult": float(d["itemMult"])},
        "crew_efficiency": dict(d["crewEfficiency"]),
        "drive_speed": float(d["avgDriveMph"]),
    }


async def _estimating_active() -> Dict[str, Any]:
    """Authoritative estimating state. `params` OWNS the base labor rate (manHoursPer100CuFt) and package
    HOURS in addition to the engine knobs — the legacy rates API reads those through. Also carries the
    sequential calibration version/seq, per-factor locks, optimizer baselines and the optimizer on/off
    state. Self-seeds once (from the current rate doc) and normalizes missing scaffolding — no math change."""
    doc = await mongo_db.settings.find_one({"_id": "estimating_params"}) or {}
    defaults = scope_engine.estimating_defaults()
    params = dict(doc.get("params") or {})
    set_fields: Dict[str, Any] = {}
    for k in EST_ENGINE_KEYS:
        if k not in params:
            params[k] = defaults[k]
    if "manHoursPer100CuFt" not in params or not isinstance(params.get("packageHours"), dict):
        rd = await mongo_db.settings.find_one({"_id": "calculator_rates"}) or {}
        stored = rd.get("pricing_v2") or {}
        params.setdefault("manHoursPer100CuFt",
                          float(stored.get("manHoursPer100CuFt", DEFAULT_RATES["manHoursPer100CuFt"])))
        if not isinstance(params.get("packageHours"), dict):
            params["packageHours"] = {
                "studio": float(stored.get("pkgStudioHours", DEFAULT_RATES["pkgStudioHours"])),
                "br2": float(stored.get("pkg2brHours", DEFAULT_RATES["pkg2brHours"])),
                "br3": float(stored.get("pkg3brHours", DEFAULT_RATES["pkg3brHours"])),
                "br4": float(stored.get("pkg4brHours", DEFAULT_RATES["pkg4brHours"]))}
        set_fields["params"] = params
    seq = int(doc.get("calibration_seq", 0))
    version = doc.get("calibration_version") or "v0"
    locks = doc.get("locks")
    baselines = doc.get("baselines")
    opt = doc.get("optimizer")
    if "calibration_seq" not in doc:
        set_fields["calibration_seq"] = seq
    if not doc.get("calibration_version"):
        set_fields["calibration_version"] = version
    if not isinstance(locks, dict):
        locks = {}
        set_fields["locks"] = locks
    if not isinstance(baselines, dict):
        baselines = _default_calibration_baselines()
        set_fields["baselines"] = baselines
    if not isinstance(opt, dict):
        opt = {"activated": False, "paused": False}
        set_fields["optimizer"] = opt
    if set_fields:
        set_fields.setdefault("seeded_at", doc.get("seeded_at") or now_iso())
        set_fields["updated_at"] = now_iso()
        await mongo_db.settings.update_one({"_id": "estimating_params"}, {"$set": set_fields}, upsert=True)
    return {"params": params, "calibration_version": version, "calibration_seq": seq,
            "locks": locks, "baselines": baselines, "optimizer": opt}


async def get_estimating_params() -> Dict[str, Any]:
    """Current estimating parameters (authoritative). Base rate + package hours live in estimating_params
    and read through to the rates API; the engine knobs come from the same record. Served to all tiers, so
    it carries no lock/optimizer internals (those are owner+Quality-only via the optimizer state endpoint)."""
    est = await _estimating_active()
    p = dict(scope_engine.estimating_defaults())
    p.update({k: v for k, v in est["params"].items() if k in EST_ENGINE_KEYS})
    p["manHoursPer100CuFt"] = float(est["params"].get("manHoursPer100CuFt", DEFAULT_RATES["manHoursPer100CuFt"]))
    ph = est["params"].get("packageHours") or {}
    p["packageHours"] = {"studio": float(ph.get("studio", DEFAULT_RATES["pkgStudioHours"])),
                         "br2": float(ph.get("br2", DEFAULT_RATES["pkg2brHours"])),
                         "br3": float(ph.get("br3", DEFAULT_RATES["pkg3brHours"])),
                         "br4": float(ph.get("br4", DEFAULT_RATES["pkg4brHours"]))}
    p["calibration_version"] = est["calibration_version"]
    p["calibration_seq"] = est["calibration_seq"]
    return p


def _pricing_version(rates: Dict[str, Any]) -> str:
    """Stable short hash of the monetary settings so a scope records which price world it was quoted in."""
    monetary = {k: rates.get(k) for k in sorted(rates.keys())}
    return hashlib.sha256(json.dumps(monetary, sort_keys=True, default=str).encode()).hexdigest()[:12]


@api_router.get("/settings/estimating-params")
async def get_estimating_params_endpoint(request: Request):
    # Served to EVERY calculator tier (incl. survey) — these values are non-monetary.
    await require_scope_tier(request)
    params = await get_estimating_params()
    return {**params, "feature_registry": scope_engine.feature_registry()}


class EstimatingParamsPayload(BaseModel):
    params: Dict[str, Any]


@api_router.put("/settings/estimating-params")
async def put_estimating_params(payload: EstimatingParamsPayload, p: Dict[str, Any] = Depends(require_owner)):
    """Owner edit of the engine knobs (packingMult/accessPer/itemMult/crewEfficiency/scheduling).
    manHoursPer100CuFt + package hours stay in /settings/rates. No auto-suggestions in Stage 5."""
    doc = await _estimating_engine_doc()
    current = dict(doc.get("params") or scope_engine.estimating_defaults())
    for k in EST_ENGINE_KEYS:
        if k in payload.params:
            current[k] = payload.params[k]
    await mongo_db.settings.update_one(
        {"_id": "estimating_params"},
        {"$set": {"params": current, "updated_at": now_iso(), "updated_by": p.get("name")}}, upsert=True)
    await audit(p, "edited estimating parameters", "estimating_params", {})
    return await get_estimating_params()


# ======= Stage 7: guarded auto-optimizer + calibration versioning =======
# The optimizer LEARNS non-monetary work-model parameters from completed-job outcomes and, once the owner
# has explicitly ACTIVATED it, automatically applies bounded, movement-capped, accuracy-gated changes on a
# nightly run (2:30 AM ET, after outcome reconcile) and on an authorized "Run now". Before activation or
# while paused it computes SHADOW results only and never changes an active parameter. Every applied update,
# manual edit and rollback is a sequential calibration version with an append-only history row; rejected
# candidates and no-op runs live in the run log, not the version history. Saved/sent quotes keep their
# recorded calibration snapshot — nothing is ever retro-repriced.
LOCK_GROUPS = ("base_rate", "package_studio", "package_br2", "package_br3", "package_br4",
               "multipliers", "crew_efficiency", "drive_speed")

# manual-settable scalar factors -> (param path, lock group, sane bounds, human label)
CALIB_SCALARS: Dict[str, Any] = {
    "base_rate": (("manHoursPer100CuFt",), "base_rate", (1.2, 3.5), "Base rate (mh / 100 cu ft)"),
    "package_studio": (("packageHours", "studio"), "package_studio", (1.0, 24.0), "Package hours — Studio/1BR"),
    "package_br2": (("packageHours", "br2"), "package_br2", (1.0, 24.0), "Package hours — 2BR"),
    "package_br3": (("packageHours", "br3"), "package_br3", (1.0, 24.0), "Package hours — 3BR"),
    "package_br4": (("packageHours", "br4"), "package_br4", (1.0, 24.0), "Package hours — 4BR+"),
    "item_mult": (("itemMult",), "multipliers", (0.5, 2.0), "Item man-hour multiplier"),
    "crew_2": (("crewEfficiency", "2"), "crew_efficiency", (0.8, 1.2), "Crew efficiency — 2 movers"),
    "crew_3": (("crewEfficiency", "3"), "crew_efficiency", (0.8, 1.2), "Crew efficiency — 3 movers"),
    "crew_4": (("crewEfficiency", "4"), "crew_efficiency", (0.8, 1.2), "Crew efficiency — 4 movers"),
    "crew_5plus": (("crewEfficiency", "5plus"), "crew_efficiency", (0.8, 1.2), "Crew efficiency — 5+ movers"),
    "drive_speed": (("avgDriveMph",), "drive_speed", (10.0, 45.0), "Drive speed (mph — scheduling only)"),
}


def _f(v: Any, d: float = 0.0) -> float:
    try:
        f = float(v)
        return f if f == f else d
    except (TypeError, ValueError):
        return d


def _get_path(d: Dict[str, Any], path: Tuple[str, ...]) -> Any:
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _set_path(d: Dict[str, Any], path: Tuple[str, ...], value: Any) -> None:
    cur = d
    for k in path[:-1]:
        nxt = cur.get(k)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[k] = nxt
        cur = nxt
    cur[path[-1]] = value


async def _apply_calibration(new_params: Dict[str, Any], *, trigger: str, actor: Any, reason: str,
                             changes: List[Dict[str, Any]], locks: Optional[Dict[str, Any]] = None,
                             baselines: Optional[Dict[str, Any]] = None, run_id: Optional[str] = None,
                             extras: Optional[Dict[str, Any]] = None,
                             expected_seq: Optional[int] = None) -> Dict[str, Any]:
    """Atomically (CAS on calibration_seq) bump the version, persist the new params/locks/baselines, and
    append ONE immutable calibration_history row. Rejects a stale concurrent update with 409."""
    doc = await mongo_db.settings.find_one({"_id": "estimating_params"}) or {}
    cur_seq = int(doc.get("calibration_seq", 0))
    if expected_seq is not None and int(expected_seq) != cur_seq:
        raise HTTPException(status_code=409, detail="This calibration changed since you loaded it. Refresh and try again.")
    new_seq = cur_seq + 1
    version = f"v{new_seq}"
    set_doc = {"params": new_params, "calibration_seq": new_seq, "calibration_version": version,
               "updated_at": now_iso(), "updated_by": (actor.get("name") if isinstance(actor, dict) else str(actor))}
    if locks is not None:
        set_doc["locks"] = locks
    if baselines is not None:
        set_doc["baselines"] = baselines
    res = await mongo_db.settings.update_one(
        {"_id": "estimating_params", "calibration_seq": cur_seq}, {"$set": set_doc})
    if res.modified_count != 1:
        raise HTTPException(status_code=409, detail="Calibration was updated concurrently — please retry.")
    hist = {"_id": str(uuid4()), "version": version, "seq": new_seq, "at": now_iso(),
            "type": trigger, "trigger": trigger, "reason": reason,
            "actor": (actor.get("name") if isinstance(actor, dict) else str(actor)),
            "actor_id": (actor.get("user_id") if isinstance(actor, dict) else None),
            "actor_role": (actor.get("role") if isinstance(actor, dict) else "system"),
            "changes": changes, "params_after": new_params,
            "locks_after": (locks if locks is not None else doc.get("locks") or {}),
            "baselines_after": (baselines if baselines is not None else doc.get("baselines") or {}),
            "run_id": run_id, **(extras or {})}
    await mongo_db.calibration_history.insert_one(hist)
    return {"version": version, "seq": new_seq, "history": hist}


def _optimizer_training_data(outcomes: List[Dict[str, Any]], params: Dict[str, Any]) -> Dict[str, Any]:
    """Turn residential completed-job outcomes into per-factor observations for optimizer.py. Commercial
    jobs are excluded from every fitting metric (single residential calibration track)."""
    pack_mults = params.get("packingMult") if isinstance(params.get("packingMult"), list) else scope_engine.PACKING_MULT
    base_rate: List[Dict[str, Any]] = []
    pkg: Dict[str, List[Dict[str, Any]]] = {"studio": [], "br2": [], "br3": [], "br4": []}
    crew: Dict[str, List[Dict[str, Any]]] = {"2": [], "3": [], "4": [], "5plus": []}
    drive: List[Dict[str, Any]] = []
    mult: List[Dict[str, Any]] = []
    job_keys: List[str] = []
    for o in outcomes:
        if not o.get("learning_eligible"):
            continue
        errs = o.get("errors") or {}
        if errs.get("model_work_mh_error") is None:
            continue
        q = o.get("quote") or {}
        inputs = q.get("inputs") or {}
        if inputs.get("commercial") or o.get("commercial"):
            continue
        actuals = o.get("actuals") or {}
        work = actuals.get("work_man_hours")
        if work is None:
            continue
        work = float(work)
        feats = scope_engine.compute_scope_features(inputs, params)
        date = (o.get("job_date") or "")[:10]
        wt = 1.0
        job_keys.append(o["_id"])
        pack = int(feats.get("pack") or 0)
        pmult = float(pack_mults[pack]) if 0 <= pack < len(pack_mults) else 1.0
        base_rate.append({"work_mh": work, "access_mh": feats.get("access_mh") or 0.0,
                          "item_mh": feats.get("item_mh") or 0.0, "volume_units": feats.get("volume_units") or 0.0,
                          "packing_mult": pmult, "weight": wt, "date": date})
        size = inputs.get("pkg") or ""
        onsite_actual = actuals.get("on_site_hours")
        if size in pkg and onsite_actual is not None:
            pkg[size].append({"actual_hours": float(onsite_actual), "weight": wt, "date": date})
        try:
            crew_n = int(float(q.get("crew_rec"))) if q.get("crew_rec") is not None else None
        except (TypeError, ValueError):
            crew_n = None
        cadj = actuals.get("crew_adjusted_work_hours")
        if crew_n and crew_n > 0 and cadj:
            bucket = "2" if crew_n <= 2 else "3" if crew_n == 3 else "4" if crew_n == 4 else "5plus"
            model_onsite = (feats.get("predicted_work_mh") or 0.0) / crew_n
            crew[bucket].append({"model_onsite": model_onsite, "actual_onsite": float(cadj), "weight": wt, "date": date})
        mult.append({"pack": pack, "access_units": feats.get("access_units") or {},
                     "item_mh_base": feats.get("item_mh_base") or 0.0, "volume_units": feats.get("volume_units") or 0.0,
                     "rate_used": feats.get("rate_used") or params.get("manHoursPer100CuFt"),
                     "work_mh": work, "weight": wt, "date": date})
    return {"base_rate": base_rate, "package": pkg, "crew": crew, "drive": drive,
            "multipliers": mult, "usable_count": len(job_keys), "job_keys": job_keys}


async def run_optimizer(trigger: str, actor: Any = "system", *, run_id: Optional[str] = None) -> Dict[str, Any]:
    """One optimizer pass. SHADOW (no changes) unless the optimizer is activated and not paused; then it
    applies every eligible, unlocked, gate-passing candidate as ONE calibration version. Always writes a
    run-log row (candidates + guardrail decisions, incl. rejected). Identical data => a no-op on re-run."""
    est = await _estimating_active()
    params, locks, baselines = est["params"], est["locks"], est["baselines"]
    opt = est["optimizer"]
    activated, paused = bool(opt.get("activated")), bool(opt.get("paused"))
    outcomes = await mongo_db.job_outcomes.find({}).to_list(3000)
    data = _optimizer_training_data(outcomes, params)

    ph = params.get("packageHours") or {}
    mult_current = {"packingMult": params.get("packingMult"), "accessPer": params.get("accessPer"),
                    "itemMult": params.get("itemMult")}
    br = optimizer.base_rate_run(data["base_rate"], float(params.get("manHoursPer100CuFt", 2.1)),
                                 float(baselines.get("base_rate", 2.1)))
    pkg_runs: Dict[str, Any] = {}
    for size, factor in (("studio", "package_studio"), ("br2", "package_br2"),
                         ("br3", "package_br3"), ("br4", "package_br4")):
        cur = _f(ph.get(size), 5.0)
        pkg_runs[size] = optimizer.package_hours_run(data["package"][size], cur,
                                                     float(baselines.get(factor, cur)))
    crew_run = optimizer.crew_efficiency_run(data["crew"], params.get("crewEfficiency") or {})
    drive_run = optimizer.drive_speed_run(data["drive"], float(params.get("avgDriveMph", 25)))
    mult_run = optimizer.multiplier_joint_run(data["multipliers"], mult_current,
                                              baselines.get("multipliers") or {}, list(scope_engine.ACCESS_KEYS))
    candidates = {"base_rate": br, "package_hours": pkg_runs, "crew_efficiency": crew_run,
                  "drive_speed": drive_run, "multipliers": mult_run}

    def locked(group: str) -> bool:
        return bool((locks.get(group) or {}).get("locked"))

    changes: List[Dict[str, Any]] = []
    if activated and not paused:
        if br.get("apply") and not locked("base_rate"):
            changes.append({"factor": "base_rate", "key": "manHoursPer100CuFt", "before": br["current"],
                            "after": br["candidate"], "n_eff": br.get("n_eff"), "gate": br.get("gate")})
        for size, factor in (("studio", "package_studio"), ("br2", "package_br2"),
                             ("br3", "package_br3"), ("br4", "package_br4")):
            r = pkg_runs[size]
            if r.get("apply") and not locked(factor):
                changes.append({"factor": factor, "key": f"packageHours.{size}", "before": r["current"],
                                "after": r["candidate"], "n_eff": r.get("n_eff"), "gate": r.get("gate")})
        if not locked("crew_efficiency"):
            for c, r in (crew_run.get("by_crew") or {}).items():
                if r.get("apply"):
                    changes.append({"factor": "crew_efficiency", "key": f"crewEfficiency.{c}",
                                    "before": r["current"], "after": r["candidate"], "n_eff": r.get("n_eff")})
        if drive_run.get("apply") and not locked("drive_speed"):
            changes.append({"factor": "drive_speed", "key": "avgDriveMph", "before": drive_run["current"],
                            "after": drive_run["candidate"], "usable_jobs": drive_run.get("usable_jobs")})
        if mult_run.get("apply") and not locked("multipliers"):
            for name, c in (mult_run.get("candidates") or {}).items():
                if c.get("changed"):
                    changes.append({"factor": "multipliers", "key": name, "before": c["current"],
                                    "after": c["candidate"]})

    mode = "shadow" if (not activated or paused) else ("applied" if changes else "noop")
    applied_version = None
    run_id = run_id or str(uuid4())
    if changes:
        new_params = copy.deepcopy(params)
        for ch in changes:
            key = ch["key"]
            if key.startswith("packageHours."):
                _set_path(new_params, ("packageHours", key.split(".", 1)[1]), ch["after"])
            elif key.startswith("crewEfficiency."):
                _set_path(new_params, ("crewEfficiency", key.split(".", 1)[1]), ch["after"])
            elif key.startswith("pack"):
                t = int(key[4:]); pm = list(new_params.get("packingMult") or scope_engine.PACKING_MULT); pm[t] = ch["after"]; new_params["packingMult"] = pm
            elif key.startswith("acc:"):
                ap = dict(new_params.get("accessPer") or {}); ap[key[4:]] = ch["after"]; new_params["accessPer"] = ap
            elif key == "item":
                new_params["itemMult"] = ch["after"]
            else:
                _set_path(new_params, (key,), ch["after"])
        applied = await _apply_calibration(
            new_params, trigger=trigger, actor=actor, reason="Automatic optimizer run", changes=changes,
            run_id=run_id, extras={"job_keys": data["job_keys"], "usable_jobs": data["usable_count"]})
        applied_version = applied["version"]

    run_doc = {"_id": run_id, "at": now_iso(), "trigger": trigger, "mode": mode,
               "actor": (actor.get("name") if isinstance(actor, dict) else str(actor)),
               "actor_role": (actor.get("role") if isinstance(actor, dict) else "system"),
               "activated": activated, "paused": paused, "usable_jobs": data["usable_count"],
               "job_keys": data["job_keys"], "candidates": candidates, "changes": changes,
               "applied_version": applied_version}
    await mongo_db.optimizer_runs.insert_one(run_doc)
    if applied_version and isinstance(actor, dict) and actor.get("role") == "quality":
        await notify(None, "owner", "Calibration applied by Quality",
                     f"{actor.get('name')} ran the optimizer — {len(changes)} change(s), {applied_version}.",
                     "calibration", {"version": applied_version, "run_id": run_id})
    return run_doc


async def _optimizer_state_out() -> Dict[str, Any]:
    """Owner+Quality view of the optimizer: activation, per-factor current/baseline/lock + the newest
    shadow candidate for each, plus the last run summary and version count. Non-monetary only."""
    est = await _estimating_active()
    params, locks, baselines, opt = est["params"], est["locks"], est["baselines"], est["optimizer"]
    last_run = await mongo_db.optimizer_runs.find_one({}, sort=[("at", -1)])
    cand = (last_run or {}).get("candidates") or {}
    ph = params.get("packageHours") or {}

    def factor_row(factor: str) -> Dict[str, Any]:
        path, group, bounds, label = CALIB_SCALARS[factor]
        current = _get_path(params, path)
        lock = locks.get(group) or {}
        row = {"factor": factor, "group": group, "label": label, "current": current,
               "bounds": list(bounds), "locked": bool(lock.get("locked")),
               "lock": {"by": lock.get("by"), "at": lock.get("at"), "reason": lock.get("reason")} if lock.get("locked") else None}
        # baseline
        if factor.startswith("package_"):
            row["baseline"] = baselines.get(factor)
        elif factor == "item_mult":
            row["baseline"] = (baselines.get("multipliers") or {}).get("itemMult")
        elif factor.startswith("crew_"):
            row["baseline"] = (baselines.get("crew_efficiency") or {}).get(factor.split("_", 1)[1])
        else:
            row["baseline"] = baselines.get(factor)
        # newest shadow candidate + eligibility for this factor
        if factor == "base_rate":
            c = cand.get("base_rate") or {}
            row.update({"candidate": c.get("candidate"), "sample": c.get("usable_jobs"), "n_eff": c.get("n_eff"),
                        "eligible": c.get("eligible"), "changed": c.get("changed"), "gate": c.get("gate")})
        elif factor.startswith("package_"):
            size = factor.split("_", 1)[1]
            c = (cand.get("package_hours") or {}).get(size) or {}
            row.update({"candidate": c.get("candidate"), "sample": c.get("usable_jobs"), "n_eff": c.get("n_eff"),
                        "eligible": c.get("eligible"), "changed": c.get("changed"), "gate": c.get("gate")})
        elif factor.startswith("crew_"):
            c = ((cand.get("crew_efficiency") or {}).get("by_crew") or {}).get(factor.split("_", 1)[1]) or {}
            row.update({"candidate": c.get("candidate"), "sample": c.get("usable_jobs"), "n_eff": c.get("n_eff"),
                        "eligible": c.get("eligible"), "changed": c.get("changed")})
        elif factor == "drive_speed":
            c = cand.get("drive_speed") or {}
            row.update({"candidate": c.get("candidate"), "sample": c.get("usable_jobs"),
                        "eligible": c.get("eligible"), "changed": c.get("changed")})
        elif factor == "item_mult":
            c = (cand.get("multipliers") or {})
            row.update({"candidate": (c.get("candidates") or {}).get("item", {}).get("candidate"),
                        "sample": c.get("jobs"), "eligible": c.get("eligible"), "held_at_baseline": c.get("held_at_baseline")})
        return row

    factors = [factor_row(f) for f in CALIB_SCALARS]
    hist_count = await mongo_db.calibration_history.count_documents({"seq": {"$exists": True}})
    return {
        "activated": bool(opt.get("activated")), "paused": bool(opt.get("paused")),
        "activated_by": opt.get("activated_by"), "activated_at": opt.get("activated_at"),
        "calibration_version": est["calibration_version"], "calibration_seq": est["calibration_seq"],
        "factors": factors, "multipliers": cand.get("multipliers"),
        "last_run": ({"at": last_run.get("at"), "trigger": last_run.get("trigger"), "mode": last_run.get("mode"),
                      "usable_jobs": last_run.get("usable_jobs"), "applied_version": last_run.get("applied_version")}
                     if last_run else None),
        "history_count": hist_count,
        "note": ("The optimizer is ACTIVE — it applies eligible, unlocked, gate-passing changes on the nightly run."
                 if (opt.get("activated") and not opt.get("paused"))
                 else "The optimizer is computing shadow suggestions only. It cannot change an active parameter until you activate it."),
    }



async def _attach_estimating_features(doc: Dict[str, Any], inputs: Dict[str, Any]) -> None:
    """Record the learnable feature breakdown + parameter/pricing snapshots on a saved scope.
    Stage 5 = data capture only; this changes no pricing and is not itself a training example."""
    params = await get_estimating_params()
    rates = await get_rates_values()
    feats = scope_engine.compute_scope_features(inputs, params)
    result = doc.get("result") or {}
    hours_source = "rep_override" if inputs.get("hoursOverride") else ("package" if inputs.get("pkg") else "model")
    base_rate = float(params.get("manHoursPer100CuFt", 2.1))
    rate_in = inputs.get("rate")
    try:
        rate_override = float(rate_in) if (rate_in is not None and abs(float(rate_in) - base_rate) > 1e-9) else None
    except (TypeError, ValueError):
        rate_override = None
    doc["features"] = feats
    doc["model"] = {
        "schedMH": result.get("schedMH"), "billMH": result.get("billMH"),
        "onsiteRec": result.get("onsiteRec"), "crewRec": result.get("crewRec"),
        "crew": result.get("crew"), "final_hours": result.get("onsite"),
        "predicted_work_mh": feats.get("predicted_work_mh"),
    }
    doc["hours_source"] = hours_source
    doc["estimating_snapshot"] = params
    doc["calibration_version"] = params.get("calibration_version", "v0")
    doc["pricing_version"] = _pricing_version(rates)
    doc["rate_override_used"] = rate_override
    doc["quote_scope_id"] = doc["_id"]


# ------- Saved job scopes (lead_scopes) + calculator access tiers
# Tiers: owner (everything) · final (final quotes, no margin) · survey (no pricing) · sales (range only)

SCOPE_MONETARY_KEYS = ("bandLo", "bandHi", "finalTotal", "deposit", "distFee")


async def scope_tier_for(p: Dict[str, Any]) -> Optional[str]:
    if p.get("role") == "owner":
        return "owner"
    user = await mongo_db.users.find_one({"_id": p["user_id"]}) if p.get("user_id") else None
    calc = (user or {}).get("calculator_access")
    if calc in ("survey", "final"):
        return calc
    roles = (user or {}).get("roles") or []
    if p.get("role") == "sales" or "sales" in roles:
        return "sales"
    return None


async def require_scope_tier(request: Request) -> Tuple[Dict[str, Any], str]:
    p = await current_principal(request)
    tier = await scope_tier_for(p)
    if not tier:
        raise HTTPException(status_code=403, detail="You don't have calculator access.")
    return p, tier


def redact_scope_doc(doc: Dict[str, Any], tier: str) -> Dict[str, Any]:
    """Never let margin/pricing data reach a tier that shouldn't see it — even in payloads."""
    if tier == "owner":
        return doc
    d = dict(doc)
    result = dict(d.get("result") or {})
    if tier == "survey":
        d["pricing"] = {}
        for k in SCOPE_MONETARY_KEYS:
            result.pop(k, None)
    elif tier == "sales":
        d["pricing"] = {}
        result.pop("finalTotal", None)
        result.pop("deposit", None)
        result.pop("distFee", None)
    d["result"] = result
    return d


class ScopeSavePayload(BaseModel):
    lead_id: Optional[str] = None
    label: Optional[str] = None
    inputs: Dict[str, Any]
    pricing: Dict[str, Any]
    result: Dict[str, Any]
    survey_complete: bool = False
    refined_from: Optional[str] = None
    video: Optional[Dict[str, Any]] = None


def _clean_video(v: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    v = v or {}
    return {
        "link": str(v.get("link") or "").strip()[:500],
        "received": bool(v.get("received")),
        "received_date": str(v.get("received_date") or "").strip()[:10],
    }


@api_router.get("/scopes/access")
async def scope_access(request: Request):
    p = await current_principal(request)
    return {"tier": await scope_tier_for(p)}


@api_router.get("/scopes/pricing-values")
async def scope_pricing_values(request: Request):
    p, tier = await require_scope_tier(request)
    if tier == "survey":
        raise HTTPException(status_code=403, detail="Survey access doesn't include pricing.")
    values = await get_rates_values()
    if tier == "sales":
        # fold the cushion into every dollar figure — sales quotes identical numbers
        # without ever receiving the cushion (or margin) itself
        factor = 1 + float(values.get("cushionPercent", 0)) / 100
        for k in CUSHION_FOLDED_KEYS:
            values[k] = round(float(values.get(k, 0)) * factor, 2)
        values["cushionPercent"] = 0.0
    return values


@api_router.post("/scopes")
async def save_scope(payload: ScopeSavePayload, request: Request):
    p, tier = await require_scope_tier(request)
    if payload.survey_complete and tier == "sales":
        raise HTTPException(status_code=403, detail="Sales access can't mark a survey complete.")
    wants_final = (payload.result or {}).get("mode") == "final" or (payload.inputs or {}).get("mode") == "final"
    if wants_final and tier not in ("owner", "final"):
        raise HTTPException(status_code=403, detail="Your access level can't produce a final quote.")
    server_values = await get_rates_values()
    if tier in ("owner", "final"):
        # snapshot the values the client actually priced with (true, unfolded values)
        pricing = {}
        for k, v in server_values.items():
            sent = (payload.pricing or {}).get(k, v)
            if k in RATE_STRING_KEYS:
                pricing[k] = str(sent)[:100]
            else:
                try:
                    pricing[k] = float(sent)
                except (TypeError, ValueError):
                    pricing[k] = float(v)
    else:
        # sales gets folded values / survey gets none — snapshot server truth instead
        pricing = server_values
    result = dict(payload.result or {})
    if tier == "survey":
        for k in SCOPE_MONETARY_KEYS:
            result[k] = None
    doc = {
        "_id": str(uuid4()),
        "lead_id": payload.lead_id or None,
        "label": (payload.label or "").strip(),
        "created_by": p.get("name") or p.get("role") or "Unknown",
        "created_by_id": p.get("user_id"),
        "tier": tier,
        "inputs": payload.inputs,
        "pricing": pricing,
        "result": result,
        "survey_complete": bool(payload.survey_complete),
        "video": _clean_video(payload.video),
        "refined_from": payload.refined_from or None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await _attach_estimating_features(doc, payload.inputs or {})
    await mongo_db.lead_scopes.insert_one(doc)
    return redact_scope_doc(doc, tier)


@api_router.get("/scopes")
async def list_scopes(request: Request, lead_id: Optional[str] = None):
    p, tier = await require_scope_tier(request)
    query = {"lead_id": lead_id} if lead_id else {}
    docs = await mongo_db.lead_scopes.find(query).sort("created_at", -1).to_list(100)
    return {"scopes": [redact_scope_doc(d, tier) for d in docs]}


@api_router.get("/scopes/{scope_id}")
async def get_scope(scope_id: str, request: Request):
    p, tier = await require_scope_tier(request)
    doc = await mongo_db.lead_scopes.find_one({"_id": scope_id})
    if not doc:
        raise HTTPException(status_code=404, detail="No such saved scope.")
    return redact_scope_doc(doc, tier)


class ScopeVideoPayload(BaseModel):
    link: Optional[str] = None
    received: bool = False
    received_date: Optional[str] = None


@api_router.patch("/scopes/{scope_id}/video")
async def patch_scope_video(scope_id: str, payload: ScopeVideoPayload, request: Request):
    p, tier = await require_scope_tier(request)
    doc = await mongo_db.lead_scopes.find_one({"_id": scope_id})
    if not doc:
        raise HTTPException(status_code=404, detail="No such saved scope.")
    video = _clean_video(payload.model_dump())
    await mongo_db.lead_scopes.update_one(
        {"_id": scope_id}, {"$set": {"video": video, "updated_at": now_iso()}})
    doc["video"] = video
    doc["updated_at"] = now_iso()
    return redact_scope_doc(doc, tier)


# ------- Stage 1: draft auto-save + deliberate Save Quote / Save Range commit -------
# Drafts live in their own collection (scope_drafts) so they are excluded from every
# committed-scope consumer by construction — lead scope list, quality, recommendations,
# booking-rate counts and customer comms all read lead_scopes, never scope_drafts.

LEAD_QUOTE_FIELD = "fldI5HufBfW35A1fD"             # verified against fields.js (LF.quote)
QUOTE_AUTO_STATUS_FROM = {"Contacted", "Warm", "Hot"}
STAGE1_CALIBRATION_VERSION = "v0"


def _pricing_version(pricing: Dict[str, Any]) -> str:
    try:
        blob = json.dumps(pricing, sort_keys=True, default=str)
    except (TypeError, ValueError):
        blob = str(pricing)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def _hours_source(inputs: Dict[str, Any]) -> str:
    if inputs.get("pkg"):
        return "package"
    if inputs.get("hoursOverride"):
        return "rep_override"
    return "model"


def _safe_airtable_error(exc: Exception) -> str:
    # airtable_request already returns sanitized messages; never surface tokens/keys.
    if isinstance(exc, HTTPException):
        return str(exc.detail)[:300]
    return "The quote couldn't be written to Airtable. It's saved here and can be retried."


class ScopeDraftPayload(BaseModel):
    draft_id: str
    lead_id: Optional[str] = None
    rev: int = 0
    inputs: Dict[str, Any] = {}
    pricing: Dict[str, Any] = {}
    result: Dict[str, Any] = {}
    survey_complete: bool = False
    video: Optional[Dict[str, Any]] = None


@api_router.put("/scope-drafts")
async def save_scope_draft(payload: ScopeDraftPayload, request: Request):
    """Debounced background auto-save. Idempotent by draft_id; a monotonic rev guard prevents
    clobbering a newer revision or another device. Drafts never write Airtable or train anything."""
    p, tier = await require_scope_tier(request)
    if not payload.draft_id:
        raise HTTPException(status_code=422, detail="Missing draft id.")
    existing = await mongo_db.scope_drafts.find_one({"_id": payload.draft_id})
    if existing:
        if existing.get("created_by_id") and existing.get("created_by_id") != p.get("user_id"):
            raise HTTPException(status_code=403, detail="This draft belongs to someone else.")
        if payload.rev <= int(existing.get("rev", 0)):
            return {"draft_id": payload.draft_id, "rev": int(existing.get("rev", 0)),
                    "saved_at": existing.get("updated_at"), "stale": True}
    result = dict(payload.result or {})
    pricing = dict(payload.pricing or {})
    if tier == "survey":
        pricing = {}
        for k in SCOPE_MONETARY_KEYS:
            result[k] = None
    doc = {
        "_id": payload.draft_id, "status": "draft", "training_eligible": False,
        "lead_id": payload.lead_id or None, "rev": int(payload.rev),
        "created_by": p.get("name") or p.get("role") or "Unknown", "created_by_id": p.get("user_id"),
        "tier": tier, "inputs": payload.inputs, "pricing": pricing, "result": result,
        "survey_complete": bool(payload.survey_complete), "video": _clean_video(payload.video),
        "created_at": (existing or {}).get("created_at") or now_iso(), "updated_at": now_iso(),
    }
    await mongo_db.scope_drafts.replace_one({"_id": payload.draft_id}, doc, upsert=True)
    return {"draft_id": payload.draft_id, "rev": doc["rev"], "saved_at": doc["updated_at"], "stale": False}


@api_router.get("/scope-drafts")
async def find_scope_draft(request: Request, lead_id: Optional[str] = None):
    """Resume the caller's most recent draft for this lead (or the blank calculator)."""
    p, tier = await require_scope_tier(request)
    doc = await mongo_db.scope_drafts.find_one(
        {"created_by_id": p.get("user_id"), "lead_id": lead_id or None}, sort=[("updated_at", -1)])
    return {"draft": redact_scope_doc(doc, tier) if doc else None}


@api_router.get("/scope-drafts/{draft_id}")
async def get_scope_draft(draft_id: str, request: Request):
    p, tier = await require_scope_tier(request)
    doc = await mongo_db.scope_drafts.find_one({"_id": draft_id})
    if not doc:
        raise HTTPException(status_code=404, detail="No such draft.")
    if doc.get("created_by_id") and doc.get("created_by_id") != p.get("user_id") and p.get("role") != "owner":
        raise HTTPException(status_code=403, detail="This draft belongs to someone else.")
    return redact_scope_doc(doc, tier)


class ScopeCommitPayload(BaseModel):
    commit_id: str
    lead_id: Optional[str] = None
    commit_type: str = "firm"        # firm | range
    label: Optional[str] = None
    refined_from: Optional[str] = None
    reason: Optional[str] = None
    draft_id: Optional[str] = None
    inputs: Dict[str, Any]
    pricing: Dict[str, Any]
    result: Dict[str, Any]
    survey_complete: bool = False
    video: Optional[Dict[str, Any]] = None


async def _write_lead_quote(lead_id: str, amount: float) -> Dict[str, Any]:
    """Write the firm quote to the lead's real Airtable field and, ONLY from Contacted/Warm/Hot,
    advance status to Quoted. Returns a durable write-state dict; never raises."""
    rec = await fetch_lead_record(lead_id)
    if not rec or not rec.get("id"):
        return {"state": "error", "attempts": 1, "last_error": "The lead couldn't be found in Airtable.",
                "status_changed": None, "at": now_iso()}
    cur_status = (rec.get("fields") or {}).get(LEAD_STATUS_F)
    fields: Dict[str, Any] = {LEAD_QUOTE_FIELD: amount}
    status_changed = None
    if cur_status in QUOTE_AUTO_STATUS_FROM:
        fields[LEAD_STATUS_F] = "Quoted"
        status_changed = "Quoted"
    try:
        await airtable_request("PATCH", TABLES["leads"],
                               json_body={"records": [{"id": lead_id, "fields": fields}], "typecast": True})
        return {"state": "committed", "attempts": 1, "last_error": None,
                "status_changed": status_changed, "at": now_iso()}
    except Exception as exc:
        return {"state": "error", "attempts": 1, "last_error": _safe_airtable_error(exc),
                "status_changed": None, "at": now_iso()}


async def _set_active_quote_link(lead_id: str, scope_id: str, amount: Any, mode: str, by: str, action: str) -> Optional[str]:
    prev = (await mongo_db.lead_quote_links.find_one({"_id": lead_id}) or {}).get("active_quote_scope_id")
    entry = {"quote_scope_id": scope_id, "supersedes": prev, "amount": amount, "mode": mode,
             "by": by, "action": action, "at": now_iso()}
    await mongo_db.lead_quote_links.update_one(
        {"_id": lead_id},
        {"$set": {"active_quote_scope_id": scope_id, "amount": amount, "mode": mode, "updated_at": now_iso()},
         "$push": {"history": entry}}, upsert=True)
    return prev


@api_router.post("/scopes/commit")
async def commit_scope(payload: ScopeCommitPayload, request: Request):
    """Deliberate Save Quote / Save Range — one idempotent, server-owned commit boundary."""
    p, tier = await require_scope_tier(request)
    if not payload.commit_id:
        raise HTTPException(status_code=422, detail="Missing commit id.")
    existing = await mongo_db.lead_scopes.find_one({"commit_id": payload.commit_id})
    if existing:   # idempotency — retrying the same commit never duplicates
        return redact_scope_doc(existing, tier)
    if not payload.lead_id:
        raise HTTPException(status_code=422, detail="Who is this quote for? Select or create a lead first.")
    lead = await fetch_lead_record(payload.lead_id)
    if not lead or not lead.get("id"):
        raise HTTPException(status_code=404, detail="That lead no longer exists. Pick another lead.")
    result_mode = (payload.result or {}).get("mode")
    is_firm = payload.commit_type == "firm" and result_mode == "final"
    if payload.commit_type == "firm" and result_mode != "final":
        raise HTTPException(status_code=422, detail="This isn't a firm quote yet — save it as a range instead.")
    if is_firm and tier not in ("owner", "final"):
        raise HTTPException(status_code=403, detail="Your access level can't produce a firm quote.")
    if payload.survey_complete and tier == "sales":
        raise HTTPException(status_code=403, detail="Sales access can't mark a survey complete.")
    server_values = await get_rates_values()
    if tier in ("owner", "final"):
        pricing: Dict[str, Any] = {}
        for k, v in server_values.items():
            sent = (payload.pricing or {}).get(k, v)
            if k in RATE_STRING_KEYS:
                pricing[k] = str(sent)[:100]
            else:
                try:
                    pricing[k] = float(sent)
                except (TypeError, ValueError):
                    pricing[k] = float(v)
    else:
        pricing = server_values
    result = dict(payload.result or {})
    if tier == "survey":
        for k in SCOPE_MONETARY_KEYS:
            result[k] = None
    amount = result.get("finalTotal") if is_firm else None
    scope_id = str(uuid4())
    prev_active = (await mongo_db.lead_quote_links.find_one({"_id": payload.lead_id}) or {}).get("active_quote_scope_id")
    doc = {
        "_id": scope_id, "quote_scope_id": scope_id, "commit_id": payload.commit_id,
        "status": "saved", "commit_type": payload.commit_type, "training_eligible": False,
        "lead_id": payload.lead_id, "label": (payload.label or "").strip(),
        "created_by": p.get("name") or p.get("role") or "Unknown", "created_by_id": p.get("user_id"),
        "tier": tier, "inputs": payload.inputs, "pricing": pricing, "result": result,
        "amount": amount, "estimate_mode": result_mode, "hours_source": _hours_source(payload.inputs or {}),
        "pricing_version": _pricing_version(pricing), "calibration_version": STAGE1_CALIBRATION_VERSION,
        "survey_complete": bool(payload.survey_complete), "video": _clean_video(payload.video),
        "refined_from": payload.refined_from or None, "supersedes_quote_scope_id": prev_active or None,
        "reason": (payload.reason or "").strip() or None,
        "commit_state": "committed", "airtable_write": None, "status_changed": None,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    if is_firm and amount is not None:
        doc["commit_state"] = "pending"
        await mongo_db.lead_scopes.insert_one(doc)
        write = await _write_lead_quote(payload.lead_id, float(amount))
        state = "committed" if write["state"] == "committed" else "error"
        await mongo_db.lead_scopes.update_one({"_id": scope_id}, {"$set": {
            "airtable_write": write, "commit_state": state,
            "status_changed": write.get("status_changed"), "updated_at": now_iso()}})
        doc.update({"airtable_write": write, "commit_state": state, "status_changed": write.get("status_changed")})
        await _set_active_quote_link(payload.lead_id, scope_id, amount, "firm", doc["created_by"], "firm_quote")
    else:
        await mongo_db.lead_scopes.insert_one(doc)
        if payload.commit_type == "range":   # links to the lead but NEVER the firm active quote / no Airtable write
            await mongo_db.lead_quote_links.update_one(
                {"_id": payload.lead_id},
                {"$set": {"last_range_scope_id": scope_id, "updated_at": now_iso()},
                 "$push": {"history": {"quote_scope_id": scope_id, "amount": amount, "mode": "range",
                                       "by": doc["created_by"], "action": "range", "at": now_iso()}}}, upsert=True)
    if payload.draft_id:   # the deliberate commit retires its recoverable draft
        await mongo_db.scope_drafts.delete_one({"_id": payload.draft_id, "created_by_id": p.get("user_id")})
    await audit(p, f"committed a {'firm quote' if is_firm else payload.commit_type}",
                doc["label"] or payload.lead_id, {"scope_id": scope_id, "amount": amount})
    return redact_scope_doc(doc, tier)


@api_router.post("/scopes/{scope_id}/retry-write")
async def retry_scope_write(scope_id: str, request: Request):
    """Re-attempt a firm quote's Airtable write after a failure. Owner/final only."""
    p, tier = await require_scope_tier(request)
    doc = await mongo_db.lead_scopes.find_one({"_id": scope_id})
    if not doc:
        raise HTTPException(status_code=404, detail="No such saved quote.")
    if doc.get("commit_type") != "firm" or doc.get("commit_state") == "committed":
        raise HTTPException(status_code=422, detail="Nothing to retry — this quote is already committed.")
    if tier not in ("owner", "final"):
        raise HTTPException(status_code=403, detail="Your access level can't write firm quotes.")
    write = await _write_lead_quote(doc["lead_id"], float(doc.get("amount") or 0))
    write["attempts"] = int((doc.get("airtable_write") or {}).get("attempts", 0)) + 1
    state = "committed" if write["state"] == "committed" else "error"
    await mongo_db.lead_scopes.update_one({"_id": scope_id}, {"$set": {
        "airtable_write": write, "commit_state": state,
        "status_changed": write.get("status_changed"), "updated_at": now_iso()}})
    doc.update({"airtable_write": write, "commit_state": state, "status_changed": write.get("status_changed")})
    return redact_scope_doc(doc, tier)


# ------- Calculator access assignment (owner-only)

class CalcAccessPayload(BaseModel):
    mode: str


@api_router.get("/users/calculator-access")
async def list_calculator_access(p: Dict[str, Any] = Depends(require_owner)):
    docs = await mongo_db.users.find({"calculator_access": {"$in": ["survey", "final"]}}).to_list(200)
    return {"access": {d["_id"]: d["calculator_access"] for d in docs}}


@api_router.put("/users/{user_id}/calculator-access")
async def set_calculator_access(user_id: str, payload: CalcAccessPayload, p: Dict[str, Any] = Depends(require_owner)):
    if payload.mode not in ("survey", "final"):
        raise HTTPException(status_code=422, detail="Mode must be 'survey' or 'final'.")
    u = await mongo_db.users.find_one({"_id": user_id})
    if not u:
        raise HTTPException(status_code=404, detail="No such team member.")
    prev = u.get("calculator_access")
    await mongo_db.users.update_one({"_id": user_id}, {"$set": {"calculator_access": payload.mode}})
    await audit(p, "changed calculator access mode" if prev else "granted calculator access",
                u.get("name") or user_id, {"mode": payload.mode, "was": prev})
    return {"user_id": user_id, "calculator_access": payload.mode}


@api_router.delete("/users/{user_id}/calculator-access")
async def remove_calculator_access(user_id: str, p: Dict[str, Any] = Depends(require_owner)):
    u = await mongo_db.users.find_one({"_id": user_id})
    if not u:
        raise HTTPException(status_code=404, detail="No such team member.")
    await mongo_db.users.update_one({"_id": user_id}, {"$unset": {"calculator_access": ""}})
    await audit(p, "removed calculator access", u.get("name") or user_id, {"was": u.get("calculator_access")})
    return {"user_id": user_id, "calculator_access": None}


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


# ------- Customer Page (portal) settings + message templates (settings _id "portal")
PORTAL_TEMPLATE_KEYS = ("booked", "move_day", "wrap_up", "reminder")
PORTAL_DEFAULTS = {
    "booked": ("Hi {first_name}, thanks for choosing Haul Yeah Moving! Here's your move page for {move_date}: {link}\n"
               "See your crew, track the truck on move day, add gate/parking details, and view your balance. "
               "No login needed. Questions? Just reply here."),
    "move_day": ("Haul Yeah Moving: Your crew is on the way! Track them live: {link}\n"
                 "Reply here if you need us."),
    "wrap_up": ("Thanks for moving with Haul Yeah, {first_name}! Your receipt, crew tip, and review link are all here: {link}\n"
                "We appreciate you!"),
    "reminder": ("Hi {first_name}, your Haul Yeah move is {move_date} at {arrival_window}. {paperwork_line}"
                 "Add gate, elevator, or parking details here: {link} Reply STOP to opt out."),
}


async def _portal_settings() -> Dict[str, Any]:
    return await mongo_db.settings.find_one({"_id": "portal"}) or {}


def _portal_template(portal: Dict[str, Any], key: str) -> str:
    t = (portal.get("templates") or {}).get(key)
    return t if isinstance(t, str) and t.strip() else PORTAL_DEFAULTS.get(key, "")


async def _portal_base(portal: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Customer-facing link base: the owner's Settings value, else the PUBLIC_BASE_URL env.
    Never the request host — a customer link must not point at whatever host answered."""
    portal = portal if portal is not None else await _portal_settings()
    base = (portal.get("portal_base_url") or "").strip() or os.environ.get("PUBLIC_BASE_URL", "").strip()
    base = base.rstrip("/")
    return base or None


async def _business_phone(portal: Optional[Dict[str, Any]] = None) -> str:
    portal = portal if portal is not None else await _portal_settings()
    bp = (portal.get("business_phone") or "").strip()
    if bp:
        return bp
    return (await openphone_config()).get("number") or ""


def _fmt_move_date(d: Any) -> str:
    dt = _c_date(d)
    return f"{dt.strftime('%a, %b')} {dt.day}" if dt else ""


def _render_portal_message(tmpl: str, job: Dict[str, Any], link: str, business_phone: str = "",
                           extra: Optional[Dict[str, Any]] = None) -> str:
    """Fill {first_name} {move_date} {link} {job_number} {business_phone} {start_time}
    {arrival_window} {paperwork_line}. Unknown or empty variables render as empty strings —
    never '{undefined}' or 'None'."""
    cust = job.get("customer") or {}
    vals = {
        "first_name": (cust.get("name") or "").split(" ")[0] or "",
        "move_date": _fmt_move_date(job.get("job_date")),
        "link": link or "",
        "job_number": str(job.get("invoice_number") or ""),
        "business_phone": business_phone or "",
        "start_time": _fmt_time12(job.get("start_time")),
        "arrival_window": "",
        "paperwork_line": "",
    }
    if extra:
        vals.update({k: ("" if v is None else str(v)) for k, v in extra.items()})
    out = tmpl or ""
    for k, v in vals.items():
        out = out.replace("{" + k + "}", str(v))
    return re.sub(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", "", out)   # strip any leftover placeholder


class PortalSettingsPayload(BaseModel):
    portal_base_url: Optional[str] = None
    business_phone: Optional[str] = None
    license_number: Optional[str] = None
    brochure_url: Optional[str] = None
    templates: Optional[Dict[str, str]] = None
    prep_checklist: Optional[List[str]] = None
    arrival_window_minutes: Optional[int] = None
    policy_cancellation: Optional[str] = None
    policy_protection: Optional[str] = None
    policy_claims: Optional[str] = None


async def _portal_settings_out(portal: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    portal = portal if portal is not None else await _portal_settings()
    return {
        "portal_base_url": (portal.get("portal_base_url") or "").strip(),
        "business_phone": await _business_phone(portal),
        "license_number": (portal.get("license_number") or "").strip(),
        "brochure_url": (portal.get("brochure_url") or "").strip(),
        "templates": {k: _portal_template(portal, k) for k in PORTAL_TEMPLATE_KEYS},
        "base_effective": await _portal_base(portal),
        "env_base_set": bool(os.environ.get("PUBLIC_BASE_URL", "").strip()),
        "prep_checklist": portal.get("prep_checklist") or [],
        "arrival_window_minutes": int(portal.get("arrival_window_minutes") or 30),
        "policy_cancellation": portal.get("policy_cancellation") or "",
        "policy_protection": portal.get("policy_protection") or "",
        "policy_claims": portal.get("policy_claims") or "",
    }


@api_router.get("/settings/portal")
async def get_portal_settings(p: Dict[str, Any] = Depends(require_owner)):
    return await _portal_settings_out()


@api_router.put("/settings/portal")
async def save_portal_settings(payload: PortalSettingsPayload, p: Dict[str, Any] = Depends(require_owner)):
    data = payload.model_dump(exclude_none=True)
    updates: Dict[str, Any] = {}
    if "portal_base_url" in data:
        base = data["portal_base_url"].strip().rstrip("/")
        if base and not base.startswith("https://"):
            raise HTTPException(status_code=422, detail="The Customer page URL must start with https://")
        updates["portal_base_url"] = base
    for k in ("business_phone", "license_number", "brochure_url",
              "policy_cancellation", "policy_protection", "policy_claims"):
        if k in data:
            updates[k] = str(data[k]).strip()
    if isinstance(data.get("templates"), dict):
        updates["templates"] = {k: str(data["templates"][k]).strip()[:1000]
                                for k in PORTAL_TEMPLATE_KEYS if isinstance(data["templates"].get(k), str)}
    if isinstance(data.get("prep_checklist"), list):
        updates["prep_checklist"] = [str(x).strip()[:300] for x in data["prep_checklist"] if str(x).strip()][:30]
    if data.get("arrival_window_minutes") is not None:
        try:
            updates["arrival_window_minutes"] = max(0, min(240, int(data["arrival_window_minutes"])))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Arrival window must be a whole number of minutes.")
    if updates:
        await mongo_db.settings.update_one({"_id": "portal"}, {"$set": updates}, upsert=True)
        await audit(p, "updated customer page settings", "settings", {"fields": list(updates.keys())})
    out = await _portal_settings_out()
    out["warning"] = None
    base = out["portal_base_url"]
    if base:   # a typo here breaks every customer link — warn (never block) if it isn't this app
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                r = await client.get(f"{base}/api/portal/ping")
            if r.status_code >= 400 or "haul-yeah-moving" not in (r.text or ""):
                out["warning"] = "That URL didn't answer as this app. Double-check it — a typo breaks every customer link."
        except Exception:
            out["warning"] = "Couldn't reach that URL. Double-check it — a typo breaks every customer link."
    return out


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


# ------- Airtable Projects mirror (deposit-paid jobs sync to the Day Sheet / Crew Report)

PROJECT_LEAD_LINK_FIELD = "fldiN7fny2dKI2r2V"


def _project_fields_for_job(job: Dict[str, Any]) -> Dict[str, Any]:
    name = (job.get("customer") or {}).get("name") or "Job"
    fields: Dict[str, Any] = {
        PROJECT_NAME_FIELD: f"{name} — {job.get('job_date') or 'date TBD'}",
        PROJECT_STATUS_FIELD: "Scheduled",
    }
    if job.get("job_date"):
        fields[PROJECT_DATE_FIELD] = job["job_date"]
    try:
        if job.get("quote_total"):
            fields[PROJECT_QUOTE_FIELD] = float(job["quote_total"])
        dep = (job.get("deposit_paid") or {}).get("amount")
        if dep:
            fields[PROJECT_DEPOSIT_FIELD] = float(dep)
    except (TypeError, ValueError):
        pass
    if job.get("pickup_address"):
        fields[PROJECT_FROM_FIELD] = job["pickup_address"]
    if job.get("dropoff_address"):
        fields[PROJECT_TO_FIELD] = job["dropoff_address"]
    if job.get("lead_id"):
        fields[PROJECT_LEAD_LINK_FIELD] = [job["lead_id"]]
    return fields


async def sync_project_for_job(job: Dict[str, Any]) -> None:
    """Upsert the Airtable Projects record for a deposit-paid job so it lands on the Day Sheet."""
    if not job:
        return
    try:
        rec_id = job.get("project_record_id")
        existing = None
        if rec_id:
            try:
                existing = await airtable_request("GET", TABLES["projects"], path=f"/{rec_id}",
                                                  params={"returnFieldsByFieldId": "true"})
            except HTTPException as exc:
                if exc.status_code == 404:
                    rec_id, existing = None, None
                else:
                    raise
        if not rec_id and job.get("lead_id"):
            data = await airtable_request("GET", TABLES["projects"],
                                          params={"returnFieldsByFieldId": "true", "pageSize": 100})
            for rec in data.get("records", []):
                if job["lead_id"] in ((rec.get("fields") or {}).get(PROJECT_LEAD_LINK_FIELD) or []):
                    rec_id, existing = rec["id"], rec
                    break
        fields = _project_fields_for_job(job)
        if rec_id:
            cur = (existing or {}).get("fields") or {}
            cur_status = cur.get(PROJECT_STATUS_FIELD)
            if cur_status and cur_status not in ("Pending Deposit", "Scheduled"):
                fields.pop(PROJECT_STATUS_FIELD, None)  # never downgrade an in-progress/completed job
            fields.pop(PROJECT_NAME_FIELD, None)  # never rename an existing project
            body = {"records": [{"id": rec_id, "fields": fields}], "typecast": True}
            await airtable_request("PATCH", TABLES["projects"], json_body=body)
        else:
            body = {"records": [{"fields": fields}], "typecast": True}
            data = await airtable_request("POST", TABLES["projects"], json_body=body)
            rec_id = ((data.get("records") or [{}])[0]).get("id")
        if rec_id:
            await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {
                "project_record_id": rec_id, "project_synced_date": job.get("job_date")}})
    except HTTPException as exc:
        logger.warning("Projects sync skipped for job %s: %s", job.get("invoice_number"), exc.detail)
    except Exception as exc:
        logger.warning("Projects sync failed for job %s: %s", job.get("invoice_number"), exc)


async def ensure_job_for_deposit(inv: Dict[str, Any], mark_full: bool = False, notify_owner: bool = True) -> None:
    paid_at = inv.get("paid_at") or now_iso()
    existing = await mongo_db.jobs.find_one({"deposit_invoice_id": inv["invoice_id"]})
    if existing:
        await _sync_existing_deposit_job(existing, inv, mark_full, paid_at)
        if not existing.get("project_record_id") or existing.get("project_synced_date") != existing.get("job_date"):
            await sync_project_for_job(existing)
        fresh = await mongo_db.jobs.find_one({"_id": existing["_id"]}) or existing
        await _check_owner_paperwork_alert(fresh, "booking")
        return
    lead = await fetch_lead_details(inv.get("lead_id"))
    integrations = await get_integrations()
    job = _job_doc_from_invoice(inv, lead, integrations, paid_at, mark_full)
    await mongo_db.jobs.insert_one(job)
    await sync_project_for_job(job)
    if notify_owner:
        who = job["customer"]["name"] or "the customer"
        await notify(None, "owner", "New job — deposit paid",
                     f"Job #{job['invoice_number']} is live: {who} paid the deposit. Open Jobs to assign a crew.",
                     "success", {"job_id": job["_id"]})
    await _check_owner_paperwork_alert(job, "booking")


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
        if "job_date" in updates:
            await sync_project_for_job(job)
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
        "tracking_sms_sent": bool((job.get("tracking") or {}).get("onway_sms_sent")
                                  or (job.get("tracking") or {}).get("sms_sent")),
        "review_link": business.get("reviewLink", ""),
        "is_today": job.get("job_date") == today,
    }, "upcoming_count": len(docs) - 1}


async def _ensure_tracking_token(job: Dict[str, Any]) -> str:
    """One stable token per job. Reuse it forever; only create one if it is truly missing.
    Sending NEVER rotates it — only an explicit owner Reset does."""
    token = (job.get("tracking") or {}).get("token")
    if not token:
        token = uuid4().hex
        await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {"tracking.token": token}})
        job.setdefault("tracking", {})["token"] = token
    return token


async def _log_portal_send(job: Dict[str, Any], channel: str, template_key: str, by: str) -> Dict[str, Any]:
    entry = {"at": now_iso(), "channel": channel, "template_key": template_key, "by": by or "Owner"}
    await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$push": {"portal_sends": entry}})
    return entry


async def _send_tracking_sms(job: Dict[str, Any], by: str = "Auto — crew clock-in",
                             template_key: str = "move_day", mark_onway: bool = True) -> None:
    portal = await _portal_settings()
    base = await _portal_base(portal)
    if not base:
        raise HTTPException(status_code=503,
                            detail="Set your Customer page URL in Settings → Customer Page first.")
    token = await _ensure_tracking_token(job)
    link = f"{base}/track/{token}"
    text = _render_portal_message(_portal_template(portal, template_key), job, link, await _business_phone(portal))
    await openphone_send_sms((job.get("customer") or {}).get("phone"), text)
    if mark_onway:
        await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {
            "tracking.onway_sms_sent": True, "tracking.onway_sms_sent_at": now_iso()}})
    await _log_portal_send(job, "sms", template_key, by)


async def maybe_send_tracking_sms(p: Dict[str, Any], request: Request) -> None:
    job = await mongo_db.jobs.find_one({"crew.user_id": p["user_id"], "job_date": _et_today()})
    if not job:
        return
    tr = job.get("tracking") or {}
    if tr.get("onway_sms_sent") or tr.get("sms_sent"):   # legacy sms_sent=True counts as already sent
        return
    try:
        await _send_tracking_sms(job)
        await notify(None, "owner", "Move-day text sent",
                     f"The customer for Job #{job['invoice_number']} got the move-day tracking text.", "info")
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Could not send the move-day text."
        await notify(None, "owner", "Tracking text NOT sent", f"Job #{job['invoice_number']}: {detail}", "warning")


@api_router.post("/crew/jobs/{job_id}/tracking-link")
async def send_new_tracking_link(job_id: str, request: Request, p: Dict[str, Any] = Depends(require_crew)):
    job = await mongo_db.jobs.find_one({"_id": job_id, "crew.user_id": p["user_id"]})
    if not job:
        raise HTTPException(status_code=404, detail="That job isn't yours.")
    await _send_tracking_sms(job, by=p.get("name") or "Crew")   # reuses the SAME token — old link keeps working
    await audit(p, "resent the move page", f"job {job.get('invoice_number')}")
    return {"ok": True, "message": "Move page resent to the customer."}


async def _job_assignment_ids(job: Dict[str, Any]) -> List[str]:
    """Assignment(s) belonging to THIS job — matched by the Airtable project link, falling back
    to job_date + crew ONLY when the job has no project link."""
    pr = job.get("project_record_id")
    if pr:
        docs = await mongo_db.assignments.find({"project_id": pr}).to_list(20)
        if docs:
            return [d["_id"] for d in docs]
    crew_ids = [c["user_id"] for c in job.get("crew", [])]
    if job.get("job_date") and crew_ids:
        docs = await mongo_db.assignments.find(
            {"job_date": job["job_date"], "crew.user_id": {"$in": crew_ids}}).to_list(20)
        return [d["_id"] for d in docs]
    return []


def _portal_stage(job: Dict[str, Any], status: str, today_str: str) -> Dict[str, Any]:
    jd = (job.get("job_date") or "")[:10]
    today = _c_date(today_str)
    move = _c_date(jd)
    days_after = (today - move).days if (today and move) else None   # >0 = N days after the move
    is_complete = status == "Complete"
    archived = days_after is not None and days_after > 120
    show_review = is_complete or (days_after is not None and days_after > 0)
    show_tip = status in ("Arrived", "In Progress", "Complete") or (days_after is not None and 0 <= days_after <= 14)
    return {"archived": archived, "is_complete": is_complete, "days_after_move": days_after,
            "show_review": show_review, "show_tip": show_tip, "editable": not is_complete and not archived}


async def _log_portal_view(job: Dict[str, Any], request: Request) -> None:
    if request.headers.get("Authorization", "").startswith("Bearer "):
        try:
            decode_token(request)   # a logged-in CRM user (owner preview) — don't count it as a customer view
            return
        except HTTPException:
            pass
    views = job.get("portal_views") or {}
    last = views.get("last_at")
    if last:
        try:
            if (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() < 600:
                return   # throttle: 1 logged view per 10 minutes per job
        except ValueError:
            pass
    now = now_iso()
    first = not views.get("count")
    await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {"portal_views": {
        "count": (views.get("count") or 0) + 1, "first_at": views.get("first_at") or now, "last_at": now}}})
    if first:
        who = (job.get("customer") or {}).get("name") or "The customer"
        await _owner_portal_ping(job, "Move page opened",
                                 f"{who} opened their move page (Job #{job.get('invoice_number')}).")


@public_router.get("/portal/ping")
async def portal_ping():
    """Public marker so the owner's Customer-page URL can be validated without auth."""
    return {"app": "haul-yeah-moving"}


@public_router.get("/track/{token}")
async def track_job(token: str, request: Request) -> Dict[str, Any]:
    job = await mongo_db.jobs.find_one({"tracking.token": token})
    if not job:
        raise HTTPException(status_code=404, detail="This tracking link is no longer active. Reply to our text and we'll send a new one.")
    await _log_portal_view(job, request)
    crew_ids = [c["user_id"] for c in job.get("crew", [])]
    status = await _track_status(job, crew_ids)
    today = _et_today()
    stage = _portal_stage(job, status, today)
    portal_settings = await _portal_settings()
    business_phone = await _business_phone(portal_settings)
    if stage["archived"]:   # >120 days after the move — stop returning money, uploads, details
        return {"archived": True, "status": status, "job_date": job.get("job_date"),
                "invoice_number": job.get("invoice_number"), "business_phone": business_phone,
                "customer_name": (job.get("customer") or {}).get("name", "")}
    # Live GPS ONLY for this job, ONLY on move day, ONLY while not complete, ONLY from a crew
    # member clocked into THIS job's assignment. Never bleed a crew's other job onto this page.
    live, position, minutes_ago = False, None, None
    if crew_ids and job.get("job_date") == today and not stage["is_complete"]:
        assignment_ids = await _job_assignment_ids(job)
        q: Dict[str, Any] = {"clock_out": None, "user_id": {"$in": crew_ids}}
        if assignment_ids:
            q["assignment_id"] = {"$in": assignment_ids}
        open_entries = await mongo_db.time_entries.find(q).to_list(20)
        if open_entries:
            live = True
            entry_users = [e["user_id"] for e in open_entries]
            pings = await mongo_db.gps_pings.find({"user_id": {"$in": entry_users}}).sort("at", -1).limit(1).to_list(1)
            if pings:
                try:
                    at = datetime.fromisoformat(pings[0]["at"])
                    minutes_ago = max(0, int((datetime.now(timezone.utc) - at).total_seconds() // 60))
                except ValueError:
                    minutes_ago = None
                if minutes_ago is not None and minutes_ago <= 10:
                    position = {"lat": pings[0]["lat"], "lng": pings[0]["lng"]}
    money = _track_money(job)
    portal = await _track_portal_bits(job)
    timeline = await _customer_timeline(job, status, stage)
    confirm = _move_confirmation_state(job)
    arrival_window = _arrival_window_str(job.get("start_time"), int(portal_settings.get("arrival_window_minutes") or 30))
    cancelled = (job.get("status") or "").lower() == "cancelled" or bool(job.get("cancelled_at"))
    return {"invoice_number": job.get("invoice_number"), "job_date": job.get("job_date"),
            "start_time": job.get("start_time"), "live": live, "position": position,
            "updated_minutes_ago": minutes_ago, "business_phone": business_phone,
            "customer_name": (job.get("customer") or {}).get("name", ""),
            "status": status,
            "pickup_address": job.get("pickup_address"), "dropoff_address": job.get("dropoff_address"),
            "crew": [{"name": c.get("name", "Crew member"), "position": c.get("position", "Helper")}
                     for c in job.get("crew", [])],
            "truck_name": job.get("truck_name") or "",
            "timeline": timeline, "confirm": confirm, "arrival_window": arrival_window,
            "prep_checklist": portal_settings.get("prep_checklist") or [],
            "brochure_url": (portal_settings.get("brochure_url") or "").strip(),
            "cancelled": cancelled,
            **stage, **money, **portal}


# ------- customer portal (phase D — extends the public tracking link)

async def _track_status(job: Dict[str, Any], crew_ids: List[str]) -> str:
    # Match the assignment to THIS job (by Airtable project link), so a crew's second job of the
    # day can never flip this customer's status. Fall back to date+crew only when unlinked.
    assignment_ids = await _job_assignment_ids(job)
    a = await mongo_db.assignments.find_one({"_id": {"$in": assignment_ids}}) if assignment_ids else None
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


# ===================== Phase D — customer portal timeline, paperwork, reminders =====================

def _fmt_time12(t: Optional[str]) -> str:
    if not t:
        return ""
    try:
        hh, mm = str(t).split(":")[:2]
        h, m = int(hh), int(mm)
        return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"
    except (ValueError, TypeError):
        return str(t)


def _arrival_window_str(start_time: Optional[str], minutes: int) -> str:
    start = _fmt_time12(start_time)
    if not start or not minutes:
        return start
    try:
        hh, mm = str(start_time).split(":")[:2]
        total = (int(hh) * 60 + int(mm) + int(minutes)) % (24 * 60)
        end = _fmt_time12(f"{total // 60:02d}:{total % 60:02d}")
        return f"{start} – {end}"
    except (ValueError, TypeError):
        return start


async def _mirror_gates(job: Dict[str, Any], fields: Dict[str, Any]) -> Dict[str, Any]:
    """Copy the 3 Airtable Projects gate timestamps onto the Mongo job so /track never calls
    Airtable. Airtable wins when present; an ack-set brochure/estimate stamp is preserved while
    Airtable is still empty. ofs_signed_at mirrors Airtable exactly (owner-entered only)."""
    prev = job.get("gates") or {}
    gates = {
        "brochure_sent_at": fields.get(PROJECT_BROCHURE_SENT_F) or prev.get("brochure_sent_at"),
        "estimate_delivered_at": fields.get(PROJECT_ESTIMATE_DELIVERED_F) or prev.get("estimate_delivered_at"),
        "ofs_signed_at": fields.get(PROJECT_OFS_SIGNED_F),
    }
    if gates != prev:
        await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {"gates": gates}})
        job["gates"] = gates
    return gates


def _move_snapshot(job: Dict[str, Any]) -> Dict[str, Any]:
    return {"job_date": job.get("job_date"), "start_time": job.get("start_time"),
            "pickup_address": job.get("pickup_address"), "dropoff_address": job.get("dropoff_address")}


async def _latest_ack(job_id: str) -> Optional[Dict[str, Any]]:
    return await mongo_db.paperwork_acks.find_one({"job_id": job_id}, sort=[("at", -1)])


async def _customer_timeline(job: Dict[str, Any], status: str, stage: Dict[str, Any]) -> Dict[str, Any]:
    gates = job.get("gates") or {}
    ack = await _latest_ack(job["_id"])
    acked = bool(ack)
    brochure_done = bool(gates.get("brochure_sent_at")) or acked
    estimate_done = bool(gates.get("estimate_delivered_at")) or acked
    ofs_done = bool(gates.get("ofs_signed_at"))
    items = [
        {"key": "brochure", "label": "Consumer brochure", "done": brochure_done},
        {"key": "estimate", "label": "Written estimate", "done": estimate_done},
        {"key": "ofs", "label": "Order for Service signed", "done": ofs_done},
    ]
    paperwork_all = brochure_done and estimate_done and ofs_done
    action_needed = (not acked) and not (bool(gates.get("brochure_sent_at")) and bool(gates.get("estimate_delivered_at")))
    paperwork_state = "done" if paperwork_all else ("action" if action_needed else "current")

    is_complete = stage.get("is_complete")
    days_after = stage.get("days_after_move")
    if is_complete:
        move_state, complete_state = "done", "done"
    elif days_after == 0 or status in ("En Route", "Arrived", "In Progress"):
        move_state, complete_state = "current", "upcoming"
    else:
        move_state, complete_state = "upcoming", "upcoming"
    steps = [
        {"key": "booked", "label": "Booked", "state": "done"},
        {"key": "paperwork", "label": "Paperwork", "state": paperwork_state, "items": items},
        {"key": "crew", "label": "Crew assigned", "state": "done" if job.get("crew") else "upcoming"},
        {"key": "move_day", "label": "Move day", "state": move_state},
        {"key": "complete", "label": "Complete", "state": complete_state},
    ]
    return {"steps": steps, "paperwork_acknowledged": acked, "paperwork_action_needed": action_needed,
            "paperwork_all_done": paperwork_all, "acknowledged_at": (ack or {}).get("at"),
            "acknowledged_name": (ack or {}).get("name")}


def _move_confirmation_state(job: Dict[str, Any]) -> Dict[str, Any]:
    confs = job.get("move_confirmations") or []
    if not confs:
        return {"confirmed": False, "at": None, "needs_reconfirm": False}
    last = confs[-1]
    return {"confirmed": True, "at": last.get("at"),
            "needs_reconfirm": (last.get("snapshot") or {}) != _move_snapshot(job)}


async def _paperwork_ack_summary(job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ack = await _latest_ack(job["_id"])
    if not ack:
        return None
    return {"name": ack.get("name"), "at": ack.get("at"), "ip": ack.get("ip"),
            "brochure_url": ack.get("brochure_url"),
            "documents": [{"filename": d.get("filename"), "sha256": d.get("sha256"), "kind": d.get("kind")}
                          for d in (ack.get("documents") or [])]}


class PaperworkAckPayload(BaseModel):
    name: str


@public_router.post("/track/{token}/acknowledge-paperwork")
async def portal_acknowledge_paperwork(token: str, payload: PaperworkAckPayload, request: Request) -> Dict[str, Any]:
    job = await _job_by_token(token)
    name = (payload.name or "").strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Please type your full name to confirm.")
    portal = await _portal_settings()
    brochure_url = (portal.get("brochure_url") or "").strip()
    documents: List[Dict[str, Any]] = []
    if brochure_url:
        sha, size = None, None
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                r = await client.get(brochure_url)
            if r.status_code < 300:
                sha, size = hashlib.sha256(r.content).hexdigest(), len(r.content)
        except Exception as exc:
            logger.warning("brochure hash failed: %s", exc)
        documents.append({"id": str(uuid4()), "kind": "brochure",
                          "filename": (brochure_url.rsplit("/", 1)[-1] or "brochure")[:120],
                          "url": brochure_url, "sha256": sha, "bytes": size})
    rec = {"_id": str(uuid4()), "job_id": job["_id"], "invoice_number": job.get("invoice_number"),
           "name": name, "ip": (request.client.host if request.client else None),
           "user_agent": (request.headers.get("user-agent") or "")[:400],
           "brochure_url": brochure_url or None, "documents": documents, "at": now_iso()}
    await mongo_db.paperwork_acks.insert_one(rec)   # append-only; never updated or deleted
    gates = job.get("gates") or {}
    gset = {"paperwork_alert.active": False}   # customer ack clears the owner paperwork-gate alert
    if not gates.get("brochure_sent_at"):
        gset["gates.brochure_sent_at"] = rec["at"]
    if not gates.get("estimate_delivered_at"):
        gset["gates.estimate_delivered_at"] = rec["at"]
    await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": gset})
    await _owner_portal_ping(job, "Paperwork acknowledged",
                             f"{name} confirmed receipt of the brochure & estimate for Job #{job.get('invoice_number')}.")
    return {"ok": True, "at": rec["at"], "name": name}


@public_router.post("/track/{token}/confirm-move")
async def portal_confirm_move(token: str, request: Request) -> Dict[str, Any]:
    job = await _job_by_token(token)
    entry = {"at": now_iso(), "ip": (request.client.host if request.client else None),
             "user_agent": (request.headers.get("user-agent") or "")[:400], "snapshot": _move_snapshot(job)}
    await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$push": {"move_confirmations": entry}})
    await _owner_portal_ping(job, "Move details confirmed",
                             f"{(job.get('customer') or {}).get('name') or 'The customer'} confirmed their "
                             f"move details for Job #{job.get('invoice_number')}.")
    return {"ok": True, "at": entry["at"]}


# ---- T-48h customer reminder (daily 9am ET cron; sends ONE text per job) ----

async def _reminder_paperwork_line(job: Dict[str, Any]) -> str:
    ack = await _latest_ack(job["_id"])
    gates = job.get("gates") or {}
    acked = bool(ack) or (bool(gates.get("brochure_sent_at")) and bool(gates.get("estimate_delivered_at")))
    if acked:
        return ""
    return "Please review and confirm your paperwork today — we need it at least 24 hours before your move. "


def _move_datetime_et(job: Dict[str, Any]) -> Optional[datetime]:
    jd = (job.get("job_date") or "")[:10]
    if not jd:
        return None
    for st in (job.get("start_time") or "08:00", "08:00"):
        try:
            return datetime.fromisoformat(f"{jd}T{st}:00").replace(tzinfo=ZoneInfo("America/New_York"))
        except (ValueError, TypeError):
            continue
    return None


async def _send_customer_reminder(job: Dict[str, Any], portal: Dict[str, Any]) -> None:
    base = await _portal_base(portal)
    if not base:
        raise HTTPException(status_code=503, detail="Customer page URL isn't set in Settings.")
    token = await _ensure_tracking_token(job)
    link = f"{base}/track/{token}"
    aw = _arrival_window_str(job.get("start_time"), int(portal.get("arrival_window_minutes") or 30))
    extra = {"arrival_window": aw or _fmt_time12(job.get("start_time")),
             "paperwork_line": await _reminder_paperwork_line(job)}
    text = _render_portal_message(_portal_template(portal, "reminder"), job, link,
                                  await _business_phone(portal), extra)
    await openphone_send_sms((job.get("customer") or {}).get("phone"), text)
    await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {"reminder_sent_at": now_iso()}})
    await _log_portal_send(job, "sms", "reminder", "Auto — T-48h reminder")


async def _run_customer_reminders() -> Dict[str, Any]:
    portal = await _portal_settings()
    now = datetime.now(ZoneInfo("America/New_York"))
    horizon = now + timedelta(hours=48)
    sent = skipped = failed = 0
    async for job in mongo_db.jobs.find({"reminder_sent_at": {"$exists": False}}):
        if not (job.get("customer") or {}).get("phone"):
            skipped += 1; continue
        if (job.get("status") or "").lower() == "cancelled" or job.get("cancelled_at"):
            skipped += 1; continue
        move_dt = _move_datetime_et(job)
        if not move_dt or move_dt <= now or move_dt > horizon:
            skipped += 1; continue
        booked_raw = (job.get("deposit_paid") or {}).get("at") or job.get("created_at")
        try:
            booked = (datetime.fromisoformat(str(booked_raw).replace("Z", "+00:00"))
                      .astimezone(ZoneInfo("America/New_York"))) if booked_raw else None
        except (ValueError, TypeError):
            booked = None
        if booked and (move_dt - booked) < timedelta(hours=48):
            skipped += 1; continue   # booked inside the 48h window — no T-48h send
        try:
            await _send_customer_reminder(job, portal)
            sent += 1
        except Exception as exc:
            failed += 1
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            await notify(None, "owner", "Customer reminder NOT sent",
                         f"Job #{job.get('invoice_number')}: {detail}", "warning")
    logger.info("customer reminders: sent=%s skipped=%s failed=%s", sent, skipped, failed)
    return {"sent": sent, "skipped": skipped, "failed": failed}


async def _owner_alert_ping(job: Dict[str, Any], title: str, body: str, ntype: str = "warning") -> None:
    await notify(None, "owner", title, body, ntype,
                 {"job_id": job["_id"], "invoice_number": job.get("invoice_number")})
    try:
        integ = await get_integrations()
        phone = (integ.get("owner_alert_phone") or "").strip()
        if phone:
            await openphone_send_sms(phone, f"{title} — {body}")
    except Exception as exc:
        logger.warning("owner alert sms failed: %s", exc)


def _paperwork_alert_tier(hours: float) -> Optional[Tuple[str, str]]:
    if hours <= 24:
        return ("t24", "red")
    if hours <= 48:
        return ("t48", "amber")   # final routine reminder
    if hours <= 72:
        return ("t72", "amber")   # first routine reminder
    return None


def _paperwork_alert_card(job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    st = job.get("paperwork_alert") or {}
    if not st.get("active"):
        return None
    return {"active": True, "level": st.get("level") or "amber"}


async def _check_owner_paperwork_alert(job: Dict[str, Any], source: str = "cron") -> Optional[str]:
    """Owner-facing paperwork-gate alert. First alert inside 72h + final inside 48h (max 2 routine),
    plus a red escalation inside 24h. Clears only when the customer acknowledges the paperwork."""
    if await _latest_ack(job["_id"]):
        if (job.get("paperwork_alert") or {}).get("active"):
            await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {"paperwork_alert.active": False}})
        return None
    if (job.get("status") or "").lower() == "cancelled" or job.get("cancelled_at"):
        return None
    move_dt = _move_datetime_et(job)
    if not move_dt:
        return None
    now = datetime.now(ZoneInfo("America/New_York"))
    hours = (move_dt - now).total_seconds() / 3600
    if hours <= 0:
        return None
    tier_info = _paperwork_alert_tier(hours)
    if not tier_info:
        return None
    tier, level = tier_info
    state = job.get("paperwork_alert") or {}
    if state.get("for_date") != job.get("job_date"):   # reschedule → re-evaluate from scratch
        state = {"for_date": job.get("job_date"), "tiers": [], "active": False}
    sent = list(state.get("tiers") or [])
    if tier in sent:
        return None
    if tier in ("t72", "t48") and len([t for t in sent if t in ("t72", "t48")]) >= 2:
        return None
    who = (job.get("customer") or {}).get("name") or "the customer"
    inv = job.get("invoice_number")
    if tier == "t24":
        title = "🚩 Paperwork under 24 hours"
        body = (f"Job #{inv} ({who}) is under 24 hours away and paperwork still isn't acknowledged. "
                "Record the customer's short-notice request in short_notice_proof, or reschedule.")
    elif tier == "t48":
        title = "Paperwork not confirmed — final reminder (under 48h)"
        body = (f"Job #{inv} ({who}) is under 48 hours away and the customer hasn't confirmed their paperwork. "
                "It needs to be confirmed at least 24 hours before the move.")
    else:
        title = "Paperwork not confirmed — under 72h"
        body = f"Job #{inv} ({who}) is under 72 hours away and hasn't confirmed their paperwork yet."
    await _owner_alert_ping(job, title, body, "warning")
    sent.append(tier)
    state.update({"tiers": sent, "active": True, "level": level, "last_at": now_iso(), "for_date": job.get("job_date")})
    await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {"paperwork_alert": state}})
    logger.info("owner paperwork alert (%s) fired for job %s tier=%s", source, inv, tier)
    return tier


async def _run_owner_paperwork_alerts() -> Dict[str, Any]:
    et = ZoneInfo("America/New_York")
    today = datetime.now(et).date()
    lo, hi = today.isoformat(), (today + timedelta(days=4)).isoformat()
    fired = 0
    async for job in mongo_db.jobs.find({"job_date": {"$gte": lo, "$lte": hi}}):
        try:
            if await _check_owner_paperwork_alert(job, "cron"):
                fired += 1
        except Exception as exc:
            logger.warning("owner paperwork alert failed for job %s: %s", job.get("invoice_number"), exc)
    logger.info("owner paperwork alerts: fired=%s", fired)
    return {"fired": fired}


async def _run_daily_9am_et() -> None:
    await _run_customer_reminders()
    await _run_owner_paperwork_alerts()


@public_router.post("/cron/customer-reminders")
async def cron_customer_reminders(request: Request) -> Dict[str, Any]:
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if not secret or not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    asyncio.create_task(_run_daily_9am_et())
    return {"ok": True}


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
    # A review of 4 stars or below is a near miss worth a root cause (Quality Manual) —
    # auto-open a "Low review" nonconformance once per job. Best-effort: never break the
    # public review flow if Airtable is down.
    if payload.rating <= 4 and not job.get("portal_review_nc"):
        try:
            nc_fields = {
                NC_TYPE_F: "Low review", NC_SEVERITY_F: "Minor", NC_STATUS_F: "Open",
                NC_RAISED_BY_F: "Customer portal", NC_RAISED_DATE_F: _et_today(),
                NC_WHAT_F: (f"{payload.rating}-star portal review on Job #{job.get('invoice_number') or '—'}"
                            + (f': "{review["text"][:200]}"' if review["text"] else ".")),
            }
            if job.get("project_record_id"):
                nc_fields[NC_LINKED_JOB_F] = [job["project_record_id"]]
            nc = await airtable_request("POST", TABLES["nonconformances"],
                                        json_body={"records": [{"fields": nc_fields}], "typecast": True})
            await mongo_db.jobs.update_one({"_id": job["_id"]},
                                           {"$set": {"portal_review_nc": nc["records"][0]["id"]}})
        except HTTPException as exc:
            logger.warning("Low-review NC skipped for job %s: %s", job.get("invoice_number"), exc.detail)
    who = (job.get("customer") or {}).get("name") or "The customer"
    stars = "★" * payload.rating + "☆" * (5 - payload.rating)
    await _owner_portal_ping(job, f"New review — {payload.rating}/5",
                             f"{who} (Job #{job.get('invoice_number')}) left {stars}"
                             + (f': "{review["text"][:120]}"' if review["text"] else "."))
    business = await mongo_db.settings.find_one({"_id": "business"}) or {}
    return {"ok": True, "review_link": business.get("reviewLink", "")}


@api_router.get("/jobs/{job_id}/portal-uploads")
async def job_portal_uploads(job_id: str, p: Dict[str, Any] = Depends(require_owner)):
    job = await mongo_db.jobs.find_one({"_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="No such job.")
    ups = await mongo_db.portal_uploads.find({"job_id": job_id}).sort("created_at", -1).to_list(50)
    return {"token": (job.get("tracking") or {}).get("token"),
            "uploads": [{"id": u["_id"], "kind": u.get("kind"), "filename": u.get("filename"),
                         "content_type": u.get("content_type"), "created_at": u.get("created_at")} for u in ups]}


# ------- Owner: "Send customer page" (stable link, multi-channel send, view history, reset)

def _portal_state(job: Dict[str, Any]) -> Dict[str, Any]:
    sends = job.get("portal_sends") or []
    views = job.get("portal_views") or {}
    ack = job.get("docs_ack") or {}
    return {
        "sends": [{"at": s.get("at"), "channel": s.get("channel"),
                   "template_key": s.get("template_key"), "by": s.get("by")} for s in sends],
        "views": {"count": views.get("count") or 0, "first_at": views.get("first_at"), "last_at": views.get("last_at")},
        "docs": {"ack_at": ack.get("at"), "ack_name": ack.get("name")},
    }


@api_router.get("/jobs/{job_id}/portal")
async def get_job_portal(job_id: str, p: Dict[str, Any] = Depends(require_owner)):
    job = await mongo_db.jobs.find_one({"_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="No such job.")
    portal = await _portal_settings()
    base = await _portal_base(portal)
    token = (job.get("tracking") or {}).get("token")
    url = f"{base}/track/{token}" if (base and token) else None
    bp = await _business_phone(portal)
    rendered = {k: _render_portal_message(_portal_template(portal, k), job, url or "", bp) for k in PORTAL_TEMPLATE_KEYS}
    return {"url": url, "base_set": bool(base), "customer": job.get("customer") or {},
            "job_date": job.get("job_date"), "invoice_number": job.get("invoice_number"),
            "templates": rendered, "business_phone": bp, **_portal_state(job)}


class PortalSendPayload(BaseModel):
    channel: str
    template_key: str = "booked"
    message: str = ""


@api_router.post("/jobs/{job_id}/portal/send")
async def send_job_portal(job_id: str, payload: PortalSendPayload, p: Dict[str, Any] = Depends(require_owner)):
    job = await mongo_db.jobs.find_one({"_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="No such job.")
    channel = (payload.channel or "").lower()
    if channel not in ("sms", "copy", "email"):
        raise HTTPException(status_code=422, detail="Channel must be sms, copy, or email.")
    base = await _portal_base()
    if not base:
        raise HTTPException(status_code=503, detail="Set your Customer page URL in Settings → Customer Page first.")
    token = await _ensure_tracking_token(job)
    url = f"{base}/track/{token}"
    if channel == "sms":   # only OpenPhone actually sends; a failure keeps the dialog open for Copy
        msg = (payload.message or "").strip()
        if not msg:
            raise HTTPException(status_code=422, detail="Write the message first.")
        await openphone_send_sms((job.get("customer") or {}).get("phone"), msg)
    await _log_portal_send(job, channel, payload.template_key, p.get("name") or "Owner")
    await audit(p, f"sent customer page ({channel})", f"job {job.get('invoice_number')}", {"template": payload.template_key})
    return {"ok": True, "url": url}


@api_router.post("/jobs/{job_id}/portal/reset")
async def reset_job_portal(job_id: str, p: Dict[str, Any] = Depends(require_owner)):
    job = await mongo_db.jobs.find_one({"_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="No such job.")
    token = uuid4().hex
    await mongo_db.jobs.update_one({"_id": job["_id"]}, {"$set": {"tracking.token": token}})
    await audit(p, "reset the customer page link", f"job {job.get('invoice_number')}")
    base = await _portal_base()
    return {"ok": True, "url": f"{base}/track/{token}" if base else None}


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


# Rule 8: quality gets a READ-ONLY, cost-stripped quote breakdown. ALLOWLIST (fail-closed):
# copy only these customer-facing keys out of the breakdown; drop everything else, whatever it is named.
_QUALITY_QUOTE_ALLOWLIST = {
    "customerName", "customerPhone", "jobDate", "moveDate",
    "addressFrom", "addressTo", "from", "to",
    "package", "packageLabel", "scope", "scopeLabel", "homeSize",
    "crew", "crewSize", "hours", "estimatedHours", "estHours",
    "hourlyRate", "manHourRate", "rate",
    "tripFee", "travel", "travelFee",
    "mileageFree", "mileageExtra", "mileage", "distFee",
    "stairs", "stairsFee", "longCarry", "longCarryFee",
    "specialtyItems", "specialty", "extraStop", "extraStopFee",
    "packingMaterials", "materials", "materialsFee",
    "subtotal", "finalQuote", "finalTotal", "quoteLow", "quoteHigh",
    "bandLo", "bandHi", "deposit", "depositAmount",
    "invoiceLineItems", "lineItems", "surcharges",
}


def _strip_quote_for_quality(breakdown: Any) -> Any:
    """Return a cost-stripped copy of the quote for the quality role.
    Allowlist, not denylist: only customer-facing keys survive, so a new internal
    key added to the breakdown later can never leak (fails closed)."""
    if not isinstance(breakdown, dict):
        return breakdown
    return {k: v for k, v in breakdown.items() if k in _QUALITY_QUOTE_ALLOWLIST}


@api_router.get("/quotes/{lead_id}")
async def get_quote_breakdown(lead_id: str, role: str = Depends(require_auth)):
    if role not in ("owner", "sales", "quality"):
        raise HTTPException(status_code=403, detail="Your role can't see quotes.")
    doc = await mongo_db.lead_quotes.find_one({"_id": lead_id}) or {}
    breakdown = doc.get("breakdown")
    if role == "quality":
        breakdown = _strip_quote_for_quality(breakdown)
    return {"breakdown": breakdown, "updated_at": doc.get("updated_at"), "token": doc.get("token")}


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
async def create_record(table_key: str, request: Request, payload: RecordPayload = Body(...), role: str = Depends(require_auth)):
    table_id = resolve_table(table_key)
    await check_table_access(role, table_key)
    if table_key in ("tasks", "blog") and role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can add these.")
    if table_key == "projects" and role in ("sales", "quality"):
        raise HTTPException(status_code=403, detail="Create jobs from a booked lead — your role can't add projects directly.")
    body = {"records": [{"fields": clean_write_fields(payload.fields, role, table_key)}], "typecast": True}
    data = await airtable_request("POST", table_id, json_body=body)
    rec = filter_record(data["records"][0], role, table_key)
    if table_key == "tasks":
        rec["audience"] = []
    if table_key == "blog" and payload.fields.get(BLOG_STATUS_F) == "Published":
        await notify_blog_published(data["records"][0])
    if table_key == "job_audits":
        await _maybe_open_audit_nc(data["records"][0], request)
    return rec


@api_router.patch("/tables/{table_key}/{record_id}")
async def update_record(table_key: str, record_id: str, request: Request, payload: RecordPayload = Body(...), role: str = Depends(require_auth)):
    table_id = resolve_table(table_key)
    await check_table_access(role, table_key)
    if table_key == "projects" and role in ("sales", "quality"):
        msg = ("Quality can view jobs but not edit them." if role == "quality"
               else "Update job details from the Compliance panel.")
        raise HTTPException(status_code=403, detail=msg)
    if table_key == "blog" and role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can edit blog posts.")
    if table_key == "tasks" and role != "owner":
        if any(k != TASK_STATUS_F for k in payload.fields):
            raise HTTPException(status_code=403, detail="You can only move a task between columns.")
        grp = TASK_GROUP_FOR_ROLE.get(role)
        meta = await mongo_db.task_meta.find_one({"_id": record_id})
        if not meta or grp not in (meta.get("audience") or []):
            raise HTTPException(status_code=403, detail="That task isn't shared with your team.")
    if table_key == "nonconformances" and payload.fields.get(NC_STATUS_F) == "Closed":
        await _guard_nc_close(record_id, payload.fields)
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
    if table_key == "projects" and payload.fields.get(PROJECT_STATUS_FIELD) == PROJECT_COMPLETED_STATUS:
        await _mark_review_requested(record_id, source="observed")
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


# ================= Quality & Compliance module (prompt 1 of 3) =================
# NOTE: unrelated to audit()/audit_log (the system activity log). Everything here is job_audit / job_audits.

async def _airtable_all(table_id: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
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
    return records


async def _maybe_open_audit_nc(audit_rec: Dict[str, Any], request: Request) -> None:
    """Rule 4: saving an audit with Result 'Pass with findings' or 'Fail' auto-opens a
    linked nonconformance of Type 'Audit finding', and links the audit back to it."""
    fields = audit_rec.get("fields") or {}
    result = fields.get(JA_RESULT_F)
    if result not in ("Pass with findings", "Fail"):
        return
    try:
        p = await current_principal(request)
        linked_jobs = fields.get(JA_LINKED_JOB_F) or []
        nc_fields: Dict[str, Any] = {
            NC_TYPE_F: "Audit finding",
            NC_SEVERITY_F: "Major" if result == "Fail" else "Minor",
            NC_STATUS_F: "Open",
            NC_RAISED_BY_F: p.get("name") or "Quality",
            NC_RAISED_DATE_F: _et_today(),
            NC_WHAT_F: fields.get(JA_FINDINGS_F) or f"Audit result: {result}",
        }
        if linked_jobs:
            nc_fields[NC_LINKED_JOB_F] = linked_jobs
        nc_data = await airtable_request(
            "POST", TABLES["nonconformances"], json_body={"records": [{"fields": nc_fields}], "typecast": True})
        nc_id = nc_data["records"][0]["id"]
        await airtable_request(
            "PATCH", TABLES["job_audits"],
            json_body={"records": [{"id": audit_rec["id"], "fields": {JA_LINKED_NC_F: [nc_id]}}], "typecast": True})
    except Exception as exc:
        logger.warning("Auto-nonconformance from audit failed: %s", exc)


async def _guard_nc_close(record_id: str, patch_fields: Dict[str, Any]) -> None:
    """Rule 5: a nonconformance cannot be closed without a root cause and a corrective action."""
    root = patch_fields.get(NC_ROOT_F)
    corrective = patch_fields.get(NC_CORRECTIVE_F)
    if root is None or corrective is None:
        try:
            prev = await airtable_request("GET", TABLES["nonconformances"], path=f"/{record_id}",
                                          params={"returnFieldsByFieldId": "true"})
            pf = prev.get("fields") or {}
        except HTTPException:
            pf = {}
        if root is None:
            root = pf.get(NC_ROOT_F)
        if corrective is None:
            corrective = pf.get(NC_CORRECTIVE_F)
    if not (str(root or "").strip() and str(corrective or "").strip()):
        raise HTTPException(status_code=422,
                            detail="Add a root cause and a corrective action before closing this nonconformance.")


def _num(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


async def _resolve_people() -> Dict[str, str]:
    """Map user _id -> display name so quoted_by / surveyor ids render as names."""
    users = await mongo_db.users.find({}, {"_id": 1, "name": 1}).to_list(500)
    return {u["_id"]: u.get("name", "") for u in users}


def _person_label(raw: Any, people: Dict[str, str]) -> str:
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    key = str(raw or "").strip()
    return people.get(key, key)


async def _actual_hours_by_project(projects: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """On-site actual hours per project from time_entries (last clock-out minus first clock-in).
    Link chain: project -> Mongo job (project_record_id, else linked lead_id) -> job_date ->
    assignments on that date -> their time_entries. Best-effort; refined by name when several
    assignments share a date."""
    jobs = await mongo_db.jobs.find({}).to_list(1000)
    by_recid: Dict[str, Dict[str, Any]] = {}
    by_lead: Dict[str, Dict[str, Any]] = {}
    for j in jobs:
        if j.get("project_record_id"):
            by_recid[j["project_record_id"]] = j
        if j.get("lead_id"):
            by_lead[j["lead_id"]] = j
    assignments = await mongo_db.assignments.find({}).to_list(2000)
    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for a in assignments:
        by_date.setdefault((a.get("job_date") or "")[:10], []).append(a)

    out: Dict[str, Optional[float]] = {}
    for pr in projects:
        f = pr.get("fields") or {}
        job = by_recid.get(pr["id"])
        if not job:
            for lid in (f.get(PROJECT_LEAD_LINK_FIELD) or []):
                if lid in by_lead:
                    job = by_lead[lid]
                    break
        job_date = (job.get("job_date") if job else None) or (str(f.get(PROJECT_DATE_FIELD) or "")[:10] or None)
        if not job_date:
            out[pr["id"]] = None
            continue
        candidates = by_date.get(job_date, [])
        name = str(f.get(PROJECT_NAME_FIELD) or "").lower()
        matched = [a for a in candidates if a.get("job_name") and str(a["job_name"]).lower()[:12] in name] if name else []
        chosen = matched or candidates
        # Stage 4 A1/A9: the ONE shared on-site definition (Arrived→Complete), not yard-in→last-out.
        out[pr["id"]] = await _shared_on_site_hours([a["_id"] for a in chosen])
    return out


@api_router.get("/quality/audit-queue")
async def quality_audit_queue(request: Request):
    p = await current_principal(request)
    if p["role"] not in ("owner", "quality"):
        raise HTTPException(status_code=403, detail="Only the owner and quality can open the audit queue.")
    projects = await _airtable_all(TABLES["projects"])
    audits = await _airtable_all(TABLES["job_audits"])
    audited: set = set()
    for a in audits:
        for jid in ((a.get("fields") or {}).get(JA_LINKED_JOB_F) or []):
            audited.add(jid)
    today = datetime.now(ZoneInfo("America/New_York")).date()
    rows = []
    queued = []
    for pr in projects:
        f = pr.get("fields") or {}
        if f.get(PROJECT_STATUS_FIELD) != PROJECT_COMPLETED_STATUS or pr["id"] in audited:
            continue
        move_date = str(f.get(PROJECT_DATE_FIELD) or "")[:10] or None
        days_since = audit_due = None
        past_due = False
        if move_date:
            try:
                md = datetime.fromisoformat(move_date).date()
                days_since = (today - md).days
                due = md + timedelta(days=7)
                audit_due = due.isoformat()
                past_due = today > due
            except ValueError:
                pass
        queued.append(pr)
        rows.append({
            "id": pr["id"],
            "name": f.get(PROJECT_NAME_FIELD) or "Untitled job",
            "move_date": move_date,
            "days_since": days_since,
            "audit_due": audit_due,
            "past_due": past_due,
            "quoted_total": _num(f.get(PROJECT_QUOTE_FIELD)),
        })
    # read-only gate state per queued job (rule 5: 7-day audit records "gates green or override")
    if queued:
        ctx = await _compliance_context(queued)
        ov = {d["_id"]: d.get("override") for d in
              await mongo_db.job_compliance.find({"_id": {"$in": [pr["id"] for pr in queued]}}).to_list(500)}
        by_id = {pr["id"]: pr for pr in queued}
        for row in rows:
            pr = by_id.get(row["id"])
            row["gate_summary"] = _gate_summary(evaluate_gates(pr, ctx)) if pr else None
            row["overridden"] = bool(ov.get(row["id"]))
    # review state so the queue row can tick "Google review received" without leaving the page
    reviews = {d["_id"]: d for d in await mongo_db.project_reviews.find(
        {"_id": {"$in": [r["id"] for r in rows]}}).to_list(500)} if rows else {}
    for row in rows:
        rv = reviews.get(row["id"]) or {}
        row["google_review_received"] = bool(rv.get("google_review_received"))
        row["review_requested_at"] = rv.get("review_requested_at")
    rows.sort(key=lambda r: (not r["past_due"], r["audit_due"] or "9999-99-99"))
    return {"rows": rows}


@api_router.get("/quality/quote-accuracy")
async def quality_quote_accuracy(request: Request):
    p = await current_principal(request)
    if p["role"] not in ("owner", "quality"):
        raise HTTPException(status_code=403, detail="Only the owner and quality can open quote accuracy.")
    q = request.query_params
    d_from, d_to, rep = q.get("from"), q.get("to"), q.get("rep")
    rates = await get_rates_values()
    max_hours = _num(rates.get("maxHoursOnSite")) or 10.0
    projects = await _airtable_all(TABLES["projects"])
    audits = await _airtable_all(TABLES["job_audits"])
    people = await _resolve_people()
    pkg_by_lead = await _pkg_by_lead()
    completed = [pr for pr in projects if (pr.get("fields") or {}).get(PROJECT_STATUS_FIELD) == PROJECT_COMPLETED_STATUS]
    actual_by_project = await _actual_hours_by_project(completed)
    # newest audit per linked project for final total + variance-explained
    audit_by_job: Dict[str, Dict[str, Any]] = {}
    for a in audits:
        af = a.get("fields") or {}
        for jid in (af.get(JA_LINKED_JOB_F) or []):
            audit_by_job[jid] = af
    rows = []
    for pr in completed:
        f = pr.get("fields") or {}
        move_date = str(f.get(PROJECT_DATE_FIELD) or "")[:10] or None
        if d_from and move_date and move_date < d_from:
            continue
        if d_to and move_date and move_date > d_to:
            continue
        quoted_by_raw = f.get(PROJECT_QUOTED_BY_FIELD)
        rep_id = str((quoted_by_raw[0] if isinstance(quoted_by_raw, list) and quoted_by_raw else quoted_by_raw) or "").strip()
        if rep and rep_id != rep:
            continue
        af = audit_by_job.get(pr["id"]) or {}
        quoted_total = _num(f.get(PROJECT_QUOTE_FIELD))
        final_total = _num(af.get(JA_FINAL_TOTAL_F))
        est_hours = _num(f.get(PROJECT_HOURS_FIELD))
        actual_hours = actual_by_project.get(pr["id"])
        dollar_var = round(final_total - quoted_total, 2) if (final_total is not None and quoted_total is not None) else None
        hours_var = round(actual_hours - est_hours, 2) if (actual_hours is not None and est_hours is not None) else None
        hours_flag = None
        if hours_var is not None:
            if abs(hours_var) > 1.0:
                hours_flag = "red"
            elif abs(hours_var) > 0.5:
                hours_flag = "amber"
        over_max = actual_hours is not None and actual_hours > max_hours
        lead_link = f.get(PROJECT_LEAD_LINK_FIELD) or []
        rows.append({
            "id": pr["id"],
            "lead_id": lead_link[0] if lead_link else None,
            "name": f.get(PROJECT_NAME_FIELD) or "Untitled job",
            "move_date": move_date,
            "quoted_by": _person_label(quoted_by_raw, people),
            "quoted_by_id": rep_id or None,
            "surveyor": _person_label(f.get(PROJECT_SURVEYOR_FIELD), people),
            "quoted_total": quoted_total,
            "final_total": final_total,
            "dollar_variance": dollar_var,
            "estimated_hours": est_hours,
            "actual_hours": actual_hours,
            "hours_variance": hours_var,
            "hours_flag": hours_flag,
            "over_max_hours": over_max,
            "variance_explained": af.get(JA_VARIANCE_EXPLAINED_F),
            "package": pkg_by_lead.get(lead_link[0]) if lead_link else None,
        })
    rows.sort(key=lambda r: r["move_date"] or "", reverse=True)

    def _mean(vals: List[float]) -> Optional[float]:
        return round(sum(vals) / len(vals), 2) if vals else None

    hv = [r["hours_variance"] for r in rows if r["hours_variance"] is not None]
    dv = [r["dollar_variance"] for r in rows if r["dollar_variance"] is not None]
    per_rep: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        key = r["quoted_by"] or "Unassigned"
        slot = per_rep.setdefault(key, {"rep": key, "rep_id": r["quoted_by_id"], "_hv": [], "_dv": [], "jobs": 0})
        slot["jobs"] += 1
        if r["hours_variance"] is not None:
            slot["_hv"].append(r["hours_variance"])
        if r["dollar_variance"] is not None:
            slot["_dv"].append(r["dollar_variance"])
    reps = []
    for v in per_rep.values():
        enough = v["jobs"] >= 5   # small samples make bad feedback — no mean shown below 5 completed jobs
        reps.append({"rep": v["rep"], "rep_id": v["rep_id"], "jobs": v["jobs"], "enough": enough,
                     "mean_hours_variance": _mean(v["_hv"]) if enough else None,
                     "mean_dollar_variance": _mean(v["_dv"]) if enough else None})
    reps.sort(key=lambda v: v["rep"].lower())
    return {
        "rows": rows,
        "summary": {"jobs": len(rows), "mean_hours_variance": _mean(hv), "mean_dollar_variance": _mean(dv),
                    "max_hours_on_site": max_hours, "per_rep": reps},
        "reps": [{"id": v["rep_id"], "name": v["rep"]} for v in per_rep.values() if v["rep_id"]],
        "package_alerts": _detect_package_overruns(rows),
    }


class FeedbackPayload(BaseModel):
    job_id: Optional[str] = None
    job_name: Optional[str] = None
    rep_user_id: Optional[str] = None
    rep_name: Optional[str] = None
    date: Optional[str] = None
    what_was_off: str
    what_to_do: str = ""


@api_router.post("/quality/feedback")
async def create_quote_feedback(payload: FeedbackPayload, request: Request):
    p = await current_principal(request)
    if p["role"] not in ("owner", "quality"):
        raise HTTPException(status_code=403, detail="Only the owner and quality can log feedback.")
    if not payload.what_was_off.strip():
        raise HTTPException(status_code=422, detail="Say what was off before saving feedback.")
    raised_date = (payload.date or _et_today())[:10]
    nc_fields: Dict[str, Any] = {
        NC_TYPE_F: "Quote variance",
        NC_SEVERITY_F: "Minor",
        NC_STATUS_F: "Open",
        NC_RAISED_BY_F: p.get("name") or "Quality",
        NC_RAISED_DATE_F: raised_date,
        NC_WHAT_F: payload.what_was_off.strip(),
        NC_CORRECTIVE_F: payload.what_to_do.strip(),
    }
    if payload.job_id:
        nc_fields[NC_LINKED_JOB_F] = [payload.job_id]
    nc_id = None
    try:
        nc_data = await airtable_request(
            "POST", TABLES["nonconformances"], json_body={"records": [{"fields": nc_fields}], "typecast": True})
        nc_id = nc_data["records"][0]["id"]
    except HTTPException as exc:
        # Airtable unavailable in preview — still record the feedback app-side so the log/rep view works.
        logger.warning("Feedback nonconformance write skipped: %s", exc.detail)
    doc = {
        "_id": nc_id or str(uuid4()),
        "nc_id": nc_id,
        "job_id": payload.job_id,
        "job_name": payload.job_name,
        "rep_user_id": payload.rep_user_id,
        "rep_name": payload.rep_name,
        "date": raised_date,
        "what_was_off": payload.what_was_off.strip(),
        "what_to_do": payload.what_to_do.strip(),
        "created_by": p.get("name"),
        "created_at": now_iso(),
    }
    await mongo_db.quality_feedback.insert_one(doc)
    if payload.rep_user_id:
        await notify(payload.rep_user_id, None, "Feedback on a quote",
                     f"{p.get('name') or 'Quality'} left feedback on {payload.job_name or 'a job'}. "
                     f"What was off: {payload.what_was_off.strip()[:120]}",
                     "quality_feedback", {"job_id": payload.job_id})
    return {"ok": True, "id": str(doc["_id"]), "nc_id": nc_id}


@api_router.get("/quality/feedback")
async def list_quote_feedback(request: Request):
    p = await current_principal(request)
    if p["role"] in ("owner", "quality"):
        query: Dict[str, Any] = {}
    elif p.get("user_id"):
        # a rep sees only feedback given to them, never another rep's
        query = {"rep_user_id": p["user_id"]}
    else:
        raise HTTPException(status_code=403, detail="Your role can't see feedback.")
    docs = await mongo_db.quality_feedback.find(query, {"_id": 0}).to_list(1000)
    docs.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    return {"feedback": docs}


# ================= Compliance gates (Quality prompt 2 of 3) =================
# Gates never block booking. A failing gate books the job anyway, raises a
# nonconformance, and notifies the owner. Override is OWNER-ONLY (server-enforced).

_ET = ZoneInfo("America/New_York")
# severity labels match nonconformances select options; rank = seriousness (lower = worse)
GATE_SEVERITY_RANK = {"Liability risk": 0, "Regulatory": 1, "Major": 2, "Minor": 3}
GATE_DEFS = [
    ("brochure_delivered", "Brochure delivered", "Liability risk"),
    ("ofs_24h", "Order for Service signed 24h before", "Liability risk"),
    ("owner_operator", "Owner-operator notice", "Liability risk"),
    ("move_classification", "Move classification", "Regulatory"),
    ("survey_performed", "Survey performed", "Regulatory"),
    ("surveyor_eligible", "Surveyor eligible", "Regulatory"),
    ("inventory_complete", "Inventory complete", "Regulatory"),
    ("estimate_24h", "Written estimate 24h before", "Regulatory"),
    ("protection_selected", "Protection option selected", "Regulatory"),
    ("labor_equip_change", "Labor/equipment change agreed", "Regulatory"),
    ("company_credentials", "Company credentials current", "Regulatory"),
    ("crew_ready", "Crew ready", "Major"),
    ("deposit_cleared", "Deposit cleared", "Minor"),
    ("long_haul_review", "Long-haul review", "Minor"),
]
GATE_LABELS = {k: label for k, label, _ in GATE_DEFS}
GATE_SEVERITY = {k: sev for k, _, sev in GATE_DEFS}
# Document-compliance "critical" gates = the legal ones (Liability risk + Regulatory), 11 total.
# Deliberately EXCLUDES crew_ready (Major), deposit_cleared (Minor), long_haul_review (Minor):
# those are company policy, not NJ law, and must not drag a 100%-target risk metric red.
CRITICAL_GATE_KEYS = {k for (k, _label, sev) in GATE_DEFS if sev in ("Liability risk", "Regulatory")}
COMPLIANCE_INPUT_FIELDS = {
    "move_classification": PROJECT_MOVE_CLASS_F,
    "survey_type": PROJECT_SURVEY_TYPE_F,
    "survey_date": PROJECT_SURVEY_DATE_F,
    "inventory_complete": PROJECT_INVENTORY_COMPLETE_F,
    "brochure_sent_at": PROJECT_BROCHURE_SENT_F,
    "estimate_delivered_at": PROJECT_ESTIMATE_DELIVERED_F,
    "ofs_signed_at": PROJECT_OFS_SIGNED_F,
    "short_notice_proof": PROJECT_SHORT_NOTICE_PROOF_F,
    "protection_option": PROJECT_PROTECTION_OPTION_F,
    "declared_value": PROJECT_DECLARED_VALUE_F,
    "deductible": PROJECT_DEDUCTIBLE_F,
    "owner_operator_used": PROJECT_OWNER_OP_USED_F,
    "owner_operator_notice_at": PROJECT_OWNER_OP_NOTICE_F,
    "labor_equipment_change_agreed": PROJECT_LABOR_EQUIP_F,
    "one_way_miles": PROJECT_ONE_WAY_MILES_F,
    "long_haul_owner_ack": PROJECT_LONG_HAUL_ACK_F,
}
OWNER_ONLY_INPUTS = {"long_haul_owner_ack"}  # rule: only the owner acknowledges a long-haul move
CRED_KEYWORDS = {"License": ["license"], "Workers comp": ["workers"], "Cargo insurance": ["cargo"], "Auto insurance": ["auto"]}


def _c_dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(_ET)
    except (ValueError, TypeError):
        return None


def _c_date(v: Any):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v)[:10]).date()
    except (ValueError, TypeError):
        return None


def _credentials_status(quality_docs: Optional[List[Dict[str, Any]]], today) -> Dict[str, Any]:
    if quality_docs is None:
        return {"available": False, "missing": list(CRED_KEYWORDS.keys())}
    missing = []
    for label, keywords in CRED_KEYWORDS.items():
        ok = False
        for doc in quality_docs:
            f = doc.get("fields") or {}
            name = str(f.get(QD_NAME_F) or "").lower()
            if not any(kw in name for kw in keywords):
                continue
            if (f.get(QD_STATUS_F) or "") != "Current":
                continue
            review = _c_date(f.get(QD_REVIEW_F))
            if review and review < today:
                continue
            ok = True
            break
        if not ok:
            missing.append(label)
    return {"available": True, "missing": missing}


async def _compliance_context(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    rates = await get_rates_values()
    users = await mongo_db.users.find({}).to_list(500)
    users_by_id = {u["_id"]: u for u in users}
    try:
        quality_docs = await _airtable_all(TABLES["quality_docs"])
    except HTTPException:
        quality_docs = None
    jobs = await mongo_db.jobs.find({}).to_list(2000)
    jobs_by_recid, jobs_by_lead = {}, {}
    for j in jobs:
        if j.get("project_record_id"):
            jobs_by_recid[j["project_record_id"]] = j
        if j.get("lead_id"):
            jobs_by_lead[j["lead_id"]] = j
    assignments = await mongo_db.assignments.find({}).to_list(3000)
    assignments_by_date: Dict[str, List[Dict[str, Any]]] = {}
    for a in assignments:
        assignments_by_date.setdefault((a.get("job_date") or "")[:10], []).append(a)
    today = datetime.now(_ET).date()
    return {
        "rates": rates, "users_by_id": users_by_id,
        "jobs_by_recid": jobs_by_recid, "jobs_by_lead": jobs_by_lead,
        "assignments_by_date": assignments_by_date, "today": today,
        "credentials": _credentials_status(quality_docs, today),
    }


def _project_crew(pr: Dict[str, Any], ctx: Dict[str, Any]):
    """Best-effort link project -> the day's assignment(s) -> crew user ids + the day's total crew."""
    fields = pr.get("fields") or {}
    job = ctx["jobs_by_recid"].get(pr["id"])
    if not job:
        for lid in (fields.get(PROJECT_LEAD_LINK_FIELD) or []):
            if lid in ctx["jobs_by_lead"]:
                job = ctx["jobs_by_lead"][lid]
                break
    day = (job.get("job_date") if job else None) or (str(fields.get(PROJECT_DATE_FIELD) or "")[:10] or None)
    if not day:
        return [], 0
    same_day = ctx["assignments_by_date"].get(day, [])
    name = str(fields.get(PROJECT_NAME_FIELD) or "").lower()
    matched = [a for a in same_day if a.get("job_name") and str(a["job_name"]).lower()[:12] in name] if name else []
    chosen = matched or same_day
    crew_ids = [c.get("user_id") for a in chosen for c in (a.get("crew") or []) if c.get("user_id")]
    day_total = sum(len(a.get("crew") or []) for a in same_day)
    return crew_ids, day_total


def evaluate_gates(pr: Dict[str, Any], ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The 14 compliance gates for one project. Returns [{key,label,severity,passed,reason,exempt}]."""
    f = pr.get("fields") or {}
    today = ctx["today"]
    move_date = _c_date(f.get(PROJECT_DATE_FIELD))
    move_midnight = datetime.combine(move_date, datetime.min.time(), tzinfo=_ET) if move_date else None
    threshold_24h = (move_midnight - timedelta(hours=24)) if move_midnight else None
    mc = f.get(PROJECT_MOVE_CLASS_F)
    office_only = mc == "Office Goods Only"
    out: List[Dict[str, Any]] = []

    def add(key, passed, reason="", exempt=False):
        out.append({"key": key, "label": GATE_LABELS[key], "severity": GATE_SEVERITY[key],
                    "passed": bool(passed), "reason": reason, "exempt": exempt})

    # Regulatory
    add("move_classification", mc in ("Household Goods", "Office Goods Only"),
        "" if mc in ("Household Goods", "Office Goods Only") else "Set the move classification to Household Goods or Office Goods Only on the job.")
    survey_type = f.get(PROJECT_SURVEY_TYPE_F)
    add("survey_performed", survey_type in ("On site", "Video"),
        "" if survey_type in ("On site", "Video") else "Record an on-site or video survey — a survey type of 'None' won't pass.")
    # surveyor eligibility
    surv_raw = f.get(PROJECT_SURVEYOR_FIELD)
    surv_id = (surv_raw[0] if isinstance(surv_raw, list) and surv_raw else surv_raw) or ""
    surv = ctx["users_by_id"].get(str(surv_id).strip())
    if not surv:
        add("surveyor_eligible", False, "No eligible surveyor on the job — assign someone who's attested and has final-calc access.")
    else:
        final_access = surv.get("role") == "owner" or surv.get("calculator_access") == "final"
        attested = bool(surv.get("surveyor_attested"))
        active = surv.get("active", True)
        reasons = []
        if not active:
            reasons.append("account inactive")
        if not final_access:
            reasons.append("no final-calc access")
        if not attested:
            reasons.append("not attested")
        add("surveyor_eligible", not reasons,
            ("Surveyor can't sign off (" + ", ".join(reasons) + "). Use an attested surveyor with final-calc access.") if reasons else "")
    add("inventory_complete", bool(f.get(PROJECT_INVENTORY_COMPLETE_F)),
        "" if f.get(PROJECT_INVENTORY_COMPLETE_F) else "Finish the inventory and check 'Inventory complete'.")
    # Liability risk: brochure
    brochure = _c_dt(f.get(PROJECT_BROCHURE_SENT_F))
    b_ok = bool(brochure) and move_date is not None and brochure.date() <= move_date
    add("brochure_delivered", b_ok,
        "" if b_ok else ("Send the brochure and record the date. Without it the $1.00/lb cap may not hold." if not brochure
                         else "The brochure went out after the move date — it must be sent before the move. Without it the $1.00/lb cap may not hold."))
    # estimate 24h (office-exempt)
    if office_only:
        add("estimate_24h", True, "Exempt — office goods only.", exempt=True)
    else:
        est = _c_dt(f.get(PROJECT_ESTIMATE_DELIVERED_F))
        e_ok = bool(est) and threshold_24h is not None and est <= threshold_24h
        add("estimate_24h", e_ok, "" if e_ok else "Deliver the written estimate at least 24 hours before the move.")
    # ofs 24h (office-exempt), Liability risk
    if office_only:
        add("ofs_24h", True, "Exempt — office goods only.", exempt=True)
    else:
        ofs = _c_dt(f.get(PROJECT_OFS_SIGNED_F))
        short_notice = str(f.get(PROJECT_SHORT_NOTICE_PROOF_F) or "").strip()
        o_ok = (bool(ofs) and threshold_24h is not None and ofs <= threshold_24h) or bool(short_notice)
        add("ofs_24h", o_ok, "" if o_ok else "Needs a signature 24h before the move, or written proof the customer booked inside 24 hours.")
    # protection
    prot = f.get(PROJECT_PROTECTION_OPTION_F)
    if not prot:
        add("protection_selected", False, "Pick Option 1, 2 or 3 on the Order for Service. Option 2 also needs declared value and deductible.")
    elif prot == "Option 2":
        both = f.get(PROJECT_DECLARED_VALUE_F) not in (None, "") and f.get(PROJECT_DEDUCTIBLE_F) not in (None, "")
        add("protection_selected", both, "" if both else "Option 2 needs both a declared value and a deductible on the Order for Service.")
    else:
        add("protection_selected", True)
    # owner-operator, Liability risk
    oo_used = bool(f.get(PROJECT_OWNER_OP_USED_F))
    oo_notice = _c_dt(f.get(PROJECT_OWNER_OP_NOTICE_F))
    oo_ok = (not oo_used) or (bool(oo_notice) and move_date is not None and oo_notice.date() <= move_date)
    add("owner_operator", oo_ok, "" if oo_ok else "Send the written consumer notice before the move.")
    # labor/equipment change
    labor = f.get(PROJECT_LABOR_EQUIP_F)
    add("labor_equip_change", labor != "Not agreed",
        "" if labor != "Not agreed" else "A labor/equipment change wasn't agreed in writing — get it in writing or set the field to None.")
    # company credentials
    creds = ctx["credentials"]
    if not creds["available"]:
        add("company_credentials", False, "Document Register unavailable — can't verify credentials. Add the Airtable key, then refresh.")
    else:
        add("company_credentials", not creds["missing"],
            "" if not creds["missing"] else "Not current: " + ", ".join(creds["missing"]) + ". Renew them in the Document Register.")
    # crew ready, Major
    crew_ids, day_total = _project_crew(pr, ctx)
    cap = int(ctx["rates"].get("maxCrewPerDay") or 12)
    if not crew_ids:
        add("crew_ready", False, "No crew assigned yet — put a crew on the job.")
    else:
        bad = []
        for uid in crew_ids:
            u = ctx["users_by_id"].get(uid)
            if not u or not u.get("active", True):
                bad.append("a crew member's account is off")
                continue
            exp = _c_date(u.get("crew_docs_expiry"))
            if not exp or exp <= today:
                bad.append(f"{u.get('name', 'a crew member')}'s documents are expired or missing")
        if day_total > cap:
            bad.append(f"the day is overbooked ({day_total} vs cap {cap})")
        add("crew_ready", not bad,
            ("; ".join(sorted(set(bad))) + " — fix before the move.") if bad else "")
    # deposit, Minor
    quote = _num(f.get(PROJECT_QUOTE_FIELD))
    deposit = _num(f.get(PROJECT_DEPOSIT_FIELD))
    if not quote:
        add("deposit_cleared", False, "No quote on file to compare the deposit against — add the quote first.")
    else:
        d_ok = (deposit or 0) >= 0.25 * quote
        add("deposit_cleared", d_ok, "" if d_ok else "Deposit is under 25% of the quote — collect the rest before the move.")
    # long-haul, Minor
    miles = _num(f.get(PROJECT_ONE_WAY_MILES_F)) or 0
    lh_ok = miles < 60 or bool(f.get(PROJECT_LONG_HAUL_ACK_F))
    add("long_haul_review", lh_ok, "" if lh_ok else "This is a 60+ mile move. The owner needs to acknowledge it (owner-only checkbox).")

    out.sort(key=lambda g: (GATE_SEVERITY_RANK.get(g["severity"], 9), g["passed"]))
    return out


def _gate_summary(gates: List[Dict[str, Any]]) -> Dict[str, Any]:
    failing = [g for g in gates if not g["passed"]]
    worst = min((GATE_SEVERITY_RANK.get(g["severity"], 9) for g in failing), default=None)
    worst_sev = next((s for s, r in GATE_SEVERITY_RANK.items() if r == worst), None) if worst is not None else None
    return {"total": len(gates), "passed": len(gates) - len(failing), "failing": len(failing),
            "all_green": not failing, "worst_severity": worst_sev,
            "failing_keys": [g["key"] for g in failing]}


def _compliance_inputs(f: Dict[str, Any]) -> Dict[str, Any]:
    return {name: f.get(fid) for name, fid in COMPLIANCE_INPUT_FIELDS.items()}


async def _fetch_project(project_id: str) -> Dict[str, Any]:
    return await airtable_request("GET", TABLES["projects"], path=f"/{project_id}",
                                  params={"returnFieldsByFieldId": "true"})


async def _compliance_result(project_id: str) -> Dict[str, Any]:
    record = await _fetch_project(project_id)
    ctx = await _compliance_context([record])
    gates = evaluate_gates(record, ctx)
    summary = _gate_summary(gates)
    await mongo_db.job_compliance.update_one(
        {"_id": project_id},
        {"$set": {"gate_results": gates, "summary": summary, "evaluated_at": now_iso()}}, upsert=True)
    comp = await mongo_db.job_compliance.find_one({"_id": project_id}) or {}
    return {"project_id": project_id, "name": (record.get("fields") or {}).get(PROJECT_NAME_FIELD),
            "inputs": _compliance_inputs(record.get("fields") or {}), "gates": gates,
            "summary": summary, "override": comp.get("override")}


@api_router.get("/jobs/{project_id}/compliance")
async def get_job_compliance(project_id: str, request: Request):
    p = await current_principal(request)
    if p["role"] not in ("owner", "sales", "quality"):
        raise HTTPException(status_code=403, detail="Your role can't see compliance.")
    result = await _compliance_result(project_id)
    result["can_edit"] = p["role"] in ("owner", "sales")
    result["can_override"] = p["role"] == "owner"
    return result


class CompliancePayload(BaseModel):
    inputs: Dict[str, Any]


@api_router.put("/jobs/{project_id}/compliance")
async def save_job_compliance(project_id: str, payload: CompliancePayload, request: Request):
    p = await current_principal(request)
    if p["role"] not in ("owner", "sales"):
        raise HTTPException(status_code=403, detail="Only the owner and sales can edit gate inputs.")
    unknown = [k for k in payload.inputs if k not in COMPLIANCE_INPUT_FIELDS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown field(s): {', '.join(unknown)}")
    if p["role"] != "owner" and any(k in OWNER_ONLY_INPUTS for k in payload.inputs):
        raise HTTPException(status_code=403, detail="Only the owner can acknowledge a long-haul move.")
    fields = {COMPLIANCE_INPUT_FIELDS[k]: v for k, v in payload.inputs.items()}
    await airtable_request("PATCH", TABLES["projects"],
                           json_body={"records": [{"id": project_id, "fields": fields}], "typecast": True})
    result = await _compliance_result(project_id)
    result["can_edit"] = True
    result["can_override"] = p["role"] == "owner"
    return result


class OverridePayload(BaseModel):
    reason: str
    confirm: str


@api_router.post("/jobs/{project_id}/compliance/override")
async def override_job_compliance(project_id: str, payload: OverridePayload, p: Dict[str, Any] = Depends(require_owner)):
    reason = (payload.reason or "").strip()
    if len(reason) < 20:
        raise HTTPException(status_code=422, detail="Give a written reason of at least 20 characters.")
    if payload.confirm != "OVERRIDE":
        raise HTTPException(status_code=422, detail="Type the word OVERRIDE to confirm.")
    record = await _fetch_project(project_id)
    ctx = await _compliance_context([record])
    gates = evaluate_gates(record, ctx)
    failing = [g for g in gates if not g["passed"]]
    if not failing:
        raise HTTPException(status_code=422, detail="Nothing to override — every gate passes.")
    worst_rank = min(GATE_SEVERITY_RANK.get(g["severity"], 9) for g in failing)
    worst_sev = next(s for s, r in GATE_SEVERITY_RANK.items() if r == worst_rank)
    what = (f"Compliance gate override by {p.get('name')}.\nReason: {reason}\n"
            f"Failing gates: {', '.join(g['label'] for g in failing)}")
    nc_fields = {
        NC_TYPE_F: "Gate override", NC_SEVERITY_F: worst_sev, NC_STATUS_F: "Open",
        NC_RAISED_BY_F: p.get("name") or "Owner", NC_RAISED_DATE_F: _et_today(),
        NC_WHAT_F: what, NC_LINKED_JOB_F: [project_id],
    }
    try:
        nc = await airtable_request("POST", TABLES["nonconformances"],
                                    json_body={"records": [{"fields": nc_fields}], "typecast": True})
        nc_id = nc["records"][0]["id"]
    except HTTPException:
        raise HTTPException(status_code=502,
                            detail="Override could not be recorded — the nonconformance write failed. Nothing was saved.")
    override = {"reason": reason, "by": p.get("name"), "by_id": p.get("user_id"),
                "at": now_iso(), "nc_id": nc_id, "worst_severity": worst_sev}
    summary = _gate_summary(gates)
    await mongo_db.job_compliance.update_one(
        {"_id": project_id},
        {"$set": {"gate_results": gates, "summary": summary, "evaluated_at": now_iso(), "override": override}},
        upsert=True)
    await notify(None, "owner", "Compliance override recorded",
                 f"{p.get('name')} overrode {len(failing)} failing gate(s) on a job. NC opened ({worst_sev}).",
                 "gate_override", {"project_id": project_id, "nc_id": nc_id})
    return {"project_id": project_id, "name": (record.get("fields") or {}).get(PROJECT_NAME_FIELD),
            "inputs": _compliance_inputs(record.get("fields") or {}), "gates": gates,
            "summary": summary, "override": override, "can_edit": True, "can_override": True}




# =====================================================================================
# Quality & Compliance — PROMPT 3: claims tracker, review capture, KPI dashboard,
# monthly review. Claims live in Airtable (7-year legal retention); review tracking is
# operational and lives in Mongo (project_reviews). Form due / Settlement due are Airtable
# FORMULA fields — read them, never compute or write them. The extension's +30 days is
# ALREADY inside the Settlement due formula; never add it again in code.
# =====================================================================================

CLAIM_WRITABLE = {
    "linked_job": CLAIM_LINKED_JOB_F,
    "notice_received_date": CLAIM_NOTICE_DATE_F,
    "form_sent_date": CLAIM_FORM_SENT_F,
    "completed_claim_received_date": CLAIM_COMPLETED_RECEIVED_F,
    "extension_agreed": CLAIM_EXTENSION_F,
    "protection_option": CLAIM_PROTECTION_F,
    "amount_claimed": CLAIM_AMOUNT_CLAIMED_F,
    "amount_settled": CLAIM_AMOUNT_SETTLED_F,   # OWNER ONLY (enforced in the endpoints)
    "status": CLAIM_STATUS_F,
    "notes": CLAIM_NOTES_F,
    "linked_nonconformance": CLAIM_LINKED_NC_F,
}
CLAIM_TERMINAL_STATUSES = {"Settled", "Denied", "Withdrawn"}


def _et_date_today():
    return datetime.now(_ET).date()


def _days_until(date_str, today=None):
    d = _c_date(date_str)
    if not d:
        return None
    return (d - (today or _et_date_today())).days


def _days_since(date_str, today=None):
    d = _c_date(date_str)
    if not d:
        return None
    return ((today or _et_date_today()) - d).days


def _claim_urgency(out: Dict[str, Any], today) -> Dict[str, Any]:
    """The active clock: the 7-day form clock until the form is sent, then the 90/120-day
    settlement clock once the completed claim is back. Terminal claims have no clock."""
    if out["status"] in CLAIM_TERMINAL_STATUSES:
        return {"which": None, "deadline": None, "days": None, "state": None}
    if not out["form_sent_date"]:
        deadline, which, amber = out["form_due"], "form", 3
    elif out["completed_claim_received_date"]:
        deadline, which, amber = out["settlement_due"], "settlement", 14
    else:
        return {"which": None, "deadline": None, "days": None, "state": None}
    days = _days_until(deadline, today)
    if days is None:
        state = None
    elif days < 0:
        state = "red"
    elif days <= amber:
        state = "amber"
    else:
        state = "green"
    return {"which": which, "deadline": deadline, "days": days, "state": state}


def _claim_out(rec: Dict[str, Any], job_names: Dict[str, str], today) -> Dict[str, Any]:
    f = rec.get("fields") or {}
    linked_job = f.get(CLAIM_LINKED_JOB_F) or []
    linked_nc = f.get(CLAIM_LINKED_NC_F) or []
    out = {
        "id": rec["id"],
        "claim_number": f.get(CLAIM_NUMBER_F),
        "linked_job_id": linked_job[0] if linked_job else None,
        "linked_job_name": job_names.get(linked_job[0]) if linked_job else None,
        "notice_received_date": f.get(CLAIM_NOTICE_DATE_F),
        "form_due": f.get(CLAIM_FORM_DUE_F),                  # FORMULA — read-only (Notice + 7)
        "form_sent_date": f.get(CLAIM_FORM_SENT_F),
        "completed_claim_received_date": f.get(CLAIM_COMPLETED_RECEIVED_F),
        "settlement_due": f.get(CLAIM_SETTLEMENT_DUE_F),      # FORMULA — read-only (extension already applied)
        "extension_agreed": bool(f.get(CLAIM_EXTENSION_F)),
        "protection_option": f.get(CLAIM_PROTECTION_F),
        "amount_claimed": _num(f.get(CLAIM_AMOUNT_CLAIMED_F)),
        "amount_settled": _num(f.get(CLAIM_AMOUNT_SETTLED_F)),
        "status": f.get(CLAIM_STATUS_F) or "Notice received",
        "notes": f.get(CLAIM_NOTES_F) or "",
        "linked_nc_id": linked_nc[0] if linked_nc else None,
    }
    out["urgency"] = _claim_urgency(out, today)
    out["pinned"] = out["urgency"]["state"] == "red"
    return out


async def _project_names() -> Dict[str, str]:
    projects = await _airtable_all(TABLES["projects"])
    return {pr["id"]: (pr.get("fields") or {}).get(PROJECT_NAME_FIELD) or "Untitled job" for pr in projects}


def _claim_write_fields(inputs: Dict[str, Any]) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    for k, v in inputs.items():
        if k not in CLAIM_WRITABLE:
            raise HTTPException(status_code=422, detail=f"Unknown or read-only claim field: {k}")
        fid = CLAIM_WRITABLE[k]
        if k in ("linked_job", "linked_nonconformance"):
            fields[fid] = [v] if v else []
        elif k == "extension_agreed":
            fields[fid] = bool(v)
        elif k in ("amount_claimed", "amount_settled"):
            fields[fid] = None if v in (None, "") else float(v)
        else:
            fields[fid] = v or None
    return fields


def _enforce_claim_owner_rules(inputs: Dict[str, Any], role: str) -> None:
    if role == "owner":
        return
    if "amount_settled" in inputs and inputs.get("amount_settled") not in (None, ""):
        raise HTTPException(status_code=403, detail="Only the owner can record a settlement amount.")
    if inputs.get("status") == "Settled":
        raise HTTPException(status_code=403, detail="Only the owner can mark a claim Settled.")


@api_router.get("/quality/claims")
async def list_claims(request: Request):
    p = await current_principal(request)
    if p["role"] not in ("owner", "quality"):
        raise HTTPException(status_code=403, detail="Only the owner and quality can open claims.")
    today = _et_date_today()
    names = await _project_names()
    recs = await _airtable_all(CLAIMS_TABLE)
    rows = [_claim_out(r, names, today) for r in recs]

    def sort_key(r):   # past-due (red) pinned to the top, then soonest active deadline
        u = r["urgency"]
        has = u["days"] is not None
        return (not r["pinned"], 0 if has else 1, u["days"] if has else 10 ** 9)

    rows.sort(key=sort_key)
    return {"rows": rows, "can_settle": p["role"] == "owner",
            "statuses": CLAIM_STATUSES, "protection_options": ["Option 1", "Option 2", "Option 3"]}


class ClaimPayload(BaseModel):
    inputs: Dict[str, Any]


async def _open_claim_nc(project_id: Optional[str], desc: str, raised_by: str) -> str:
    nc_fields = {
        NC_TYPE_F: "Claim", NC_SEVERITY_F: "Liability risk", NC_STATUS_F: "Open",
        NC_RAISED_BY_F: raised_by or "Quality", NC_RAISED_DATE_F: _et_today(), NC_WHAT_F: desc,
    }
    if project_id:
        nc_fields[NC_LINKED_JOB_F] = [project_id]
    nc = await airtable_request("POST", TABLES["nonconformances"],
                                json_body={"records": [{"fields": nc_fields}], "typecast": True})
    return nc["records"][0]["id"]


@api_router.post("/quality/claims")
async def create_claim(payload: ClaimPayload, request: Request):
    p = await current_principal(request)
    if p["role"] not in ("owner", "quality"):
        raise HTTPException(status_code=403, detail="Only the owner and quality can create claims.")
    inputs = dict(payload.inputs or {})
    inputs.pop("linked_nonconformance", None)      # the server sets the NC link
    _enforce_claim_owner_rules(inputs, p["role"])
    inputs.setdefault("status", "Notice received")
    fields = _claim_write_fields(inputs)
    project_id = inputs.get("linked_job")
    names = await _project_names()
    job_name = names.get(project_id) if project_id else None
    desc = (f"Claim opened on {job_name or 'a job'}. Protection {inputs.get('protection_option') or '—'}. "
            f"Amount claimed ${inputs.get('amount_claimed') or '—'}. Notice received "
            f"{inputs.get('notice_received_date') or '—'}.")
    # open the linked "Claim" nonconformance FIRST — if it fails, no orphan claim is created
    try:
        nc_id = await _open_claim_nc(project_id, desc, p.get("name"))
    except HTTPException:
        raise HTTPException(status_code=502,
                            detail="Couldn't open the linked nonconformance — the claim was not created. Try again.")
    fields[CLAIM_LINKED_NC_F] = [nc_id]
    created = await airtable_request("POST", CLAIMS_TABLE,
                                     json_body={"records": [{"fields": fields}], "typecast": True})
    claim_id = created["records"][0]["id"]
    rec = await airtable_request("GET", CLAIMS_TABLE, path=f"/{claim_id}",
                                 params={"returnFieldsByFieldId": "true"})
    await notify(None, "owner", "Claim opened",
                 f"A claim was opened on {job_name or 'a job'}. The 7-day form clock is running.",
                 "claim", {"claim_id": claim_id})
    return {"claim": _claim_out(rec, names, _et_date_today()), "nc_id": nc_id}


@api_router.patch("/quality/claims/{claim_id}")
async def update_claim(claim_id: str, payload: ClaimPayload, request: Request):
    p = await current_principal(request)
    if p["role"] not in ("owner", "quality"):
        raise HTTPException(status_code=403, detail="Only the owner and quality can edit claims.")
    inputs = dict(payload.inputs or {})
    inputs.pop("linked_nonconformance", None)
    _enforce_claim_owner_rules(inputs, p["role"])
    fields = _claim_write_fields(inputs)
    if not fields:
        raise HTTPException(status_code=422, detail="Nothing to update.")
    await airtable_request("PATCH", CLAIMS_TABLE,
                           json_body={"records": [{"id": claim_id, "fields": fields}], "typecast": True})
    rec = await airtable_request("GET", CLAIMS_TABLE, path=f"/{claim_id}",
                                 params={"returnFieldsByFieldId": "true"})
    names = await _project_names()
    return {"claim": _claim_out(rec, names, _et_date_today())}


# ------- Review capture (operational — Mongo project_reviews keyed by project id)

async def _mark_review_requested(project_id: str, source: str = "observed") -> None:
    existing = await mongo_db.project_reviews.find_one({"_id": project_id})
    if existing and existing.get("review_requested_at"):
        return
    await mongo_db.project_reviews.update_one(
        {"_id": project_id},
        {"$set": {"review_requested_at": now_iso(), "review_requested_source": source, "updated_at": now_iso()},
         "$setOnInsert": {"google_review_received": False}}, upsert=True)


async def _backfill_reviews(completed: List[Dict[str, Any]]) -> None:
    """A project can be flipped to Completed straight in the Airtable base, where the app never
    sees the edit — so its review_requested_at would stay empty and it would silently drop out of
    the review-capture denominator. Backfill any such job from its move date, flagged 'backfill'
    (vs 'observed') so the distinction survives."""
    ids = [pr["id"] for pr in completed]
    if not ids:
        return
    have = {d["_id"] for d in await mongo_db.project_reviews.find(
        {"_id": {"$in": ids}, "review_requested_at": {"$ne": None}}).to_list(len(ids) + 1)}
    for pr in completed:
        if pr["id"] in have:
            continue
        md = str((pr.get("fields") or {}).get(PROJECT_DATE_FIELD) or "")[:10] or None
        await mongo_db.project_reviews.update_one(
            {"_id": pr["id"]},
            {"$set": {"review_requested_at": (md + "T00:00:00+00:00") if md else now_iso(),
                      "review_requested_source": "backfill", "review_requested_move_date": md,
                      "updated_at": now_iso()},
             "$setOnInsert": {"google_review_received": False}}, upsert=True)
        logger.info("Backfilled review_requested_at for completed project %s (move %s)", pr["id"], md)


class GoogleReviewPayload(BaseModel):
    received: bool


@api_router.put("/quality/projects/{project_id}/google-review")
async def set_google_review(project_id: str, payload: GoogleReviewPayload, request: Request):
    p = await current_principal(request)
    if p["role"] not in ("owner", "quality"):
        raise HTTPException(status_code=403, detail="Only the owner and quality can log reviews.")
    await mongo_db.project_reviews.update_one(
        {"_id": project_id},
        {"$set": {"google_review_received": bool(payload.received),
                  "google_review_at": now_iso() if payload.received else None, "updated_at": now_iso()}},
        upsert=True)
    return {"project_id": project_id, "google_review_received": bool(payload.received)}


def _review_state(received: bool, requested_at) -> str:
    if received:
        return "received"
    return "waiting" if requested_at else "none"


def _review_flag(received: bool, days_since) -> Optional[str]:
    """Two asks then stop: text at day 2, again at day 6, then leave it alone. Nothing past
    day 8 is flagged — a list that keeps nagging about dead jobs stops getting read."""
    if received or days_since is None or days_since > 8 or days_since < 2:
        return None
    return "day6" if days_since >= 6 else "day2"


@api_router.get("/quality/reviews")
async def quality_reviews(request: Request):
    """Daily review chase — this month's completed jobs, oldest first, with the two-ask
    (day 2 / day 6) window flagged. Not for auditing; for knowing who to text next."""
    p = await current_principal(request)
    if p["role"] not in ("owner", "quality"):
        raise HTTPException(status_code=403, detail="Only the owner and quality can open review capture.")
    today = _et_date_today()
    month = _current_month()
    start, end = _month_bounds(month)
    projects = await _airtable_all(TABLES["projects"])
    completed = [pr for pr in projects
                 if (pr.get("fields") or {}).get(PROJECT_STATUS_FIELD) == PROJECT_COMPLETED_STATUS
                 and start <= str((pr.get("fields") or {}).get(PROJECT_DATE_FIELD) or "")[:10] < end]
    await _backfill_reviews(completed)
    ids = [pr["id"] for pr in completed]
    reviews = {d["_id"]: d for d in await mongo_db.project_reviews.find(
        {"_id": {"$in": ids}}).to_list(len(ids) + 1)} if ids else {}
    rows = []
    for pr in completed:
        f = pr.get("fields") or {}
        md = str(f.get(PROJECT_DATE_FIELD) or "")[:10] or None
        days_since = _days_since(md, today)
        rv = reviews.get(pr["id"]) or {}
        received = bool(rv.get("google_review_received"))
        requested_at = rv.get("review_requested_at")
        rows.append({
            "id": pr["id"],
            "name": f.get(PROJECT_NAME_FIELD) or "Untitled job",
            "move_date": md,
            "days_since": days_since,
            "review_requested_at": requested_at,
            "review_requested_source": rv.get("review_requested_source"),
            "google_review_received": received,
            "state": _review_state(received, requested_at),
            "flag": _review_flag(received, days_since),
        })
    rows.sort(key=lambda r: (r["days_since"] if r["days_since"] is not None else -1), reverse=True)
    to_chase = sum(1 for r in rows if r["flag"])
    return {"rows": rows, "month": month, "to_chase": to_chase}


# ------- Quote-accuracy helpers (per-rep gate + SOP 9 package-overrun alert)

def _pkg_label(v: Any) -> Optional[str]:
    s = str(v or "").strip().lower()
    if not s:
        return None
    if "studio" in s:
        return "Studio"
    for n in ("4", "3", "2", "1"):
        if s in (f"br{n}", f"{n}br", f"{n} br", f"{n}-br", f"{n}bd", f"{n} bedroom", f"{n}bedroom", n):
            return f"{n}BR"
        if s.startswith(f"br{n}") or s.startswith(f"{n}br") or s.startswith(f"{n} bed"):
            return f"{n}BR"
    return None


async def _pkg_by_lead() -> Dict[str, str]:
    """lead_id -> package label, from the most recent saved scope that names a package."""
    scopes = await mongo_db.lead_scopes.find({"lead_id": {"$ne": None}}).sort("created_at", -1).to_list(3000)
    out: Dict[str, str] = {}
    for s in scopes:
        lid = s.get("lead_id")
        if not lid or lid in out:
            continue
        inp = s.get("inputs") or {}
        label = _pkg_label(inp.get("pkg") or inp.get("package") or inp.get("homeSize") or inp.get("beds"))
        if label:
            out[lid] = label
    return out


def _detect_package_overruns(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """SOP 9: three consecutive completed jobs of the same package size that ran over the
    estimated hours point at the package DEFAULTS being wrong, not a slow crew."""
    by_pkg: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        if r.get("package") and r.get("move_date") and r.get("hours_variance") is not None:
            by_pkg.setdefault(r["package"], []).append(r)
    alerts = []
    for pkg, items in by_pkg.items():
        items.sort(key=lambda r: r["move_date"])
        run: List[Dict[str, Any]] = []
        best = None
        for r in items:
            if r["hours_variance"] > 0:
                run.append(r)
                if len(run) >= 3:
                    best = run[-3:]
            else:
                run = []
        if best:
            alerts.append({
                "package": pkg,
                "message": (f"Three {pkg} jobs in a row ran over the estimated hours. Per SOP 9 that points at "
                            f"the {pkg} package defaults being set too low — not the crew being slow. Review the "
                            f"crew and hours defaults for {pkg} in pricing settings."),
                "jobs": [{"id": r["id"], "name": r["name"], "move_date": r["move_date"],
                          "hours_variance": r["hours_variance"]} for r in best],
            })
    return alerts


# ------- Quality KPI dashboard + monthly review

def _current_month() -> str:
    return datetime.now(_ET).strftime("%Y-%m")


def _prev_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    return f"{y - 1:04d}-12" if m == 1 else f"{y:04d}-{m - 1:02d}"


def _month_bounds(month: str) -> Tuple[str, str]:
    y, m = int(month[:4]), int(month[5:7])
    start = f"{y:04d}-{m:02d}-01"
    end = f"{y + 1:04d}-01-01" if m == 12 else f"{y:04d}-{m + 1:02d}-01"
    return start, end   # half-open [start, end)


def _pct(num: int, den: int) -> Optional[float]:
    return round(100.0 * num / den, 1) if den else None


def _pct_state(v: Optional[float], tgt: float, at_least: bool = True) -> Optional[str]:
    if v is None:
        return None
    return "green" if (v >= tgt if at_least else v <= tgt) else "red"


async def _on_time_rate(start: str, end: str) -> Tuple[int, int]:
    """(on-time, total) over assignments in [start,end) with a scheduled arrival and >=1 clock-in."""
    assignments = await mongo_db.assignments.find(
        {"job_date": {"$gte": start, "$lt": end}, "arrival_time": {"$nin": [None, ""]}}).to_list(3000)
    on_time = total = 0
    for a in assignments:
        entries = await mongo_db.time_entries.find({"assignment_id": a["_id"]}).to_list(50)
        ins = [e["clock_in"]["at"] for e in entries if e.get("clock_in")]
        if not ins:
            continue
        try:
            hh, mm = [int(x) for x in str(a["arrival_time"]).split(":")[:2]]
            sched = datetime.fromisoformat(f'{str(a["job_date"])[:10]}T00:00:00').replace(
                hour=hh, minute=mm, tzinfo=_ET)
            earliest = min(datetime.fromisoformat(i).astimezone(_ET) for i in ins)
        except (ValueError, TypeError, KeyError, IndexError):
            continue
        total += 1
        if earliest <= sched + timedelta(minutes=30):
            on_time += 1
    return on_time, total


def _metric(key, label, value, target, target_display, state, num, den, unit="pct", is_risk=False):
    return {"key": key, "label": label, "value": value, "target": target, "target_display": target_display,
            "state": state, "numerator": num, "denominator": den, "unit": unit, "is_risk": is_risk}


async def _quality_metrics(month: str) -> Dict[str, Any]:
    start, end = _month_bounds(month)
    projects = await _airtable_all(TABLES["projects"])
    ncs = await _airtable_all(TABLES["nonconformances"])
    claims = await _airtable_all(CLAIMS_TABLE)

    def in_month(pr):
        md = str((pr.get("fields") or {}).get(PROJECT_DATE_FIELD) or "")[:10]
        return bool(md) and start <= md < end

    completed_all = [pr for pr in projects
                     if (pr.get("fields") or {}).get(PROJECT_STATUS_FIELD) == PROJECT_COMPLETED_STATUS]
    await _backfill_reviews(completed_all)
    completed = [pr for pr in completed_all if in_month(pr)]
    completed_ids = [pr["id"] for pr in completed]

    ncs_by_job: Dict[str, List[Dict[str, Any]]] = {}
    for nc in ncs:
        for jid in ((nc.get("fields") or {}).get(NC_LINKED_JOB_F) or []):
            ncs_by_job.setdefault(jid, []).append(nc.get("fields") or {})

    # 1) review capture — completed jobs this month with google_review_received
    reviews = await mongo_db.project_reviews.find(
        {"_id": {"$in": completed_ids}}).to_list(len(completed_ids) + 1) if completed_ids else []
    got_review = sum(1 for r in reviews if r.get("google_review_received"))
    review_rate = _pct(got_review, len(completed))

    # 2) quote variance — mean hours over/under, last 20 completed jobs (not month-bound)
    completed_sorted = sorted(
        completed_all, key=lambda pr: str((pr.get("fields") or {}).get(PROJECT_DATE_FIELD) or ""), reverse=True)
    last20 = completed_sorted[:20]
    actual = await _actual_hours_by_project(last20)
    hv = []
    for pr in last20:
        est = _num((pr.get("fields") or {}).get(PROJECT_HOURS_FIELD))
        act = actual.get(pr["id"])
        if est is not None and act is not None:
            hv.append(act - est)
    quote_var = round(sum(hv) / len(hv), 2) if hv else None

    # 3) claim rate — claims with notice this month, per 100 completed jobs this month
    claims_in_month = sum(
        1 for c in claims
        if start <= str((c.get("fields") or {}).get(CLAIM_NOTICE_DATE_F) or "")[:10] < end)
    claim_rate = round(100.0 * claims_in_month / len(completed), 2) if completed else None

    # 4) on-time start
    on_time, on_time_total = await _on_time_rate(start, end)
    on_time_rate = _pct(on_time, on_time_total)

    # 5) document compliance (11 critical gates pass, override = fail) — the risk measure
    doc_ok = 0
    if completed:
        ctx = await _compliance_context(completed)
        overridden = {d["_id"] for d in await mongo_db.job_compliance.find(
            {"_id": {"$in": completed_ids}, "override": {"$ne": None}}).to_list(len(completed_ids) + 1)}
        for pr in completed:
            gates = evaluate_gates(pr, ctx)
            if all(g["passed"] for g in gates if g["key"] in CRITICAL_GATE_KEYS) and pr["id"] not in overridden:
                doc_ok += 1
    doc_rate = _pct(doc_ok, len(completed))

    # 6) first-time-right — completed jobs with zero nonconformances
    ftr = sum(1 for pr in completed if not ncs_by_job.get(pr["id"]))
    ftr_rate = _pct(ftr, len(completed))

    metrics = [
        _metric("review_capture", "Review capture rate", review_rate, 60, "≥ 60%",
                _pct_state(review_rate, 60), got_review, len(completed)),
        _metric("quote_variance", "Quote variance (last 20 jobs)", quote_var, 0.5, "± 0.5 hr",
                ("green" if quote_var is not None and abs(quote_var) <= 0.5 else
                 ("red" if quote_var is not None else None)),
                len(hv), len(last20), unit="hours"),
        _metric("claim_rate", "Claim rate (per 100 jobs)", claim_rate, 2, "< 2",
                ("green" if claim_rate is not None and claim_rate < 2 else
                 ("red" if claim_rate is not None else None)),
                claims_in_month, len(completed), unit="rate"),
        _metric("on_time_start", "On-time start", on_time_rate, 90, "≥ 90%",
                _pct_state(on_time_rate, 90), on_time, on_time_total),
        _metric("first_time_right", "First-time-right", ftr_rate, 90, "≥ 90%",
                _pct_state(ftr_rate, 90), ftr, len(completed)),
    ]
    doc_metric = _metric("document_compliance", "Document compliance", doc_rate, 100, "100% — no exceptions",
                         _pct_state(doc_rate, 100), doc_ok, len(completed), is_risk=True)
    return {"month": month, "metrics": metrics, "document_compliance": doc_metric,
            "completed_jobs": len(completed)}


async def _overdue_audits(projects: List[Dict[str, Any]], audits: List[Dict[str, Any]], today) -> List[Dict[str, Any]]:
    audited: set = set()
    for a in audits:
        for jid in ((a.get("fields") or {}).get(JA_LINKED_JOB_F) or []):
            audited.add(jid)
    out = []
    for pr in projects:
        f = pr.get("fields") or {}
        if f.get(PROJECT_STATUS_FIELD) != PROJECT_COMPLETED_STATUS or pr["id"] in audited:
            continue
        md = _c_date(f.get(PROJECT_DATE_FIELD))
        if md and today > md + timedelta(days=7):
            due = md + timedelta(days=7)
            out.append({"id": pr["id"], "name": f.get(PROJECT_NAME_FIELD) or "Untitled job",
                        "due": due.isoformat(), "days_over": (today - due).days})
    out.sort(key=lambda a: -a["days_over"])
    return out


async def _needs_you_now(today) -> Dict[str, Any]:
    names = await _project_names()
    claim_recs = await _airtable_all(CLAIMS_TABLE)
    claim_alerts = []
    for r in claim_recs:
        c = _claim_out(r, names, today)
        u = c["urgency"]
        if u["days"] is not None and u["days"] <= 14:
            claim_alerts.append({"id": c["id"], "claim_number": c["claim_number"], "job": c["linked_job_name"],
                                 "which": u["which"], "deadline": u["deadline"], "days": u["days"], "state": u["state"]})
    claim_alerts.sort(key=lambda a: a["days"])
    projects = await _airtable_all(TABLES["projects"])
    audits = await _airtable_all(TABLES["job_audits"])
    overdue = await _overdue_audits(projects, audits, today)
    ncs = await _airtable_all(TABLES["nonconformances"])
    liab = []
    for nc in ncs:
        f = nc.get("fields") or {}
        if f.get(NC_SEVERITY_F) == "Liability risk" and (f.get(NC_STATUS_F) or "Open") != "Closed":
            liab.append({"id": nc["id"], "number": f.get(NC_NUMBER_F), "type": f.get(NC_TYPE_F),
                         "status": f.get(NC_STATUS_F) or "Open", "what": (f.get(NC_WHAT_F) or "")[:140]})
    return {"claims": claim_alerts, "overdue_audits": overdue, "liability_ncs": liab,
            "count": len(claim_alerts) + len(overdue) + len(liab)}


@api_router.get("/quality/dashboard")
async def quality_dashboard(request: Request):
    p = await current_principal(request)
    if p["role"] not in ("owner", "quality"):
        raise HTTPException(status_code=403, detail="Only the owner and quality can open the dashboard.")
    data = await _quality_metrics(_current_month())
    data["needs_you_now"] = await _needs_you_now(_et_date_today())
    data["is_current_month"] = True
    return data


async def _snapshot_month(month: str, force: bool = False) -> Dict[str, Any]:
    existing = await mongo_db.monthly_metrics.find_one({"_id": month})
    if existing and not force:
        return existing
    data = await _quality_metrics(month)
    doc = {"_id": month, "month": month, "metrics": data["metrics"],
           "document_compliance": data["document_compliance"], "completed_jobs": data["completed_jobs"],
           "frozen_at": now_iso()}
    await mongo_db.monthly_metrics.update_one({"_id": month}, {"$set": doc}, upsert=True)
    return doc


@api_router.get("/quality/monthly")
async def quality_monthly(request: Request, month: Optional[str] = None):
    p = await current_principal(request)
    if p["role"] not in ("owner", "quality"):
        raise HTTPException(status_code=403, detail="Only the owner and quality can open the monthly review.")
    month = month or _current_month()
    today = _et_date_today()
    is_current = month >= _current_month()
    prev = _prev_month(month)
    if is_current:
        # the live in-progress view — clearly not yet final; never frozen
        data = await _quality_metrics(month)
        metrics, doc_metric, completed_jobs, frozen = (
            data["metrics"], data["document_compliance"], data["completed_jobs"], False)
    else:
        # a closed period reads ONLY the frozen snapshot — never recompute history. A back-filled
        # number that looks identical to a frozen one is worse than a gap, so show the gap.
        snap = await mongo_db.monthly_metrics.find_one({"_id": month})
        if not snap:
            return {"month": month, "no_snapshot": True, "frozen": False, "is_current_month": False,
                    "previous_month": prev, "frozen_at": None}
        metrics, doc_metric, completed_jobs, frozen = (
            snap["metrics"], snap["document_compliance"], snap.get("completed_jobs"), True)

    # month-over-month movement reads the PREVIOUS month's frozen snapshot only (never computed).
    prev_snap = await mongo_db.monthly_metrics.find_one({"_id": prev})
    prev_map: Dict[str, Any] = {}
    if prev_snap:
        for m in prev_snap.get("metrics", []):
            prev_map[m["key"]] = m.get("value")
        pdoc = prev_snap.get("document_compliance") or {}
        if pdoc.get("key"):
            prev_map[pdoc["key"]] = pdoc.get("value")

    def _with_movement(m):
        pv = prev_map.get(m["key"])
        out = dict(m)
        out["prev_value"] = pv
        out["movement"] = (round(m["value"] - pv, 2) if (m.get("value") is not None and pv is not None) else None)
        return out

    metrics = [_with_movement(m) for m in metrics]
    doc_metric = _with_movement(doc_metric)

    ncs = await _airtable_all(TABLES["nonconformances"])
    open_ncs = [{"id": nc["id"], "number": (nc.get("fields") or {}).get(NC_NUMBER_F),
                 "type": (nc.get("fields") or {}).get(NC_TYPE_F),
                 "severity": (nc.get("fields") or {}).get(NC_SEVERITY_F),
                 "status": (nc.get("fields") or {}).get(NC_STATUS_F) or "Open",
                 "what": ((nc.get("fields") or {}).get(NC_WHAT_F) or "")[:160],
                 "raised": (nc.get("fields") or {}).get(NC_RAISED_DATE_F)}
                for nc in ncs if ((nc.get("fields") or {}).get(NC_STATUS_F) or "Open") != "Closed"]
    open_ncs.sort(key=lambda n: (GATE_SEVERITY_RANK.get(n["severity"], 9), n["raised"] or ""))
    names = await _project_names()
    claim_recs = await _airtable_all(CLAIMS_TABLE)
    near_claims = [c for c in (_claim_out(r, names, today) for r in claim_recs)
                   if c["urgency"]["days"] is not None and c["urgency"]["days"] <= 14]
    near_claims.sort(key=lambda c: c["urgency"]["days"])
    projects = await _airtable_all(TABLES["projects"])
    audits = await _airtable_all(TABLES["job_audits"])
    overdue = await _overdue_audits(projects, audits, today)
    soon = today + timedelta(days=60)
    users = await mongo_db.users.find({"crew_docs_expiry": {"$nin": [None, ""]}}).to_list(500)
    expiring = []
    for u in users:
        exp = _c_date(u.get("crew_docs_expiry"))
        if exp and exp <= soon:
            expiring.append({"user_id": u["_id"], "name": u.get("name") or "Crew",
                             "expires": str(u.get("crew_docs_expiry"))[:10], "days": (exp - today).days,
                             "expired": exp < today})
    expiring.sort(key=lambda e: e["days"])
    return {"month": month, "no_snapshot": False, "frozen": frozen, "is_current_month": is_current,
            "previous_month": prev, "has_previous": bool(prev_snap),
            "frozen_at": (snap.get("frozen_at") if not is_current else None),
            "metrics": metrics, "document_compliance": doc_metric,
            "completed_jobs": completed_jobs, "open_nonconformances": open_ncs,
            "claims_near_deadline": near_claims, "overdue_audits": overdue, "crew_docs_expiring": expiring}


@public_router.post("/cron/monthly-metrics-snapshot")
async def cron_monthly_metrics(request: Request):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if not secret or not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    target = _prev_month(_current_month())

    async def _work():
        try:
            await _snapshot_month(target, force=False)
            logger.info("Monthly metrics snapshot frozen for %s", target)
        except Exception as exc:
            logger.warning("Monthly metrics snapshot failed for %s: %s", target, exc)

    asyncio.create_task(_work())
    return {"ok": True, "month": target}


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


# ------- Job Management (owner + role-aware read views over the canonical Project record)
# The Airtable Project is the ONE lifecycle record. This layer briefly caches the project
# list (shared across roles so search/filtering never hits Airtable per keystroke) and merges
# the linked Mongo job (payment / customer page / crew) + assignments (timeline) by
# project_record_id, else the linked lead. Money fields are stripped SERVER-SIDE per role.

JOB_MGMT_ROLES = ("owner", "sales", "employee", "quality")
_projects_list_cache: Dict[str, Any] = {"data": None, "at": 0.0}
_PROJECTS_CACHE_TTL = 30.0


async def _require_job_mgmt(request: Request) -> Dict[str, Any]:
    p = await current_principal(request)
    if p["role"] not in JOB_MGMT_ROLES:
        raise HTTPException(status_code=403, detail="Your role can't open Jobs.")
    return p


async def _cached_projects(force: bool = False) -> List[Dict[str, Any]]:
    """Raw Airtable project records, cached briefly and shared across roles/requests so the
    list + client-side search/filtering never triggers a per-keystroke Airtable call."""
    now = time.monotonic()
    cached = _projects_list_cache["data"]
    if not force and cached is not None and now - _projects_list_cache["at"] < _PROJECTS_CACHE_TTL:
        return cached
    records = await _airtable_all(TABLES["projects"])
    _projects_list_cache["data"] = records
    _projects_list_cache["at"] = now
    return records


def _compliance_status(comp: Optional[Dict[str, Any]]) -> str:
    """One word for the list chip/filter, from a cached job_compliance doc (never re-evaluates)."""
    if not comp:
        return "unknown"
    if comp.get("override"):
        return "overridden"
    summary = comp.get("summary") or {}
    if summary.get("all_green"):
        return "compliant"
    if summary.get("worst_severity") in ("Liability risk", "Regulatory", "Major"):
        return "failed"
    if summary.get("failing"):
        return "warning"
    return "compliant"


def _job_payment_summary(job: Optional[Dict[str, Any]], money: bool) -> Dict[str, Any]:
    if not job:
        return {"deposit": "unknown", "full": "unknown"}
    out = {
        "deposit": (job.get("deposit_paid") or {}).get("status") or "unpaid",
        "full": (job.get("paid_in_full") or {}).get("status") or "unpaid",
    }
    if money:
        out["quote_total"] = job.get("quote_total")
        out["deposit_amount"] = (job.get("deposit_paid") or {}).get("amount")
        out["paid_amount"] = (job.get("paid_in_full") or {}).get("amount")
    return out


async def _jobs_index() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Mongo jobs keyed by their linked Airtable project record id and by linked lead id."""
    by_recid: Dict[str, Any] = {}
    by_lead: Dict[str, Any] = {}
    for j in await mongo_db.jobs.find({}).to_list(1000):
        if j.get("project_record_id"):
            by_recid[j["project_record_id"]] = j
        if j.get("lead_id"):
            by_lead[j["lead_id"]] = j
    return by_recid, by_lead


def _match_job(project: Dict[str, Any], by_recid: Dict[str, Any], by_lead: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    job = by_recid.get(project["id"])
    if job:
        return job
    for lid in ((project.get("fields") or {}).get(PROJECT_LEAD_LINK_FIELD) or []):
        if lid in by_lead:
            return by_lead[lid]
    return None


def _job_customer_block(project_fields: Dict[str, Any], job: Optional[Dict[str, Any]], show_contact: bool) -> Dict[str, Any]:
    cust = (job or {}).get("customer") or {}
    block = {"name": cust.get("name") or project_fields.get(PROJECT_NAME_FIELD) or ""}
    if show_contact:
        block["phone"] = cust.get("phone") or ""
        block["email"] = cust.get("email") or ""
    return block


# Owner-editable job fields -> canonical Airtable Projects field ids (no duplicate records; the
# Projects record stays the single source of truth). Every change is written to job_audit_log.
JOB_EDIT_FIELDS: Dict[str, Dict[str, Any]] = {
    "status":        {"field": PROJECT_STATUS_FIELD, "label": "Status", "type": "select",
                      "options": ["Pending Deposit", "Scheduled", "In Progress", "Completed", "Cancelled"],
                      "financial": False},
    "move_date":     {"field": PROJECT_DATE_FIELD, "label": "Move date", "type": "date", "financial": False},
    "crew_size":     {"field": PROJECT_CREW_FIELD, "label": "Crew size", "type": "number", "financial": False},
    "est_hours":     {"field": PROJECT_HOURS_FIELD, "label": "Est. hours", "type": "number", "financial": False},
    "truck":         {"field": PROJECT_TRUCK_FIELD, "label": "Truck", "type": "text", "financial": False},
    "from_addr":     {"field": PROJECT_FROM_FIELD, "label": "From address", "type": "text", "financial": False},
    "to_addr":       {"field": PROJECT_TO_FIELD, "label": "To address", "type": "text", "financial": False},
    "quote":         {"field": PROJECT_QUOTE_FIELD, "label": "Quote", "type": "currency", "financial": True},
    "final_revenue": {"field": PROJECT_REVENUE_FIELD, "label": "Final revenue", "type": "currency", "financial": True},
}


def _coerce_edit_value(spec: Dict[str, Any], raw: Any) -> Any:
    t = spec["type"]
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if t in ("number", "currency"):
        try:
            return float(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail=f"{spec['label']} must be a number.")
    if t == "select":
        if raw not in spec.get("options", []):
            raise HTTPException(status_code=422,
                                detail=f"{spec['label']} must be one of: {', '.join(spec['options'])}.")
        return raw
    if t == "date":
        return str(raw)[:10]
    return str(raw).strip()


def _norm_for_compare(spec: Dict[str, Any], val: Any) -> Any:
    if val in (None, ""):
        return None
    if spec["type"] in ("number", "currency"):
        try:
            return float(val)
        except (TypeError, ValueError):
            return None
    if spec["type"] == "date":
        return str(val)[:10]
    return str(val).strip()


async def _job_history(project_id: str, money: bool) -> List[Dict[str, Any]]:
    docs = await mongo_db.job_audit_log.find({"project_id": project_id}).sort("at", -1).to_list(500)
    out: List[Dict[str, Any]] = []
    for d in docs:
        mask = bool(d.get("financial")) and not money
        out.append({
            "id": d["_id"], "field_key": d.get("field_key"), "label": d.get("label"),
            "old": ("•••" if mask else d.get("old")), "new": ("•••" if mask else d.get("new")),
            "by": d.get("by"), "at": d.get("at"), "note": d.get("note"),
            "financial": bool(d.get("financial")),
        })
    return out


@api_router.get("/job-mgmt/list")
async def job_mgmt_list(request: Request, refresh: int = 0) -> Dict[str, Any]:
    p = await _require_job_mgmt(request)
    role = p["role"]
    money = role == "owner"
    show_contact = role in ("owner", "sales")
    projects = await _cached_projects(force=bool(refresh))
    by_recid, by_lead = await _jobs_index()
    comp_docs = {c["_id"]: c for c in await mongo_db.job_compliance.find({}).to_list(2000)}
    out: List[Dict[str, Any]] = []
    for pr in projects:
        rec = filter_record(pr, role, "projects")
        f = rec.get("fields") or {}
        job = _match_job(pr, by_recid, by_lead)
        if job:
            await _mirror_gates(job, pr.get("fields") or {})
        crew = (job or {}).get("crew") or []
        out.append({
            "id": pr["id"],
            "fields": rec.get("fields"),
            "internal": rec.get("internal"),
            "mgmt": {
                "invoice_number": (job or {}).get("invoice_number"),
                "job_id": (job or {}).get("_id"),
                "crew": [{"name": c.get("name"), "position": c.get("position")} for c in crew],
                "crew_count": len(crew),
                "truck_name": (job or {}).get("truck_name") or f.get(PROJECT_TRUCK_FIELD),
                "payment": _job_payment_summary(job, money),
                "has_portal": bool(((job or {}).get("tracking") or {}).get("token")),
                "portal_review": (job or {}).get("portal_review"),
                "compliance": _compliance_status(comp_docs.get(pr["id"])),
                "paperwork_alert": _paperwork_alert_card(job) if job else None,
                "customer": _job_customer_block(f, job, show_contact),
            },
        })
    return {"jobs": out, "count": len(out), "can_see_money": money,
            "cached_at": _projects_list_cache["at"]}


async def _job_timeline_events(project_id: str) -> List[Dict[str, Any]]:
    """Compact merged timeline across every assignment tied to this project (no per-role RBAC
    barrier — the Job Management gate already applies)."""
    assignments = await mongo_db.assignments.find({"project_id": project_id}).to_list(50)
    events: List[Dict[str, Any]] = []
    for a in assignments:
        aid = a["_id"]
        if a.get("created_at"):
            events.append({"at": a["created_at"], "kind": "created", "title": "Job put on the schedule", "by": ""})
        for ev in a.get("status_history", []):
            events.append({"at": ev.get("at"), "kind": "status",
                           "title": f"Status: {ev.get('status')}", "by": ev.get("by", "")})
        for d in await mongo_db.job_events.find({"assignment_id": aid}).to_list(200):
            events.append({"at": d.get("at"), "kind": d.get("kind", "event"),
                           "title": d.get("title", ""), "by": d.get("by", ""), "detail": d.get("detail", "")})
        for e in await mongo_db.time_entries.find({"assignment_id": aid}).to_list(100):
            if e.get("clock_in"):
                events.append({"at": e["clock_in"]["at"], "kind": "clock",
                               "title": f"{e.get('user_name')} clocked in", "by": e.get("user_name", "")})
            if e.get("clock_out"):
                hrs = e.get("hours")
                events.append({"at": e["clock_out"]["at"], "kind": "clock",
                               "title": f"{e.get('user_name')} clocked out" + (f" — {hrs:.1f}h" if hrs else ""),
                               "by": e.get("user_name", "")})
        for ph in await mongo_db.job_photos.find({"assignment_id": aid}).to_list(100):
            events.append({"at": ph.get("created_at"), "kind": "photo",
                           "title": f"Photo added by {ph.get('user_name')}", "by": ph.get("user_name", "")})
    events = [e for e in events if e.get("at")]
    events.sort(key=lambda e: e["at"], reverse=True)
    return events[:200]


def _actual_onsite_for_assignments(assignments: List[Dict[str, Any]],
                                   entries_by_a: Dict[str, List[Dict[str, Any]]]) -> Optional[float]:
    ins, outs, open_left = [], [], 0
    for a in assignments:
        for e in entries_by_a.get(a["_id"], []):
            if e.get("clock_in"):
                ins.append(e["clock_in"]["at"])
            if e.get("clock_out"):
                outs.append(e["clock_out"]["at"])
            else:
                open_left += 1
    if not ins or not outs or open_left:
        return None
    try:
        span = (datetime.fromisoformat(max(outs)) - datetime.fromisoformat(min(ins))).total_seconds() / 3600
        return round(max(0.0, span), 2)
    except (ValueError, TypeError):
        return None


async def _job_quality_links(project_id: str, name: str) -> Dict[str, Any]:
    """Claims / nonconformances / audits / review tied to this project (Airtable-backed).
    Best-effort; returns empty lists if Airtable is unavailable."""
    out: Dict[str, Any] = {"claims": [], "nonconformances": [], "audits": [], "review": None}
    try:
        ncs = await _airtable_all(TABLES["nonconformances"])
        out["nonconformances"] = [{
            "id": r["id"], "number": (r.get("fields") or {}).get(NC_NUMBER_F),
            "type": (r.get("fields") or {}).get(NC_TYPE_F),
            "severity": (r.get("fields") or {}).get(NC_SEVERITY_F),
            "status": (r.get("fields") or {}).get(NC_STATUS_F),
            "what": (r.get("fields") or {}).get(NC_WHAT_F),
        } for r in ncs if project_id in ((r.get("fields") or {}).get(NC_LINKED_JOB_F) or [])]
    except HTTPException:
        pass
    try:
        audits = await _airtable_all(TABLES["job_audits"])
        out["audits"] = [{
            "id": r["id"], "number": (r.get("fields") or {}).get(JA_NUMBER_F),
            "result": (r.get("fields") or {}).get(JA_RESULT_F),
            "completed": (r.get("fields") or {}).get(JA_COMPLETED_DATE_F),
            "findings": (r.get("fields") or {}).get(JA_FINDINGS_F),
        } for r in audits if project_id in ((r.get("fields") or {}).get(JA_LINKED_JOB_F) or [])]
    except HTTPException:
        pass
    try:
        claims = await _airtable_all(CLAIMS_TABLE)
        out["claims"] = [{
            "id": r["id"], "number": (r.get("fields") or {}).get(CLAIM_NUMBER_F),
            "status": (r.get("fields") or {}).get(CLAIM_STATUS_F),
            "notice_date": (r.get("fields") or {}).get(CLAIM_NOTICE_DATE_F),
        } for r in claims if project_id in ((r.get("fields") or {}).get(CLAIM_LINKED_JOB_F) or [])]
    except HTTPException:
        pass
    rv = await mongo_db.project_reviews.find_one({"_id": project_id})
    if rv:
        out["review"] = {"state": rv.get("state"), "rating": rv.get("rating"),
                         "google_review_received": rv.get("google_review_received")}
    return out


@api_router.get("/job-mgmt/{project_id}")
async def job_mgmt_detail(project_id: str, request: Request) -> Dict[str, Any]:
    p = await _require_job_mgmt(request)
    role = p["role"]
    money = role == "owner"
    show_contact = role in ("owner", "sales")
    try:
        record = await _fetch_project(project_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="No such job.")
        raise
    rec = filter_record(record, role, "projects")
    f = record.get("fields") or {}
    by_recid, by_lead = await _jobs_index()
    job = _match_job(record, by_recid, by_lead)
    if job:
        await _mirror_gates(job, f)

    portal = None
    if job:
        base = await _portal_base()
        token = (job.get("tracking") or {}).get("token")
        tr = job.get("tracking") or {}
        uploads = await mongo_db.portal_uploads.find({"job_id": job["_id"]}).sort("created_at", -1).to_list(50)
        tips = await mongo_db.portal_tips.find({"job_id": job["_id"]}).sort("created_at", -1).to_list(20)
        portal = {
            "job_id": job["_id"],
            "invoice_number": job.get("invoice_number"),
            "token": token,
            "link": f"{base}/track/{token}" if base and token else None,
            "sends": job.get("portal_sends") or [],
            "details": job.get("portal_details") or {},
            "review": job.get("portal_review"),
            "onway_sms_sent": bool(tr.get("onway_sms_sent") or tr.get("sms_sent")),
            "uploads": [{"id": u["_id"], "filename": u.get("filename"),
                         "content_type": u.get("content_type"), "kind": u.get("kind"),
                         "created_at": u.get("created_at")} for u in uploads],
            "tips": [{"name": t.get("tipper_name"),
                      "amount": (t.get("amount") if money else None),
                      "created_at": t.get("created_at"), "status": t.get("status")} for t in tips],
            "payment": _job_payment_summary(job, money),
        }

    assignments = await mongo_db.assignments.find({"project_id": project_id}).to_list(50)
    entries = await mongo_db.time_entries.find(
        {"assignment_id": {"$in": [a["_id"] for a in assignments]}}).to_list(500) if assignments else []
    entries_by_a: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        entries_by_a.setdefault(e.get("assignment_id"), []).append(e)
    crew_clock = []
    for a in assignments:
        for e in entries_by_a.get(a["_id"], []):
            crew_clock.append({
                "name": e.get("user_name"),
                "clock_in": (e.get("clock_in") or {}).get("at"),
                "clock_out": (e.get("clock_out") or {}).get("at"),
                "hours": e.get("hours"),
                "position": next((c.get("position") for c in a.get("crew", [])
                                  if c.get("user_id") == e.get("user_id")), None),
            })
    assignment_summaries = [{
        "id": a["_id"], "job_name": a.get("job_name"),
        "job_date": a.get("job_date"), "arrival_time": a.get("arrival_time"),
        "exec_status": a.get("exec_status") or a.get("status"),
        "truck_name": a.get("truck_name"), "truck_id": a.get("truck_id"),
        "crew": [{"name": c.get("name"), "position": c.get("position"), "user_id": c.get("user_id")} for c in a.get("crew", [])],
        "crew_lead": _crew_lead_detail_out(a),
    } for a in assignments]

    scope = None
    if job and job.get("lead_id"):
        tier = await scope_tier_for(p)
        if tier:
            sdoc = await mongo_db.lead_scopes.find({"lead_id": job["lead_id"]}).sort("created_at", -1).to_list(1)
            if sdoc:
                scope = redact_scope_doc(sdoc[0], tier)

    quality = None
    if role in ("owner", "sales", "quality"):
        quality = await _job_quality_links(project_id, str(f.get(PROJECT_NAME_FIELD) or ""))

    outcome = None
    if role in ("owner", "quality") and assignments:
        job_key = _job_key_for_assignment(assignments[0])
        odoc = await mongo_db.job_outcomes.find_one({"_id": job_key})
        if not odoc:
            odoc = await build_outcome(job_key, "job_detail_view", p.get("name", ""))
        outcome = _outcome_out(odoc, role)

    return {
        "id": project_id,
        "fields": rec.get("fields"),
        "internal": rec.get("internal"),
        "customer": _job_customer_block(f, job, show_contact),
        "portal": portal,
        "assignments": assignment_summaries,
        "crew_clock": crew_clock,
        "actual_onsite_hours": _actual_onsite_for_assignments(assignments, entries_by_a),
        "outcome": outcome,
        "timeline": await _job_timeline_events(project_id),
        "scope": scope,
        "quality": quality,
        "paperwork_ack": (await _paperwork_ack_summary(job)) if job else None,
        "move_confirmation": (_move_confirmation_state(job) if job else None),
        "history": await _job_history(project_id, money),
        "can_edit": role == "owner",
        "can_see_money": money,
        "can_see_quality": role in ("owner", "sales", "quality"),
        "can_see_compliance": role in ("owner", "sales", "quality"),
    }


class JobEditPayload(BaseModel):
    changes: Dict[str, Any]
    note: Optional[str] = None


@api_router.patch("/job-mgmt/{project_id}")
async def job_mgmt_update(project_id: str, payload: JobEditPayload, request: Request) -> Dict[str, Any]:
    p = await current_principal(request)
    if p["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can edit job records.")
    changes = payload.changes or {}
    unknown = [k for k in changes if k not in JOB_EDIT_FIELDS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"These fields can't be edited: {', '.join(unknown)}.")
    if not changes:
        raise HTTPException(status_code=422, detail="No changes provided.")

    try:
        record = await _fetch_project(project_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="No such job.")
        raise
    cur = record.get("fields") or {}

    air_fields: Dict[str, Any] = {}
    diffs: List[Tuple[str, Dict[str, Any], Any, Any]] = []
    for key, raw in changes.items():
        spec = JOB_EDIT_FIELDS[key]
        new_val = _coerce_edit_value(spec, raw)
        old_val = _norm_for_compare(spec, cur.get(spec["field"]))
        if new_val == old_val:
            continue
        air_fields[spec["field"]] = new_val
        diffs.append((key, spec, old_val, new_val))

    if not diffs:
        return {"updated": False, "count": 0, "message": "Nothing changed.",
                "history": await _job_history(project_id, True)}

    # Canonical write — the read-only staging token intentionally returns 403 here, so no audit is logged.
    await airtable_request("PATCH", TABLES["projects"],
                           json_body={"records": [{"id": project_id, "fields": air_fields}], "typecast": True})

    at = now_iso()
    by = p.get("name") or p.get("email") or "owner"
    note = (payload.note or "").strip() or None
    entries = [{
        "_id": str(uuid4()), "project_id": project_id, "field_key": key, "label": spec["label"],
        "old": old_val, "new": new_val, "financial": spec["financial"],
        "by": by, "by_id": p.get("user_id"), "note": note, "at": at,
    } for key, spec, old_val, new_val in diffs]
    await mongo_db.job_audit_log.insert_many(entries)

    if air_fields.get(PROJECT_STATUS_FIELD) == PROJECT_COMPLETED_STATUS:
        await _mark_review_requested(project_id, source="observed")
    if PROJECT_DATE_FIELD in air_fields:   # move date changed → mirror to the linked job + re-check paperwork alert
        linked = await mongo_db.jobs.find_one({"project_record_id": project_id})
        if linked:
            await mongo_db.jobs.update_one({"_id": linked["_id"]}, {"$set": {"job_date": air_fields[PROJECT_DATE_FIELD]}})
            linked["job_date"] = air_fields[PROJECT_DATE_FIELD]
            await _check_owner_paperwork_alert(linked, "date_change")
    _projects_list_cache["at"] = 0.0  # force the list to refresh from Airtable on next load

    return {"updated": True, "count": len(diffs), "history": await _job_history(project_id, True)}


@api_router.get("/job-mgmt/{project_id}/history")
async def job_mgmt_history(project_id: str, request: Request) -> Dict[str, Any]:
    p = await _require_job_mgmt(request)
    return {"history": await _job_history(project_id, p["role"] == "owner"),
            "can_edit": p["role"] == "owner"}


@api_router.post("/job-mgmt/{project_id}/record-delivered")
async def job_mgmt_record_delivered(project_id: str, request: Request) -> Dict[str, Any]:
    """Owner copies the customer's paperwork-acknowledgment time into the Airtable brochure/estimate
    gate fields (only when empty). Never touches ofs_signed_at. Every write is audited."""
    p = await current_principal(request)
    if p["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can record delivery.")
    try:
        record = await _fetch_project(project_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="No such job.")
        raise
    by_recid, by_lead = await _jobs_index()
    job = _match_job(record, by_recid, by_lead)
    if not job:
        raise HTTPException(status_code=404, detail="No linked job for this project.")
    ack = await _latest_ack(job["_id"])
    if not ack:
        raise HTTPException(status_code=422, detail="No customer acknowledgment on file yet.")
    cur = record.get("fields") or {}
    at = ack.get("at")
    air: Dict[str, Any] = {}
    labels: List[Tuple[str, str]] = []
    if not cur.get(PROJECT_BROCHURE_SENT_F):
        air[PROJECT_BROCHURE_SENT_F] = at
        labels.append(("brochure_sent_at", "Brochure delivered"))
    if not cur.get(PROJECT_ESTIMATE_DELIVERED_F):
        air[PROJECT_ESTIMATE_DELIVERED_F] = at
        labels.append(("estimate_delivered_at", "Estimate delivered"))
    if not air:
        return {"updated": False, "message": "Both gates already have delivery dates."}
    await airtable_request("PATCH", TABLES["projects"],
                           json_body={"records": [{"id": project_id, "fields": air}], "typecast": True})
    entries = [{"_id": str(uuid4()), "project_id": project_id, "field_key": k, "label": lbl,
                "old": None, "new": at, "financial": False,
                "by": p.get("name") or p.get("email") or "owner", "by_id": p.get("user_id"),
                "note": "Recorded from customer paperwork acknowledgment", "at": now_iso()}
               for k, lbl in labels]
    await mongo_db.job_audit_log.insert_many(entries)
    _projects_list_cache["at"] = 0.0
    return {"updated": True, "count": len(entries)}



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
    surveyor_attested: Optional[bool] = None
    crew_docs_expiry: Optional[str] = None


@api_router.get("/users")
async def list_users(p: Dict[str, Any] = Depends(require_owner)):
    docs = await mongo_db.users.find({"ghost": {"$ne": True}}).sort("created_at", 1).to_list(200)
    return {"users": [_user_public(u) for u in docs]}


@api_router.post("/users")
async def create_user(payload: UserCreatePayload, p: Dict[str, Any] = Depends(require_owner)):
    roles = [r for r in (payload.roles or [payload.role]) if r]
    if not roles or any(r not in ("crew", "sales", "owner", "marketing", "quality") for r in roles):
        raise HTTPException(status_code=422, detail="Roles must be crew, sales, owner, marketing, or quality.")
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
        if not roles or any(r not in ("crew", "sales", "owner", "marketing", "quality") for r in roles):
            raise HTTPException(status_code=422, detail="Roles must be crew, sales, owner, marketing, or quality.")
        if p["user_id"] == user_id and "owner" not in roles:
            raise HTTPException(status_code=422, detail="You can't take Owner off your own account — you'd lock yourself out.")
        updates["roles"] = roles
        updates["role"] = roles[0]
        changes.append(f"roles → {'+'.join(roles)}")
    elif payload.role is not None:
        if payload.role not in ("crew", "sales", "owner", "marketing", "quality"):
            raise HTTPException(status_code=422, detail="Role must be crew, sales, owner, marketing, or quality.")
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
    if payload.surveyor_attested is not None:
        updates["surveyor_attested"] = bool(payload.surveyor_attested)
        changes.append("surveyor attested" if payload.surveyor_attested else "surveyor attestation removed")
    if payload.crew_docs_expiry is not None:
        updates["crew_docs_expiry"] = payload.crew_docs_expiry or None
        changes.append("crew docs expiry")
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
    crew_lead_id: Optional[str] = None
    crew_lead_secondary_id: Optional[str] = None
    ignore_warnings: bool = False


# ------- Stage 2: Crew Lead (per-assignment coordinator) + eight-tap documentation flow -------
# "Crew Lead" is an ADDITIONAL role on ONE assignment (primary + optional secondary), chosen by the
# owner from that assignment's crew. It is NOT a pay position (Driver/Helper stays) and NOT a customer lead.
# The assignment doc is the single source of truth for Crew Lead selection.

CRITICAL_INSPECTION_KEYS = {"lights", "tires", "brakes", "fluids"}
JOB_LEAD_STEPS = ["clock_in", "depart", "arrived", "no_damage", "loaded", "dropoff", "complete", "clock_out"]
JOB_LEAD_STEP_LABEL = {
    "clock_in": "Clock in to this job",
    "depart": "All good — Depart",
    "arrived": "Arrived — walkthrough done",
    "no_damage": "No damage",
    "loaded": "Loaded — leaving pickup",
    "dropoff": "At drop-off",
    "complete": "All as quoted & Complete",
    "clock_out": "Clock out & No defects",
}


def _driver_user_id(crew: List[Dict[str, Any]]) -> Optional[str]:
    for c in crew:
        if (c.get("position") or "").lower() == "driver":
            return c.get("user_id")
    return crew[0]["user_id"] if crew else None


def _build_crew_lead(crew: List[Dict[str, Any]], primary_id: Optional[str] = None,
                     secondary_id: Optional[str] = None, prev: Optional[Dict[str, Any]] = None,
                     by: str = "", explicit_secondary: bool = True) -> Dict[str, Any]:
    """Resolve the Crew Lead selection against the assignment's crew. Preserves any prior taps/override/
    corrections. Defaults the primary to the Driver (source 'driver_default') when nothing is chosen."""
    prev = dict(prev or {})
    names = {c["user_id"]: c.get("name") for c in crew}
    pid = primary_id if primary_id in names else None
    source = "explicit" if pid else None
    if not pid:
        pid = prev.get("primary_id") if prev.get("primary_id") in names else None
        source = prev.get("source")
    if not pid:
        pid = _driver_user_id(crew)
        source = "driver_default"
    if explicit_secondary:
        sid = secondary_id if (secondary_id in names and secondary_id != pid) else None
    else:
        prev_sid = prev.get("secondary_id")
        sid = prev_sid if (prev_sid in names and prev_sid != pid) else None
    cl = dict(prev)
    cl.update({
        "primary_id": pid, "primary_name": names.get(pid),
        "secondary_id": sid, "secondary_name": names.get(sid) if sid else None,
        "source": source or "driver_default",
        "set_by": by or prev.get("set_by") or "", "set_at": now_iso(),
    })
    cl.setdefault("taps", {})
    cl.setdefault("corrections", [])
    cl.setdefault("depart_override", None)
    cl.setdefault("depart_blocker", None)
    return cl


def _effective_lead_ids(a: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    cl = a.get("crew_lead") or {}
    pid = cl.get("primary_id") or _driver_user_id(a.get("crew", []))
    return pid, cl.get("secondary_id")


def _is_crew_lead(a: Dict[str, Any], user_id: Optional[str]) -> bool:
    pid, sid = _effective_lead_ids(a)
    return bool(user_id) and (user_id == pid or user_id == sid)


def _crew_lead_role(a: Dict[str, Any], user_id: Optional[str]) -> str:
    pid, sid = _effective_lead_ids(a)
    if user_id == pid:
        return "primary"
    if user_id == sid:
        return "secondary"
    return "helper"


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
    crew_list = [{"user_id": c.user_id, "name": users_by_id[c.user_id]["name"], "position": c.position} for c in payload.crew]
    crew_lead = _build_crew_lead(crew_list, payload.crew_lead_id, payload.crew_lead_secondary_id, by=p["name"])
    doc = {
        "_id": str(uuid4()), "project_id": payload.project_id, "job_name": payload.job_name.strip(),
        "job_date": payload.job_date, "arrival_time": payload.arrival_time,
        "start_address": payload.start_address.strip(), "end_address": payload.end_address.strip(),
        "truck_id": payload.truck_id, "truck_name": truck["name"] if truck else None,
        "job_size": payload.job_size,
        "crew": crew_list, "crew_lead": crew_lead,
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
    await _announce_crew_lead(doc, crew_lead, None, p)
    return {**_sanitize_assignment(doc), "warnings": warnings}


async def _announce_crew_lead(a: Dict[str, Any], cl: Dict[str, Any], prev: Optional[Dict[str, Any]], p: Dict[str, Any]) -> None:
    """Notify + log a Crew Lead naming/swap. Only fires when the primary/secondary actually changed."""
    prev = prev or {}
    if cl.get("primary_id") == prev.get("primary_id") and cl.get("secondary_id") == prev.get("secondary_id"):
        return
    label = cl.get("primary_name") or "—"
    if cl.get("secondary_name"):
        label += f" (backup: {cl['secondary_name']})"
    await log_job_event(a["_id"], "crew_lead", f"Crew Lead: {label}", by=p.get("name", ""))
    for uid, role in ((cl.get("primary_id"), "Crew Lead"), (cl.get("secondary_id"), "backup Crew Lead")):
        if uid and uid != (prev.get("primary_id") if role == "Crew Lead" else prev.get("secondary_id")):
            await notify(uid, None, f"You're the {role}",
                         f"You're the {role} on \"{a.get('job_name')}\" ({a.get('job_date')}). "
                         f"Open My Jobs on move day to run the checklist.",
                         "assignment", {"assignment_id": a["_id"]})


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
    crew_lead = _build_crew_lead(
        updates["crew"], payload.crew_lead_id, payload.crew_lead_secondary_id,
        prev=existing.get("crew_lead"), by=p["name"],
        explicit_secondary=(payload.crew_lead_secondary_id is not None or payload.crew_lead_id is not None))
    updates["crew_lead"] = crew_lead
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
    await _announce_crew_lead(fresh, crew_lead, existing.get("crew_lead"), p)
    return {**_sanitize_assignment(fresh), "warnings": warnings}


# ------- Crew Lead selection + exception controls (owner)

class CrewLeadPayload(BaseModel):
    primary_id: Optional[str] = None
    secondary_id: Optional[str] = None


@api_router.patch("/assignments/{assignment_id}/crew-lead")
async def set_crew_lead(assignment_id: str, payload: CrewLeadPayload, p: Dict[str, Any] = Depends(require_owner)):
    a = await mongo_db.assignments.find_one({"_id": assignment_id})
    if not a:
        raise HTTPException(status_code=404, detail="No such assignment.")
    crew = a.get("crew", [])
    crew_ids = {c["user_id"] for c in crew}
    if not payload.primary_id or payload.primary_id not in crew_ids:
        raise HTTPException(status_code=422, detail="Pick a primary Crew Lead from this job's crew.")
    if payload.secondary_id and payload.secondary_id not in crew_ids:
        raise HTTPException(status_code=422, detail="The backup Crew Lead must be on this job's crew.")
    if payload.secondary_id and payload.secondary_id == payload.primary_id:
        raise HTTPException(status_code=422, detail="Primary and backup Crew Lead must be different people.")
    prev = a.get("crew_lead")
    cl = _build_crew_lead(crew, payload.primary_id, payload.secondary_id, prev=prev, by=p["name"])
    cl["source"] = "explicit"
    await mongo_db.assignments.update_one({"_id": assignment_id}, {"$set": {"crew_lead": cl, "updated_at": now_iso()}})
    await audit(p, "named the Crew Lead", a.get("job_name") or assignment_id,
                {"primary": cl.get("primary_name"), "secondary": cl.get("secondary_name")})
    fresh = await mongo_db.assignments.find_one({"_id": assignment_id})
    await _announce_crew_lead(fresh, cl, prev, p)
    return {**_sanitize_assignment(fresh)}


class DepartOverridePayload(BaseModel):
    reason: str
    resolution: str = "override"   # "corrected" = defect fixed & verified | "override" = authorized departure despite it


@api_router.post("/assignments/{assignment_id}/depart-override")
async def depart_override(assignment_id: str, payload: DepartOverridePayload, p: Dict[str, Any] = Depends(require_owner)):
    """Owner reviews a critical-defect block so the Crew Lead can depart. Records either 'corrected'
    (fixed & verified) or 'override' (authorized despite the defect). Preserves the failed inspection and the
    owner's decision; NEVER departs the truck — the Crew Lead must still tap Depart. Always audited."""
    a = await mongo_db.assignments.find_one({"_id": assignment_id})
    if not a:
        raise HTTPException(status_code=404, detail="No such assignment.")
    reason = (payload.reason or "").strip()
    if len(reason) < 10:
        raise HTTPException(status_code=422, detail="Give a real reason (at least 10 characters) for the decision.")
    resolution = payload.resolution if payload.resolution in ("corrected", "override") else "override"
    prev_blocker = (a.get("crew_lead") or {}).get("depart_blocker")
    override = {"by": p["name"], "by_id": p.get("user_id"), "resolution": resolution,
                "reason": reason[:500], "at": now_iso(), "cleared_blocker": prev_blocker}
    await mongo_db.assignments.update_one({"_id": assignment_id},
                                          {"$set": {"crew_lead.depart_override": override,
                                                    "crew_lead.depart_blocker": None, "updated_at": now_iso()}})
    verb = "confirmed the defect corrected & verified" if resolution == "corrected" else "authorized departure despite the defect"
    await log_job_event(assignment_id, "crew_lead", f"Owner {verb}: {reason[:120]}", by=p["name"])
    await audit(p, "reviewed a critical-defect departure block", a.get("job_name") or assignment_id,
                {"resolution": resolution, "reason": reason})
    pid, sid = _effective_lead_ids(a)
    note = (f"The owner confirmed the truck defect is fixed on \"{a.get('job_name')}\". Tap Depart when ready."
            if resolution == "corrected"
            else f"The owner authorized departure on \"{a.get('job_name')}\" despite the defect. Tap Depart when ready.")
    for uid in (pid, sid):
        if uid:
            await notify(uid, None, "Departure cleared by owner", note,
                         "assignment", {"assignment_id": assignment_id})
    fresh = await mongo_db.assignments.find_one({"_id": assignment_id})
    return {**_sanitize_assignment(fresh)}


class CrewLeadCorrectionPayload(BaseModel):
    tap_key: str
    action: str = "note"   # note | clear
    reason: str
    note: Optional[str] = None


@api_router.post("/assignments/{assignment_id}/crew-lead/correct")
async def correct_crew_lead(assignment_id: str, payload: CrewLeadCorrectionPayload,
                            p: Dict[str, Any] = Depends(require_owner)):
    """Owner correction of a documentation record — always keeps an audited reason. 'clear' undoes a tap
    so the Crew Lead can redo it; 'note' just annotates. Never silently rewrites what the crew attested."""
    a = await mongo_db.assignments.find_one({"_id": assignment_id})
    if not a:
        raise HTTPException(status_code=404, detail="No such assignment.")
    if payload.tap_key not in JOB_LEAD_STEPS:
        raise HTTPException(status_code=422, detail="Unknown step.")
    reason = (payload.reason or "").strip()
    if len(reason) < 5:
        raise HTTPException(status_code=422, detail="Give a reason for the correction.")
    entry = {"tap_key": payload.tap_key, "action": payload.action, "reason": reason[:500],
             "note": (payload.note or "").strip()[:500] or None, "by": p["name"], "at": now_iso()}
    ops: Dict[str, Any] = {"$push": {"crew_lead.corrections": entry}, "$set": {"updated_at": now_iso()}}
    if payload.action == "clear":
        ops["$unset"] = {f"crew_lead.taps.{payload.tap_key}": ""}
    await mongo_db.assignments.update_one({"_id": assignment_id}, ops)
    await log_job_event(assignment_id, "crew_lead",
                        f"Owner correction on {JOB_LEAD_STEP_LABEL.get(payload.tap_key, payload.tap_key)}: {reason[:120]}",
                        by=p["name"])
    await audit(p, "corrected a crew-lead record", a.get("job_name") or assignment_id,
                {"step": payload.tap_key, "action": payload.action, "reason": reason})
    fresh = await mongo_db.assignments.find_one({"_id": assignment_id})
    return {**_sanitize_assignment(fresh)}


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
    await _scan_no_shows(day)
    rflags = await mongo_db.reliability_flags.find(
        {"job_date": day, "status": {"$in": ["open", "unverified", "disputed"]}}).sort("created_at", -1).to_list(300)
    flags_by_user: Dict[str, int] = {}
    for f in rflags:
        flags_by_user[f.get("user_id")] = flags_by_user.get(f.get("user_id"), 0) + 1
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
                  "off": u["_id"] in off_ids, "flags": flags_by_user.get(u["_id"], 0)} for u in crew_users]
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
            "reliability": [_reliability_flag_out(f) for f in rflags],
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
        await _queue_outcome_rebuild_for_assignment(assignment_id, "crew_status", p.get("name", ""))


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
    for f in await mongo_db.reliability_flags.find({"assignment_id": assignment_id}).to_list(100):
        events.append({"at": f.get("created_at"), "kind": "flag",
                       "title": f"{RELIABILITY_LABELS.get(f.get('type'), f.get('type'))} — {f.get('user_name')}: "
                                f"{f.get('detail')} [{f.get('status')}]", "by": f.get("user_name", "")})
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
    if assignment:   # Stage 3: late clock-in vs the person's scheduled report time (owner-configurable grace)
        sched = _scheduled_report_dt(assignment)
        if sched:
            grace = (await _reliability_config())["grace_minutes"]
            late_min = int((now.astimezone(ZoneInfo("America/New_York")) - sched).total_seconds() / 60)
            if late_min > grace:
                await _create_reliability_flag(
                    assignment, p["user_id"], p["name"], "late_clock_in",
                    f"Clocked in {late_min} min after the {assignment.get('arrival_time')} report time "
                    f"(grace {grace} min).", meta={"minutes_late": late_min, "grace_minutes": grace})
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
    if entry.get("assignment_id"):
        await _queue_outcome_rebuild_for_assignment(entry["assignment_id"], "time_edit", p.get("name", ""))
    if assignment and (assignment.get("exec_status") or "Assigned") != "Complete":
        # Stage 3: clocked out before the job is Complete → owner review (never auto-called an early departure)
        await _create_reliability_flag(
            assignment, p["user_id"], p["name"], "early_clock_out",
            f"Clocked out while \"{assignment.get('job_name')}\" was still "
            f"\"{assignment.get('exec_status') or 'Assigned'}\" (not Complete).",
            meta={"exec_status": assignment.get("exec_status")})
    job_today = await mongo_db.jobs.find_one({"crew.user_id": p["user_id"], "job_date": _et_today()})
    return {"entry_id": str(entry["_id"]), "hours": hours, "flags": flags,
            "review_prompt": bool(job_today), "job_id": str(job_today["_id"]) if job_today else None,
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
    nudge = False
    if open_entry and open_entry.get("assignment_id"):
        oa = await mongo_db.assignments.find_one({"_id": open_entry["assignment_id"]}, {"exec_status": 1})
        nudge = bool(oa and oa.get("exec_status") == "Complete")
    return {
        "entries": [{"id": e["_id"], "clock_in": e["clock_in"], "clock_out": e.get("clock_out"),
                     "hours": e.get("hours"), "job_name": e.get("job_name"), "position": e.get("position"),
                     "approved": e.get("approved", False)} for e in docs],
        "weekly_totals": weeks,
        "clocked_in": bool(open_entry),
        "open_entry": {"id": open_entry["_id"], "clocked_in_at": open_entry["clock_in"]["at"],
                       "job_name": open_entry.get("job_name"),
                       "assignment_id": open_entry.get("assignment_id")} if open_entry else None,
        "still_clocked_in_after_complete": nudge,
    }


# ======= Stage 3: helpers, clocks, reliability, accountability & records =======
# Everything here is REVIEW + VISIBILITY. Derived flags never auto-dock pay, change assignments,
# clock anyone out, or touch rewards. Documentation points stay OFF (0) until the owner enables them.

RELIABILITY_LABELS = {
    "late_clock_in": "Late clock-in",
    "possible_no_show": "Possible no-show (unverified)",
    "early_clock_out": "Clocked out before Complete",
    "missing_clock_out": "Missing clock-out",
    "owner_correction": "Owner corrected a punch",
    "disputed_punch": "Disputed punch",
}


async def _reliability_config() -> Dict[str, Any]:
    doc = await mongo_db.settings.find_one({"_id": "reliability_config"}) or {}
    return {
        "grace_minutes": int(doc.get("grace_minutes", 10)),
        "documentation_points": int(doc.get("documentation_points", 0)),
        "documentation_points_enabled": bool(doc.get("documentation_points_enabled", False)),
    }


class ReliabilityConfigPayload(BaseModel):
    grace_minutes: Optional[int] = None
    documentation_points: Optional[int] = None
    documentation_points_enabled: Optional[bool] = None


@api_router.get("/settings/reliability")
async def get_reliability_config(p: Dict[str, Any] = Depends(require_owner)):
    return await _reliability_config()


@api_router.put("/settings/reliability")
async def save_reliability_config(payload: ReliabilityConfigPayload, p: Dict[str, Any] = Depends(require_owner)):
    updates: Dict[str, Any] = {}
    if payload.grace_minutes is not None:
        updates["grace_minutes"] = max(0, min(240, int(payload.grace_minutes)))
    if payload.documentation_points is not None:
        updates["documentation_points"] = max(0, min(1000, int(payload.documentation_points)))
    if payload.documentation_points_enabled is not None:
        updates["documentation_points_enabled"] = bool(payload.documentation_points_enabled)
    if updates:
        await mongo_db.settings.update_one({"_id": "reliability_config"}, {"$set": updates}, upsert=True)
        await audit(p, "updated reliability settings", "settings", updates)
    return await _reliability_config()


def _parse_iso(s: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(s))
    except (ValueError, TypeError):
        return None


def _scheduled_report_dt(a: Dict[str, Any]) -> Optional[datetime]:
    at, d = a.get("arrival_time"), a.get("job_date")
    if not at or not d:
        return None
    try:
        hh, mm = [int(x) for x in str(at).split(":")[:2]]
        return datetime.fromisoformat(f"{d}T00:00:00").replace(
            hour=hh, minute=mm, tzinfo=ZoneInfo("America/New_York"))
    except (ValueError, TypeError):
        return None


def _reliability_flag_out(f: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": f["_id"], "assignment_id": f.get("assignment_id"), "job_name": f.get("job_name"),
        "job_date": f.get("job_date"), "user_id": f.get("user_id"), "user_name": f.get("user_name"),
        "type": f.get("type"), "label": RELIABILITY_LABELS.get(f.get("type"), f.get("type")),
        "status": f.get("status"), "detail": f.get("detail"), "meta": f.get("meta") or {},
        "created_at": f.get("created_at"), "resolved_by": f.get("resolved_by"),
        "resolved_at": f.get("resolved_at"), "resolve_reason": f.get("resolve_reason"),
        "disputed_at": f.get("disputed_at"), "dispute_reason": f.get("dispute_reason"),
    }


async def _create_reliability_flag(a: Dict[str, Any], user_id: Optional[str], user_name: Optional[str],
                                   ftype: str, detail: str, status: str = "open",
                                   meta: Optional[Dict[str, Any]] = None, notify_owner: bool = True) -> Optional[str]:
    """Create a review flag (deduped per assignment+user+type while still open/unverified). NEVER changes
    pay, credits, badges, or assignments — it's a review item the owner resolves and the crew can dispute."""
    if not user_id:
        return None
    existing = await mongo_db.reliability_flags.find_one(
        {"assignment_id": a["_id"], "user_id": user_id, "type": ftype, "status": {"$in": ["open", "unverified"]}})
    if existing:
        return existing["_id"]
    doc = {"_id": str(uuid4()), "assignment_id": a["_id"], "job_name": a.get("job_name"),
           "job_date": a.get("job_date"), "user_id": user_id, "user_name": user_name,
           "type": ftype, "status": status, "detail": detail, "meta": meta or {},
           "created_at": now_iso(), "resolved_by": None, "resolved_at": None, "resolve_reason": None,
           "disputed_at": None, "dispute_reason": None}
    await mongo_db.reliability_flags.insert_one(doc)
    label = RELIABILITY_LABELS.get(ftype, ftype)
    if notify_owner:
        await notify(None, "owner", f"Reliability flag — {label}",
                     f"{user_name}: {detail} (\"{a.get('job_name')}\"). Review it on the Dispatch board.",
                     "flag", {"assignment_id": a["_id"], "flag_id": doc["_id"]})
    await notify(user_id, None, f"Timekeeping flag — {label}",
                 f"{detail} on \"{a.get('job_name')}\". If that's not right, open the job and dispute it.",
                 "flag", {"assignment_id": a["_id"], "flag_id": doc["_id"]})
    return doc["_id"]


async def _scan_no_shows(day: str) -> None:
    """Persist an unverified possible-no-show for anyone scheduled who has no punch by report-time + grace.
    Idempotent (deduped). Labeled 'unverified' — the owner confirms or dismisses; nothing is assumed."""
    grace = (await _reliability_config())["grace_minutes"]
    now_et = datetime.now(ZoneInfo("America/New_York"))
    day_prefix = f"{day}T00:00:00"
    for a in await mongo_db.assignments.find({"job_date": day}).to_list(200):
        sched = _scheduled_report_dt(a)
        if not sched or now_et < sched + timedelta(minutes=grace):
            continue
        for c in a.get("crew", []):
            uid = c.get("user_id")
            if not uid:
                continue
            bound = await mongo_db.time_entries.find_one({"user_id": uid, "assignment_id": a["_id"]})
            if bound:
                continue
            any_today = await mongo_db.time_entries.find_one(
                {"user_id": uid, "clock_in.at": {"$gte": day_prefix}})
            if any_today:   # they clocked in somewhere today — a consecutive-job case, not a no-show
                continue
            # Once a no-show has been raised for this person on this job today, don't resurrect it —
            # even after the owner resolves or the crew disputes it (dedup below only covers open/unverified).
            prior = await mongo_db.reliability_flags.find_one(
                {"assignment_id": a["_id"], "user_id": uid, "type": "possible_no_show"})
            if prior:
                continue
            await _create_reliability_flag(
                a, uid, c.get("name"), "possible_no_show",
                f"No clock-in by {a.get('arrival_time')} + {grace} min grace. Unverified — confirm or dismiss.",
                status="unverified", meta={"grace_minutes": grace})


async def _user_phone(user_id: Optional[str]) -> str:
    if not user_id:
        return ""
    u = await mongo_db.users.find_one({"_id": user_id}, {"member_profile": 1, "profile": 1})
    if not u:
        return ""
    return (((u.get("member_profile") or {}).get("phone")) or ((u.get("profile") or {}).get("phone")) or "").strip()


async def _assignment_window(a: Dict[str, Any]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Best-effort on-site window for a job: Crew Lead main clock-in → the Complete status time."""
    cl = a.get("crew_lead") or {}
    start = _parse_iso(cl.get("main_clock_at"))
    end = None
    for ev in reversed(a.get("status_history") or []):
        if ev.get("status") == "Complete":
            end = _parse_iso(ev.get("at"))
            break
    if not start:
        e = await mongo_db.time_entries.find_one({"assignment_id": a["_id"]}, sort=[("clock_in.at", 1)])
        start = _parse_iso((e or {}).get("clock_in", {}).get("at")) if e else None
    return start, end


async def _estimate_helper_hours(a: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """Actual hours from a punch bound to this job, else an ESTIMATE from the job's main-clock window
    overlapped with the person's own punches that day. Estimates are labeled and are NOT payroll punches."""
    bound = await mongo_db.time_entries.find({"assignment_id": a["_id"], "user_id": user_id}).to_list(10)
    actual = sum((e.get("hours") or 0) for e in bound if e.get("hours"))
    if bound and actual:
        return {"hours": round(actual, 2), "estimated": False}
    start, end = await _assignment_window(a)
    if not start:
        return {"hours": None, "estimated": True}
    end = end or datetime.now(timezone.utc)
    day = a.get("job_date")
    punches = await mongo_db.time_entries.find(
        {"user_id": user_id, "clock_out": {"$ne": None},
         "clock_in.at": {"$gte": f"{day}T00:00:00"}}).to_list(20) if day else []
    total = 0.0
    for e in punches:
        s = _parse_iso(e.get("clock_in", {}).get("at"))
        en = _parse_iso((e.get("clock_out") or {}).get("at"))
        if not s or not en:
            continue
        lo, hi = max(s, start), min(en, end)
        if hi > lo:
            total += (hi - lo).total_seconds() / 3600
    return {"hours": round(total, 2) if total else None, "estimated": True}


async def _crew_work_record(user_id: str) -> Dict[str, Any]:
    """Dated job history + documentation completion + reliability flags for a crew member (Team HQ record)."""
    assigns = await mongo_db.assignments.find({"crew.user_id": user_id}).sort("job_date", -1).to_list(60)
    jobs, as_lead_total, fully_documented = [], 0, 0
    for a in assigns:
        slot = next((c for c in a.get("crew", []) if c["user_id"] == user_id), {})
        was_lead = _is_crew_lead(a, user_id)
        taps_done = len((a.get("crew_lead") or {}).get("taps") or {}) if was_lead else 0
        if was_lead:
            as_lead_total += 1
            if taps_done >= len(JOB_LEAD_STEPS):
                fully_documented += 1
        est = await _estimate_helper_hours(a, user_id)
        jobs.append({
            "assignment_id": a["_id"], "job_name": a.get("job_name"), "job_date": a.get("job_date"),
            "position": slot.get("position"), "exec_status": a.get("exec_status") or "Assigned",
            "was_lead": was_lead, "taps_done": taps_done, "taps_total": len(JOB_LEAD_STEPS),
            "hours": est["hours"], "hours_estimated": est["estimated"],
        })
    flags = await mongo_db.reliability_flags.find({"user_id": user_id}).sort("created_at", -1).to_list(80)
    return {
        "jobs": jobs,
        "documentation": {"as_lead_total": as_lead_total, "fully_documented": fully_documented},
        "flags": [_reliability_flag_out(f) for f in flags],
        "flags_open": sum(1 for f in flags if f.get("status") in ("open", "unverified", "disputed")),
        "flags_resolved": sum(1 for f in flags if f.get("status") == "resolved"),
    }


@api_router.get("/reliability/flags")
async def reliability_flags(date: Optional[str] = None, status: Optional[str] = None,
                            user_id: Optional[str] = None, p: Dict[str, Any] = Depends(require_owner)):
    day = (date or _et_today())[:10]
    await _scan_no_shows(day)
    q: Dict[str, Any] = {"job_date": day}
    if status:
        q["status"] = status
    if user_id:
        q["user_id"] = user_id
    docs = await mongo_db.reliability_flags.find(q).sort("created_at", -1).to_list(300)
    cfg = await _reliability_config()
    return {"date": day, "grace_minutes": cfg["grace_minutes"],
            "flags": [_reliability_flag_out(f) for f in docs],
            "open_count": sum(1 for f in docs if f.get("status") in ("open", "unverified", "disputed"))}


class FlagResolvePayload(BaseModel):
    reason: str


@api_router.post("/reliability/flags/{flag_id}/resolve")
async def resolve_reliability_flag(flag_id: str, payload: FlagResolvePayload, p: Dict[str, Any] = Depends(require_owner)):
    f = await mongo_db.reliability_flags.find_one({"_id": flag_id})
    if not f:
        raise HTTPException(status_code=404, detail="No such flag.")
    reason = (payload.reason or "").strip()
    if len(reason) < 3:
        raise HTTPException(status_code=422, detail="Give a short reason so the record makes sense later.")
    await mongo_db.reliability_flags.update_one({"_id": flag_id}, {"$set": {
        "status": "resolved", "resolved_by": p["name"], "resolved_at": now_iso(), "resolve_reason": reason[:500]}})
    await audit(p, "resolved a reliability flag",
                f"{f.get('user_name')} — {RELIABILITY_LABELS.get(f.get('type'), f.get('type'))}", {"reason": reason})
    if f.get("user_id"):
        await notify(f["user_id"], None, "Timekeeping flag resolved",
                     f"The owner reviewed the {RELIABILITY_LABELS.get(f.get('type'), 'flag').lower()} on "
                     f"\"{f.get('job_name')}\": {reason[:160]}", "info", {"flag_id": flag_id})
    fresh = await mongo_db.reliability_flags.find_one({"_id": flag_id})
    return _reliability_flag_out(fresh)


@api_router.get("/crew/my-flags")
async def my_reliability_flags(p: Dict[str, Any] = Depends(require_crew)):
    docs = await mongo_db.reliability_flags.find({"user_id": p["user_id"]}).sort("created_at", -1).to_list(60)
    return {"flags": [_reliability_flag_out(f) for f in docs]}


class FlagDisputePayload(BaseModel):
    reason: str


@api_router.post("/crew/my-flags/{flag_id}/dispute")
async def dispute_reliability_flag(flag_id: str, payload: FlagDisputePayload, p: Dict[str, Any] = Depends(require_crew)):
    f = await mongo_db.reliability_flags.find_one({"_id": flag_id})
    if not f or f.get("user_id") != p["user_id"]:
        raise HTTPException(status_code=404, detail="No such flag.")
    reason = (payload.reason or "").strip()
    if len(reason) < 3:
        raise HTTPException(status_code=422, detail="Tell the owner what actually happened.")
    await mongo_db.reliability_flags.update_one({"_id": flag_id}, {"$set": {
        "status": "disputed", "disputed_at": now_iso(), "dispute_reason": reason[:500]}})
    await notify(None, "owner", "Punch flag disputed",
                 f"{p['name']} disputes the {RELIABILITY_LABELS.get(f.get('type'), 'flag').lower()} on "
                 f"\"{f.get('job_name')}\": {reason[:160]}", "flag", {"flag_id": flag_id})
    fresh = await mongo_db.reliability_flags.find_one({"_id": flag_id})
    return _reliability_flag_out(fresh)


class ProblemReportPayload(BaseModel):
    message: str


@api_router.post("/crew/jobs/{assignment_id}/report-problem")
async def report_problem(assignment_id: str, payload: ProblemReportPayload, p: Dict[str, Any] = Depends(require_crew)):
    """Any crew member on the job (helper or lead) can flag a problem to the Crew Lead + owner. This never
    changes job status, completes a checklist, or counts as a Crew Lead milestone."""
    a = await mongo_db.assignments.find_one({"_id": assignment_id, "crew.user_id": p["user_id"]})
    if not a:
        raise HTTPException(status_code=404, detail="That job isn't on your schedule.")
    msg = (payload.message or "").strip()
    if len(msg) < 3:
        raise HTTPException(status_code=422, detail="Add a quick note about the problem.")
    msg = msg[:800]
    await log_job_event(assignment_id, "problem", f"Problem reported by {p['name']}", by=p["name"], detail=msg)
    pid, sid = _effective_lead_ids(a)
    for uid in (pid, sid):
        if uid and uid != p["user_id"]:
            await notify(uid, None, "Crew flagged a problem",
                         f"{p['name']} on \"{a.get('job_name')}\": {msg[:160]}", "flag",
                         {"assignment_id": assignment_id})
    await notify(None, "owner", "Problem reported on a job",
                 f"{p['name']} on \"{a.get('job_name')}\": {msg[:160]}", "flag", {"assignment_id": assignment_id})
    return {"ok": True}


@dl_router.get("/fleet/inspections-export")
async def export_inspections(start: Optional[str] = None, end: Optional[str] = None,
                             auth: Optional[str] = None, request: Request = None):
    p = await principal_from_token_string(auth) if auth else await current_principal(request)
    if p["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can export inspections.")
    q: Dict[str, Any] = {}
    if start:
        q.setdefault("date", {})["$gte"] = start
    if end:
        q.setdefault("date", {})["$lte"] = end
    docs = await mongo_db.truck_inspections.find(q).sort([("date", -1), ("created_at", -1)]).to_list(2000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Date", "Truck", "Phase", "By", "Result", "Failed items", "Odometer", "Job", "Logged at"])
    for d in docs:
        writer.writerow([d.get("date", ""), d.get("truck_name", ""), d.get("phase", ""), d.get("by", ""),
                         "PASS" if d.get("passed") else "FAIL", "; ".join(d.get("failed", [])),
                         d.get("odometer", "") or "", d.get("assignment_id", "") or "",
                         (d.get("created_at") or "")[:19]])
    filename = f"haulyeah-inspections-{start or 'all'}-to-{end or 'now'}.csv"
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


async def _run_nightly_open_punch() -> Dict[str, Any]:
    """11 PM ET review pass: flag every still-open punch for owner review (proposing a clock-out but NEVER
    performing it) and persist end-of-day no-shows. Only the owner can act on these."""
    et = ZoneInfo("America/New_York")
    day = datetime.now(et).date().isoformat()
    flagged = 0
    for e in await mongo_db.time_entries.find({"clock_out": None}).to_list(300):
        a = await mongo_db.assignments.find_one({"_id": e.get("assignment_id")}) if e.get("assignment_id") else None
        target = a or {"_id": f"punch:{e['_id']}", "job_name": e.get("job_name") or "no assigned job", "job_date": day}
        fid = await _create_reliability_flag(
            target, e["user_id"], e.get("user_name"), "missing_clock_out",
            "Still clocked in at the 11 PM check — needs a clock-out. Proposed: clock out now (owner must approve).",
            status="open", meta={"entry_id": e["_id"], "proposed_clock_out": now_iso(), "clocked_in_at": e.get("clock_in", {}).get("at")})
        if fid:
            flagged += 1
    await _scan_no_shows(day)
    logger.info("nightly open-punch review: flagged=%s", flagged)
    return {"flagged": flagged}


@public_router.post("/cron/nightly-open-punch")
async def cron_nightly_open_punch(request: Request) -> Dict[str, Any]:
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if not secret or not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    asyncio.create_task(_run_nightly_open_punch())
    return {"ok": True}


# ------- Stage 2: eight-tap Crew Lead flow (lives inside crew "My Jobs") -------

async def _assignment_linked_job(a: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The customer job (mongo `jobs`) linked to this assignment — by Airtable project link, else date+crew."""
    pr = a.get("project_id")
    if pr:
        j = await mongo_db.jobs.find_one({"project_record_id": pr})
        if j:
            return j
    crew_ids = [c["user_id"] for c in a.get("crew", [])]
    if a.get("job_date") and crew_ids:
        return await mongo_db.jobs.find_one({"job_date": a["job_date"], "crew.user_id": {"$in": crew_ids}})
    return None


async def _depart_send_tracking(a: Dict[str, Any], by: str) -> Dict[str, Any]:
    """Fire the one 'crew is on the way' customer text — idempotent via job.tracking.onway_sms_sent."""
    job = await _assignment_linked_job(a)
    if not job:
        return {"status": "no_customer_job", "detail": "No linked customer job — no text to send."}
    tr = job.get("tracking") or {}
    if tr.get("onway_sms_sent") or tr.get("sms_sent"):
        return {"status": "already_sent"}
    try:
        await _send_tracking_sms(job, by=by, template_key="move_day", mark_onway=True)
        return {"status": "sent"}
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Could not send the on-the-way text."
        await notify(None, "owner", "On-the-way text NOT sent",
                     f"Job #{job.get('invoice_number')}: {detail}", "warning")
        return {"status": "failed", "detail": str(detail)[:200]}


async def _record_crew_inspection(a: Dict[str, Any], items: Dict[str, bool], p: Dict[str, Any], phase: str) -> Dict[str, Any]:
    truck_id = a.get("truck_id")
    norm = {k: bool((items or {}).get(k, False)) for k, _ in INSPECTION_ITEMS}
    failed = [k for k, _ in INSPECTION_ITEMS if not norm[k]]
    passed = not failed
    critical = [k for k in failed if k in CRITICAL_INSPECTION_KEYS]
    if truck_id:
        await mongo_db.truck_inspections.insert_one({
            "_id": str(uuid4()), "truck_id": truck_id, "truck_name": a.get("truck_name"),
            "date": _et_today(), "by": p["name"], "by_id": p.get("user_id"),
            "items": norm, "failed": failed, "passed": passed, "phase": phase,
            "odometer": None, "notes": "", "assignment_id": a["_id"], "created_at": now_iso()})
        if not passed:
            t = await mongo_db.trucks.find_one({"_id": truck_id})
            if t and t.get("fleet_status", "in_service") == "in_service":
                await mongo_db.trucks.update_one({"_id": truck_id}, {"$set": {"fleet_status": "needs_attention"}})
    return {"passed": passed, "failed": failed,
            "failed_labels": [INSPECTION_LABELS[k] for k in failed],
            "critical": critical, "critical_labels": [INSPECTION_LABELS[k] for k in critical]}


async def _lead_mark_checklist(assignment_id: str, list_key: str, by: str) -> None:
    template = next((t for t in CHECKLIST_TEMPLATES if t[0] == list_key), None)
    if not template:
        return
    items = {str(i): {"done": True, "by": by, "at": now_iso()} for i in range(len(template[2]))}
    await mongo_db.job_checklists.update_one(
        {"_id": assignment_id},
        {"$set": {f"lists.{list_key}.items": items, f"lists.{list_key}.completed_at": now_iso()}}, upsert=True)


async def _lead_advance_status(a: Dict[str, Any], status: str, p: Dict[str, Any],
                               notes: Optional[str] = None, delay_factors: Optional[List[str]] = None) -> None:
    """Forward-only status advance — never moves a job backwards. Reuses the canonical side effects."""
    cur = a.get("exec_status") or "Assigned"
    if EXEC_STATUSES.index(status) > EXEC_STATUSES.index(cur):
        await _apply_exec_status(a, status, p, notes, delay_factors)
        a["exec_status"] = status


def _crew_lead_detail_out(a: Dict[str, Any]) -> Dict[str, Any]:
    """Owner-facing crew-lead documentation summary for Job Detail: who tapped each step + corrections."""
    cl = a.get("crew_lead") or {}
    pid, sid = _effective_lead_ids(a)
    taps = cl.get("taps") or {}
    steps = []
    for key in JOB_LEAD_STEPS:
        rec = taps.get(key) or {}
        steps.append({"key": key, "label": JOB_LEAD_STEP_LABEL[key], "done": bool(rec),
                      "by": rec.get("by"), "at": rec.get("at"),
                      "detail": {k: v for k, v in rec.items() if k not in ("by", "by_id", "at")}})
    return {
        "primary_id": pid, "primary_name": cl.get("primary_name"),
        "secondary_id": sid, "secondary_name": cl.get("secondary_name"),
        "source": cl.get("source"), "set_by": cl.get("set_by"), "set_at": cl.get("set_at"),
        "steps": steps, "taps_done": sum(1 for s in steps if s["done"]), "taps_total": len(JOB_LEAD_STEPS),
        "depart_override": cl.get("depart_override"), "depart_blocker": cl.get("depart_blocker"),
        "corrections": cl.get("corrections") or [], "main_clock_at": cl.get("main_clock_at"),
    }


async def _crew_lead_flow_state(a: Dict[str, Any], p: Dict[str, Any]) -> Dict[str, Any]:
    cl = a.get("crew_lead") or {}
    pid, sid = _effective_lead_ids(a)
    taps = cl.get("taps") or {}
    role = _crew_lead_role(a, p["user_id"])
    open_entry = await mongo_db.time_entries.find_one({"user_id": p["user_id"], "clock_out": None})
    names = {c["user_id"]: c.get("name") for c in a.get("crew", [])}
    steps = [{"key": k, "label": JOB_LEAD_STEP_LABEL[k], "done": bool(taps.get(k)),
              "by": (taps.get(k) or {}).get("by"), "at": (taps.get(k) or {}).get("at"),
              "detail": {kk: vv for kk, vv in (taps.get(k) or {}).items() if kk not in ("by", "by_id", "at")}}
             for k in JOB_LEAD_STEPS]
    next_tap = next((s["key"] for s in steps if not s["done"]), None)
    return {
        "assignment_id": a["_id"], "job_name": a.get("job_name"), "job_date": a.get("job_date"),
        "arrival_time": a.get("arrival_time"), "start_address": a.get("start_address"),
        "end_address": a.get("end_address"), "truck_id": a.get("truck_id"), "truck_name": a.get("truck_name"),
        "is_today": a.get("job_date") == _et_today(), "exec_status": a.get("exec_status") or "Assigned",
        "primary_id": pid, "primary_name": names.get(pid) or cl.get("primary_name"),
        "primary_phone": await _user_phone(pid),
        "secondary_id": sid, "secondary_name": (names.get(sid) if sid else None) or cl.get("secondary_name"),
        "lead_source": cl.get("source"),
        "role_on_job": role, "is_lead": role in ("primary", "secondary"),
        "steps": steps, "next_tap": next_tap,
        "inspection_items": [{"key": k, "label": v} for k, v in INSPECTION_ITEMS],
        "critical_keys": sorted(CRITICAL_INSPECTION_KEYS),
        "depart_override": cl.get("depart_override"), "depart_blocker": cl.get("depart_blocker"),
        "corrections": cl.get("corrections") or [],
        "clocked_in": bool(open_entry), "main_clock_at": cl.get("main_clock_at"),
    }


@api_router.get("/crew/job-lead/{assignment_id}")
async def get_crew_lead_flow(assignment_id: str, p: Dict[str, Any] = Depends(require_crew)):
    a = await mongo_db.assignments.find_one({"_id": assignment_id, "crew.user_id": p["user_id"]})
    if not a:
        raise HTTPException(status_code=404, detail="That job isn't on your schedule.")
    return await _crew_lead_flow_state(a, p)


class TapPayload(BaseModel):
    lat: Optional[float] = None
    lng: Optional[float] = None
    accuracy: Optional[float] = None
    inspection_items: Optional[Dict[str, bool]] = None
    damage_found: Optional[bool] = None
    delay_factors: Optional[List[str]] = None
    notes: Optional[str] = None
    lead_identity: Optional[str] = None
    no_defects: Optional[bool] = None
    posttrip_items: Optional[Dict[str, bool]] = None


async def _truck_last_job_today(a: Dict[str, Any]) -> bool:
    truck_id = a.get("truck_id")
    if not truck_id:
        return True
    others = await mongo_db.assignments.find(
        {"truck_id": truck_id, "job_date": a.get("job_date"), "_id": {"$ne": a["_id"]}}).to_list(20)
    if not others:
        return True
    return all((o.get("exec_status") == "Complete") for o in others)


@api_router.post("/crew/job-lead/{assignment_id}/{tap_key}")
async def crew_lead_tap(assignment_id: str, tap_key: str, payload: TapPayload, p: Dict[str, Any] = Depends(require_crew)):
    """One of the eight discrete Crew Lead actions. Every side effect is an explicit tap — nothing here
    is triggered by GPS, elapsed time, or another crew member's punch. Idempotent per step."""
    if tap_key not in JOB_LEAD_STEPS:
        raise HTTPException(status_code=404, detail="Unknown step.")
    a = await mongo_db.assignments.find_one({"_id": assignment_id, "crew.user_id": p["user_id"]})
    if not a:
        raise HTTPException(status_code=404, detail="That job isn't on your schedule.")
    if not _is_crew_lead(a, p["user_id"]):
        raise HTTPException(status_code=403,
                            detail="Only the Crew Lead runs this checklist. Ask the owner to name you Crew Lead.")
    cl = a.get("crew_lead") or _build_crew_lead(a.get("crew", []))
    if cl.get("source") == "driver_default" and not cl.get("owner_told_default"):
        cl["owner_told_default"] = True
        await mongo_db.assignments.update_one({"_id": assignment_id}, {"$set": {"crew_lead": cl}})
        await notify(None, "owner", "Crew Lead defaulted to the driver",
                     f"{p['name']} is running \"{a.get('job_name')}\" as Crew Lead (driver default). "
                     f"Confirm or change it on the Crew Assign board.",
                     "assignment", {"assignment_id": assignment_id})
        await log_job_event(assignment_id, "crew_lead", f"{p['name']} acting as Crew Lead (driver default)", by=p["name"])
    taps = dict(cl.get("taps") or {})
    if tap_key in taps:   # idempotent — a repeated tap never re-fires a side effect (e.g. the customer text)
        return await _crew_lead_flow_state(await mongo_db.assignments.find_one({"_id": assignment_id}), p)
    expected = next((s for s in JOB_LEAD_STEPS if s not in taps), None)
    if tap_key != expected:
        raise HTTPException(status_code=409,
                            detail=f"Do \u201c{JOB_LEAD_STEP_LABEL.get(expected, expected)}\u201d first.")
    coords = None
    if payload.lat is not None and payload.lng is not None:
        coords = {"lat": payload.lat, "lng": payload.lng, "accuracy": payload.accuracy}
    rec: Dict[str, Any] = {"by": p["name"], "by_id": p["user_id"], "at": now_iso()}
    if coords:
        rec["coords"] = coords
    set_ops: Dict[str, Any] = {}

    if tap_key == "clock_in":
        entry = await mongo_db.time_entries.find_one({"user_id": p["user_id"], "clock_out": None})
        if not entry:
            raise HTTPException(status_code=409, detail="Clock in didn't register — tap Clock in again.")
        rec["entry_id"] = entry["_id"]
        rec["at"] = (entry.get("clock_in") or {}).get("at") or rec["at"]
        pid, sid = _effective_lead_ids(a)
        if p["user_id"] == pid or (p["user_id"] == sid and not cl.get("main_clock_entry_id")):
            set_ops["crew_lead.main_clock_entry_id"] = entry["_id"]
            set_ops["crew_lead.main_clock_at"] = rec["at"]
        await log_job_event(assignment_id, "crew_lead", f"{p['name']} clocked in as Crew Lead", by=p["name"])

    elif tap_key == "depart":
        if a.get("truck_id"):
            insp = await _record_crew_inspection(a, payload.inspection_items or {}, p, "pre_trip")
            if insp["critical"] and not cl.get("depart_override"):
                blocker = {"failed_labels": insp["critical_labels"], "at": now_iso(), "by": p["name"]}
                await mongo_db.assignments.update_one({"_id": assignment_id},
                                                      {"$set": {"crew_lead.depart_blocker": blocker}})
                await notify(None, "owner", "Departure blocked — critical truck defect",
                             f"{p['name']} can't leave on \"{a.get('job_name')}\": "
                             + ", ".join(insp["critical_labels"]) + ". Clear it with an override or reschedule.",
                             "flag", {"assignment_id": assignment_id})
                await log_job_event(assignment_id, "crew_lead",
                                    "Departure blocked — critical defect: " + ", ".join(insp["critical_labels"]),
                                    by=p["name"])
                raise HTTPException(status_code=409, detail={
                    "error": "critical_defect", "failed": insp["critical_labels"],
                    "message": "Critical truck defect — departure needs an owner override."})
            rec["inspection"] = {"passed": insp["passed"], "failed": insp["failed_labels"]}
        if cl.get("depart_override"):
            rec["override"] = cl["depart_override"]
        set_ops["crew_lead.depart_blocker"] = None
        await _lead_advance_status(a, "En Route", p)
        await _lead_mark_checklist(assignment_id, "warehouse_departure", p["name"])
        sms = await _depart_send_tracking(a, by="Crew Lead — Depart")
        rec["sms"] = sms
        await log_job_event(assignment_id, "crew_lead", "Departed pickup — on-the-way text " + sms["status"], by=p["name"])

    elif tap_key == "arrived":
        await _lead_advance_status(a, "Arrived", p)
        await _lead_mark_checklist(assignment_id, "arrival", p["name"])
        await log_job_event(assignment_id, "crew_lead", "Arrived — walkthrough done", by=p["name"])

    elif tap_key == "no_damage":
        found = bool(payload.damage_found)
        rec["damage_found"] = found
        if found:
            await notify(None, "owner", "Existing damage noted at pickup",
                         f"{p['name']} logged existing damage on \"{a.get('job_name')}\" — check the job photos.",
                         "flag", {"assignment_id": assignment_id})
        await log_job_event(assignment_id, "crew_lead",
                            "Damage check: existing damage found (photos)" if found else "Damage check: no existing damage",
                            by=p["name"])

    elif tap_key == "loaded":
        await _lead_advance_status(a, "In Progress", p)
        await _lead_mark_checklist(assignment_id, "loading", p["name"])
        await log_job_event(assignment_id, "milestone", "Leaving pickup", by=p["name"])

    elif tap_key == "dropoff":
        await _lead_advance_status(a, "In Progress", p)
        await log_job_event(assignment_id, "milestone", "At drop-off", by=p["name"])

    elif tap_key == "complete":
        rec["delay_factors"] = [d for d in (payload.delay_factors or []) if d in DELAY_FACTORS]
        rec["as_found"] = (payload.notes or "").strip()[:1000]
        rec["lead_identity"] = ((payload.lead_identity or p["name"]) or "")[:120]
        await _lead_mark_checklist(assignment_id, "delivery", p["name"])
        await _lead_mark_checklist(assignment_id, "completion", p["name"])
        await _lead_advance_status(a, "Complete", p, notes=rec["as_found"] or None,
                                   delay_factors=rec["delay_factors"] or None)
        await log_job_event(assignment_id, "crew_lead", "Marked complete — all as quoted", by=p["name"])

    elif tap_key == "clock_out":
        rec["no_defects"] = payload.no_defects if payload.no_defects is not None else True
        is_last = await _truck_last_job_today(a)
        rec["last_job_of_day"] = is_last
        if is_last and a.get("truck_id"):
            posttrip = payload.posttrip_items
            if posttrip is None:
                posttrip = {k: bool(rec["no_defects"]) for k, _ in INSPECTION_ITEMS}
            insp = await _record_crew_inspection(a, posttrip, p, "post_trip")
            rec["posttrip"] = {"passed": insp["passed"], "failed": insp["failed_labels"]}
            if not insp["passed"]:
                await notify(None, "owner", "Post-trip defect reported",
                             f"{p['name']} flagged a post-trip defect on {a.get('truck_name')}: "
                             + ", ".join(insp["failed_labels"]) + ".",
                             "flag", {"assignment_id": assignment_id})
        await log_job_event(assignment_id, "crew_lead",
                            "Clocked out — post-trip " + ("no defects" if rec.get("no_defects") else "DEFECT flagged"),
                            by=p["name"])
        # Stage 3: this tap clocks out ONLY the Crew Lead's own punch — never the whole crew.
        own = await mongo_db.time_entries.find_one({"user_id": p["user_id"], "clock_out": None})
        if own:
            co = {"at": now_iso(), "lat": payload.lat, "lng": payload.lng, "accuracy": payload.accuracy}
            hrs = entry_hours({**own, "clock_out": co})
            await mongo_db.time_entries.update_one({"_id": own["_id"]}, {"$set": {"clock_out": co, "hours": hrs}})
            rec["clocked_out_entry"] = own["_id"]
            await queue_timelog_sync(own.get("assignment_id"))

    set_ops[f"crew_lead.taps.{tap_key}"] = rec
    set_ops["updated_at"] = now_iso()
    await mongo_db.assignments.update_one({"_id": assignment_id}, {"$set": set_ops})
    fresh = await mongo_db.assignments.find_one({"_id": assignment_id})
    return await _crew_lead_flow_state(fresh, p)


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
        if (payload.clock_in_at or payload.clock_out_at) and entry.get("assignment_id"):
            a = await mongo_db.assignments.find_one({"_id": entry["assignment_id"]})
            if a:   # Stage 3: keep a labeled record that the owner corrected this punch (already-resolved)
                await mongo_db.reliability_flags.insert_one({
                    "_id": str(uuid4()), "assignment_id": a["_id"], "job_name": a.get("job_name"),
                    "job_date": a.get("job_date"), "user_id": entry["user_id"], "user_name": entry.get("user_name"),
                    "type": "owner_correction", "status": "resolved", "detail": f"Owner edited {', '.join(changes)}.",
                    "meta": {"entry_id": entry_id}, "created_at": now_iso(),
                    "resolved_by": p["name"], "resolved_at": now_iso(), "resolve_reason": "Owner time-clock correction",
                    "disputed_at": None, "dispute_reason": None})
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
           "active": b.get("active", True), "unlock_reward": b.get("unlock_reward")}
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
    ur = badge.get("unlock_reward") or {}
    if (ur.get("points") or 0) > 0 or (ur.get("amount") or 0) > 0:
        await create_reward(
            user=user, team=badge.get("track") or "crew", source="badge",
            reward_type="cash" if (ur.get("amount") or 0) > 0 else "points",
            name=f"{badge['name']} milestone reward",
            amount=ur.get("amount") or 0, points=ur.get("points") or 0,
            reason=f"Unlocked the \u201c{badge['name']}\u201d badge",
            badge=badge)
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
        out["records"] = await _crew_work_record(user_id)
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
    unlock_points: Optional[int] = None
    unlock_amount: Optional[float] = None


class BadgePatchPayload(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    rarity: Optional[str] = None
    icon: Optional[str] = None
    active: Optional[bool] = None
    auto_metric: Optional[str] = None
    auto_threshold: Optional[int] = None
    unlock_points: Optional[int] = None
    unlock_amount: Optional[float] = None


def _unlock_reward_from(points: Optional[int], amount: Optional[float]) -> Optional[Dict[str, Any]]:
    pts, amt = max(0, int(points or 0)), max(0.0, float(amount or 0))
    return {"points": pts, "amount": round(amt, 2)} if (pts or amt) else None


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
           "unlock_reward": _unlock_reward_from(payload.unlock_points, payload.unlock_amount),
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
    if payload.unlock_points is not None or payload.unlock_amount is not None:
        updates["unlock_reward"] = _unlock_reward_from(payload.unlock_points, payload.unlock_amount)
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
    reward_amount: Optional[float] = None
    reward_points: Optional[int] = None
    reward_label: Optional[str] = None
    eligible_roles: str = "all"


async def challenge_progress(ch: Dict[str, Any]) -> List[Dict[str, Any]]:
    members = await _active_members(ch["team"])
    elig = ch.get("eligible_roles") or "all"
    if ch.get("metric") == "job_credits":
        docs = await mongo_db.job_credits.find(
            {"team": ch["team"], "date": {"$gte": ch["start"], "$lte": ch["end"]}}).to_list(5000)
        counts: Dict[str, int] = {}
        for d in docs:
            if ch["team"] == "crew" and elig in ("driver", "helper") and d.get("role_tag") != elig:
                continue
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
        won_bits: List[str] = []
        if reward.get("badge_id"):
            b = await mongo_db.badges.find_one({"_id": reward["badge_id"]})
            if b:
                await award_badge(u, b, by=f"challenge: {ch['name']}")
                won_bits.append(f"the \u201c{b['name']}\u201d badge")
        if reward.get("title"):
            await mongo_db.users.update_one({"_id": uid}, {"$addToSet": {"titles": reward["title"]}})
            won_bits.append(f"the \u201c{reward['title']}\u201d title")
        amount = float(reward.get("amount") or 0)
        points = int(reward.get("points") or 0)
        if amount > 0 or points > 0:
            rtype = reward.get("kind") if reward.get("kind") in REWARD_TYPES else ("cash" if amount > 0 else "points")
            await create_reward(
                user=u, team=ch["team"], source="challenge", reward_type=rtype,
                name=reward.get("label") or f"{ch['name']} reward",
                amount=amount, points=points,
                reason=f"Won the \u201c{ch['name']}\u201d challenge", challenge=ch)
            if amount > 0:
                won_bits.append(f"a ${amount:g} reward (pending owner approval)")
            if points > 0:
                won_bits.append(f"{points} Haul Points (pending owner approval)")
        elif reward.get("label"):
            await create_reward(
                user=u, team=ch["team"], source="challenge",
                reward_type=reward.get("kind") if reward.get("kind") in REWARD_TYPES else "custom",
                name=reward["label"], amount=0, points=0,
                reason=f"Won the \u201c{ch['name']}\u201d challenge", challenge=ch)
            won_bits.append(f"{reward['label']} (pending owner approval)")
        if won_bits:
            await notify(uid, None, "\U0001F3C6 Challenge complete!",
                         f"You won \u201c{ch['name']}\u201d \u2014 you earned {', '.join(won_bits)}.",
                         "challenge", {"challenge_id": ch["_id"], "celebrate": True})
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
        if ch.get("type") in ("individual", "team"):
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
            "eligible_roles": ch.get("eligible_roles") or "all",
            "created_by": ch.get("created_by"), "ai": ch.get("ai"),
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


CHALLENGE_REWARD_KINDS = ("badge", "title", "cash", "gift_card", "points", "merch", "meal", "custom", "combo")


async def _validate_challenge(payload: ChallengePayload) -> Dict[str, Any]:
    if payload.team not in TEAMS:
        raise HTTPException(status_code=422, detail="Team must be crew or sales.")
    if payload.type not in ("individual", "competition", "team"):
        raise HTTPException(status_code=422, detail="Type must be individual, competition, or team.")
    if payload.metric not in ("job_credits", "owner_verified"):
        raise HTTPException(status_code=422, detail="Metric must be job_credits or owner_verified.")
    if payload.type in ("individual", "team") and (not payload.target or payload.target < 1):
        raise HTTPException(status_code=422, detail="Individual and team challenges need a goal count of 1 or more.")
    if not payload.start or not payload.end or payload.end < payload.start:
        raise HTTPException(status_code=422, detail="Check the start and end dates.")
    if payload.eligible_roles not in ("all", "driver", "helper", "dual"):
        raise HTTPException(status_code=422, detail="Eligibility must be all, driver, helper, or dual.")
    if payload.team == "sales" and payload.eligible_roles != "all":
        raise HTTPException(status_code=422, detail="Sales challenges are open to the whole sales team.")
    kind = payload.reward_kind
    if kind not in CHALLENGE_REWARD_KINDS:
        raise HTTPException(status_code=422, detail="That reward type doesn't exist.")
    amount = round(max(0.0, float(payload.reward_amount or 0)), 2)
    points = max(0, int(payload.reward_points or 0))
    label = (payload.reward_label or "").strip()[:120]
    badge_id = payload.reward_badge_id if kind in ("badge", "combo") else None
    title = (payload.reward_title or "").strip() if kind in ("title", "combo") else ""
    if kind == "badge" and not badge_id:
        raise HTTPException(status_code=422, detail="Pick the badge to give out.")
    if kind == "title" and not title:
        raise HTTPException(status_code=422, detail="Type the title to give out.")
    if kind in ("cash",) and amount <= 0:
        raise HTTPException(status_code=422, detail="Cash rewards need a dollar amount.")
    if kind == "points" and points <= 0:
        raise HTTPException(status_code=422, detail="Point rewards need a Haul Points amount.")
    if kind in ("gift_card", "merch", "meal", "custom") and not label and amount <= 0 and points <= 0:
        raise HTTPException(status_code=422, detail="Describe the reward (and give it a value if it has one).")
    if kind == "combo" and not (badge_id or title or amount > 0 or points > 0 or label):
        raise HTTPException(status_code=422, detail="A combo reward needs at least one part.")
    cfg = await get_rewards_config()
    if kind not in ("badge", "title"):
        base_kind = "cash" if kind == "combo" and amount > 0 else kind
        if base_kind in ("cash", "gift_card", "points", "merch", "meal", "custom") and base_kind not in (cfg.get("enabledRewardTypes") or []):
            raise HTTPException(status_code=422, detail=f"{base_kind.replace('_', ' ').title()} rewards are turned off in Reward settings.")
    value = amount + points / max(1.0, float(cfg.get("pointsPerDollar") or 10))
    if value > float(cfg.get("maxSingleReward") or 0) > 0:
        raise HTTPException(status_code=422,
                            detail=f"That reward is worth ${value:.0f} \u2014 over your ${cfg['maxSingleReward']:g} single-reward cap (Reward settings).")
    reward: Dict[str, Any] = {"kind": kind}
    if badge_id:
        b = await mongo_db.badges.find_one({"_id": badge_id})
        if not b:
            raise HTTPException(status_code=422, detail="That badge doesn't exist.")
        reward["badge_id"] = badge_id
        reward["badge_name"] = b["name"]
    if title:
        reward["title"] = title
    if amount > 0:
        reward["amount"] = amount
    if points > 0:
        reward["points"] = points
    if label:
        reward["label"] = label
    return reward


@api_router.post("/challenges")
async def create_challenge(payload: ChallengePayload, p: Dict[str, Any] = Depends(require_owner)):
    reward = await _validate_challenge(payload)
    doc = {"_id": str(uuid4()), "name": payload.name.strip(), "description": payload.description.strip(),
           "team": payload.team, "type": payload.type, "metric": payload.metric,
           "target": payload.target if payload.type in ("individual", "team") else None,
           "start": payload.start, "end": payload.end, "reward": reward, "status": "active",
           "eligible_roles": payload.eligible_roles,
           "verified": {}, "winners": [], "created_by": p.get("name"), "created_at": now_iso()}
    await mongo_db.challenges.insert_one(doc)
    await audit(p, "created a challenge", f"{doc['name']} ({payload.team}, {payload.type})")
    for m in await _active_members(payload.team):
        await notify(m["_id"], None, "New challenge just dropped",
                     f"\u201c{doc['name']}\u201d is live for the {payload.team} team \u2014 check the Challenges page.",
                     "challenge", {"challenge_id": doc["_id"]})
    return _challenge_out(doc, await challenge_progress(doc))


@api_router.patch("/challenges/{challenge_id}")
async def patch_challenge(challenge_id: str, payload: ChallengePayload, p: Dict[str, Any] = Depends(require_owner)):
    ch = await mongo_db.challenges.find_one({"_id": challenge_id})
    if not ch:
        raise HTTPException(status_code=404, detail="No such challenge.")
    if ch.get("status") == "awarded":
        raise HTTPException(status_code=422, detail="That challenge already paid out \u2014 make a new one instead.")
    reward = await _validate_challenge(payload)
    await mongo_db.challenges.update_one(
        {"_id": challenge_id},
        {"$set": {"name": payload.name.strip(), "description": payload.description.strip(),
                  "team": payload.team, "type": payload.type, "metric": payload.metric,
                  "target": payload.target if payload.type in ("individual", "team") else None,
                  "start": payload.start, "end": payload.end, "reward": reward,
                  "eligible_roles": payload.eligible_roles}})
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


BADGE_UNLOCK_SEEDS = {
    "truck-boss": {"points": 250, "amount": 0},
    "haul-of-famer": {"points": 500, "amount": 0},
    "two-way-player": {"points": 500, "amount": 0},
    "five-star-shoutout": {"points": 250, "amount": 0},
    "road-captain": {"points": 250, "amount": 0},
    "deal-dozen": {"points": 250, "amount": 0},
    "quarter-club": {"points": 500, "amount": 0},
    "deposit-locksmith": {"points": 250, "amount": 0},
    "comeback-kid": {"points": 250, "amount": 0},
}


async def seed_team_module():
    for i, (slug, track, name, desc, rarity, icon, metric, thr) in enumerate(BADGE_SEEDS):
        await mongo_db.badges.update_one(
            {"_id": slug},
            {"$setOnInsert": {"_id": slug, "track": track, "name": name, "description": desc, "rarity": rarity,
                              "icon": icon, "auto": ({"metric": metric, "threshold": thr} if metric else None),
                              "active": True, "seeded": True, "sort": i, "created_at": now_iso()}},
            upsert=True)
    for slug, ur in BADGE_UNLOCK_SEEDS.items():
        await mongo_db.badges.update_one({"_id": slug, "unlock_reward": {"$exists": False}},
                                         {"$set": {"unlock_reward": ur}})
    if await mongo_db.reward_catalog.count_documents({}) == 0:
        for slug, name, pts, value, kind in CATALOG_SEEDS:
            await mongo_db.reward_catalog.update_one(
                {"_id": slug},
                {"$setOnInsert": {"_id": slug, "name": name, "points_cost": pts, "value": value, "kind": kind,
                                  "active": True, "created_at": now_iso()}},
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


# ================================================================ rewards engine (Haul Points, reward records, budgets)

REWARD_TYPES = ("cash", "gift_card", "points", "merch", "meal", "custom", "redemption")
REWARD_STATUSES = ("pending", "approved", "fulfilled", "denied", "voided")

DEFAULT_REWARDS_CONFIG = {
    "pointsPerDollar": 10.0,            # 10 Haul Points = $1
    "crewMonthlyBudget": 300.0,
    "salesMonthlyBudget": 400.0,
    "maxSingleReward": 250.0,
    "enabledRewardTypes": ["points", "cash", "gift_card", "merch", "meal", "custom"],
    "aiEnabled": True,
    "aiMonthlyGeneration": True,
    "aiAutoPublish": False,
    "aiRequireApproval": True,
    "aiCrewChallengesPerMonth": 2,
    "aiSalesChallengesPerMonth": 2,
    "aiDifficulty": "moderate",
    "aiMaxRewardPerChallenge": 100.0,
    "aiCrewMonthlyBudget": 200.0,
    "aiSalesMonthlyBudget": 250.0,
    "aiAllowCompetition": True,
    "aiAllowTeamChallenges": True,
    "aiAllowPoints": True,
    "aiAllowCash": True,
    "aiAllowGiftCards": True,
}


async def get_rewards_config() -> Dict[str, Any]:
    doc = await mongo_db.settings.find_one({"_id": "rewards_config"}) or {}
    stored = doc.get("values") or {}
    out = dict(DEFAULT_REWARDS_CONFIG)
    for k, v in stored.items():
        if k in out:
            out[k] = v
    return out


@api_router.get("/rewards/config")
async def rewards_config(p: Dict[str, Any] = Depends(require_owner)):
    return await get_rewards_config()


@api_router.put("/rewards/config")
async def save_rewards_config(payload: Dict[str, Any] = Body(...), p: Dict[str, Any] = Depends(require_owner)):
    current = await get_rewards_config()
    values = dict(current)
    for k, v in payload.items():
        if k not in DEFAULT_REWARDS_CONFIG:
            continue
        default = DEFAULT_REWARDS_CONFIG[k]
        if isinstance(default, bool):
            values[k] = bool(v)
        elif isinstance(default, list):
            values[k] = [x for x in (v or []) if x in REWARD_TYPES]
        elif isinstance(default, str):
            values[k] = str(v or default)[:40]
        else:
            try:
                n = float(v)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail=f"'{k}' must be a number.")
            if n < 0:
                raise HTTPException(status_code=422, detail="Reward settings can't be negative.")
            values[k] = int(n) if isinstance(default, int) else n
    if values["pointsPerDollar"] < 1:
        raise HTTPException(status_code=422, detail="Points per dollar must be at least 1.")
    await mongo_db.settings.update_one({"_id": "rewards_config"},
                                       {"$set": {"values": values, "updated_at": now_iso()}}, upsert=True)
    await audit(p, "changed reward settings", "")
    return values


def reward_dollar_value(amount: float, points: int, cfg: Dict[str, Any]) -> float:
    return round(float(amount or 0) + int(points or 0) / max(1.0, float(cfg.get("pointsPerDollar") or 10)), 2)


def _reward_out(r: Dict[str, Any]) -> Dict[str, Any]:
    return {k: r.get(k) for k in (
        "user_id", "user_name", "team", "challenge_id", "challenge_name", "badge_id", "badge_name",
        "reward_type", "reward_name", "amount", "points", "earned_at", "reason", "status",
        "approved_by", "approved_at", "fulfilled_by", "fulfilled_at", "payroll_required",
        "payroll_period", "notes", "void_reason", "source", "created_at", "updated_at")} | {"id": r["_id"]}


async def create_reward(user: Dict[str, Any], team: str, source: str, reward_type: str, name: str,
                        amount: float = 0, points: int = 0, reason: str = "",
                        challenge: Optional[Dict[str, Any]] = None, badge: Optional[Dict[str, Any]] = None,
                        status: str = "pending", payroll_required: Optional[bool] = None) -> Dict[str, Any]:
    if payroll_required is None:
        payroll_required = reward_type in ("cash", "gift_card") and float(amount or 0) > 0
    doc = {"_id": str(uuid4()), "user_id": user["_id"], "user_name": user.get("name", ""),
           "team": team if team in TEAMS else "crew",
           "challenge_id": (challenge or {}).get("_id"), "challenge_name": (challenge or {}).get("name"),
           "badge_id": (badge or {}).get("_id"), "badge_name": (badge or {}).get("name"),
           "reward_type": reward_type if reward_type in REWARD_TYPES else "custom",
           "reward_name": (name or "Reward").strip()[:140],
           "amount": round(float(amount or 0), 2), "points": int(points or 0),
           "earned_at": now_iso(), "reason": (reason or "").strip()[:300], "status": status,
           "approved_by": None, "approved_at": None, "fulfilled_by": None, "fulfilled_at": None,
           "payroll_required": bool(payroll_required), "payroll_period": _et_today()[:7],
           "notes": "", "void_reason": "", "source": source,
           "created_at": now_iso(), "updated_at": now_iso()}
    await mongo_db.rewards.insert_one(doc)
    if status == "pending":
        await notify(user["_id"], None, "You earned a reward!",
                     f"{doc['reward_name']} \u2014 {reason or 'nice work'}. It's waiting on the owner's approval.",
                     "reward", {"reward_id": doc["_id"]})
    return doc


async def credit_points(user_id: str, delta: int, reason: str, reward_id: Optional[str], actor_name: str) -> int:
    u = await mongo_db.users.find_one({"_id": user_id})
    if not u:
        raise HTTPException(status_code=404, detail="No such member.")
    balance = int(u.get("haul_points") or 0) + int(delta)
    if balance < 0:
        raise HTTPException(status_code=422, detail="Not enough Haul Points for that.")
    lifetime = int(u.get("haul_points_lifetime") or 0) + (int(delta) if delta > 0 else 0)
    await mongo_db.users.update_one({"_id": user_id},
                                    {"$set": {"haul_points": balance, "haul_points_lifetime": lifetime}})
    await mongo_db.points_ledger.insert_one({"_id": str(uuid4()), "user_id": user_id, "delta": int(delta),
                                             "balance_after": balance, "reason": (reason or "")[:200],
                                             "reward_id": reward_id, "actor": actor_name, "created_at": now_iso()})
    if delta > 0:
        await notify(user_id, None, f"+{delta} Haul Points",
                     f"{reason or 'Points added'}. Your balance is now {balance}.", "reward")
    return balance


@api_router.get("/rewards")
async def list_rewards(status: Optional[str] = None, month: Optional[str] = None, user_id: Optional[str] = None,
                       p: Dict[str, Any] = Depends(require_owner)):
    q: Dict[str, Any] = {}
    if status in REWARD_STATUSES:
        q["status"] = status
    if month:
        q["earned_at"] = {"$regex": f"^{month[:7]}"}
    if user_id:
        q["user_id"] = user_id
    docs = await mongo_db.rewards.find(q).sort("earned_at", -1).to_list(400)
    return {"rewards": [_reward_out(r) for r in docs]}


class RewardActionPayload(BaseModel):
    reason: str = ""
    notes: str = ""


@api_router.post("/rewards/{reward_id}/approve")
async def approve_reward(reward_id: str, p: Dict[str, Any] = Depends(require_owner)):
    r = await mongo_db.rewards.find_one({"_id": reward_id})
    if not r:
        raise HTTPException(status_code=404, detail="No such reward.")
    if r["status"] != "pending":
        raise HTTPException(status_code=422, detail="Only pending rewards can be approved \u2014 this one already moved on.")
    if r["reward_type"] == "redemption":
        await credit_points(r["user_id"], -int(r.get("points") or 0),
                            f"Redeemed: {r['reward_name']}", reward_id, p.get("name") or "owner")
    elif int(r.get("points") or 0) > 0:
        await credit_points(r["user_id"], int(r["points"]),
                            r.get("reason") or r["reward_name"], reward_id, p.get("name") or "owner")
    await mongo_db.rewards.update_one({"_id": reward_id},
                                      {"$set": {"status": "approved", "approved_by": p.get("name"),
                                                "approved_at": now_iso(), "updated_at": now_iso()}})
    await notify(r["user_id"], None, "Reward approved \u2705",
                 f"{r['reward_name']} was approved" + (" \u2014 you'll get it shortly." if r["reward_type"] != "points" else "."),
                 "reward", {"reward_id": reward_id})
    await audit(p, "approved a reward", f"{r['reward_name']} \u2192 {r.get('user_name', '')}")
    fresh = await mongo_db.rewards.find_one({"_id": reward_id})
    return _reward_out(fresh)


@api_router.post("/rewards/{reward_id}/fulfill")
async def fulfill_reward(reward_id: str, payload: RewardActionPayload = Body(default=RewardActionPayload()),
                         p: Dict[str, Any] = Depends(require_owner)):
    r = await mongo_db.rewards.find_one({"_id": reward_id})
    if not r:
        raise HTTPException(status_code=404, detail="No such reward.")
    if r["status"] != "approved":
        raise HTTPException(status_code=422, detail="Approve it first \u2014 rewards can only be fulfilled once, after approval.")
    await mongo_db.rewards.update_one({"_id": reward_id},
                                      {"$set": {"status": "fulfilled", "fulfilled_by": p.get("name"),
                                                "fulfilled_at": now_iso(), "notes": (payload.notes or "").strip()[:300],
                                                "updated_at": now_iso()}})
    await notify(r["user_id"], None, "Reward delivered \U0001F389",
                 f"{r['reward_name']} is done and on your record.", "reward", {"reward_id": reward_id})
    await audit(p, "fulfilled a reward", f"{r['reward_name']} \u2192 {r.get('user_name', '')}")
    fresh = await mongo_db.rewards.find_one({"_id": reward_id})
    return _reward_out(fresh)


@api_router.post("/rewards/{reward_id}/deny")
async def deny_reward(reward_id: str, payload: RewardActionPayload = Body(default=RewardActionPayload()),
                      p: Dict[str, Any] = Depends(require_owner)):
    r = await mongo_db.rewards.find_one({"_id": reward_id})
    if not r:
        raise HTTPException(status_code=404, detail="No such reward.")
    if r["status"] != "pending":
        raise HTTPException(status_code=422, detail="Only pending rewards can be denied.")
    await mongo_db.rewards.update_one({"_id": reward_id},
                                      {"$set": {"status": "denied", "void_reason": (payload.reason or "").strip()[:300],
                                                "updated_at": now_iso()}})
    await audit(p, "denied a reward", f"{r['reward_name']} \u2192 {r.get('user_name', '')}")
    return {"ok": True}


@api_router.post("/rewards/{reward_id}/void")
async def void_reward(reward_id: str, payload: RewardActionPayload = Body(default=RewardActionPayload()),
                      p: Dict[str, Any] = Depends(require_owner)):
    r = await mongo_db.rewards.find_one({"_id": reward_id})
    if not r:
        raise HTTPException(status_code=404, detail="No such reward.")
    if r["status"] not in ("pending", "approved", "fulfilled"):
        raise HTTPException(status_code=422, detail="That reward is already closed out.")
    if r["status"] in ("approved", "fulfilled"):
        if r["reward_type"] == "redemption" and int(r.get("points") or 0) > 0:
            await credit_points(r["user_id"], int(r["points"]), f"Refund: {r['reward_name']} voided",
                                reward_id, p.get("name") or "owner")
        elif int(r.get("points") or 0) > 0:
            await credit_points(r["user_id"], -int(r["points"]), f"Reversed: {r['reward_name']} voided",
                                reward_id, p.get("name") or "owner")
    await mongo_db.rewards.update_one({"_id": reward_id},
                                      {"$set": {"status": "voided", "void_reason": (payload.reason or "").strip()[:300],
                                                "updated_at": now_iso()}})
    await audit(p, "voided a reward", f"{r['reward_name']} \u2192 {r.get('user_name', '')}")
    return {"ok": True}


@api_router.get("/rewards/summary")
async def rewards_summary(month: Optional[str] = None, p: Dict[str, Any] = Depends(require_owner)):
    cfg = await get_rewards_config()
    m = (month or _et_today())[:7]
    docs = await mongo_db.rewards.find({"earned_at": {"$regex": f"^{m}"}}).to_list(2000)
    live = [r for r in docs if r["status"] in ("pending", "approved", "fulfilled")]
    committed = {"crew": 0.0, "sales": 0.0}
    totals = {"cash": 0.0, "gift_card": 0.0, "points_issued": 0, "points_redeemed": 0, "other": 0.0, "total_value": 0.0}
    counts = {s: 0 for s in REWARD_STATUSES}
    for r in docs:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    for r in live:
        if r["reward_type"] == "redemption":
            if r["status"] in ("approved", "fulfilled"):
                totals["points_redeemed"] += int(r.get("points") or 0)
            continue
        v = reward_dollar_value(r.get("amount") or 0, r.get("points") or 0, cfg)
        committed[r.get("team") or "crew"] = committed.get(r.get("team") or "crew", 0) + v
        totals["total_value"] += v
        if r["reward_type"] == "cash":
            totals["cash"] += float(r.get("amount") or 0)
        elif r["reward_type"] == "gift_card":
            totals["gift_card"] += float(r.get("amount") or 0)
        else:
            totals["other"] += float(r.get("amount") or 0)
        if r["status"] in ("approved", "fulfilled"):
            totals["points_issued"] += int(r.get("points") or 0)
    ai_spent = {"crew": 0.0, "sales": 0.0}
    ai_chs = await mongo_db.challenges.find({"created_by": "ai-agent", "start": {"$regex": f"^{m}"}}).to_list(100)
    for ch in ai_chs:
        ai_spent[ch["team"]] = ai_spent.get(ch["team"], 0) + float(ch.get("estimated_cost") or 0)
    return {"month": m, "counts": counts,
            "totals": {k: round(v, 2) if isinstance(v, float) else v for k, v in totals.items()},
            "budgets": {
                "crew": {"budget": cfg["crewMonthlyBudget"], "committed": round(committed["crew"], 2),
                         "remaining": round(cfg["crewMonthlyBudget"] - committed["crew"], 2)},
                "sales": {"budget": cfg["salesMonthlyBudget"], "committed": round(committed["sales"], 2),
                          "remaining": round(cfg["salesMonthlyBudget"] - committed["sales"], 2)}},
            "ai_budgets": {
                "crew": {"budget": cfg["aiCrewMonthlyBudget"], "committed": round(ai_spent["crew"], 2)},
                "sales": {"budget": cfg["aiSalesMonthlyBudget"], "committed": round(ai_spent["sales"], 2)}}}


@api_router.get("/rewards/payroll")
async def rewards_payroll_csv(month: Optional[str] = None, p: Dict[str, Any] = Depends(require_owner)):
    import csv
    import io
    m = (month or _et_today())[:7]
    docs = await mongo_db.rewards.find({"payroll_required": True, "status": {"$in": ["approved", "fulfilled"]},
                                        "payroll_period": m}).sort("earned_at", 1).to_list(1000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Employee", "Reward", "Type", "Amount", "Points", "Date earned", "Date approved",
                "Payroll period", "Challenge", "Reward ID"])
    for r in docs:
        w.writerow([r.get("user_name", ""), r.get("reward_name", ""), r.get("reward_type", ""),
                    f"{float(r.get('amount') or 0):.2f}", r.get("points") or 0,
                    (r.get("earned_at") or "")[:10], (r.get("approved_at") or "")[:10],
                    r.get("payroll_period", ""), r.get("challenge_name") or "", r["_id"]])
    await audit(p, "exported the rewards payroll CSV", m)
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=rewards-payroll-{m}.csv"})


# ------- reward catalog & redemption

CATALOG_SEEDS = [
    ("amazon-25", "$25 Amazon gift card", 250, 25.0, "gift_card"),
    ("gas-25", "$25 gas gift card", 250, 25.0, "gift_card"),
    ("restaurant-25", "$25 restaurant gift card", 250, 25.0, "gift_card"),
    ("visa-50", "$50 Visa gift card", 500, 50.0, "gift_card"),
    ("amazon-50", "$50 Amazon gift card", 500, 50.0, "gift_card"),
    ("merch-50", "Haul Yeah merch package", 500, 50.0, "merch"),
    ("lunch-team", "Lunch on the company", 500, 50.0, "meal"),
    ("gift-100", "$100 gift card (your pick)", 1000, 100.0, "gift_card"),
    ("payroll-100", "$100 payroll bonus", 1000, 100.0, "cash"),
]


def _catalog_out(c: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": c["_id"], "name": c["name"], "points_cost": c["points_cost"], "value": c.get("value") or 0,
            "kind": c.get("kind", "custom"), "active": c.get("active", True)}


@api_router.get("/rewards/catalog")
async def rewards_catalog(request: Request):
    p = await current_principal(request)
    docs = await mongo_db.reward_catalog.find({}).sort("points_cost", 1).to_list(100)
    balance = 0
    if p.get("user_id"):
        u = await mongo_db.users.find_one({"_id": p["user_id"]}, {"haul_points": 1})
        balance = int((u or {}).get("haul_points") or 0)
    items = [_catalog_out(c) for c in docs if c.get("active", True) or p["role"] == "owner"]
    return {"items": items, "balance": balance, "is_owner": p["role"] == "owner"}


class CatalogPayload(BaseModel):
    name: str
    points_cost: int
    value: float = 0
    kind: str = "gift_card"
    active: bool = True


@api_router.post("/rewards/catalog")
async def create_catalog_item(payload: CatalogPayload, p: Dict[str, Any] = Depends(require_owner)):
    if payload.points_cost < 1 or not payload.name.strip():
        raise HTTPException(status_code=422, detail="Give it a name and a points cost of 1 or more.")
    doc = {"_id": str(uuid4()), "name": payload.name.strip()[:120], "points_cost": int(payload.points_cost),
           "value": round(max(0.0, payload.value), 2), "kind": payload.kind if payload.kind in REWARD_TYPES else "custom",
           "active": bool(payload.active), "created_at": now_iso()}
    await mongo_db.reward_catalog.insert_one(doc)
    await audit(p, "added a catalog reward", doc["name"])
    return _catalog_out(doc)


@api_router.patch("/rewards/catalog/{item_id}")
async def patch_catalog_item(item_id: str, payload: CatalogPayload, p: Dict[str, Any] = Depends(require_owner)):
    c = await mongo_db.reward_catalog.find_one({"_id": item_id})
    if not c:
        raise HTTPException(status_code=404, detail="No such catalog reward.")
    await mongo_db.reward_catalog.update_one(
        {"_id": item_id},
        {"$set": {"name": payload.name.strip()[:120] or c["name"], "points_cost": max(1, int(payload.points_cost)),
                  "value": round(max(0.0, payload.value), 2),
                  "kind": payload.kind if payload.kind in REWARD_TYPES else c.get("kind", "custom"),
                  "active": bool(payload.active)}})
    await audit(p, "edited a catalog reward", payload.name.strip())
    fresh = await mongo_db.reward_catalog.find_one({"_id": item_id})
    return _catalog_out(fresh)


class RedeemPayload(BaseModel):
    catalog_id: str


@api_router.post("/rewards/redeem")
async def redeem_points(payload: RedeemPayload, request: Request):
    p = await current_principal(request)
    if not p.get("user_id"):
        raise HTTPException(status_code=403, detail="Only user accounts can redeem points.")
    item = await mongo_db.reward_catalog.find_one({"_id": payload.catalog_id, "active": True})
    if not item:
        raise HTTPException(status_code=404, detail="That reward isn't available.")
    u = await mongo_db.users.find_one({"_id": p["user_id"]})
    pending = await mongo_db.rewards.find({"user_id": p["user_id"], "reward_type": "redemption",
                                           "status": "pending"}).to_list(50)
    held = sum(int(r.get("points") or 0) for r in pending)
    available = int(u.get("haul_points") or 0) - held
    if available < item["points_cost"]:
        raise HTTPException(status_code=422,
                            detail=f"You need {item['points_cost']} available points \u2014 you have {max(0, available)} (pending requests hold points too).")
    team = (teams_for_roles(u.get("roles") or [u.get("role")]) or ["crew"])[0]
    doc = await create_reward(user=u, team=team, source="redemption", reward_type="redemption",
                              name=item["name"], amount=item.get("value") or 0, points=item["points_cost"],
                              reason="Haul Points redemption request",
                              payroll_required=item.get("kind") == "cash", status="pending")
    await notify(None, "owner", "Redemption request",
                 f"{u.get('name', 'Someone')} wants to redeem {item['points_cost']} Haul Points for \u201c{item['name']}\u201d. Review it in Team HQ \u2192 Rewards.",
                 "reward", {"reward_id": doc["_id"]})
    await audit(p, "requested a redemption", item["name"])
    return _reward_out(doc)


@api_router.get("/rewards/wallet")
async def rewards_wallet(request: Request, user_id: Optional[str] = None):
    p = await current_principal(request)
    target = user_id or p.get("user_id")
    if not target:
        raise HTTPException(status_code=403, detail="Only user accounts have a rewards wallet.")
    if target != p.get("user_id") and p["role"] != "owner":
        raise HTTPException(status_code=403, detail="Reward history is private \u2014 you can only see your own.")
    u = await mongo_db.users.find_one({"_id": target})
    if not u:
        raise HTTPException(status_code=404, detail="No such member.")
    rewards = await mongo_db.rewards.find({"user_id": target}).sort("earned_at", -1).to_list(200)
    ledger = await mongo_db.points_ledger.find({"user_id": target}).sort("created_at", -1).to_list(50)
    live = [r for r in rewards if r["status"] in ("pending", "approved", "fulfilled")]
    cash_earned = sum(float(r.get("amount") or 0) for r in live
                      if r["reward_type"] == "cash" and r["status"] == "fulfilled")
    gift_earned = sum(float(r.get("amount") or 0) for r in live
                      if r["reward_type"] == "gift_card" and r["status"] == "fulfilled")
    pending_pts = sum(int(r.get("points") or 0) for r in rewards
                      if r["status"] == "pending" and r["reward_type"] != "redemption")
    held_pts = sum(int(r.get("points") or 0) for r in rewards
                   if r["status"] == "pending" and r["reward_type"] == "redemption")
    return {"user_id": target, "name": u.get("name", ""),
            "balance": int(u.get("haul_points") or 0), "lifetime": int(u.get("haul_points_lifetime") or 0),
            "pending_points": pending_pts, "held_points": held_pts,
            "cash_earned": round(cash_earned, 2), "gift_cards_earned": round(gift_earned, 2),
            "pending_count": sum(1 for r in rewards if r["status"] == "pending"),
            "rewards": [_reward_out(r) for r in rewards],
            "ledger": [{"delta": d["delta"], "balance_after": d["balance_after"], "reason": d.get("reason", ""),
                        "created_at": d["created_at"]} for d in ledger]}


class RecognitionPayload(BaseModel):
    user_id: str
    reason: str
    points: int = 0
    amount: float = 0
    badge_id: str = ""
    title: str = ""
    reward_name: str = ""


@api_router.post("/rewards/recognition")
async def give_recognition(payload: RecognitionPayload, p: Dict[str, Any] = Depends(require_owner)):
    if not (payload.reason or "").strip():
        raise HTTPException(status_code=422, detail="Say why \u2014 the reason goes on the record.")
    u = await mongo_db.users.find_one({"_id": payload.user_id})
    if not u:
        raise HTTPException(status_code=404, detail="No such member.")
    cfg = await get_rewards_config()
    given: List[str] = []
    if payload.badge_id:
        b = await mongo_db.badges.find_one({"_id": payload.badge_id})
        if not b:
            raise HTTPException(status_code=404, detail="No such badge.")
        if await award_badge(u, b, by=p.get("name") or "owner"):
            given.append(f"the \u201c{b['name']}\u201d badge")
    if (payload.title or "").strip():
        await mongo_db.users.update_one({"_id": payload.user_id}, {"$addToSet": {"titles": payload.title.strip()[:60]}})
        given.append(f"the \u201c{payload.title.strip()}\u201d title")
    points, amount = max(0, int(payload.points or 0)), round(max(0.0, float(payload.amount or 0)), 2)
    if points or amount:
        if reward_dollar_value(amount, points, cfg) > float(cfg["maxSingleReward"]):
            raise HTTPException(status_code=422,
                                detail=f"That's over your ${cfg['maxSingleReward']:g} single-reward cap (Reward settings).")
        team = (teams_for_roles(u.get("roles") or [u.get("role")]) or ["crew"])[0]
        r = await create_reward(user=u, team=team, source="recognition",
                                reward_type="cash" if amount > 0 else "points",
                                name=(payload.reward_name or "").strip() or "Owner recognition",
                                amount=amount, points=points, reason=payload.reason.strip(), status="approved")
        await mongo_db.rewards.update_one({"_id": r["_id"]},
                                          {"$set": {"approved_by": p.get("name"), "approved_at": now_iso()}})
        if points:
            await credit_points(payload.user_id, points, payload.reason.strip(), r["_id"], p.get("name") or "owner")
            given.append(f"{points} Haul Points")
        if amount:
            given.append(f"a ${amount:g} spot bonus")
    if not given:
        raise HTTPException(status_code=422, detail="Pick at least one thing to give \u2014 a badge, title, points, or bonus.")
    await notify(payload.user_id, None, "\U0001F31F The owner recognized you",
                 f"\u201c{payload.reason.strip()}\u201d \u2014 you earned {', '.join(given)}.", "reward")
    await audit(p, "gave recognition", f"{u.get('name', '')} \u2014 {', '.join(given)} ({payload.reason.strip()[:80]})")
    return {"ok": True, "given": given}


# ================================================================ AI challenge agent

AGENT_BANNED = re.compile(
    r"fastest|quickest|speed[- ]?run|shortest (?:job|time)|fewest breaks|skip(?:ping)? break|most hours|"
    r"overtime|off the clock|injur|no damage|without (?:a )?damage|hide|hiding|conceal|heaviest|"
    r"work(?:ing)? sick|no sick|fewest (?:reported )?(?:injuries|claims)|overcharg|inflat|upsell past|fake",
    re.IGNORECASE)

AGENT_CATEGORIES = {
    "crew": ["customer_service", "safety", "quality", "reliability", "teamwork", "leadership",
             "job_volume", "skill_development", "documentation"],
    "sales": ["closes", "revenue", "deposits", "conversion", "follow_up", "revived_leads",
              "consistency", "crm_quality"],
}

# target_rule: (baseline_key, multiplier, minimum). baseline keys come from _agent_baselines().
CHALLENGE_TEMPLATES = [
    {"key": "customer-hero", "team": "crew", "name": "Customer Hero", "category": "customer_service",
     "metric": "owner_verified", "type": "individual", "eligible_roles": "all", "target_rule": ("fixed", 0, 3),
     "reward": {"kind": "points", "points": 500},
     "desc": "Get {target} verified positive customer mentions this period \u2014 reviews, texts, or direct shout-outs. The owner confirms each one."},
    {"key": "safety-scout", "team": "crew", "name": "Safety Scout", "category": "safety",
     "metric": "owner_verified", "type": "individual", "eligible_roles": "all", "target_rule": ("fixed", 0, 1),
     "reward": {"kind": "points", "points": 250},
     "desc": "Report a legitimate hazard or near-miss, or land an approved safety improvement. One award per period \u2014 honest reporting never costs anyone a reward."},
    {"key": "ready-to-roll", "team": "crew", "name": "Ready to Roll", "category": "quality",
     "metric": "owner_verified", "type": "individual", "eligible_roles": "all", "target_rule": ("jobs_pm", 0.8, 3),
     "reward": {"kind": "points", "points": 250},
     "desc": "Complete the full pre-job prep and truck check on {target} jobs this period. The owner confirms the count."},
    {"key": "road-captain-month", "team": "crew", "name": "Road Captain of the Month", "category": "leadership",
     "metric": "owner_verified", "type": "competition", "eligible_roles": "driver", "target_rule": None,
     "reward": {"kind": "cash", "amount": 75},
     "desc": "Drivers only. Best combination of completed jobs, clean documentation, reliability and customer feedback. The owner picks the winner \u2014 driving safely always beats driving fast."},
    {"key": "crew-mvp", "team": "crew", "name": "Crew MVP", "category": "teamwork",
     "metric": "owner_verified", "type": "competition", "eligible_roles": "all", "target_rule": None,
     "reward": {"kind": "cash", "amount": 100},
     "desc": "Balanced score across job credits, customer recognition, reliability, documentation and teamwork. The owner confirms the winner."},
    {"key": "team-player", "team": "crew", "name": "Team Player", "category": "teamwork",
     "metric": "owner_verified", "type": "individual", "eligible_roles": "all", "target_rule": ("fixed", 0, 1),
     "reward": {"kind": "points", "points": 250},
     "desc": "Step up for a teammate when it matters \u2014 covering a shift, helping another crew, coaching a new hire. Owner-awarded, not farmable."},
    {"key": "perfect-prep", "team": "crew", "name": "Perfect Prep Team Challenge", "category": "documentation",
     "metric": "owner_verified", "type": "team", "eligible_roles": "all", "target_rule": ("jobs_pm", 0.6, 2),
     "reward": {"kind": "points", "points": 250},
     "desc": "Every eligible crew member completes required prep and job documentation on {target} jobs this period \u2014 everyone who does earns the reward."},
    {"key": "full-house", "team": "crew", "name": "Full House", "category": "job_volume",
     "metric": "job_credits", "type": "individual", "eligible_roles": "all", "target_rule": ("jobs_pm", 1.15, 3),
     "reward": {"kind": "combo", "badge_id": "workhorse", "badge_name": "Workhorse", "points": 250},
     "desc": "Complete {target} quality jobs this month. Verified misconduct can disqualify a win \u2014 honestly reporting an issue never does."},
    {"key": "deposit-sprint", "team": "sales", "name": "Weekly Deposit Sprint", "category": "deposits",
     "metric": "owner_verified", "type": "individual", "eligible_roles": "all", "target_rule": ("closes_pw", 1.0, 2),
     "reward": {"kind": "cash", "amount": 40}, "duration": "week",
     "desc": "Lock {target} valid deposits this week. Refunded or cancelled deposits don't count."},
    {"key": "consistency-king", "team": "sales", "name": "Consistency King", "category": "consistency",
     "metric": "owner_verified", "type": "individual", "eligible_roles": "all", "target_rule": ("fixed", 0, 4),
     "reward": {"kind": "cash", "amount": 75},
     "desc": "Hit the weekly minimum every single week this month \u2014 {target} qualifying weeks. Steady beats one big spike."},
    {"key": "comeback-challenge", "team": "sales", "name": "Comeback Challenge", "category": "revived_leads",
     "metric": "owner_verified", "type": "individual", "eligible_roles": "all", "target_rule": ("fixed", 0, 1),
     "reward": {"kind": "points", "points": 250},
     "desc": "Revive a legitimately Lost lead and close it. The owner verifies the revival was real."},
    {"key": "sales-champion", "team": "sales", "name": "Monthly Sales Champion", "category": "closes",
     "metric": "owner_verified", "type": "competition", "eligible_roles": "all", "target_rule": None,
     "reward": {"kind": "cash", "amount": 100},
     "desc": "Most valid, collected closes this month wins \u2014 with a minimum floor so a single tiny deal can't take it. Refunds and cancellations don't count."},
    {"key": "revenue-milestone", "team": "sales", "name": "Revenue Milestone", "category": "revenue",
     "metric": "owner_verified", "type": "individual", "eligible_roles": "all", "target_rule": ("closes_pm", 1.0, 3),
     "reward": {"kind": "cash", "amount": 50},
     "desc": "Reach {target} valid collected closes this month. The owner sets the matching revenue tiers from real history \u2014 goal, stretch, elite."},
    {"key": "deal-drive", "team": "sales", "name": "Deal Drive", "category": "closes",
     "metric": "job_credits", "type": "individual", "eligible_roles": "all", "target_rule": ("closes_pm", 1.1, 2),
     "reward": {"kind": "points", "points": 250},
     "desc": "Close {target} moves this month \u2014 tracked automatically from your close credits."},
]


async def _agent_baselines(team: str) -> Dict[str, Any]:
    today = datetime.strptime(_et_today(), "%Y-%m-%d").date()
    out: Dict[str, Any] = {"team": team}
    members = await _active_members(team)
    out["active_members"] = len(members)
    for days in (30, 60, 90):
        since = (today - timedelta(days=days)).isoformat()
        docs = await mongo_db.job_credits.find({"team": team, "date": {"$gte": since}}).to_list(5000)
        out[f"credits_{days}d"] = len(docs)
        if team == "crew" and days == 90:
            out["driver_credits_90d"] = sum(1 for d in docs if d.get("role_tag") == "driver")
            out["helper_credits_90d"] = sum(1 for d in docs if d.get("role_tag") == "helper")
    n = max(1, out["active_members"])
    monthly_total = out["credits_90d"] / 3.0
    out["per_member_monthly"] = round(monthly_total / n, 2)
    out["jobs_pm"] = out["per_member_monthly"]
    out["closes_pm"] = out["per_member_monthly"]
    out["closes_pw"] = round(out["per_member_monthly"] / 4.3, 2)
    return out


def _template_target(t: Dict[str, Any], base: Dict[str, Any]) -> Optional[int]:
    rule = t.get("target_rule")
    if rule is None:
        return None
    key, mult, floor = rule
    if key == "fixed":
        return int(floor)
    raw = float(base.get(key) or 0) * float(mult)
    return max(int(floor), int(math.ceil(raw)))


async def _recent_challenge_fingerprints(months: int = 6) -> Dict[str, Any]:
    since = (datetime.strptime(_et_today(), "%Y-%m-%d").date() - timedelta(days=months * 31)).isoformat()
    docs = await mongo_db.challenges.find({"start": {"$gte": since}}).to_list(300)
    drafts = await mongo_db.challenge_drafts.find({"status": "draft", "created_at": {"$gte": since}}).to_list(100)
    keys = {d.get("template_key") for d in docs + drafts if d.get("template_key")}
    cats = {}
    for d in docs:
        if d.get("category"):
            cats.setdefault(d["team"], set()).add(d["category"])
    names = [d["name"].strip().lower() for d in docs + drafts]
    return {"keys": keys, "categories": {k: v for k, v in cats.items()}, "names": names}


async def _ai_month_spend(team: str, month: str) -> float:
    chs = await mongo_db.challenges.find({"created_by": "ai-agent", "team": team,
                                          "start": {"$regex": f"^{month}"}}).to_list(100)
    return sum(float(c.get("estimated_cost") or 0) for c in chs)


async def _guard_draft(d: Dict[str, Any], cfg: Dict[str, Any], base: Dict[str, Any],
                       recent: Dict[str, Any]) -> Optional[str]:
    """Returns a rejection reason, or None if the draft is safe to save."""
    if d["team"] not in TEAMS:
        return "unknown team"
    if d["metric"] not in ("job_credits", "owner_verified"):
        return "metric isn't tracked by the CRM"
    if d["type"] not in ("individual", "competition", "team"):
        return "unknown challenge type"
    if d["type"] == "competition" and not cfg["aiAllowCompetition"]:
        return "competition challenges are turned off"
    if d["type"] == "team" and not cfg["aiAllowTeamChallenges"]:
        return "team challenges are turned off"
    if d["type"] in ("individual", "team") and (not d.get("target") or int(d["target"]) < 1):
        return "missing a valid target"
    if AGENT_BANNED.search(f"{d['name']} {d['description']}"):
        return "failed the safety check (speed/injury/damage/overwork language)"
    if d.get("eligible_roles") not in ("all", "driver", "helper", "dual"):
        return "invalid eligibility"
    r = d.get("reward") or {}
    amount, points = float(r.get("amount") or 0), int(r.get("points") or 0)
    if amount > 0 and not cfg["aiAllowCash"]:
        return "cash rewards are turned off for the agent"
    if points > 0 and not cfg["aiAllowPoints"]:
        return "point rewards are turned off for the agent"
    if r.get("kind") == "gift_card" and not cfg["aiAllowGiftCards"]:
        return "gift card rewards are turned off for the agent"
    value = reward_dollar_value(amount, points, cfg)
    if value > float(cfg["aiMaxRewardPerChallenge"]):
        return f"reward (${value:.0f}) is over the agent's per-challenge cap (${cfg['aiMaxRewardPerChallenge']:g})"
    if value > float(cfg["maxSingleReward"]):
        return f"reward (${value:.0f}) is over the single-reward cap"
    winners = 1 if d["type"] == "competition" else max(1, base.get("active_members") or 1)
    d["estimated_winners"] = winners
    d["estimated_cost"] = round(value * winners, 2)
    month = d["start"][:7]
    ai_budget = float(cfg["aiCrewMonthlyBudget"] if d["team"] == "crew" else cfg["aiSalesMonthlyBudget"])
    spent = await _ai_month_spend(d["team"], month)
    if d["estimated_cost"] + spent > ai_budget:
        return f"potential reward budget exceeded (${d['estimated_cost'] + spent:.0f} vs ${ai_budget:g} AI budget)"
    if d.get("template_key") and d["template_key"] in recent["keys"]:
        return "too similar to a recent challenge (same template)"
    if d["name"].strip().lower() in recent["names"]:
        return "duplicate name from the last 6 months"
    if d["metric"] == "job_credits" and d.get("target"):
        cap = max(3.0, float(base.get("jobs_pm") or 0) * 2.5)
        if base.get("credits_90d", 0) >= 6 and int(d["target"]) > cap:
            return f"target {d['target']} is unrealistic vs history (cap ~{int(cap)})"
    if d["end"] <= d["start"]:
        return "bad dates"
    try:
        span = (datetime.strptime(d["end"], "%Y-%m-%d") - datetime.strptime(d["start"], "%Y-%m-%d")).days
    except ValueError:
        return "bad dates"
    if span > 62:
        return "challenge runs too long"
    return None


def _month_window() -> Dict[str, str]:
    today = datetime.strptime(_et_today(), "%Y-%m-%d").date()
    start = today.replace(day=1)
    end = datetime.strptime(_next_month(_et_today()[:7]) + "-01", "%Y-%m-%d").date() - timedelta(days=1)
    return {"start": start.isoformat(), "end": end.isoformat()}


def _week_window() -> Dict[str, str]:
    today = datetime.strptime(_et_today(), "%Y-%m-%d").date()
    start = today - timedelta(days=today.weekday())
    return {"start": start.isoformat(), "end": (start + timedelta(days=6)).isoformat()}


def _draft_from_template(t: Dict[str, Any], base: Dict[str, Any], why: str) -> Dict[str, Any]:
    win = _week_window() if t.get("duration") == "week" else _month_window()
    target = _template_target(t, base)
    return {"team": t["team"], "name": t["name"], "category": t["category"], "template_key": t["key"],
            "eligible_roles": t.get("eligible_roles", "all"), "type": t["type"], "metric": t["metric"],
            "target": target, "baseline": base.get("per_member_monthly"),
            "start": win["start"], "end": win["end"],
            "description": t["desc"].format(target=target or ""),
            "reward": dict(t["reward"]), "why": why,
            "difficulty": "moderate", "confidence": 0.8,
            "verification": "auto" if t["metric"] == "job_credits" else "owner"}


async def _fallback_drafts(team: str, count: int, base: Dict[str, Any], recent: Dict[str, Any]) -> List[Dict[str, Any]]:
    pool = [t for t in CHALLENGE_TEMPLATES if t["team"] == team and t["key"] not in recent["keys"]]
    used_cats = recent["categories"].get(team, set())
    pool.sort(key=lambda t: (t["category"] in used_cats, t["key"]))
    month_num = int(_et_today()[5:7])
    pool = pool[month_num % max(1, len(pool)):] + pool[:month_num % max(1, len(pool))]
    return [_draft_from_template(t, base, f"Deterministic pick \u2014 the {t['category'].replace('_', ' ')} category hasn't run recently.")
            for t in pool[:count]]


async def _llm_drafts(team: str, count: int, base: Dict[str, Any], recent: Dict[str, Any],
                      cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    menu = [{k: t[k] for k in ("key", "name", "category", "metric", "type", "eligible_roles")}
            for t in CHALLENGE_TEMPLATES if t["team"] == team]
    payload = {
        "team": team, "how_many": count, "difficulty": cfg["aiDifficulty"],
        "history": {k: v for k, v in base.items() if k != "team"},
        "recently_used_template_keys": sorted(recent["keys"]),
        "recently_used_categories": sorted(recent["categories"].get(team, set())),
        "template_menu": menu,
        "reward_rules": {
            "max_dollar_value_per_winner": min(cfg["aiMaxRewardPerChallenge"], cfg["maxSingleReward"]),
            "points_per_dollar": cfg["pointsPerDollar"],
            "cash_allowed": cfg["aiAllowCash"], "points_allowed": cfg["aiAllowPoints"],
            "gift_cards_allowed": cfg["aiAllowGiftCards"],
        },
        "month_window": _month_window(), "week_window": _week_window(),
    }
    chat = LlmChat(
        api_key=os.environ.get("EMERGENT_LLM_KEY", "").strip(),
        session_id=f"challenge-agent-{uuid4().hex[:8]}",
        system_message=(
            "You design employee challenges for Haul Yeah Moving, a small weekend moving company. "
            "Crew base pay and sales commissions already exist \u2014 these are supplemental incentives. "
            "HARD RULES: never reward speed, rushing, most hours, skipping breaks, working sick, hiding damage "
            "or injuries, overcharging, inflating quotes, or anything unsafe. Reward quality, reliability, "
            "customer service, safety participation, teamwork, documentation, valid collected sales. "
            "Targets MUST be grounded in the history numbers provided \u2014 attainable but slightly challenging; "
            "never impossible, never automatic. Only two metrics exist: 'job_credits' (auto-tracked counts) and "
            "'owner_verified' (the owner confirms manually) \u2014 never invent metrics. Prefer templates from the menu; "
            "avoid recently used keys/categories for variety. "
            "Respond with STRICT JSON only: {\"challenges\":[{\"template_key\":str|null,\"name\":str,"
            "\"description\":str,\"why\":str,\"category\":str,\"eligible_roles\":\"all|driver|helper|dual\","
            "\"type\":\"individual|competition|team\",\"metric\":\"job_credits|owner_verified\",\"target\":int|null,"
            "\"start\":\"YYYY-MM-DD\",\"end\":\"YYYY-MM-DD\",\"reward\":{\"kind\":\"cash|points|gift_card\","
            "\"amount\":number,\"points\":int},\"difficulty\":\"easy|moderate|stretch\",\"confidence\":0..1}]} "
            "No markdown, no prose."
        ),
    ).with_model("openai", "gpt-5.4")
    resp = await chat.send_message(UserMessage(text=json.dumps(payload, default=str)))
    text = str(resp).strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[4:] if text[:4].lower() == "json" else text
    data = json.loads(text)
    out = []
    for c in (data.get("challenges") or [])[:count]:
        tmpl = next((t for t in CHALLENGE_TEMPLATES if t["key"] == c.get("template_key") and t["team"] == team), None)
        reward = c.get("reward") or {}
        d = {"team": team, "name": str(c.get("name") or "")[:80].strip(),
             "description": str(c.get("description") or "")[:400].strip(),
             "why": str(c.get("why") or "")[:300].strip(),
             "category": c.get("category") if c.get("category") in AGENT_CATEGORIES[team] else (tmpl or {}).get("category", "quality"),
             "template_key": (tmpl or {}).get("key"),
             "eligible_roles": c.get("eligible_roles") if c.get("eligible_roles") in ("all", "driver", "helper", "dual") else "all",
             "type": c.get("type"), "metric": c.get("metric"),
             "target": int(c["target"]) if c.get("target") else None,
             "baseline": base.get("per_member_monthly"),
             "start": str(c.get("start") or "")[:10], "end": str(c.get("end") or "")[:10],
             "reward": {"kind": reward.get("kind") if reward.get("kind") in ("cash", "points", "gift_card") else "points",
                        "amount": round(max(0.0, float(reward.get("amount") or 0)), 2),
                        "points": max(0, int(reward.get("points") or 0))},
             "difficulty": c.get("difficulty") if c.get("difficulty") in ("easy", "moderate", "stretch") else "moderate",
             "confidence": min(1.0, max(0.0, float(c.get("confidence") or 0.7))),
             "verification": "auto" if c.get("metric") == "job_credits" else "owner"}
        if tmpl and (tmpl["reward"].get("badge_id")):
            d["reward"]["kind"] = "combo"
            d["reward"]["badge_id"] = tmpl["reward"]["badge_id"]
            d["reward"]["badge_name"] = tmpl["reward"].get("badge_name")
        if not d["name"] or not d["description"]:
            continue
        out.append(d)
    return out


def _draft_doc_out(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: d.get(k) for k in (
        "team", "name", "description", "why", "category", "template_key", "eligible_roles", "type", "metric",
        "target", "baseline", "start", "end", "reward", "difficulty", "confidence", "verification",
        "estimated_winners", "estimated_cost", "source", "status", "created_at", "rejected_reason")} | {"id": d["_id"]}


async def _generate_drafts(team: str, cfg: Dict[str, Any], count: Optional[int] = None,
                           actor_name: str = "agent") -> Dict[str, Any]:
    n = count or int(cfg["aiCrewChallengesPerMonth"] if team == "crew" else cfg["aiSalesChallengesPerMonth"])
    n = max(1, min(6, n))
    base = await _agent_baselines(team)
    recent = await _recent_challenge_fingerprints()
    source, candidates, llm_error = "ai", [], ""
    try:
        candidates = await _llm_drafts(team, n + 2, base, recent, cfg)
    except Exception as exc:
        llm_error = str(exc)[:200]
        logger.warning("Challenge agent LLM failed, using fallback: %s", exc)
    if not candidates:
        source = "fallback"
        candidates = await _fallback_drafts(team, n + 2, base, recent)
    saved, rejected = [], []
    for d in candidates:
        if len(saved) >= n:
            break
        reason = await _guard_draft(d, cfg, base, recent)
        if reason:
            rejected.append({"name": d.get("name", ""), "reason": reason})
            continue
        doc = {**d, "_id": str(uuid4()), "status": "draft", "source": source,
               "month": d["start"][:7], "created_at": now_iso(), "created_by": actor_name}
        await mongo_db.challenge_drafts.insert_one(doc)
        recent["names"].append(doc["name"].strip().lower())
        if doc.get("template_key"):
            recent["keys"].add(doc["template_key"])
        saved.append(doc)
    if len(saved) < n and source == "ai":
        for d in await _fallback_drafts(team, n - len(saved) + 2, base, recent):
            if len(saved) >= n:
                break
            if await _guard_draft(d, cfg, base, recent):
                continue
            doc = {**d, "_id": str(uuid4()), "status": "draft", "source": "fallback",
                   "month": d["start"][:7], "created_at": now_iso(), "created_by": actor_name}
            await mongo_db.challenge_drafts.insert_one(doc)
            recent["keys"].add(doc.get("template_key"))
            saved.append(doc)
    await audit({"name": actor_name, "user_id": None}, "AI generated challenge drafts",
                f"{team}: {len(saved)} draft(s), {len(rejected)} rejected")
    return {"drafts": [_draft_doc_out(d) for d in saved], "rejected": rejected,
            "source": source, "llm_error": llm_error}


class GeneratePayload(BaseModel):
    team: str = "both"
    count: Optional[int] = None


@api_router.post("/challenge-agent/generate")
async def agent_generate(payload: GeneratePayload = Body(default=GeneratePayload()),
                         p: Dict[str, Any] = Depends(require_owner)):
    cfg = await get_rewards_config()
    if not cfg["aiEnabled"]:
        raise HTTPException(status_code=422, detail="The AI Challenge Agent is turned off in settings.")
    teams = TEAMS if payload.team == "both" else ([payload.team] if payload.team in TEAMS else None)
    if not teams:
        raise HTTPException(status_code=422, detail="Team must be crew, sales, or both.")
    out = {"drafts": [], "rejected": [], "source": "", "llm_error": ""}
    for t in teams:
        res = await _generate_drafts(t, cfg, payload.count, actor_name=p.get("name") or "owner")
        out["drafts"] += res["drafts"]
        out["rejected"] += res["rejected"]
        out["source"] = res["source"]
        out["llm_error"] = out["llm_error"] or res["llm_error"]
    return out


@api_router.get("/challenge-agent/drafts")
async def agent_drafts(p: Dict[str, Any] = Depends(require_owner)):
    docs = await mongo_db.challenge_drafts.find({"status": "draft"}).sort("created_at", -1).to_list(50)
    return {"drafts": [_draft_doc_out(d) for d in docs]}


class DraftPatchPayload(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    target: Optional[int] = None
    start: Optional[str] = None
    end: Optional[str] = None
    reward_amount: Optional[float] = None
    reward_points: Optional[int] = None


@api_router.patch("/challenge-agent/drafts/{draft_id}")
async def patch_draft(draft_id: str, payload: DraftPatchPayload, p: Dict[str, Any] = Depends(require_owner)):
    d = await mongo_db.challenge_drafts.find_one({"_id": draft_id, "status": "draft"})
    if not d:
        raise HTTPException(status_code=404, detail="No such draft.")
    if payload.name is not None and payload.name.strip():
        d["name"] = payload.name.strip()[:80]
    if payload.description is not None:
        d["description"] = payload.description.strip()[:400]
    if payload.target is not None:
        d["target"] = max(1, int(payload.target))
    if payload.start:
        d["start"] = payload.start[:10]
    if payload.end:
        d["end"] = payload.end[:10]
    if payload.reward_amount is not None:
        d["reward"]["amount"] = round(max(0.0, float(payload.reward_amount)), 2)
    if payload.reward_points is not None:
        d["reward"]["points"] = max(0, int(payload.reward_points))
    cfg = await get_rewards_config()
    base = await _agent_baselines(d["team"])
    recent = await _recent_challenge_fingerprints()
    recent["names"] = [n for n in recent["names"] if n != d["name"].strip().lower()]
    recent["keys"].discard(d.get("template_key"))
    reason = await _guard_draft(d, cfg, base, recent)
    if reason:
        raise HTTPException(status_code=422, detail=f"That edit fails the guardrails: {reason}.")
    await mongo_db.challenge_drafts.update_one({"_id": draft_id}, {"$set": {
        k: d[k] for k in ("name", "description", "target", "start", "end", "reward",
                          "estimated_winners", "estimated_cost")}})
    await audit(p, "edited an AI challenge draft", d["name"])
    fresh = await mongo_db.challenge_drafts.find_one({"_id": draft_id})
    return _draft_doc_out(fresh)


async def _publish_draft_doc(d: Dict[str, Any], actor_name: str) -> Dict[str, Any]:
    doc = {"_id": str(uuid4()), "name": d["name"], "description": d["description"], "team": d["team"],
           "type": d["type"], "metric": d["metric"],
           "target": d.get("target") if d["type"] in ("individual", "team") else None,
           "start": d["start"], "end": d["end"], "reward": d["reward"],
           "eligible_roles": d.get("eligible_roles", "all"), "status": "active",
           "verified": {}, "winners": [], "created_by": "ai-agent",
           "template_key": d.get("template_key"), "category": d.get("category"),
           "estimated_cost": d.get("estimated_cost"),
           "ai": {"why": d.get("why", ""), "baseline": d.get("baseline"), "difficulty": d.get("difficulty"),
                  "confidence": d.get("confidence"), "source": d.get("source")},
           "created_at": now_iso()}
    await mongo_db.challenges.insert_one(doc)
    await mongo_db.challenge_drafts.update_one({"_id": d["_id"]},
                                               {"$set": {"status": "published", "published_at": now_iso(),
                                                         "challenge_id": doc["_id"]}})
    await audit({"name": actor_name, "user_id": None}, "approved and published an AI challenge", d["name"])
    for m in await _active_members(d["team"]):
        await notify(m["_id"], None, "New challenge just dropped",
                     f"\u201c{doc['name']}\u201d is live for the {d['team']} team \u2014 check the Challenges page.",
                     "challenge", {"challenge_id": doc["_id"]})
    return doc


@api_router.post("/challenge-agent/drafts/{draft_id}/publish")
async def publish_draft(draft_id: str, p: Dict[str, Any] = Depends(require_owner)):
    d = await mongo_db.challenge_drafts.find_one({"_id": draft_id, "status": "draft"})
    if not d:
        raise HTTPException(status_code=404, detail="No such draft.")
    doc = await _publish_draft_doc(d, p.get("name") or "owner")
    return _challenge_out(doc, await challenge_progress(doc))


@api_router.post("/challenge-agent/drafts/{draft_id}/reject")
async def reject_draft(draft_id: str, payload: RewardActionPayload = Body(default=RewardActionPayload()),
                       p: Dict[str, Any] = Depends(require_owner)):
    d = await mongo_db.challenge_drafts.find_one({"_id": draft_id, "status": "draft"})
    if not d:
        raise HTTPException(status_code=404, detail="No such draft.")
    await mongo_db.challenge_drafts.update_one({"_id": draft_id},
                                               {"$set": {"status": "rejected",
                                                         "rejected_reason": (payload.reason or "").strip()[:200]}})
    await audit(p, "rejected an AI challenge draft", d["name"])
    return {"ok": True}


@api_router.get("/challenge-agent/status")
async def agent_status(p: Dict[str, Any] = Depends(require_owner)):
    cfg = await get_rewards_config()
    month = _et_today()[:7]
    run = await mongo_db.challenge_gen_runs.find_one({"_id": f"{month}:auto"})
    drafts = await mongo_db.challenge_drafts.count_documents({"status": "draft"})
    published = await mongo_db.challenges.count_documents({"created_by": "ai-agent", "start": {"$regex": f"^{month}"}})
    return {"config": cfg, "month": month, "drafts_waiting": drafts, "published_this_month": published,
            "ai_spend": {"crew": await _ai_month_spend("crew", month), "sales": await _ai_month_spend("sales", month)},
            "last_run": {"status": (run or {}).get("status"), "at": (run or {}).get("finished_at") or (run or {}).get("started_at"),
                         "error": (run or {}).get("error")} if run else None,
            "llm_available": bool(os.environ.get("EMERGENT_LLM_KEY", "").strip())}


@api_router.post("/challenge-agent/retry")
async def agent_retry_month(p: Dict[str, Any] = Depends(require_owner)):
    month = _et_today()[:7]
    await mongo_db.challenge_gen_runs.delete_one({"_id": f"{month}:auto", "status": "failed"})
    return {"ok": True}


async def _run_monthly_generation(month: str, cfg: Dict[str, Any]):
    run_id = f"{month}:auto"
    try:
        await mongo_db.challenge_gen_runs.insert_one({"_id": run_id, "status": "running", "started_at": now_iso()})
    except Exception:
        return  # another worker claimed it — idempotent
    try:
        total = []
        for team in TEAMS:
            res = await _generate_drafts(team, cfg, actor_name="ai-agent")
            total += res["drafts"]
        if cfg["aiAutoPublish"] and not cfg["aiRequireApproval"]:
            for d in list(total):
                doc = await mongo_db.challenge_drafts.find_one({"_id": d["id"], "status": "draft"})
                if doc:
                    await _publish_draft_doc(doc, "ai-agent")
        await mongo_db.challenge_gen_runs.update_one(
            {"_id": run_id}, {"$set": {"status": "ok", "finished_at": now_iso(), "drafts": len(total)}})
        await notify(None, "owner", "This month's challenges are drafted",
                     f"The Challenge Agent drew up {len(total)} draft(s) for {month}. Review and publish them in Team HQ \u2192 AI Agent.",
                     "challenge")
    except Exception as exc:
        logger.error("Monthly challenge generation failed: %s", exc)
        await mongo_db.challenge_gen_runs.update_one(
            {"_id": run_id}, {"$set": {"status": "failed", "finished_at": now_iso(), "error": str(exc)[:300]}})
        await notify(None, "owner", "Challenge generation failed \u2014 retry",
                     "This month's automatic challenge generation hit an error. Open Team HQ \u2192 AI Agent and press Generate to retry.",
                     "challenge")


async def challenge_agent_loop():
    await asyncio.sleep(120)
    while True:
        try:
            cfg = await get_rewards_config()
            if cfg["aiEnabled"] and cfg["aiMonthlyGeneration"]:
                month = _et_today()[:7]
                if not await mongo_db.challenge_gen_runs.find_one({"_id": f"{month}:auto"}):
                    await _run_monthly_generation(month, cfg)
        except Exception as exc:
            logger.error("challenge_agent_loop: %s", exc)
        await asyncio.sleep(4 * 3600)


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

SQUARE_OPEN_INVOICE_STATUSES = ("UNPAID", "PARTIALLY_PAID", "SCHEDULED", "PAYMENT_PENDING")


async def _money_summary() -> Dict[str, Any]:
    """ONE source of truth for money: Square. Every money card reads this."""
    today = _et_today()
    collected_total = revenue_today = open_invoices_total = 0.0
    paid_by_lead: Dict[str, float] = {}
    open_by_lead: Dict[str, float] = {}
    async for inv in mongo_db.square_invoices.find(
            {}, {"_id": 0, "amount": 1, "status": 1, "lead_id": 1, "paid_at": 1}):
        amt = float(inv.get("amount") or 0)
        if inv.get("status") == "PAID":
            collected_total += amt
            if inv.get("lead_id"):
                paid_by_lead[inv["lead_id"]] = paid_by_lead.get(inv["lead_id"], 0.0) + amt
            if inv.get("paid_at"):
                try:
                    d_et = datetime.fromisoformat(str(inv["paid_at"]).replace("Z", "+00:00")).astimezone(
                        ZoneInfo("America/New_York")).date().isoformat()
                    if d_et == today:
                        revenue_today += amt
                except ValueError:
                    pass
        elif inv.get("status") in SQUARE_OPEN_INVOICE_STATUSES:
            open_invoices_total += amt
            if inv.get("lead_id"):
                open_by_lead[inv["lead_id"]] = open_by_lead.get(inv["lead_id"], 0.0) + amt
    booked_total = outstanding_total = 0.0
    jobs_count = 0
    unpaid_jobs: List[str] = []
    job_leads: set = set()
    async for j in mongo_db.jobs.find({"deposit_paid.status": "paid"}):
        jobs_count += 1
        if j.get("lead_id"):
            job_leads.add(j["lead_id"])
        try:
            quote = float(j.get("quote_total") or 0)
        except (TypeError, ValueError):
            quote = 0.0
        try:
            deposit = float((j.get("deposit_paid") or {}).get("amount") or 0)
        except (TypeError, ValueError):
            deposit = 0.0
        booked_total += quote or deposit
        if (j.get("paid_in_full") or {}).get("status") == "paid" or not quote:
            continue
        paid_against = paid_by_lead.get(j.get("lead_id") or "", 0.0) or deposit
        rem = max(0.0, quote - paid_against)
        if rem > 0:
            outstanding_total += rem
            unpaid_jobs.append(
                f"Job #{j.get('invoice_number')} ({(j.get('customer') or {}).get('name', '?')}): ${rem:,.0f} due")
    # open Square invoices for leads with no job yet (not double-counted above)
    for lead_id, amt in open_by_lead.items():
        if lead_id not in job_leads:
            outstanding_total += amt
    async for i in mongo_db.square_invoices.find(
            {"status": {"$in": list(SQUARE_OPEN_INVOICE_STATUSES)}, "lead_id": None},
            {"_id": 0, "amount": 1}):
        outstanding_total += float(i.get("amount") or 0)
    return {
        "source": "square",
        "booked_total": round(booked_total, 2),
        "jobs_count": jobs_count,
        "collected_total": round(collected_total, 2),
        "outstanding_total": round(outstanding_total, 2),
        "unpaid_jobs": unpaid_jobs[:10],
        "revenue_today": round(revenue_today, 2),
    }


@api_router.get("/money/summary")
async def money_summary(p: Dict[str, Any] = Depends(require_owner)) -> Dict[str, Any]:
    return await _money_summary()


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
    # money — same Square-backed summary every dashboard uses
    money = await _money_summary()
    revenue_today = money["revenue_today"]
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
        "money": {"outstanding_balance_total": money["outstanding_total"],
                  "unpaid_jobs": money["unpaid_jobs"],
                  "collected_total": money["collected_total"],
                  "booked_total": money["booked_total"]},
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

async def _merge_user_pair(keep: Dict[str, Any], dup: Dict[str, Any]) -> None:
    kid, did = keep["_id"], dup["_id"]
    for coll in ("time_entries", "job_credits", "availability", "points_ledger", "rewards", "notifications"):
        await mongo_db[coll].update_many({"user_id": did}, {"$set": {"user_id": kid}})
    async for a in mongo_db.assignments.find({"crew.user_id": did}):
        crew = a.get("crew") or []
        if any(c.get("user_id") == kid for c in crew):
            crew = [c for c in crew if c.get("user_id") != did]
        else:
            for c in crew:
                if c.get("user_id") == did:
                    c["user_id"] = kid
                    c["name"] = keep.get("name") or c.get("name")
        await mongo_db.assignments.update_one({"_id": a["_id"]}, {"$set": {"crew": crew}})
    async for ub in mongo_db.user_badges.find({"user_id": did}):
        new_id = f"{kid}:{ub.get('badge_id')}"
        if not await mongo_db.user_badges.find_one({"_id": new_id}):
            await mongo_db.user_badges.insert_one({**ub, "_id": new_id, "user_id": kid})
        await mongo_db.user_badges.delete_one({"_id": ub["_id"]})
    inc = {}
    if dup.get("haul_points"):
        inc["haul_points"] = int(dup["haul_points"])
    if dup.get("haul_points_lifetime"):
        inc["haul_points_lifetime"] = int(dup["haul_points_lifetime"])
    if inc:
        await mongo_db.users.update_one({"_id": kid}, {"$inc": inc})
    await mongo_db.users.delete_one({"_id": did})
    logger.info("Merged duplicate user '%s' (%s) into '%s' (%s)", dup.get("name"), did, keep.get("name"), kid)


async def _dup_weight(u: Dict[str, Any]) -> Tuple[int, str]:
    activity = (await mongo_db.job_credits.count_documents({"user_id": u["_id"]})
                + await mongo_db.time_entries.count_documents({"user_id": u["_id"]}))
    return (activity, u.get("created_at") or "9999")


async def dedupe_crew_users() -> None:
    """Data hygiene: collapse known duplicate crew accounts (exact + spelling variants)."""
    groups = (
        (("javante brown",), None),
        (("junior saintil", "junior santil"), "Junior Saintil"),
    )
    for names, canonical in groups:
        pattern = "|".join(re.escape(n) for n in names)
        rx = re.compile(rf"^\s*(?:{pattern})\s*$", re.IGNORECASE)
        users = await mongo_db.users.find({"name": rx, "ghost": {"$ne": True}}).to_list(20)
        if not users:
            continue
        if len(users) > 1:
            weighted = [(await _dup_weight(u), u) for u in users]
            weighted.sort(key=lambda w: (-w[0][0], w[0][1]))
            keep = weighted[0][1]
            for _, dup in weighted[1:]:
                await _merge_user_pair(keep, dup)
        else:
            keep = users[0]
        if canonical and keep.get("name") != canonical:
            await mongo_db.users.update_one({"_id": keep["_id"]}, {"$set": {"name": canonical}})


# ======= Stage 4: reliable actuals & versioned job outcomes =======
# ONE definition of job actuals feeds every screen. Outcomes are DATA CAPTURE for later learning —
# Stage 4 changes NO pricing, trains NOTHING, writes NO Square/invoice, and honors staging's read-only
# Airtable (a 403 stays queued/reported). job_outcomes holds the CURRENT snapshot per job; every material
# change appends an immutable job_outcome_versions row (append-only, never overwritten/deleted).

# Stage 2 tap keys → the milestones this stage reasons about (mapped, never duplicated).
TAP_ARRIVED, TAP_LEAVE_PICKUP, TAP_DROPOFF, TAP_COMPLETE = "arrived", "loaded", "dropoff", "complete"
OUTCOME_GEOFENCE_MI = 0.15
OUTCOME_AVG_DRIVE_MPH = 25.0
GPS_LEARN_WEIGHT = 0.75
OUTCOME_OUTLIER_HOURS = 3.0


async def require_outcome_role(request: Request) -> Dict[str, Any]:
    p = await current_principal(request)
    if p["role"] not in ("owner", "quality"):
        raise HTTPException(status_code=403, detail="Only the owner and Quality can review job outcomes.")
    return p


def _job_key_for_assignment(a: Dict[str, Any]) -> str:
    """Stable outcome identity: the Airtable Project when matched (assignment.project_id), else the
    Mongo assignment itself. Never merges two jobs by date+name."""
    pid = a.get("project_id")
    return f"project:{pid}" if pid else f"assignment:{a['_id']}"


async def _assignments_for_job_key(job_key: str) -> List[Dict[str, Any]]:
    kind, _, ref = job_key.partition(":")
    if kind == "project":
        return await mongo_db.assignments.find({"project_id": ref}).to_list(50)
    a = await mongo_db.assignments.find_one({"_id": ref})
    return [a] if a else []


def _tap_at(a: Dict[str, Any], key: str) -> Optional[datetime]:
    t = ((a.get("crew_lead") or {}).get("taps") or {}).get(key)
    return _parse_iso((t or {}).get("at")) if t else None


def _status_at(a: Dict[str, Any], status: str) -> Optional[datetime]:
    for ev in reversed(a.get("status_history") or []):
        if ev.get("status") == status:
            return _parse_iso(ev.get("at"))
    return None


def _overlap_hours(s1: Optional[datetime], e1: Optional[datetime],
                   s2: Optional[datetime], e2: Optional[datetime]) -> float:
    if not (s1 and e1 and s2 and e2):
        return 0.0
    lo, hi = max(s1, s2), min(e1, e2)
    return (hi - lo).total_seconds() / 3600 if hi > lo else 0.0


def _gps_window_for(a: Dict[str, Any], pings: List[Dict[str, Any]]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Best-effort Arrived/Complete from GPS: first ping inside the pickup geofence → last ping near it."""
    site = a.get("site_coords") or {}
    if not (site.get("lat") is not None and site.get("lng") is not None):
        return None, None
    inside = []
    for g in pings:
        if g.get("lat") is None or g.get("lng") is None:
            continue
        try:
            d = haversine_miles(g["lat"], g["lng"], site["lat"], site["lng"])
        except (TypeError, ValueError):
            continue
        if d <= OUTCOME_GEOFENCE_MI:
            t = _parse_iso(g.get("at"))
            if t:
                inside.append(t)
    if len(inside) < 2:
        return None, None
    inside.sort()
    return inside[0], inside[-1]


async def compute_job_actuals(assignments: List[Dict[str, Any]], quoted_crew: Optional[int]) -> Dict[str, Any]:
    """THE shared actual-hours definition (spec A3). Window = Arrived→Complete from taps, else valid GPS,
    else clock_only + incomplete (never first-yard-in→last-out as on-site time). Aggregates multi-truck
    crew time without double-counting a person or an overlapping interval."""
    assignments = [a for a in assignments if a]
    if not assignments:
        return {"data_quality": "unmatched", "window_source": None, "incomplete_reasons": ["no_assignment"]}
    ids = [a["_id"] for a in assignments]
    entries = await mongo_db.time_entries.find({"assignment_id": {"$in": ids}}).to_list(500)
    incomplete: List[str] = []

    # --- on-site window: taps first, then GPS, then clock_only ---
    arrived = next((t for t in (_tap_at(a, TAP_ARRIVED) for a in assignments) if t), None) \
        or next((t for t in (_status_at(a, "Arrived") for a in assignments) if t), None)
    complete = next((t for t in (_tap_at(a, TAP_COMPLETE) for a in assignments) if t), None) \
        or next((t for t in (_status_at(a, "Complete") for a in assignments) if t), None)
    leave_pickup = next((t for t in (_tap_at(a, TAP_LEAVE_PICKUP) for a in assignments) if t), None)
    dropoff = next((t for t in (_tap_at(a, TAP_DROPOFF) for a in assignments) if t), None)
    window_source = None
    if arrived and complete and complete > arrived:
        window_source = "taps"
    else:
        day = (assignments[0].get("job_date") or "")[:10]
        uids = {c.get("user_id") for a in assignments for c in a.get("crew", []) if c.get("user_id")}
        pings = await mongo_db.gps_pings.find(
            {"user_id": {"$in": list(uids)}, "at": {"$gte": f"{day}T00:00:00"}}).to_list(2000) if (uids and day) else []
        g_start, g_end = _gps_window_for(assignments[0], pings)
        if g_start and g_end and g_end > g_start:
            arrived, complete, window_source = g_start, g_end, "gps"
        else:
            window_source = "clock_only"
            incomplete.append("no_defensible_window")

    open_punch = any(e.get("clock_in") and not e.get("clock_out") for e in entries)
    if open_punch:
        incomplete.append("open_clock_entry")

    on_site_hours = round(max(0.0, (complete - arrived).total_seconds() / 3600), 2) if (
        window_source in ("taps", "gps") and arrived and complete) else None

    # --- per-person punches, man-hours, drive subtraction (no double counting) ---
    by_user: Dict[str, Dict[str, Any]] = {}
    for a in assignments:
        for c in a.get("crew", []):
            uid = c.get("user_id")
            if uid and uid not in by_user:
                by_user[uid] = {"user_id": uid, "name": c.get("name"),
                                "position": c.get("position"), "punches": [], "worked": False,
                                "estimated": False, "approved_all": True}
    man_hours = 0.0
    work_hours = 0.0
    for e in entries:
        uid = e.get("user_id")
        if uid not in by_user:
            by_user[uid] = {"user_id": uid, "name": e.get("user_name"), "position": e.get("position"),
                            "punches": [], "worked": False, "estimated": False, "approved_all": True}
        s = _parse_iso((e.get("clock_in") or {}).get("at"))
        en = _parse_iso((e.get("clock_out") or {}).get("at"))
        rec = {"in": (e.get("clock_in") or {}).get("at"), "out": (e.get("clock_out") or {}).get("at"),
               "hours": e.get("hours"), "approved": bool(e.get("approved")),
               "estimated": bool(e.get("estimated")), "flags": e.get("flags") or []}
        by_user[uid]["punches"].append(rec)
        if e.get("estimated"):
            by_user[uid]["estimated"] = True
        if not e.get("approved"):
            by_user[uid]["approved_all"] = False
        if window_source in ("taps", "gps") and s and en:
            ov = _overlap_hours(s, en, arrived, complete)
            if ov > 0:
                by_user[uid]["worked"] = True
                man_hours += ov
                drive_ov = _overlap_hours(s, en, leave_pickup, dropoff) if (leave_pickup and dropoff) else 0.0
                work_hours += max(0.0, ov - drive_ov)

    workers = [u for u in by_user.values() if u["worked"]]
    actual_crew_count = len(workers) if workers else None
    crew_div = quoted_crew if (quoted_crew and quoted_crew > 0) else (actual_crew_count or 0)
    crew_adj_work = round(work_hours / crew_div, 2) if (crew_div and window_source in ("taps", "gps")) else None
    crew_adj_onsite = round(man_hours / crew_div, 2) if (crew_div and window_source in ("taps", "gps")) else None

    # --- total day (scheduling context only; NEVER the estimating target) ---
    all_ins = sorted(x for x in ((e.get("clock_in") or {}).get("at") for e in entries) if x)
    all_outs = sorted(x for x in ((e.get("clock_out") or {}).get("at") for e in entries) if x)
    total_day_hours = None
    if all_ins and all_outs and not open_punch:
        try:
            total_day_hours = round(max(0.0, (
                datetime.fromisoformat(all_outs[-1]) - datetime.fromisoformat(all_ins[0])).total_seconds() / 3600), 2)
        except (ValueError, TypeError):
            total_day_hours = None

    # --- segment times (labeled, for audit) + drive source ---
    def seg(a1, b1):
        return round((b1 - a1).total_seconds() / 3600, 2) if (a1 and b1 and b1 > a1) else None
    drive_source = "taps" if (leave_pickup and dropoff) else None
    drive_hours = seg(leave_pickup, dropoff)
    if drive_hours is None:
        miles = None
        for a in assignments:
            miles = miles or a.get("one_way_miles")
        if miles:
            drive_hours = round(2 * float(miles) / OUTCOME_AVG_DRIVE_MPH, 2)
            drive_source = "estimated"
    segments = {
        "load": seg(arrived, leave_pickup), "drive": drive_hours,
        "unload": seg(dropoff, complete), "travel_in": None, "travel_out": None,
    }
    if all_ins and arrived:
        segments["travel_in"] = seg(_parse_iso(all_ins[0]), arrived)
    if complete and all_outs:
        segments["travel_out"] = seg(complete, _parse_iso(all_outs[-1]))

    data_quality = "complete"
    confidence = 1.0
    if incomplete:
        data_quality = "incomplete"
        confidence = 0.0
    elif window_source == "gps":
        confidence = GPS_LEARN_WEIGHT
    if any(u["estimated"] for u in workers):
        confidence = min(confidence, GPS_LEARN_WEIGHT)

    return {
        "window_source": window_source, "drive_source": drive_source,
        "arrived_at": arrived.isoformat() if arrived else None,
        "complete_at": complete.isoformat() if complete else None,
        "leave_pickup_at": leave_pickup.isoformat() if leave_pickup else None,
        "dropoff_at": dropoff.isoformat() if dropoff else None,
        "on_site_hours": on_site_hours, "actual_man_hours": round(man_hours, 2) if window_source in ("taps", "gps") else None,
        "work_man_hours": round(work_hours, 2) if window_source in ("taps", "gps") else None,
        "crew_adjusted_work_hours": crew_adj_work, "crew_adjusted_on_site_hours": crew_adj_onsite,
        "total_day_hours": total_day_hours, "segments": segments,
        "actual_crew_count": actual_crew_count, "planned_crew_count": sum(len(a.get("crew", [])) for a in assignments),
        "quoted_crew_used": crew_div or None,
        "crew": [{"user_id": u["user_id"], "name": u["name"], "position": u["position"],
                  "worked": u["worked"], "estimated": u["estimated"], "approved": u["approved_all"],
                  "punches": u["punches"]} for u in by_user.values()],
        "delay_factors": sorted({d for a in assignments for d in (a.get("delay_factors") or [])}),
        "completion_notes": next((a.get("completion_notes") for a in assignments if a.get("completion_notes")), None),
        "data_quality": data_quality, "confidence": confidence, "incomplete_reasons": incomplete,
        "learning_eligible": data_quality == "complete",
    }


async def _shared_on_site_hours(assignment_ids: List[str]) -> Optional[float]:
    """Arrived→Complete on-site hours for a set of assignments (A9 fix — never yard clock-in→last-out).
    Used by Quality quote-accuracy so every surface agrees."""
    assigns = await mongo_db.assignments.find({"_id": {"$in": assignment_ids}}).to_list(50)
    if not assigns:
        return None
    res = await compute_job_actuals(assigns, None)
    return res.get("on_site_hours")


# ---- quote snapshot (B2–B4): the committed quote frozen as it was at Save Quote ----
async def _select_quote_scope(lead_id: Optional[str], assignments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Explicit quote_scope_id wins; otherwise a documented fallback among the lead's scopes. Ambiguous =
    unmatched (excluded from learning). Records the selection rule + confidence; never guesses across ties."""
    if not lead_id:
        return {"scope": None, "rule": "no_lead", "confidence": 0.0}
    link = await mongo_db.lead_quote_links.find_one({"_id": lead_id})
    active = (link or {}).get("active_quote_scope_id")
    if active:
        doc = await mongo_db.lead_scopes.find_one({"_id": active})
        if doc:
            return {"scope": doc, "rule": "explicit_quote_scope_id", "confidence": 1.0}
    scopes = await mongo_db.lead_scopes.find(
        {"lead_id": lead_id, "status": "saved"}).sort("created_at", -1).to_list(50)
    if not scopes:
        return {"scope": None, "rule": "no_scope", "confidence": 0.0}
    project_quote = None
    for a in assignments:
        project_quote = project_quote or a.get("quote_amount")
    if project_quote is not None:
        matches = [s for s in scopes if s.get("amount") is not None
                   and abs(float(s["amount"]) - float(project_quote)) < 0.5]
        if len(matches) == 1:
            return {"scope": matches[0], "rule": "amount_match", "confidence": 0.9}
    finals = [s for s in scopes if (s.get("result") or {}).get("mode") == "final"]
    if finals:
        return {"scope": finals[0], "rule": "latest_final", "confidence": 0.6}
    surveyed = [s for s in scopes if s.get("survey_complete")]
    if surveyed:
        return {"scope": surveyed[0], "rule": "latest_survey_complete", "confidence": 0.5}
    if len(scopes) > 1:
        # Multiple plain saved quotes and nothing to disambiguate them (no committed link, no amount
        # match, none final or survey-complete). Refuse to guess — ambiguous is unmatched, never learned.
        return {"scope": None, "rule": "ambiguous", "confidence": 0.0}
    return {"scope": scopes[0], "rule": "latest_scope", "confidence": 0.4}


def _build_quote_snapshot(sel: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    s = sel.get("scope")
    if not s:
        return None
    result = s.get("result") or {}
    inputs = s.get("inputs") or {}
    optimizer_present = bool(s.get("calibration_version") and s.get("calibration_version") != "v0")
    return {
        "quote_scope_id": s.get("_id"), "created_at": s.get("created_at"), "created_by": s.get("created_by"),
        "commit_type": s.get("commit_type"), "estimate_mode": s.get("estimate_mode") or result.get("mode"),
        "amount": s.get("amount"), "finalTotal": result.get("finalTotal"),
        "bandLo": result.get("bandLo"), "bandHi": result.get("bandHi"),
        "sched_mh": result.get("schedMH") if result.get("schedMH") is not None else inputs.get("schedMH"),
        "bill_mh": result.get("billMH"), "crew_rec": result.get("crewRec") or inputs.get("crew"),
        "hours_source": s.get("hours_source"), "pricing_version": s.get("pricing_version"),
        "calibration_version": s.get("calibration_version"), "optimizer_fields": optimizer_present,
        "survey_complete": bool(s.get("survey_complete")), "video": s.get("video") or {},
        "inputs": inputs, "pricing": s.get("pricing") or {}, "result": result,
        "floor_applied": bool(result.get("floorApplied") or result.get("floor_applied")),
    }


def _derive_errors(quote: Optional[Dict[str, Any]], actuals: Dict[str, Any],
                   final_total: Optional[float]) -> Dict[str, Any]:
    """Per-job errors (B7). bias sign convention handled at the aggregate (Stage 6); here we store raw
    predicted−actual deltas. Negative model error = under-estimate."""
    out: Dict[str, Any] = {}
    if not quote:
        return {"available": False}
    work = actuals.get("work_man_hours")
    onsite = actuals.get("actual_man_hours")
    sched = quote.get("sched_mh")
    if sched is not None and work is not None:
        out["model_work_mh_error"] = round(float(sched) - float(work), 2)
    if sched is not None and onsite is not None:
        out["model_on_site_mh_error"] = round(float(sched) - float(onsite), 2)
    q_amount = quote.get("finalTotal") if quote.get("finalTotal") is not None else quote.get("amount")
    if q_amount is not None and final_total is not None:
        out["dollar_variance"] = round(float(final_total) - float(q_amount), 2)
    lo, hi = quote.get("bandLo"), quote.get("bandHi")
    if final_total is not None and lo is not None and hi is not None:
        out["in_band"] = bool(float(lo) <= float(final_total) <= float(hi))
    out["floor_applied"] = quote.get("floor_applied")
    out["available"] = True
    return out


async def _final_total_for(assignments: List[Dict[str, Any]], lead_id: Optional[str]) -> Dict[str, Any]:
    """Final BILLED amount (B6): newest job-audit Final total, else Project Final Revenue. NEVER a Square
    deposit/paid-to-date and NEVER the original quote. Airtable-backed → 'missing' when unavailable (preview)."""
    if not get_api_key():
        return {"value": None, "source": "missing", "at": now_iso(), "note": "airtable_unavailable"}
    pid = next((a.get("project_id") for a in assignments if a.get("project_id")), None)
    try:
        if pid:
            audits = await _airtable_all(TABLES["job_audits"])
            linked = [au for au in audits if pid in ((au.get("fields") or {}).get(JA_LINKED_JOB_F) or [])]
            linked.sort(key=lambda au: ((au.get("fields") or {}).get(JA_COMPLETED_DATE_F) or "",
                                        au.get("createdTime") or ""), reverse=True)
            for au in linked:
                ft = (au.get("fields") or {}).get(JA_FINAL_TOTAL_F)
                if ft is not None:
                    return {"value": float(ft), "source": "job_audit", "audit_id": au["id"], "at": now_iso()}
            rec = await airtable_request("GET", TABLES["projects"], f"/{pid}")
            rev = (rec.get("fields") or {}).get(PROJECT_REVENUE_FIELD)
            if rev is not None:
                return {"value": float(rev), "source": "project_final_revenue", "at": now_iso()}
    except Exception as exc:
        logger.warning("final_total lookup failed: %s", _safe_airtable_error(exc))
        return {"value": None, "source": "missing", "at": now_iso(), "note": "airtable_error"}
    return {"value": None, "source": "missing", "at": now_iso()}


def _survey_miss_flags(quote: Optional[Dict[str, Any]], actuals: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Possible survey misses (B9): as-found/delay contradicts the quoted inputs. Owner/Quality decide."""
    flags: List[Dict[str, Any]] = []
    if not quote:
        return flags
    inputs = quote.get("inputs") or {}
    delays = set(actuals.get("delay_factors") or [])
    notes = (actuals.get("completion_notes") or "").lower()
    if not inputs.get("packing") and ("not packed" in notes or "customer_not_packed" in delays):
        flags.append({"key": "packing_miss", "detail": "As-found says the customer wasn't packed, but the quote didn't include packing."})
    if not (inputs.get("elevatorPickup") or inputs.get("elevatorDropoff")) and ("elevator" in notes or "elevator_wait" in delays):
        flags.append({"key": "elevator_miss", "detail": "An elevator/elevator wait appeared that the quote didn't account for."})
    if "customer_added_items" in delays or "more items" in notes or "extra items" in notes:
        flags.append({"key": "added_items", "detail": "Customer added items on move day (difference, not a counted quantity)."})
    return flags


def _sample_or_test(lead_id: Optional[str], assignments: List[Dict[str, Any]]) -> Optional[str]:
    for a in assignments:
        nm = str(a.get("job_name") or "").upper()
        if nm.startswith("TEST") or nm.startswith("QA ") or "SAMPLE DATA" in nm:
            return "test_or_sample"
    return None


async def build_outcome(job_key: str, source: str, actor: str = "", reason: str = "") -> Optional[Dict[str, Any]]:
    """Assemble the CURRENT outcome and, when a material field changed, append an immutable version.
    A no-op rebuild creates no version (B8). Never changes pricing or trains anything."""
    assignments = await _assignments_for_job_key(job_key)
    if not assignments:
        return None
    primary = assignments[0]
    lead_id = next((a.get("lead_id") for a in assignments if a.get("lead_id")), None)
    project_id = next((a.get("project_id") for a in assignments if a.get("project_id")), None)
    sel = await _select_quote_scope(lead_id, assignments)
    quote = _build_quote_snapshot(sel)
    quoted_crew = None
    if quote:
        try:
            quoted_crew = int(float(quote.get("crew_rec"))) if quote.get("crew_rec") else None
        except (TypeError, ValueError):
            quoted_crew = None
    actuals = await compute_job_actuals(assignments, quoted_crew)
    prev = await mongo_db.job_outcomes.find_one({"_id": job_key})
    prev_corr_map = (prev or {}).get("corrections_map") or {}
    prev_corrections = (prev or {}).get("corrections") or []
    final_total = await _final_total_for(assignments, lead_id)
    if prev_corr_map.get("final_total") is not None:
        # An owner's explicit correction of the final billed amount always wins over the
        # Airtable-derived value and survives every future rebuild (preserved in corrections_map).
        final_total = {"value": prev_corr_map["final_total"], "source": "owner_correction",
                       "at": final_total.get("at")}
    errors = _derive_errors(quote, actuals, final_total.get("value"))
    survey_flags = _survey_miss_flags(quote, actuals)

    prev_decisions = (prev or {}).get("survey_miss", {}).get("decisions", {}) if prev else {}
    manual_excl = (prev or {}).get("exclusion", {}) if prev else {}

    reasons: List[str] = []
    ts = _sample_or_test(lead_id, assignments)
    if ts:
        reasons.append(ts)
    if actuals.get("data_quality") == "incomplete":
        reasons.append("incomplete")
    if actuals.get("data_quality") == "unmatched" or sel.get("rule") in ("no_lead", "no_scope", "ambiguous"):
        reasons.append("unmatched_quote")
    if not any(a.get("truck_id") for a in assignments):
        reasons.append("labor_only_truck_params")
    mwe = errors.get("model_work_mh_error")
    if mwe is not None and abs(mwe) > OUTCOME_OUTLIER_HOURS:
        reasons.append("model_outlier_pending_review")
    excluded = bool(manual_excl.get("manual")) or bool(reasons)
    exclusion = {"excluded": excluded, "reasons": sorted(set(reasons)),
                 "manual": bool(manual_excl.get("manual")), "reason": manual_excl.get("reason")}

    snapshot = {
        "project_id": project_id, "assignment_ids": [a["_id"] for a in assignments], "lead_id": lead_id,
        "job_name": primary.get("job_name"), "job_date": primary.get("job_date"),
        "quote": quote, "quote_match": {"rule": sel.get("rule"), "confidence": sel.get("confidence"),
                                        "quote_scope_id": (quote or {}).get("quote_scope_id")},
        "actuals": actuals, "errors": errors, "final_total": final_total,
        "survey_miss": {"flags": survey_flags, "decisions": prev_decisions},
        "data_quality": actuals.get("data_quality"),
        "learning_eligible": bool(actuals.get("learning_eligible") and not excluded),
        "exclusion": exclusion,
    }

    compare_keys = ("actuals", "quote_match", "errors", "final_total", "data_quality", "exclusion", "survey_miss")

    def _norm_cmp(key: str, val: Any) -> Any:
        # `final_total.at` is a rebuild timestamp, not a material fact — ignore it so an unchanged
        # re-derive (nightly reconcile, manual view) never manufactures a spurious version.
        if key == "final_total" and isinstance(val, dict):
            return {kk: vv for kk, vv in val.items() if kk != "at"}
        return val

    changed: Dict[str, Any] = {}
    if prev:
        for k in compare_keys:
            if json.dumps(_norm_cmp(k, prev.get(k)), sort_keys=True, default=str) != json.dumps(_norm_cmp(k, snapshot.get(k)), sort_keys=True, default=str):
                changed[k] = {"before": prev.get(k), "after": snapshot.get(k)}
    version = int((prev or {}).get("version", 0))
    if not prev or changed:
        version += 1
        current = {"_id": job_key, "version": version, "status": "current", **snapshot,
                   "built_at": now_iso(), "built_source": source, "built_by": actor or None,
                   "reason": reason or None, "created_at": (prev or {}).get("created_at") or now_iso(),
                   "corrections": prev_corrections, "corrections_map": prev_corr_map}
        await mongo_db.job_outcomes.replace_one({"_id": job_key}, current, upsert=True)
        await mongo_db.job_outcome_versions.insert_one({
            "_id": str(uuid4()), "job_key": job_key, "version": version, "at": now_iso(),
            "source": source, "actor": actor or None, "reason": reason or None,
            "changed_fields": changed if prev else {"created": True}, "snapshot": snapshot})
        return current
    return prev


# ---- durable rebuild queue + retry loop + nightly reconcile (mirrors the timelog pattern) ----
async def queue_outcome_rebuild(job_key: str, source: str, actor: str = "", reason: str = "") -> None:
    await mongo_db.outcome_rebuild_queue.update_one(
        {"_id": job_key}, {"$set": {"status": "pending", "source": source, "actor": actor,
                                    "reason": reason, "at": now_iso()}}, upsert=True)
    asyncio.create_task(_run_outcome_rebuild(job_key))


async def _run_outcome_rebuild(job_key: str) -> None:
    q = await mongo_db.outcome_rebuild_queue.find_one({"_id": job_key})
    if not q:
        return
    try:
        await build_outcome(job_key, q.get("source", "queue"), q.get("actor", ""), q.get("reason", ""))
        await mongo_db.outcome_rebuild_queue.update_one(
            {"_id": job_key}, {"$set": {"status": "done", "done_at": now_iso(), "error": None}})
    except Exception as exc:
        logger.warning("outcome rebuild failed for %s: %s", job_key, exc)
        await mongo_db.outcome_rebuild_queue.update_one(
            {"_id": job_key}, {"$set": {"status": "pending", "error": str(exc)[:300]}})


async def _queue_outcome_rebuild_for_assignment(assignment_id: str, source: str, actor: str = "") -> None:
    a = await mongo_db.assignments.find_one({"_id": assignment_id})
    if a:
        await queue_outcome_rebuild(_job_key_for_assignment(a), source, actor)


async def outcome_rebuild_loop() -> None:
    while True:
        try:
            for d in await mongo_db.outcome_rebuild_queue.find({"status": "pending"}).to_list(50):
                await _run_outcome_rebuild(d["_id"])
        except Exception as exc:
            logger.warning("outcome_rebuild_loop: %s", exc)
        await asyncio.sleep(120)


async def _run_nightly_outcome_reconcile() -> Dict[str, Any]:
    """2 AM ET: re-derive outcomes for jobs completed in the last 180 days so a direct Airtable edit or a
    late-synced punch is caught. Never invents events."""
    cutoff = (datetime.now(ZoneInfo("America/New_York")) - timedelta(days=180)).date().isoformat()
    seen, n = set(), 0
    for a in await mongo_db.assignments.find(
            {"job_date": {"$gte": cutoff}, "exec_status": "Complete"}).to_list(2000):
        key = _job_key_for_assignment(a)
        if key in seen:
            continue
        seen.add(key)
        await queue_outcome_rebuild(key, "nightly_reconcile")
        n += 1
    logger.info("nightly outcome reconcile queued=%s", n)
    return {"queued": n}


@public_router.post("/cron/nightly-outcome-reconcile")
async def cron_nightly_outcome_reconcile(request: Request) -> Dict[str, Any]:
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if not secret or not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Bad cron secret.")
    asyncio.create_task(_run_nightly_outcome_reconcile())
    return {"ok": True}


# ---- endpoints (owner + Quality; crew have no access) ----
def _outcome_out(doc: Optional[Dict[str, Any]], role: str = "owner") -> Optional[Dict[str, Any]]:
    if not doc:
        return None
    out = {k: v for k, v in doc.items() if k != "_id"} | {"job_key": doc["_id"]}
    if role == "quality":
        # Quality reviews outcomes but never sees revenue (final billed / dollar variance vs quote).
        ft = dict(out.get("final_total") or {})
        if "value" in ft:
            ft["value"] = None
            ft["redacted"] = True
        out["final_total"] = ft
        errs = dict(out.get("errors") or {})
        errs.pop("dollar_variance", None)
        errs.pop("in_band", None)
        out["errors"] = errs
        # the corrections history must not leak revenue either — drop final_total rows entirely
        corr = out.get("corrections")
        if isinstance(corr, list):
            out["corrections"] = [c for c in corr if c.get("field") != "final_total"]
        cmap = dict(out.get("corrections_map") or {})
        cmap.pop("final_total", None)
        out["corrections_map"] = cmap
    return out


@api_router.get("/outcomes/{job_key}")
async def get_outcome(job_key: str, request: Request, rebuild: int = 0):
    p = await require_outcome_role(request)
    if rebuild:
        await build_outcome(job_key, "manual_view", p.get("name", ""))
    doc = await mongo_db.job_outcomes.find_one({"_id": job_key})
    if not doc:
        assigns = await _assignments_for_job_key(job_key)
        if not assigns:
            raise HTTPException(status_code=404, detail="No such job.")
        doc = await build_outcome(job_key, "manual_view", p.get("name", ""))
    return _outcome_out(doc, p["role"])


@api_router.get("/outcomes/{job_key}/history")
async def get_outcome_history(job_key: str, request: Request):
    p = await require_outcome_role(request)
    versions = await mongo_db.job_outcome_versions.find({"job_key": job_key}).sort("version", -1).to_list(200)
    out = []
    for x in versions:
        v = {k: val for k, val in x.items() if k != "_id"}
        if p["role"] == "quality" and isinstance(v.get("snapshot"), dict):
            snap = dict(v["snapshot"])
            ft = dict(snap.get("final_total") or {})
            if "value" in ft:
                ft["value"] = None
                ft["redacted"] = True
            snap["final_total"] = ft
            errs = dict(snap.get("errors") or {})
            errs.pop("dollar_variance", None)
            errs.pop("in_band", None)
            snap["errors"] = errs
            v["snapshot"] = snap
            if isinstance(v.get("changed_fields"), dict):
                # keep only field NAMES for quality (values in errors/final_total would leak revenue)
                v["changed_fields"] = {k: {} for k in v["changed_fields"] if k not in ("final_total",)}
        out.append(v)
    return {"versions": out}


@api_router.get("/outcomes/{job_key}/scopes")
async def outcome_candidate_scopes(job_key: str, request: Request):
    """Saved quotes the owner/Quality can re-point this job to. Quality never sees the dollar amount."""
    p = await require_outcome_role(request)
    doc = await mongo_db.job_outcomes.find_one({"_id": job_key})
    lead_id = (doc or {}).get("lead_id")
    if not lead_id:
        assigns = await _assignments_for_job_key(job_key)
        lead_id = next((a.get("lead_id") for a in assigns if a.get("lead_id")), None)
    if not lead_id:
        return {"scopes": [], "active_quote_scope_id": None}
    link = await mongo_db.lead_quote_links.find_one({"_id": lead_id})
    active = (link or {}).get("active_quote_scope_id")
    scopes = await mongo_db.lead_scopes.find({"lead_id": lead_id}).sort("created_at", -1).to_list(50)
    rows = []
    for s in scopes:
        result = s.get("result") or {}
        amount = s.get("amount") if s.get("amount") is not None else result.get("finalTotal")
        rows.append({
            "id": s["_id"], "created_at": s.get("created_at"), "created_by": s.get("created_by"),
            "label": s.get("label") or "", "mode": result.get("mode") or s.get("estimate_mode"),
            "crew_rec": result.get("crewRec") or (s.get("inputs") or {}).get("crew"),
            "survey_complete": bool(s.get("survey_complete")),
            "amount": (None if p["role"] == "quality" else amount),
            "is_active": s["_id"] == active,
        })
    return {"scopes": rows, "active_quote_scope_id": active}


class OutcomeCorrectionPayload(BaseModel):
    field: str
    value: Any = None
    reason: str


@api_router.post("/outcomes/{job_key}/correct")
async def correct_outcome(job_key: str, payload: OutcomeCorrectionPayload, request: Request):
    """Owner/Quality supplement or fix a missing/incorrect fact with a required reason. The original value
    is preserved in the corrections log and a new version is created; nothing is overwritten in place."""
    p = await require_outcome_role(request)
    if len((payload.reason or "").strip()) < 5:
        raise HTTPException(status_code=422, detail="Give a reason (5+ characters) so the record makes sense later.")
    allowed = {"final_total", "actual_mileage", "as_found_note", "quoted_crew"}
    if payload.field not in allowed:
        raise HTTPException(status_code=422, detail=f"Can't correct '{payload.field}'.")
    if payload.field == "final_total" and p["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can correct the final billed amount.")
    doc = await mongo_db.job_outcomes.find_one({"_id": job_key})
    if not doc:
        raise HTTPException(status_code=404, detail="No such job outcome.")
    entry = {"field": payload.field, "value": payload.value, "before": doc.get("corrections_map", {}).get(payload.field),
             "by": p["name"], "by_id": p.get("user_id"), "at": now_iso(), "reason": payload.reason.strip()[:500]}
    await mongo_db.job_outcomes.update_one(
        {"_id": job_key}, {"$push": {"corrections": entry},
                           "$set": {f"corrections_map.{payload.field}": payload.value}})
    # NOTE: final_total is NOT pre-written here — build_outcome honors corrections_map.final_total and
    # rewrites the field itself, so the correction survives the rebuild instead of being clobbered by it.
    await audit(p, "corrected a job outcome", job_key, {"field": payload.field, "reason": payload.reason.strip()})
    src = "quality_edit" if p["role"] == "quality" else "owner_edit"
    fresh = await build_outcome(job_key, src, p["name"], payload.reason.strip())
    return _outcome_out(fresh, p["role"])


class ScopeRepointPayload(BaseModel):
    quote_scope_id: str
    reason: str


@api_router.post("/outcomes/{job_key}/repoint-scope")
async def repoint_outcome_scope(job_key: str, payload: ScopeRepointPayload, request: Request):
    p = await require_outcome_role(request)
    if len((payload.reason or "").strip()) < 5:
        raise HTTPException(status_code=422, detail="Give a reason (5+ characters) for re-pointing the quote.")
    doc = await mongo_db.job_outcomes.find_one({"_id": job_key})
    if not doc:
        raise HTTPException(status_code=404, detail="No such job outcome.")
    scope = await mongo_db.lead_scopes.find_one({"_id": payload.quote_scope_id})
    if not scope:
        raise HTTPException(status_code=404, detail="No such saved quote.")
    if doc.get("lead_id"):
        await _set_active_quote_link(doc["lead_id"], payload.quote_scope_id, scope.get("amount"),
                                     scope.get("commit_type") or "firm", p["name"], "outcome_repoint")
    await audit(p, "re-pointed the quote for a job outcome", job_key,
                {"quote_scope_id": payload.quote_scope_id, "reason": payload.reason.strip()})
    src = "quality_edit" if p["role"] == "quality" else "owner_edit"
    fresh = await build_outcome(job_key, src, p["name"], payload.reason.strip())
    return _outcome_out(fresh, p["role"])


class OutcomeExcludePayload(BaseModel):
    excluded: bool
    reason: str


@api_router.post("/outcomes/{job_key}/exclude")
async def exclude_outcome(job_key: str, payload: OutcomeExcludePayload, request: Request):
    p = await require_outcome_role(request)
    if len((payload.reason or "").strip()) < 5:
        raise HTTPException(status_code=422, detail="Give a reason (5+ characters).")
    doc = await mongo_db.job_outcomes.find_one({"_id": job_key})
    if not doc:
        raise HTTPException(status_code=404, detail="No such job outcome.")
    excl = dict(doc.get("exclusion") or {})
    excl["manual"] = bool(payload.excluded)
    excl["reason"] = payload.reason.strip()[:500]
    await mongo_db.job_outcomes.update_one({"_id": job_key}, {"$set": {"exclusion": excl}})
    await audit(p, "manually " + ("excluded" if payload.excluded else "re-included") + " a job outcome",
                job_key, {"reason": payload.reason.strip()})
    src = "quality_edit" if p["role"] == "quality" else "owner_edit"
    fresh = await build_outcome(job_key, src, p["name"], payload.reason.strip())
    return _outcome_out(fresh, p["role"])


class SurveyMissPayload(BaseModel):
    key: str
    decision: str   # confirmed | dismissed
    reason: Optional[str] = None


@api_router.post("/outcomes/{job_key}/survey-miss")
async def decide_survey_miss(job_key: str, payload: SurveyMissPayload, request: Request):
    p = await require_outcome_role(request)
    if payload.decision not in ("confirmed", "dismissed"):
        raise HTTPException(status_code=422, detail="Decision must be 'confirmed' or 'dismissed'.")
    doc = await mongo_db.job_outcomes.find_one({"_id": job_key})
    if not doc:
        raise HTTPException(status_code=404, detail="No such job outcome.")
    decisions = dict((doc.get("survey_miss") or {}).get("decisions") or {})
    decisions[payload.key] = {"decision": payload.decision, "by": p["name"], "at": now_iso(),
                              "reason": (payload.reason or "").strip()[:400]}
    await mongo_db.job_outcomes.update_one({"_id": job_key}, {"$set": {"survey_miss.decisions": decisions}})
    await audit(p, f"{payload.decision} a survey-miss flag", job_key, {"key": payload.key})
    src = "quality_edit" if p["role"] == "quality" else "owner_edit"
    fresh = await build_outcome(job_key, src, p["name"], f"survey miss {payload.decision}")
    return _outcome_out(fresh, p["role"])


@api_router.post("/outcomes-backfill")
async def backfill_outcomes(request: Request, days: int = 180):
    """Owner-only: build version 1 (source=backfill) for completed jobs in the window. Reports the mix
    without manufacturing missing events."""
    p = await require_owner(request)
    cutoff = (datetime.now(ZoneInfo("America/New_York")) - timedelta(days=max(1, min(3650, days)))).date().isoformat()
    keys, report = set(), {"processed": 0, "complete": 0, "incomplete": 0, "unmatched": 0,
                           "test": 0, "excluded": 0, "missing_final_total": 0, "explicit_scope": 0, "legacy_scope": 0}
    for a in await mongo_db.assignments.find(
            {"job_date": {"$gte": cutoff}, "exec_status": "Complete"}).to_list(3000):
        key = _job_key_for_assignment(a)
        if key in keys:
            continue
        keys.add(key)
        doc = await build_outcome(key, "backfill", p["name"])
        if not doc:
            continue
        report["processed"] += 1
        dq = doc.get("data_quality")
        report["complete"] += dq == "complete"
        report["incomplete"] += dq == "incomplete"
        report["unmatched"] += dq == "unmatched"
        if (doc.get("quote_match") or {}).get("rule") == "explicit_quote_scope_id":
            report["explicit_scope"] += 1
        elif doc.get("quote"):
            report["legacy_scope"] += 1
        if (doc.get("exclusion") or {}).get("excluded"):
            report["excluded"] += 1
        if "test_or_sample" in ((doc.get("exclusion") or {}).get("reasons") or []):
            report["test"] += 1
        if (doc.get("final_total") or {}).get("value") is None:
            report["missing_final_total"] += 1
    await audit(p, "ran the job-outcome backfill", f"{report['processed']} jobs", report)
    return report


# ======= Stage 6: Calculator Accuracy workspace (MEASUREMENT ONLY) =======
# Read-only aggregation of Stage-4 job_outcomes against the Stage-5 recorded model. It MEASURES how
# accurate the estimator is (man-hour bias/error, per-factor sample coverage, data-quality review queue,
# Stage-7 readiness preview) and shows the CURRENT estimating parameters. It NEVER suggests a calibration
# value, changes a quote, or trains anything — that is Stage 7 (separate explicit approval).
# Owner + Quality only; revenue (final billed / dollar variance / in-band) is redacted for Quality.
STAGE7_READINESS_TARGET = 10        # readiness REVIEW marker, NOT a trigger to enable learning
SPECIALTY_ITEM_KEYS = ("upright", "grand", "safe1", "safe2", "safe3", "pool", "tread", "gym", "moto")


def _coverage_label(n: int) -> str:
    if n <= 0:
        return "no_data"
    if n < 3:
        return "insufficient"
    if n < 8:
        return "limited"
    return "ok"


def _mean(vals: List[float]) -> Optional[float]:
    return round(sum(vals) / len(vals), 3) if vals else None


@api_router.get("/quality/calculator-accuracy")
async def quality_calculator_accuracy(request: Request):
    p = await require_outcome_role(request)      # owner + quality; sales/crew/marketing → 403
    is_owner = p["role"] == "owner"
    qp = request.query_params
    d_from, d_to = qp.get("from"), qp.get("to")

    outcomes = await mongo_db.job_outcomes.find({}).to_list(3000)

    def in_range(o: Dict[str, Any]) -> bool:
        d = (o.get("job_date") or "")[:10]
        if d_from and d and d < d_from:
            return False
        if d_to and d and d > d_to:
            return False
        return True
    outcomes = [o for o in outcomes if in_range(o)]

    def qinputs(o: Dict[str, Any]) -> Dict[str, Any]:
        return ((o.get("quote") or {}).get("inputs") or {})

    def werr(o: Dict[str, Any]) -> Optional[float]:
        return (o.get("errors") or {}).get("model_work_mh_error")

    usable: List[Dict[str, Any]] = []
    review: List[Dict[str, Any]] = []
    for o in outcomes:
        errs = o.get("errors") or {}
        excl = o.get("exclusion") or {}
        dq = o.get("data_quality")
        sm = o.get("survey_miss") or {}
        decisions = sm.get("decisions") or {}
        pending_sm = [fl.get("key") for fl in (sm.get("flags") or []) if fl.get("key") not in decisions]
        reasons: List[str] = []
        if dq == "incomplete":
            reasons.append("incomplete_actuals")
        if dq == "unmatched" or not o.get("quote") or "unmatched_quote" in (excl.get("reasons") or []):
            reasons.append("no_matched_quote")
        if "model_outlier_pending_review" in (excl.get("reasons") or []):
            reasons.append("model_outlier")
        if pending_sm:
            reasons.append("survey_miss_pending")
        if excl.get("manual"):
            reasons.append("manually_excluded")
        if is_owner and dq == "complete" and (o.get("final_total") or {}).get("value") is None:
            reasons.append("final_total_missing")
        if reasons:
            review.append({
                "job_key": o["_id"], "project_id": o.get("project_id"),
                "job_name": o.get("job_name") or "Untitled job", "job_date": o.get("job_date"),
                "reasons": sorted(set(reasons)), "data_quality": dq,
                "excluded": bool(excl.get("excluded")), "exclusion_reasons": excl.get("reasons") or [],
                "survey_miss_pending": pending_sm, "linkable": bool(o.get("project_id")),
            })
        if o.get("learning_eligible") and werr(o) is not None:
            usable.append(o)

    we = [werr(o) for o in usable if werr(o) is not None]
    abs_we = [abs(x) for x in we]
    pcts = [abs(werr(o)) / (o.get("actuals") or {}).get("work_man_hours")
            for o in usable if werr(o) is not None and (o.get("actuals") or {}).get("work_man_hours")]
    bias = _mean(we)
    bias_dir = "balanced" if bias is None else ("over" if bias > 0.05 else "under" if bias < -0.05 else "balanced")
    work_mh = {
        "sample": len(we), "label": _coverage_label(len(we)),
        "mean_signed_error": bias, "bias_direction": bias_dir, "mae": _mean(abs_we),
        "mean_abs_pct_error": (round(_mean(pcts) * 100, 1) if pcts else None),
        "within_1mh_rate": (round(sum(x <= 1.0 for x in abs_we) / len(abs_we) * 100, 1) if abs_we else None),
        "within_15pct_rate": (round(sum(x <= 0.15 for x in pcts) / len(pcts) * 100, 1) if pcts else None),
    }
    summary: Dict[str, Any] = {
        "total_outcomes": len(outcomes), "usable_jobs": len(usable),
        "excluded_jobs": sum(1 for o in outcomes if (o.get("exclusion") or {}).get("excluded")),
        "incomplete_jobs": sum(1 for o in outcomes if o.get("data_quality") == "incomplete"),
        "review_count": len(review), "data_label": _coverage_label(len(usable)), "work_mh": work_mh,
    }
    if is_owner:
        dv = [(o.get("errors") or {}).get("dollar_variance") for o in usable
              if (o.get("errors") or {}).get("dollar_variance") is not None]
        ib = [(o.get("errors") or {}).get("in_band") for o in usable
              if (o.get("errors") or {}).get("in_band") is not None]
        summary["dollars"] = {
            "sample": len(dv), "mean_dollar_variance": _mean(dv),
            "in_band_sample": len(ib),
            "in_band_rate": (round(sum(1 for b in ib if b) / len(ib) * 100, 1) if ib else None),
        }

    # ---- monthly trend (usable only) ----
    from collections import defaultdict
    months: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for o in usable:
        months[(o.get("job_date") or "")[:7] or "unknown"].append(o)
    trends = []
    for m in sorted(k for k in months if k != "unknown"):
        grp = months[m]
        g = [werr(o) for o in grp if werr(o) is not None]
        row = {"month": m, "jobs": len(grp), "mean_signed_error": _mean(g), "mae": _mean([abs(v) for v in g])}
        if is_owner:
            gdv = [(o.get("errors") or {}).get("dollar_variance") for o in grp
                   if (o.get("errors") or {}).get("dollar_variance") is not None]
            row["mean_dollar_variance"] = _mean(gdv)
        trends.append(row)

    # ---- per-factor sample coverage (measurement only; NO suggested values) ----
    def cov(subset: List[Dict[str, Any]]) -> Dict[str, Any]:
        e = [werr(o) for o in subset if werr(o) is not None]
        return {"sample": len(subset), "label": _coverage_label(len(subset)),
                "mean_signed_error": _mean(e), "mae": _mean([abs(v) for v in e])}

    packing = [{"tier": t, **cov([o for o in usable if int(qinputs(o).get("pack") or 0) == t])} for t in range(4)]
    access = [{"key": k, **cov([o for o in usable if (_num((qinputs(o).get("acc") or {}).get(k)) or 0) > 0])}
              for k in scope_engine.ACCESS_KEYS]
    specialty = cov([o for o in usable
                     if any((_num((qinputs(o).get("qty") or {}).get(k)) or 0) > 0 for k in SPECIALTY_ITEM_KEYS)
                     or (isinstance(qinputs(o).get("custom"), list) and qinputs(o).get("custom"))])
    packages = [{"key": k, **cov([o for o in usable if (qinputs(o).get("pkg") or "") == k])}
                for k in ("studio", "br2", "br3", "br4")]
    packages.append({"key": "none", **cov([o for o in usable if not qinputs(o).get("pkg")])})

    def crew_of(o: Dict[str, Any]) -> Optional[int]:
        cr = (o.get("quote") or {}).get("crew_rec")
        try:
            return int(float(cr)) if cr is not None else None
        except (TypeError, ValueError):
            return None
    crew_buckets = []
    for lo, hi, lbl in [(2, 2, "2"), (3, 3, "3"), (4, 4, "4"), (5, 99, "5plus")]:
        crew_buckets.append({"key": lbl, **cov([o for o in usable if crew_of(o) is not None and lo <= crew_of(o) <= hi])})

    coverage = {"base_rate": cov(usable), "packing": packing, "access": access,
                "specialty": specialty, "packages": packages, "crew": crew_buckets}

    # ---- current estimating parameters (read-only, non-monetary) ----
    params = await get_estimating_params()
    rates = await get_rates_values()
    calib = params.get("calibration_version", "v0")
    current_parameters = {
        "calibration_version": calib, "all_default": calib == "v0",
        "base_rate_mh_per_100cuft": rates.get("manHoursPer100CuFt"),
        "package_hours": params.get("packageHours"),
        "packing_multipliers": params.get("packingMult"),
        "access_per_mh": params.get("accessPer"),
        "item_multiplier": params.get("itemMult"),
        "crew_efficiency": params.get("crewEfficiency"),
        "scheduling": {"targetHoursOnSite": rates.get("targetHoursOnSite"),
                       "maxHoursOnSite": rates.get("maxHoursOnSite"),
                       "maxCrewPerDay": rates.get("maxCrewPerDay")},
    }

    est_state = await _estimating_active()
    opt = est_state["optimizer"]
    progress = {
        "usable_jobs": len(usable), "readiness_target": STAGE7_READINESS_TARGET,
        "ready_for_stage7_review": len(usable) >= STAGE7_READINESS_TARGET,
        "stage7_enabled": bool(opt.get("activated")),
        "paused": bool(opt.get("paused")),
        "calibration_version": est_state["calibration_version"],
        "note": ("The auto-optimizer is ACTIVE — it applies eligible, unlocked, gate-passing changes on the "
                 "nightly run (2:30 AM ET). Owner/Quality can Pause, Lock, Manually set or Roll back below."
                 if (opt.get("activated") and not opt.get("paused"))
                 else ("The auto-optimizer is PAUSED — it computes shadow suggestions but changes nothing."
                       if opt.get("paused")
                       else "The auto-optimizer is computing shadow suggestions only. Turn it on (Activate) to let "
                            "the nightly run apply eligible, unlocked changes within their sample thresholds and bounds.")),
    }

    review.sort(key=lambda r: r.get("job_date") or "", reverse=True)
    trends.sort(key=lambda r: r["month"])
    return {"role": p["role"], "summary": summary, "trends": trends, "coverage": coverage,
            "review_queue": review, "current_parameters": current_parameters, "progress": progress,
            "filters": {"from": d_from, "to": d_to}}



# ---- Stage 7 optimizer controls (owner + Quality; activation owner-only). Every action except Run now
# requires an audited reason; a Quality action also notifies the owner. Non-monetary only. ----
class OptimizerReasonPayload(BaseModel):
    reason: str = ""


class OptimizerPausePayload(BaseModel):
    paused: bool
    reason: str = ""


class OptimizerLockPayload(BaseModel):
    factor: str
    locked: bool
    reason: str = ""


class OptimizerManualPayload(BaseModel):
    factor: str
    value: float
    reason: str = ""
    expected_seq: Optional[int] = None


class OptimizerRollbackPayload(BaseModel):
    version: str
    reason: str = ""


class OptimizerActivatePayload(BaseModel):
    activated: bool
    reason: str = ""


def _require_reason(reason: str) -> str:
    r = (reason or "").strip()
    if len(r) < 5:
        raise HTTPException(status_code=422, detail="A reason (5+ characters) is required for this change.")
    return r


async def _notify_owner_of_quality_action(actor: Dict[str, Any], summary: str) -> None:
    if actor.get("role") == "quality":
        await notify(None, "owner", "Calibration changed by Quality", f"{actor.get('name')}: {summary}",
                     "calibration", {"by": actor.get("name")})


@api_router.get("/quality/optimizer/state")
async def optimizer_state(request: Request):
    await require_outcome_role(request)
    return await _optimizer_state_out()


@api_router.post("/quality/optimizer/run")
async def optimizer_run_now(request: Request):
    p = await require_outcome_role(request)
    run = await run_optimizer("run_now", p)
    await audit(p, "ran the estimating optimizer (run now)", run["_id"],
                {"mode": run["mode"], "applied_version": run.get("applied_version")})
    return {"run": {"id": run["_id"], "mode": run["mode"], "usable_jobs": run["usable_jobs"],
                    "applied_version": run.get("applied_version"), "changes": run.get("changes")},
            "state": await _optimizer_state_out()}


@api_router.post("/quality/optimizer/pause")
async def optimizer_pause(payload: OptimizerPausePayload, request: Request):
    p = await require_outcome_role(request)
    reason = _require_reason(payload.reason)
    est = await _estimating_active()
    opt = dict(est["optimizer"]); opt["paused"] = bool(payload.paused)
    await mongo_db.settings.update_one({"_id": "estimating_params"},
                                       {"$set": {"optimizer": opt, "updated_at": now_iso()}})
    await mongo_db.calibration_history.insert_one(
        {"_id": str(uuid4()), "at": now_iso(), "type": "pause" if payload.paused else "resume",
         "trigger": "pause" if payload.paused else "resume", "version": None, "reason": reason,
         "actor": p.get("name"), "actor_role": p.get("role")})
    await audit(p, f"{'paused' if payload.paused else 'resumed'} the estimating optimizer", "optimizer", {"reason": reason})
    await _notify_owner_of_quality_action(p, f"{'paused' if payload.paused else 'resumed'} the optimizer")
    return await _optimizer_state_out()


@api_router.post("/quality/optimizer/lock")
async def optimizer_lock(payload: OptimizerLockPayload, request: Request):
    p = await require_outcome_role(request)
    if payload.factor not in LOCK_GROUPS:
        raise HTTPException(status_code=422, detail="Unknown parameter to lock.")
    reason = _require_reason(payload.reason)
    est = await _estimating_active()
    locks = dict(est["locks"])
    baselines = dict(est["baselines"])
    baseline_change = None
    if payload.locked:
        locks[payload.factor] = {"locked": True, "by": p.get("name"), "at": now_iso(), "reason": reason}
    else:
        # On explicit UNLOCK the manually chosen value becomes this parameter's new optimizer baseline.
        locks.pop(payload.factor, None)
        baseline_change = _baseline_from_current(payload.factor, est["params"], baselines)
        if baseline_change is not None:
            baselines[payload.factor] = baseline_change
    await mongo_db.settings.update_one({"_id": "estimating_params"},
                                       {"$set": {"locks": locks, "baselines": baselines, "updated_at": now_iso()}})
    await mongo_db.calibration_history.insert_one(
        {"_id": str(uuid4()), "at": now_iso(), "type": "lock" if payload.locked else "unlock",
         "trigger": "lock" if payload.locked else "unlock", "version": None, "reason": reason,
         "factor": payload.factor, "baseline_after": baseline_change,
         "actor": p.get("name"), "actor_role": p.get("role")})
    await audit(p, f"{'locked' if payload.locked else 'unlocked'} {payload.factor}", "optimizer", {"reason": reason})
    await _notify_owner_of_quality_action(p, f"{'locked' if payload.locked else 'unlocked'} {payload.factor}")
    return await _optimizer_state_out()


def _baseline_from_current(group: str, params: Dict[str, Any], baselines: Dict[str, Any]) -> Any:
    if group == "base_rate":
        return _f(params.get("manHoursPer100CuFt"))
    if group.startswith("package_"):
        size = group.split("_", 1)[1]
        return _f((params.get("packageHours") or {}).get(size))
    if group == "drive_speed":
        return _f(params.get("avgDriveMph"))
    if group == "crew_efficiency":
        return dict(params.get("crewEfficiency") or {})
    if group == "multipliers":
        return {"packingMult": list(params.get("packingMult") or []),
                "accessPer": dict(params.get("accessPer") or {}), "itemMult": _f(params.get("itemMult"), 1.0)}
    return None


@api_router.post("/quality/optimizer/manual-set")
async def optimizer_manual_set(payload: OptimizerManualPayload, request: Request):
    p = await require_outcome_role(request)
    if payload.factor not in CALIB_SCALARS:
        raise HTTPException(status_code=422, detail="Unknown parameter.")
    reason = _require_reason(payload.reason)
    path, group, bounds, label = CALIB_SCALARS[payload.factor]
    val = float(payload.value)
    if not (bounds[0] <= val <= bounds[1]):
        raise HTTPException(status_code=422, detail=f"{label} must be between {bounds[0]} and {bounds[1]}.")
    est = await _estimating_active()
    before = _get_path(est["params"], path)
    new_params = copy.deepcopy(est["params"])
    _set_path(new_params, path, val)
    new_locks = dict(est["locks"])
    new_locks[group] = {"locked": True, "by": p.get("name"), "at": now_iso(),
                        "reason": f"Manually set {label} to {val}"}
    applied = await _apply_calibration(
        new_params, trigger="manual_edit", actor=p, reason=reason,
        changes=[{"factor": payload.factor, "key": ".".join(path),
                  "before": before, "after": val, "locked": True}],
        locks=new_locks,
        expected_seq=int(payload.expected_seq) if payload.expected_seq is not None else None)
    await audit(p, f"manually set {payload.factor}", "optimizer", {"reason": reason, "value": val})
    await _notify_owner_of_quality_action(p, f"manually set {label} to {val} ({applied['version']})")
    return await _optimizer_state_out()


@api_router.post("/quality/optimizer/rollback")
async def optimizer_rollback(payload: OptimizerRollbackPayload, request: Request):
    p = await require_outcome_role(request)
    reason = _require_reason(payload.reason)
    target = await mongo_db.calibration_history.find_one({"version": payload.version})
    if not target or not target.get("params_after"):
        raise HTTPException(status_code=404, detail="That calibration version can't be restored.")
    new_params = copy.deepcopy(target["params_after"])
    applied = await _apply_calibration(
        new_params, trigger="rollback", actor=p, reason=reason,
        changes=[{"factor": "rollback", "restored_version": payload.version}],
        locks=target.get("locks_after"), baselines=target.get("baselines_after"),
        extras={"restored_from": payload.version})
    await audit(p, f"rolled back to {payload.version}", "optimizer", {"reason": reason})
    await _notify_owner_of_quality_action(p, f"rolled back to {payload.version} (new {applied['version']})")
    return await _optimizer_state_out()


@api_router.post("/quality/optimizer/activate")
async def optimizer_activate(payload: OptimizerActivatePayload, request: Request):
    p = await require_outcome_role(request)
    if p.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can activate or deactivate automatic calibration.")
    reason = _require_reason(payload.reason)
    est = await _estimating_active()
    opt = dict(est["optimizer"])
    opt["activated"] = bool(payload.activated)
    opt["activated_by"] = p.get("name") if payload.activated else opt.get("activated_by")
    opt["activated_at"] = now_iso() if payload.activated else opt.get("activated_at")
    await mongo_db.settings.update_one({"_id": "estimating_params"},
                                       {"$set": {"optimizer": opt, "updated_at": now_iso()}})
    await mongo_db.calibration_history.insert_one(
        {"_id": str(uuid4()), "at": now_iso(), "type": "activate" if payload.activated else "deactivate",
         "trigger": "activate" if payload.activated else "deactivate", "version": None, "reason": reason,
         "actor": p.get("name"), "actor_role": p.get("role")})
    await audit(p, f"{'activated' if payload.activated else 'deactivated'} the estimating optimizer", "optimizer", {"reason": reason})
    return await _optimizer_state_out()


@api_router.get("/quality/optimizer/history")
async def optimizer_history(request: Request):
    await require_outcome_role(request)
    rows = await mongo_db.calibration_history.find({}).sort("at", -1).to_list(200)
    for r in rows:
        r["id"] = r.pop("_id", None)
    return {"history": rows}


@api_router.get("/quality/optimizer/runs")
async def optimizer_runs(request: Request):
    await require_outcome_role(request)
    rows = await mongo_db.optimizer_runs.find({}).sort("at", -1).to_list(50)
    out = []
    for r in rows:
        out.append({"id": r.get("_id"), "at": r.get("at"), "trigger": r.get("trigger"), "mode": r.get("mode"),
                    "usable_jobs": r.get("usable_jobs"), "applied_version": r.get("applied_version"),
                    "changes": r.get("changes"), "actor": r.get("actor")})
    return {"runs": out}


@api_router.get("/scope-guidance")
async def scope_guidance(request: Request):
    """Non-monetary calculator guidance for reps quoting a job: how much real-job data backs the current
    model, the model's recent hour accuracy, and a few ANONYMIZED similar completed jobs. Served to every
    calculator tier (survey included). Never returns names or dollars — hours/volume/crew only."""
    await require_scope_tier(request)
    qp = request.query_params
    try:
        cf = float(qp.get("cf")) if qp.get("cf") else None
    except (TypeError, ValueError):
        cf = None
    pkg = qp.get("pkg") or ""
    try:
        crew = int(float(qp.get("crew"))) if qp.get("crew") else None
    except (TypeError, ValueError):
        crew = None
    est = await _estimating_active()
    params = est["params"]
    outcomes = await mongo_db.job_outcomes.find({}).to_list(3000)
    data = _optimizer_training_data(outcomes, params)
    usable = data["usable_count"]

    def crew_bucket(n: Optional[int]) -> Optional[str]:
        if not n:
            return None
        return "2" if n <= 2 else "3" if n == 3 else "4" if n == 4 else "5plus"

    want_bucket = crew_bucket(crew)
    similar: List[Dict[str, Any]] = []
    errs_all: List[float] = []
    for o in outcomes:
        if not o.get("learning_eligible"):
            continue
        e = (o.get("errors") or {}).get("model_work_mh_error")
        if e is not None:
            errs_all.append(float(e))
        q = o.get("quote") or {}
        inp = q.get("inputs") or {}
        if inp.get("commercial") or o.get("commercial"):
            continue
        feats = scope_engine.compute_scope_features(inp, params)
        vol_cf = float(feats.get("cf") or 0)
        act = (o.get("actuals") or {}).get("work_man_hours")
        if act is None:
            continue
        try:
            crew_n = int(float(q.get("crew_rec"))) if q.get("crew_rec") is not None else None
        except (TypeError, ValueError):
            crew_n = None
        ok = True
        if cf and vol_cf > 0:
            ok = abs(vol_cf - cf) / max(cf, 1.0) <= 0.4
        elif pkg:
            ok = (inp.get("pkg") or "") == pkg
        if ok and want_bucket:
            ok = crew_bucket(crew_n) == want_bucket
        if not ok:
            continue
        similar.append({"volume_cf": round(vol_cf), "crew": crew_n,
                        "predicted_work_mh": round(float(feats.get("predicted_work_mh") or 0), 1),
                        "actual_work_mh": round(float(act), 1), "month": (o.get("job_date") or "")[:7]})
    similar.sort(key=lambda s: s.get("month") or "", reverse=True)
    n_err = len(errs_all)
    mae = round(sum(abs(x) for x in errs_all) / n_err, 2) if n_err else None
    bias = round(sum(errs_all) / n_err, 2) if n_err else None
    all_default = est["calibration_version"] == "v0"
    return {
        "calibration_version": est["calibration_version"], "all_default": all_default,
        "usable_jobs": usable, "base_rate_mh_per_100cuft": params.get("manHoursPer100CuFt"),
        "package_hours": params.get("packageHours"), "crew_efficiency": params.get("crewEfficiency"),
        "accuracy": {"sample": n_err, "mae": mae, "bias": bias},
        "similar": similar[:5],
        "hint": (f"Using baseline defaults — not yet calibrated from completed jobs ({usable} usable so far)."
                 if all_default else
                 f"Calibrated from {usable} completed job(s) (calibration {est['calibration_version']})."),
    }


async def _reconcile_then_optimize(trigger: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """Nightly: finish outcome reconciliation, drain the rebuild queue, THEN run the optimizer once."""
    await _run_nightly_outcome_reconcile()
    for _ in range(3):
        pending = await mongo_db.outcome_rebuild_queue.find({"status": "pending"}).to_list(200)
        if not pending:
            break
        for d in pending:
            await _run_outcome_rebuild(d["_id"])
    return await run_optimizer(trigger, "system", run_id=run_id)


@public_router.post("/cron/nightly-optimizer")
async def cron_nightly_optimizer(request: Request) -> Dict[str, Any]:
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if not secret or not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Bad cron secret.")
    et_date = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    run_id = f"nightly:{et_date}"
    if await mongo_db.optimizer_runs.find_one({"_id": run_id}):
        return {"ok": True, "skipped": "already_ran_today"}
    asyncio.create_task(_reconcile_then_optimize("nightly", run_id))
    return {"ok": True}


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
        # SECURITY (Problem #1): hidden/backdoor "ghost" POV accounts are NO LONGER
        # seeded in production. Actively remove any a prior deploy may have created, so
        # production carries zero backdoor/test logins. The test suite seeds its own
        # ephemeral ghost accounts via tests/conftest.py and deletes them when it ends.
        await mongo_db.users.delete_many({"ghost": True})
        await mongo_db.users.delete_many({"email": {"$in": [
            "testcrewadmin", "testsalesadmin", "testmarketingadmin", "testqualityadmin"]}})
        if await mongo_db.trucks.count_documents({}) == 0:
            for i in range(1, 6):
                await mongo_db.trucks.insert_one({"_id": str(uuid4()), "name": f"Truck {i}", "plate": "", "active": True})
        await dedupe_crew_users()
        await seed_team_module()
    except Exception as exc:
        logger.error("Startup seeding failed: %s", exc)
    asyncio.create_task(timelog_retry_loop())
    asyncio.create_task(late_alert_loop())
    asyncio.create_task(invoice_sync_loop())
    asyncio.create_task(lead_alert_loop())
    asyncio.create_task(meta_poll_loop())
    asyncio.create_task(challenge_agent_loop())
    asyncio.create_task(outcome_rebuild_loop())
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
