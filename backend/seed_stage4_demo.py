"""Seed a Mongo-only Stage 4 demo outcome on the real Montclair project so the Outcome tab renders
with full data in preview. Additive only — no Airtable/Square writes. Safe to re-run (idempotent)."""
import os
import pymongo
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = pymongo.MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

PID = "recFfjigzZDl1zm6J"          # Montclair project (Airtable)
LEAD = "reccMzCODXT4SJzUj"          # its linked lead
DAY = "2026-06-14"
AID = "stage4-demo-montclair"
U1, U2 = "s4demo-u1", "s4demo-u2"
S1, S2 = "stage4-demo-scope-committed", "stage4-demo-scope-alt"


def iso(t):
    return f"{DAY}T{t}:00"


db.assignments.replace_one({"_id": AID}, {
    "_id": AID, "project_id": PID, "lead_id": LEAD,
    "job_name": "Stage 4 QA — Outcome Demo (Montclair)", "job_date": DAY,
    "exec_status": "Complete", "truck_id": "stage4-demo-truck", "one_way_miles": 25,
    "crew": [{"user_id": U1, "name": "Demo Driver", "position": "Driver"},
             {"user_id": U2, "name": "Demo Helper", "position": "Helper"}],
    "crew_lead": {"taps": {"arrived": {"at": iso("09:00")}, "loaded": {"at": iso("10:00")},
                           "dropoff": {"at": iso("11:00")}, "complete": {"at": iso("12:30")}}},
    "status_history": [],
}, upsert=True)

db.time_entries.delete_many({"assignment_id": AID})
for uid, name, cin, cout in [(U1, "Demo Driver", "08:45", "13:00"), (U2, "Demo Helper", "09:00", "12:30")]:
    db.time_entries.insert_one({
        "_id": f"stage4-demo-{uid}", "assignment_id": AID, "user_id": uid, "user_name": name,
        "clock_in": {"at": iso(cin)}, "clock_out": {"at": iso(cout)},
        "hours": None, "approved": True, "estimated": False, "flags": []})

db.lead_scopes.replace_one({"_id": S1}, {
    "_id": S1, "lead_id": LEAD, "status": "saved", "label": "Committed quote",
    "created_by": "QA Seeder", "amount": 1450, "survey_complete": True,
    "inputs": {"crew": 2}, "pricing": {}, "created_at": iso("07:00"),
    "result": {"mode": "final", "finalTotal": 1450, "bandLo": 1400, "bandHi": 1600,
               "schedMH": 6, "billMH": 6, "crewRec": 2}}, upsert=True)
db.lead_scopes.replace_one({"_id": S2}, {
    "_id": S2, "lead_id": LEAD, "status": "saved", "label": "Alternate (4-crew) quote",
    "created_by": "QA Seeder", "amount": 1750, "survey_complete": True,
    "inputs": {"crew": 4}, "pricing": {}, "created_at": iso("06:00"),
    "result": {"mode": "final", "finalTotal": 1750, "bandLo": 1700, "bandHi": 1850,
               "schedMH": 8, "billMH": 8, "crewRec": 4}}, upsert=True)
db.lead_quote_links.replace_one({"_id": LEAD}, {
    "_id": LEAD, "active_quote_scope_id": S1, "amount": 1450, "mode": "final",
    "updated_at": iso("07:05")}, upsert=True)

# force a clean rebuild
db.job_outcomes.delete_one({"_id": f"project:{PID}"})
db.job_outcome_versions.delete_many({"job_key": f"project:{PID}"})
print("Seeded Stage 4 demo on project", PID, "-> open /projects/" + PID + " (Outcome tab)")
