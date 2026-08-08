"""Pytest bootstrap: env loading + QA seed-date refresh so tests never drift off 'today'."""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pymongo
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

ET = ZoneInfo("America/New_York")
TODAY_ET = datetime.now(ET).strftime("%Y-%m-%d")
TRACK_JOB_DATE = (datetime.now(ET) + timedelta(days=3)).strftime("%Y-%m-%d")
from test_config import (CREW1_EMAIL, CREW1_PASSWORD, CREW2_EMAIL, CREW2_PASSWORD,  # noqa: E402
                         QA_TRACK_TOKEN)

QA_CREW1_ID = "f2a28cd4-2730-4ade-bc4d-3ed3e7506acb"
QA_CREW2_ID = "29f04e08-fc5a-41fc-a393-9bb886c511a6"


def _refresh_qa_seed_dates() -> None:
    client = pymongo.MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    db.assignments.delete_many({"job_name": {"$regex": "^(TEST_|TEST |TEMP |QA Prompt)"}})
    db.assignments.update_one(
        {"job_name": "QA Dispatch Move — Montclair"},
        {"$set": {"job_date": TODAY_ET, "arrival_time": "08:00"}})
    db.assignments.update_one(
        {"job_name": "QA Dispatch Move — Hoboken"},
        {"$set": {"job_date": TODAY_ET, "arrival_time": "14:30",
                  "exec_status": "Assigned", "crew": [], "truck_id": None}})
    db.jobs.update_one(
        {"tracking.token": QA_TRACK_TOKEN},
        {"$set": {"job_date": TRACK_JOB_DATE}})
    # prune test-artifact portal uploads so the 30-file cap never wedges the QA job
    db.portal_uploads.delete_many({"filename": {"$in": ["a.png", "i.pdf", "big.png", "qa_regress.png"]}})
    # prune accumulated clock/checklist history on the Montclair seed so its
    # timeline never outgrows the 200-event cap and drops old status events
    montclair = db.assignments.find_one({"job_name": "QA Dispatch Move — Montclair"}, {"_id": 1})
    if montclair:
        db.job_events.delete_many({"assignment_id": montclair["_id"]})
        db.time_entries.delete_many({"assignment_id": montclair["_id"]})
    _seed_qa_crew(db)
    client.close()


def _seed_qa_crew(db) -> None:
    """Ephemeral QA crew logins for the suite; removed again when the run ends."""
    import bcrypt
    from datetime import timezone
    now = datetime.now(timezone.utc).isoformat()
    for uid, name, email, pw, roles, consent in (
        (QA_CREW1_ID, "QA Crew One", CREW1_EMAIL, CREW1_PASSWORD, ["crew", "sales"], now),
        (QA_CREW2_ID, "QA Crew Two", CREW2_EMAIL, CREW2_PASSWORD, ["crew"], None),
    ):
        if db.users.find_one({"_id": uid, "email": email}):
            continue
        db.users.update_one(
            {"_id": uid},
            {"$set": {"name": name, "email": email, "role": "crew", "roles": roles,
                      "password_hash": bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
                      "active": True, "ghost": False, "must_change_password": False,
                      "gps_consent_at": consent, "created_at": now}},
            upsert=True)
    db.assignments.update_one(
        {"job_name": "QA Dispatch Move — Montclair", "crew.user_id": QA_CREW1_ID},
        {"$set": {"crew.$.name": "QA Crew One"}})
    db.jobs.update_one(
        {"tracking.token": QA_TRACK_TOKEN, "crew.user_id": QA_CREW1_ID},
        {"$set": {"crew.$.name": "QA Crew One"}})


def _remove_qa_crew() -> None:
    client = pymongo.MongoClient(os.environ["MONGO_URL"])
    client[os.environ["DB_NAME"]].users.delete_many({"_id": {"$in": [QA_CREW1_ID, QA_CREW2_ID]}})
    client.close()


if not os.environ.get("PYTEST_XDIST_WORKER"):
    import atexit
    atexit.register(_remove_qa_crew)


_refresh_qa_seed_dates()
