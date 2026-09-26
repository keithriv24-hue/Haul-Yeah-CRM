import json, os, uuid, subprocess

API = subprocess.check_output("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2", shell=True).decode().strip()

def call(method, path, token, body=None):
    cmd = ["curl", "-s", "-w", "\n%{http_code}", "-X", method, f"{API}/api{path}",
           "-H", "Content-Type: application/json"]
    if token:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    if body is not None:
        cmd += ["-d", json.dumps(body)]
    out = subprocess.check_output(cmd).decode()
    raw, _, code = out.rpartition("\n")
    try:
        return int(code), json.loads(raw or "{}")
    except json.JSONDecodeError:
        return int(code), {"_raw": raw[:200]}

def login(email, pw):
    _, d = call("POST", "/auth/login", None, {"email": email, "password": pw})
    return d["token"]

OT = login("HaulYeahAdmin", "HaulYeah2026!")
LEAD = "recGN17Xpd0Fm3fZx"   # a Booked production lead (read-only)

inputs = {"dens": {}, "cnt": {}, "qty": {}, "acc": {}, "mat": {}, "pack": 0, "rate": 2.1,
          "pkg": "3BR", "hoursOverride": None, "miles": 12}
pricing = {"rate": 2.1}
firm_result = {"mode": "final", "finalTotal": 2450, "deposit": 500, "crew": 3, "onsiteHours": 6.5}
range_result = {"mode": "range", "bandLo": 2200, "bandHi": 2700, "crew": 3}

print("=== 1) Draft auto-save (PUT /scope-drafts) idempotent + rev guard ===")
draft_id = str(uuid.uuid4())
s, d = call("PUT", "/scope-drafts", OT, {"draft_id": draft_id, "lead_id": LEAD, "rev": 1,
            "inputs": inputs, "pricing": pricing, "result": range_result})
print(" rev1:", s, "rev=", d.get("rev"), "stale=", d.get("stale"))
s, d = call("PUT", "/scope-drafts", OT, {"draft_id": draft_id, "lead_id": LEAD, "rev": 2,
            "inputs": inputs, "pricing": pricing, "result": firm_result})
print(" rev2:", s, "rev=", d.get("rev"), "stale=", d.get("stale"))
s, d = call("PUT", "/scope-drafts", OT, {"draft_id": draft_id, "lead_id": LEAD, "rev": 1,
            "inputs": inputs, "pricing": pricing, "result": {}})
print(" stale rev1 (expect stale True, rev stays 2):", s, "rev=", d.get("rev"), "stale=", d.get("stale"))

print("=== 2) Resume draft (GET /scope-drafts?lead_id=) ===")
s, d = call("GET", f"/scope-drafts?lead_id={LEAD}", OT)
print(" found draft:", bool(d.get("draft")), "| draft_id match:", (d.get("draft") or {}).get("_id") == draft_id)

print("=== 3) Commit with NO lead (expect 422 'Who is this quote for?') ===")
s, d = call("POST", "/scopes/commit", OT, {"commit_id": str(uuid.uuid4()), "commit_type": "firm",
            "inputs": inputs, "pricing": pricing, "result": firm_result})
print(" ", s, "|", d.get("detail"))

print("=== 4) Commit FIRM (Airtable read-only -> pending->error, Booked lead NOT auto-Quoted) ===")
cid = str(uuid.uuid4())
s, d = call("POST", "/scopes/commit", OT, {"commit_id": cid, "lead_id": LEAD, "commit_type": "firm",
            "draft_id": draft_id, "label": "Stage1 QA firm", "inputs": inputs, "pricing": pricing, "result": firm_result})
print(" ", s, "| commit_state:", d.get("commit_state"), "| amount:", d.get("amount"),
      "| status_changed:", d.get("status_changed"), "| aw.state:", (d.get("airtable_write") or {}).get("state"),
      "| aw.err:", (d.get("airtable_write") or {}).get("last_error"))
firm_scope_id = d.get("_id")

print("=== 5) Idempotency: repeat same commit_id -> same scope, no duplicate ===")
s, d2 = call("POST", "/scopes/commit", OT, {"commit_id": cid, "lead_id": LEAD, "commit_type": "firm",
            "inputs": inputs, "pricing": pricing, "result": firm_result})
print(" same _id:", d2.get("_id") == firm_scope_id)

print("=== 6) Draft retired after commit (GET should be gone) ===")
s, d = call("GET", f"/scope-drafts/{draft_id}", OT)
print(" draft after commit:", s, "(expect 404)")

print("=== 7) Retry write (still read-only -> error, attempts increments) ===")
s, d = call("POST", f"/scopes/{firm_scope_id}/retry-write", OT)
print(" ", s, "| commit_state:", d.get("commit_state"), "| attempts:", (d.get("airtable_write") or {}).get("attempts"))

print("=== 8) Commit RANGE (no Airtable write, no LF.quote, committed) ===")
s, d = call("POST", "/scopes/commit", OT, {"commit_id": str(uuid.uuid4()), "lead_id": LEAD, "commit_type": "range",
            "label": "Stage1 QA range", "inputs": inputs, "pricing": pricing, "result": range_result})
print(" ", s, "| commit_state:", d.get("commit_state"), "| amount:", d.get("amount"),
      "| commit_type:", d.get("commit_type"), "| aw:", d.get("airtable_write"))

print("=== 9) lead_quote_links reflects active firm quote + supersede history ===")
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
async def check():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = c[os.environ["DB_NAME"]]
    link = await db.lead_quote_links.find_one({"_id": LEAD})
    print(" active_quote_scope_id == firm scope:", (link or {}).get("active_quote_scope_id") == firm_scope_id)
    print(" mode:", (link or {}).get("mode"), "| amount:", (link or {}).get("amount"),
          "| history len:", len((link or {}).get("history") or []))
    # committed firm scope is training_eligible=false
    fs = await db.lead_scopes.find_one({"_id": firm_scope_id})
    print(" firm training_eligible:", fs.get("training_eligible"), "| status:", fs.get("status"),
          "| hours_source:", fs.get("hours_source"), "| pricing_version set:", bool(fs.get("pricing_version")))
asyncio.run(check())
