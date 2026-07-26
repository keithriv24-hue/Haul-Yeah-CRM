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
QA_TRACK_TOKEN = "afe748c700fc481497a5720e5d80acde"


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
    client.close()


_refresh_qa_seed_dates()
