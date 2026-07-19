import asyncio
import hmac
import logging
import os
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Request
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


def require_auth(request: Request) -> str:
    payload = decode_token(request)
    role = payload.get("role") or payload.get("sub") or "owner"
    if role not in ROLES:
        raise HTTPException(status_code=401, detail="Invalid session. Log in again.")
    return role


def check_table_access(role: str, table_key: str):
    if table_key not in ROLE_TABLES.get(role, set()):
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


@auth_router.post("/login")
async def login(payload: LoginPayload, request: Request):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    rec = _login_attempts.get(ip, {})
    if rec.get("locked_until", 0) > now:
        raise HTTPException(status_code=429, detail="Too many tries. Wait 15 minutes and try again.")
    if not any(os.environ.get(v) for v in ROLE_ENV.values()):
        raise HTTPException(status_code=503, detail="No login passwords are set on the server.")
    role = None
    for r in ROLES:
        expected = os.environ.get(ROLE_ENV[r], "")
        if expected and hmac.compare_digest(payload.password, expected):
            role = r
            break
    if role is None:
        rec = _login_attempts.setdefault(ip, {"count": 0})
        rec["count"] = rec.get("count", 0) + 1
        if rec["count"] >= 5:
            rec["locked_until"] = now + 900
            rec["count"] = 0
        raise HTTPException(status_code=401, detail="Wrong password. Try again.")
    _login_attempts.pop(ip, None)
    return {"token": make_token(role), "role": role, "can_switch": role == "owner"}


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
    payload = decode_token(request)
    role = payload.get("role") or payload.get("sub") or "owner"
    if role not in ROLES:
        raise HTTPException(status_code=401, detail="Invalid session. Log in again.")
    can_switch = role == "owner" or bool(payload.get("owner_switch"))
    return {"ok": True, "role": role, "can_switch": can_switch}


@api_router.get("/")
async def root():
    return {"message": "Haul Yeah Moving CRM API"}


@api_router.get("/health")
async def health():
    return {"airtable_configured": bool(get_api_key()), "base_id_configured": bool(get_base_id())}


@api_router.get("/settings/rates")
async def get_rates(role: str = Depends(require_auth)):
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
    check_table_access(role, table_key)
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
    check_table_access(role, table_key)
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
    check_table_access(role, table_key)
    body = {"records": [{"fields": clean_write_fields(payload.fields, role, table_key)}], "typecast": True}
    data = await airtable_request("POST", table_id, json_body=body)
    return filter_record(data["records"][0], role, table_key)


@api_router.patch("/tables/{table_key}/{record_id}")
async def update_record(table_key: str, record_id: str, payload: RecordPayload = Body(...), role: str = Depends(require_auth)):
    table_id = resolve_table(table_key)
    check_table_access(role, table_key)
    body = {"records": [{"id": record_id, "fields": clean_write_fields(payload.fields, role, table_key)}], "typecast": True}
    data = await airtable_request("PATCH", table_id, json_body=body)
    return filter_record(data["records"][0], role, table_key)


@api_router.delete("/tables/{table_key}/{record_id}")
async def delete_record(table_key: str, record_id: str, role: str = Depends(require_auth)):
    table_id = resolve_table(table_key)
    check_table_access(role, table_key)
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can delete records.")
    await airtable_request("DELETE", table_id, path=f"/{record_id}")
    return {"deleted": True, "id": record_id}


app.include_router(auth_router)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
