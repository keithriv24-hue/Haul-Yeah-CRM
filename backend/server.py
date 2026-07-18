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
BLOCKED_FIELDS = {
    ("employee", "projects"): {PROJECT_QUOTE_FIELD, PROJECT_DEPOSIT_FIELD, PROJECT_REVENUE_FIELD},
}
DRIVER_RATE = 28
HELPER_RATE = 24


def require_auth(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else None
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        role = payload.get("role") or payload.get("sub") or "owner"
        if role not in ROLES:
            raise HTTPException(status_code=401, detail="Invalid session. Log in again.")
        return role
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session. Log in again.")


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
    token = jwt.encode(
        {"sub": role, "role": role, "type": "access", "exp": datetime.now(timezone.utc) + timedelta(days=30)},
        os.environ["JWT_SECRET"],
        algorithm=JWT_ALGORITHM,
    )
    return {"token": token, "role": role}


@auth_router.get("/me")
async def me(role: str = Depends(require_auth)):
    return {"ok": True, "role": role}


@api_router.get("/")
async def root():
    return {"message": "Haul Yeah Moving CRM API"}


@api_router.get("/health")
async def health():
    return {"airtable_configured": bool(get_api_key()), "base_id_configured": bool(get_base_id())}


@api_router.get("/airtable/verify")
async def verify_connection(role: str = Depends(require_auth)):
    if role != "owner":
        raise HTTPException(status_code=403, detail="Your role can't open this.")
    data = await airtable_request("GET", TABLES["leads"], params={"maxRecords": 1, "returnFieldsByFieldId": "true"})
    return {"ok": True, "records_seen": len(data.get("records", []))}


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


app.include_router(auth_router)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
