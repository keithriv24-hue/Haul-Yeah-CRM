"""
meta_capi.py — Meta Conversions API sender for Haul Yeah CRM.

Sends server-side conversion events (Lead / Schedule / Purchase) to the Meta
dataset so Meta can optimize ad delivery toward leads that actually book and pay.

Reads config from environment (set these in the Emergent secrets panel):
    META_DATASET_ID          (required)  e.g. 1913145279380964
    META_CAPI_ACCESS_TOKEN   (required)  the Conversions API access token
    META_APP_SECRET          (optional)  enables appsecret_proof signing
    META_TEST_EVENT_CODE     (optional)  set while testing in Events Manager
    META_GRAPH_VERSION       (optional)  defaults to v21.0

Design notes:
  * All PII (email, phone, names, zip) is SHA-256 hashed before it leaves the
    server, per Meta's requirements. fbc/fbp/IP/user-agent are sent raw.
  * Every call is best-effort and never raises — a Meta outage must never break
    the CRM. Call these via asyncio.create_task(...) so they don't block the
    HTTP response.
  * event_id is stable per (lead, event) so retries and the browser Pixel
    deduplicate instead of double-counting.
"""

import os
import time
import hmac
import hashlib
import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("meta_capi")

GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v21.0").strip()


def _cfg() -> Dict[str, str]:
    return {
        "dataset_id": os.environ.get("META_DATASET_ID", "").strip(),
        "token": os.environ.get("META_CAPI_ACCESS_TOKEN", "").strip(),
        "app_secret": os.environ.get("META_APP_SECRET", "").strip(),
        "test_code": os.environ.get("META_TEST_EVENT_CODE", "").strip(),
    }


def capi_enabled() -> bool:
    c = _cfg()
    return bool(c["dataset_id"] and c["token"])


# ---------- hashing / normalization ----------

def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


def _norm_phone(phone: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) == 10:          # bare US number -> prepend country code
        digits = "1" + digits
    return digits


def build_fbc_from_fbclid(fbclid: str, click_ms: Optional[int] = None) -> str:
    """Reconstruct the fbc value from a raw fbclid query param."""
    ms = int(click_ms or time.time() * 1000)
    return f"fb.1.{ms}.{fbclid}"


def build_user_data(
    *,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    zip_code: Optional[str] = None,
    external_id: Optional[str] = None,
    fbc: Optional[str] = None,
    fbp: Optional[str] = None,
    fbclid: Optional[str] = None,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble a Meta user_data block. PII is hashed; identifiers are raw."""
    ud: Dict[str, Any] = {}
    if email:
        ud["em"] = [_sha256(_norm_email(email))]
    if phone:
        ph = _norm_phone(phone)
        if ph:
            ud["ph"] = [_sha256(ph)]
    if first_name:
        ud["fn"] = [_sha256(first_name.strip().lower())]
    if last_name:
        ud["ln"] = [_sha256(last_name.strip().lower())]
    if zip_code:
        ud["zp"] = [_sha256(str(zip_code).strip().lower())]
    if external_id:
        ud["external_id"] = [_sha256(str(external_id).strip().lower())]
    if not fbc and fbclid:
        fbc = build_fbc_from_fbclid(fbclid)
    if fbc:
        ud["fbc"] = fbc
    if fbp:
        ud["fbp"] = fbp
    if client_ip:
        ud["client_ip_address"] = client_ip
    if user_agent:
        ud["client_user_agent"] = user_agent
    return ud


# ---------- core sender ----------

async def send_event(
    event_name: str,
    user_data: Dict[str, Any],
    *,
    event_id: Optional[str] = None,
    event_time: Optional[int] = None,
    action_source: str = "system_generated",
    event_source_url: Optional[str] = None,
    custom_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    c = _cfg()
    if not (c["dataset_id"] and c["token"]):
        logger.info("Meta CAPI not configured; skipping %s", event_name)
        return {"skipped": True}

    event: Dict[str, Any] = {
        "event_name": event_name,
        "event_time": int(event_time or time.time()),
        "action_source": action_source,
        "user_data": user_data,
    }
    if event_id:
        event["event_id"] = event_id
    if event_source_url:
        event["event_source_url"] = event_source_url
    if custom_data:
        event["custom_data"] = custom_data

    payload: Dict[str, Any] = {"data": [event]}
    if c["test_code"]:
        payload["test_event_code"] = c["test_code"]

    params = {"access_token": c["token"]}
    if c["app_secret"]:
        params["appsecret_proof"] = hmac.new(
            c["app_secret"].encode("utf-8"),
            c["token"].encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{c['dataset_id']}/events"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, params=params, json=payload)
        data = resp.json() if resp.content else {}
        if resp.status_code != 200:
            logger.warning("Meta CAPI %s failed (%s): %s", event_name, resp.status_code, data)
            return {"ok": False, "status": resp.status_code, "response": data}
        logger.info("Meta CAPI %s sent: %s", event_name, data)
        return {"ok": True, "response": data}
    except Exception as exc:  # never let a marketing call break the CRM
        logger.warning("Meta CAPI %s error: %s", event_name, exc)
        return {"ok": False, "error": str(exc)}


# ---------- pipeline-stage helpers ----------
# `lead` is a plain dict you assemble from the Airtable lead + its lead_meta doc.
# Expected optional keys: id, email, phone, first_name, last_name, zip,
# fbc, fbp, fbclid, client_ip, user_agent, event_source_url.

def _ud_from_lead(lead: Dict[str, Any]) -> Dict[str, Any]:
    return build_user_data(
        email=lead.get("email"),
        phone=lead.get("phone"),
        first_name=lead.get("first_name"),
        last_name=lead.get("last_name"),
        zip_code=lead.get("zip"),
        external_id=lead.get("id"),
        fbc=lead.get("fbc"),
        fbp=lead.get("fbp"),
        fbclid=lead.get("fbclid"),
        client_ip=lead.get("client_ip"),
        user_agent=lead.get("user_agent"),
    )


async def fire_lead(lead: Dict[str, Any], *, event_time: Optional[int] = None) -> Dict[str, Any]:
    return await send_event(
        "Lead",
        _ud_from_lead(lead),
        event_id=f"{lead.get('id')}-Lead",
        event_time=event_time,
        action_source="website",
        event_source_url=lead.get("event_source_url"),
    )


async def fire_schedule(lead: Dict[str, Any], *, event_time: Optional[int] = None) -> Dict[str, Any]:
    # A move is booked — usually confirmed by phone in the CRM.
    return await send_event(
        "Schedule",
        _ud_from_lead(lead),
        event_id=f"{lead.get('id')}-Schedule",
        event_time=event_time,
        action_source="phone_call",
    )


async def fire_purchase(
    lead: Dict[str, Any],
    value: float,
    *,
    currency: str = "USD",
    event_time: Optional[int] = None,
    order_id: Optional[str] = None,
) -> Dict[str, Any]:
    # order_id (e.g. the Square invoice id) keeps the dedup id unique per payment.
    suffix = f"-{order_id}" if order_id else ""
    return await send_event(
        "Purchase",
        _ud_from_lead(lead),
        event_id=f"{lead.get('id')}-Purchase{suffix}",
        event_time=event_time,
        action_source="website",
        custom_data={"value": round(float(value), 2), "currency": currency},
    )
