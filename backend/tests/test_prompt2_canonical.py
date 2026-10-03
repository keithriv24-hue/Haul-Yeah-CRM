"""Prompt 2 — ONE CANONICAL JOB + SAFE MIGRATION.

The preview Airtable PAT is READ-ONLY (writes 403), so these drive the canonical
Project service, booking rules, job-edit propagation and the migration/backfill
IN-PROCESS with server.airtable_request monkeypatched by a tiny in-memory Airtable
(same discipline as test_partc_airtable_norm / test_quality_module). They prove:
  - one authoritative get-or-create Project service (dedup, idempotent, concurrency-safe),
  - project_record_id immutability,
  - Booked requires a real deposit OR an authorized owner override (not a sales click),
  - completed-job edits require a reason + before/after audit,
  - cancellation stops upcoming dispatch while preserving the job,
  - deterministic backfill vs. ambiguous -> Owner review queue (never guessed).
"""
import asyncio
import uuid

import server as S

_LOOP = None


def _loop():
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP


def _run(coro):
    return _loop().run_until_complete(coro)


# --------------------------------------------------------------------------------------
# in-memory Airtable (projects + leads) so create-then-find works across calls
# --------------------------------------------------------------------------------------
class FakeAir:
    def __init__(self, lead_fields=None):
        self.projects = {}          # rec_id -> {"id","fields"}
        self.lead_fields = lead_fields or {}
        self.lead_patches = []      # records writes to the leads table
        self._seq = 0

    def seed_project(self, rec_id, fields):
        self.projects[rec_id] = {"id": rec_id, "fields": dict(fields)}

    async def __call__(self, method, table_id, path="", params=None, json_body=None):
        if table_id == S.TABLES["projects"]:
            if method == "GET" and path:
                rid = path.lstrip("/")
                if rid in self.projects:
                    return self.projects[rid]
                raise S.HTTPException(status_code=404, detail="not found")
            if method == "GET":
                return {"records": list(self.projects.values())}
            if method == "POST":
                self._seq += 1
                rid = f"recNEW{self._seq}"
                fields = dict(json_body["records"][0]["fields"])
                self.projects[rid] = {"id": rid, "fields": fields}
                return {"records": [{"id": rid, "fields": fields}]}
            if method == "PATCH":
                rid = json_body["records"][0]["id"]
                self.projects.setdefault(rid, {"id": rid, "fields": {}})
                self.projects[rid]["fields"].update(json_body["records"][0]["fields"])
                return {"records": [self.projects[rid]]}
        if table_id == S.TABLES["leads"]:
            if method == "GET":
                return {"id": path.lstrip("/"), "fields": dict(self.lead_fields)}
            if method == "PATCH":
                self.lead_patches.append(json_body["records"][0]["fields"])
                return {"records": [{"id": json_body["records"][0]["id"],
                                     "fields": json_body["records"][0]["fields"]}]}
        raise AssertionError(f"unexpected airtable call {method} {table_id}{path}")


def _patch(monkeypatch, fake):
    monkeypatch.setattr(S, "airtable_request", fake)


def _lead_fields(name="Dana Q", move_date="2026-11-01", quote=2000):
    return {S.LEAD_F["name"]: name, S.LEAD_F["move_date"]: move_date,
            S.LEAD_F["quote"]: quote, S.LEAD_F["from"]: "Montclair", S.LEAD_F["to"]: "Hoboken"}


def _cleanup(*lead_ids):
    async def go():
        for lid in lead_ids:
            await S.mongo_db.project_links.delete_one({"_id": lid})
            await S.mongo_db.job_booking.delete_one({"_id": lid})
            await S.mongo_db.project_migration_queue.delete_many({"lead_id": lid})
            await S.mongo_db.canonical_link_events.delete_many({"ref_id": lid})
        S._project_locks.clear()
    _run(go())


# --------------------------------------------------------------------------------------
# authoritative get-or-create
# --------------------------------------------------------------------------------------
def test_ensure_creates_once_and_binds_link(monkeypatch):
    fake = FakeAir()
    _patch(monkeypatch, fake)
    lid = f"recLEAD{uuid.uuid4().hex[:8]}"
    seed = S._project_seed_for_booking(_lead_fields(), lid, "Pending Deposit")
    rec, created = _run(S.ensure_project_for_lead(lid, seed, "test"))
    assert created is True and rec["id"].startswith("recNEW")
    link = _run(S.mongo_db.project_links.find_one({"_id": lid}))
    assert link and link["project_record_id"] == rec["id"] and link["locked"] is True
    # second call for the same lead returns the SAME project, never creates a second one
    rec2, created2 = _run(S.ensure_project_for_lead(lid, seed, "test"))
    assert created2 is False and rec2["id"] == rec["id"]
    assert len(fake.projects) == 1
    _cleanup(lid)


def test_ensure_finds_existing_by_lead_link(monkeypatch):
    fake = FakeAir()
    lid = f"recLEAD{uuid.uuid4().hex[:8]}"
    fake.seed_project("recOLD1", {S.PROJECT_LEAD_LINK_FIELD: [lid], S.PROJECT_NAME_FIELD: "old"})
    _patch(monkeypatch, fake)
    rec, created = _run(S.ensure_project_for_lead(lid, {}, "test"))
    assert created is False and rec["id"] == "recOLD1"
    link = _run(S.mongo_db.project_links.find_one({"_id": lid}))
    assert link["project_record_id"] == "recOLD1"
    _cleanup(lid)


def test_ensure_ambiguous_queues_and_never_guesses(monkeypatch):
    fake = FakeAir()
    lid = f"recLEAD{uuid.uuid4().hex[:8]}"
    fake.seed_project("recA", {S.PROJECT_LEAD_LINK_FIELD: [lid]})
    fake.seed_project("recB", {S.PROJECT_LEAD_LINK_FIELD: [lid]})
    _patch(monkeypatch, fake)
    rec, created = _run(S.ensure_project_for_lead(lid, {}, "test"))
    assert rec is None and created is False       # never picks one
    item = _run(S.mongo_db.project_migration_queue.find_one({"_id": f"lead:{lid}"}))
    assert item and item["status"] == "pending" and len(item["candidates"]) == 2
    _cleanup(lid)
    _run(S.mongo_db.project_migration_queue.delete_one({"_id": f"lead:{lid}"}))


def test_ensure_is_concurrency_safe(monkeypatch):
    fake = FakeAir()
    _patch(monkeypatch, fake)
    lid = f"recLEAD{uuid.uuid4().hex[:8]}"
    seed = S._project_seed_for_booking(_lead_fields(), lid, "Pending Deposit")
    results = _run(asyncio.gather(
        S.ensure_project_for_lead(lid, seed, "t1"),
        S.ensure_project_for_lead(lid, seed, "t2"),
        S.ensure_project_for_lead(lid, seed, "t3")))
    ids = {r[0]["id"] for r in results}
    assert len(ids) == 1, "two near-simultaneous requests must not create two Projects"
    assert len(fake.projects) == 1
    assert sum(1 for r in results if r[1]) == 1  # exactly one 'created'
    _cleanup(lid)


def test_project_record_id_is_immutable(monkeypatch):
    fake = FakeAir()
    _patch(monkeypatch, fake)
    lid = f"recLEAD{uuid.uuid4().hex[:8]}"
    _run(S._bind_lead_project(lid, "recFIRST", "test", None, "test"))
    kept = _run(S._bind_lead_project(lid, "recSECOND", "test", None, "test"))
    assert kept == "recFIRST"  # auto path refuses to repoint an established link
    link = _run(S.mongo_db.project_links.find_one({"_id": lid}))
    assert link["project_record_id"] == "recFIRST"
    _cleanup(lid)


# --------------------------------------------------------------------------------------
# booking rules — Booked requires deposit OR owner override (not a sales click)
# --------------------------------------------------------------------------------------
class _Req:
    pass


def _owner():
    return {"role": "owner", "roles": ["owner"], "name": "QA Owner", "user_id": "owner-uid"}


def _sales():
    return {"role": "sales", "roles": ["sales"], "name": "QA Sales", "user_id": "sales-uid"}


def test_sales_book_creates_pending_deposit_not_booked(monkeypatch):
    fake = FakeAir(lead_fields=_lead_fields())
    _patch(monkeypatch, fake)
    monkeypatch.setattr(S, "current_principal", lambda req: _async(_sales()))
    lid = f"recLEAD{uuid.uuid4().hex[:8]}"
    out = _run(S.book_lead_as_job(lid, _Req()))
    assert out["booked"] is False and out["booking_state"] == "pending_deposit"
    # a sales "Book as job" must NEVER write the lead Status to Booked
    assert all(S.LEAD_STATUS_F not in p or p[S.LEAD_STATUS_F] != "Booked" for p in fake.lead_patches)
    proj = fake.projects[out["project_record_id"]]
    assert proj["fields"][S.PROJECT_STATUS_FIELD] == "Pending Deposit"
    _cleanup(lid)


def test_override_requires_reason_and_marks_booked(monkeypatch):
    fake = FakeAir(lead_fields=_lead_fields())
    _patch(monkeypatch, fake)
    lid = f"recLEAD{uuid.uuid4().hex[:8]}"
    try:
        _run(S.mark_booked_override(lid, S.BookOverridePayload(reason="no"), _owner()))
        assert False, "short reason must 422"
    except S.HTTPException as e:
        assert e.status_code == 422
    out = _run(S.mark_booked_override(lid, S.BookOverridePayload(reason="VIP repeat customer"), _owner()))
    assert out["booked"] is True and out["booking_state"] == "owner_override"
    assert fake.lead_patches and fake.lead_patches[-1][S.LEAD_STATUS_F] == "Booked"
    doc = _run(S.get_booking_state(lid))
    assert doc["override"]["reason"] == "VIP repeat customer"
    assert doc["override"]["prior_state"] in ("none", "pending_deposit")
    _cleanup(lid)


def test_deposit_promotes_to_booked_and_keeps_override(monkeypatch):
    fake = FakeAir(lead_fields=_lead_fields())
    _patch(monkeypatch, fake)
    lid = f"recLEAD{uuid.uuid4().hex[:8]}"
    _run(S.set_booking_state(lid, "recP", "pending_deposit"))
    _run(S._book_on_deposit({"lead_id": lid, "project_record_id": "recP"}))
    assert _run(S.get_booking_state(lid))["booking_state"] == "booked"
    assert fake.lead_patches[-1][S.LEAD_STATUS_F] == "Booked"
    # an owner override is NOT downgraded by a later deposit sync
    _run(S.set_booking_state(lid, "recP", "owner_override"))
    _run(S._book_on_deposit({"lead_id": lid, "project_record_id": "recP"}))
    assert _run(S.get_booking_state(lid))["booking_state"] == "owner_override"
    _cleanup(lid)


# --------------------------------------------------------------------------------------
# completed-job edit guard + cancellation
# --------------------------------------------------------------------------------------
def _insert_job(**over):
    jid = f"jobT{uuid.uuid4().hex[:8]}"
    doc = {"_id": jid, "invoice_number": "QA-T", "lead_id": None, "crew": [],
           "customer": {"name": "T"}, "job_date": "2026-11-01",
           "pickup_address": "A St", "dropoff_address": "B St",
           "paid_in_full": {"status": "unpaid"}, "created_at": S.now_iso()}
    doc.update(over)
    _run(S.mongo_db.jobs.insert_one(doc))
    return jid


def test_completed_job_edit_requires_reason(monkeypatch):
    monkeypatch.setattr(S, "sync_project_for_job", lambda *a, **k: _async(None))
    monkeypatch.setattr(S, "geocode", lambda *a, **k: _async(None))
    jid = _insert_job(paid_in_full={"status": "paid"})
    # material edit (date) on a closed job with no reason -> 422
    try:
        _run(S.patch_job(jid, S.JobPatchPayload(job_date="2026-12-25"), _owner()))
        assert False, "closed-job material edit without reason must 422"
    except S.HTTPException as e:
        assert e.status_code == 422
    # with a reason it goes through and writes a before/after audit row
    _run(S.patch_job(jid, S.JobPatchPayload(job_date="2026-12-25", edit_reason="customer rescheduled"), _owner()))
    row = _run(S.mongo_db.job_edit_audit.find_one({"job_id": jid}))
    assert row and row["reason"] == "customer rescheduled"
    assert row["before"]["job_date"] == "2026-11-01" and row["after"]["job_date"] == "2026-12-25"
    _run(S.mongo_db.jobs.delete_one({"_id": jid}))
    _run(S.mongo_db.job_edit_audit.delete_many({"job_id": jid}))


def test_open_job_edit_needs_no_reason(monkeypatch):
    monkeypatch.setattr(S, "sync_project_for_job", lambda *a, **k: _async(None))
    monkeypatch.setattr(S, "geocode", lambda *a, **k: _async(None))
    jid = _insert_job()  # unpaid / open
    out = _run(S.patch_job(jid, S.JobPatchPayload(job_date="2026-12-01"), _owner()))
    assert out["job_date"] == "2026-12-01"
    assert _run(S.mongo_db.job_edit_audit.find_one({"job_id": jid})) is None
    _run(S.mongo_db.jobs.delete_one({"_id": jid}))


def test_cancel_job_stops_future_dispatch(monkeypatch):
    jid = _insert_job(project_record_id="recCAN", job_date=S._et_today())
    aid = f"asnT{uuid.uuid4().hex[:8]}"
    _run(S.mongo_db.assignments.insert_one({
        "_id": aid, "project_id": "recCAN", "job_name": "T", "job_date": S._et_today(),
        "crew": [{"user_id": "x", "name": "X", "position": "Driver"}], "exec_status": "Assigned"}))
    try:
        _run(S.cancel_job(jid, S.JobCancelPayload(reason="no"), _owner()))
        assert False, "short reason must 422"
    except S.HTTPException as e:
        assert e.status_code == 422
    out = _run(S.cancel_job(jid, S.JobCancelPayload(reason="customer cancelled move"), _owner()))
    assert out["assignments_stopped"] == 1
    job = _run(S.mongo_db.jobs.find_one({"_id": jid}))
    assert job["status"] == "cancelled" and job["cancellation"]["reason"] == "customer cancelled move"
    asn = _run(S.mongo_db.assignments.find_one({"_id": aid}))
    assert asn["cancelled"] is True
    _run(S.mongo_db.jobs.delete_one({"_id": jid}))
    _run(S.mongo_db.assignments.delete_one({"_id": aid}))


# --------------------------------------------------------------------------------------
# migration / backfill
# --------------------------------------------------------------------------------------
def test_migration_deterministic_vs_ambiguous(monkeypatch):
    fake = FakeAir()
    lid_one = f"recLEAD{uuid.uuid4().hex[:8]}"
    lid_amb = f"recLEAD{uuid.uuid4().hex[:8]}"
    fake.seed_project("recDET", {S.PROJECT_LEAD_LINK_FIELD: [lid_one], S.PROJECT_NAME_FIELD: "det"})
    fake.seed_project("recAM1", {S.PROJECT_LEAD_LINK_FIELD: [lid_amb]})
    fake.seed_project("recAM2", {S.PROJECT_LEAD_LINK_FIELD: [lid_amb]})
    _patch(monkeypatch, fake)
    j1 = _insert_job(lead_id=lid_one)
    j2 = _insert_job(lead_id=lid_amb)
    j3 = _insert_job(lead_id=None)  # no stable key -> skipped
    # dry run writes nothing
    rep = _run(S._migrate_project_ids(dry_run=True))
    assert rep["counts"]["deterministically_linked"] == 1
    assert rep["counts"]["ambiguous"] == 1
    assert "project_record_id" not in (_run(S.mongo_db.jobs.find_one({"_id": j1})) or {})
    # real run backfills the deterministic one, queues the ambiguous one
    rep2 = _run(S._migrate_project_ids(dry_run=False, actor=_owner()))
    assert rep2["counts"]["deterministically_linked"] == 1
    assert _run(S.mongo_db.jobs.find_one({"_id": j1}))["project_record_id"] == "recDET"
    q = _run(S.mongo_db.project_migration_queue.find_one({"_id": f"job:{j2}"}))
    assert q and q["status"] == "pending" and len(q["candidates"]) == 2
    # rerun is idempotent: no new project, already-linked counted, no second queue doc
    rep3 = _run(S._migrate_project_ids(dry_run=False, actor=_owner()))
    assert rep3["counts"]["already_linked"] >= 1
    assert _run(S.mongo_db.project_migration_queue.count_documents({"_id": f"job:{j2}"})) == 1
    # owner resolves the ambiguous job by linking a candidate
    res = _run(S.migration_review_resolve(f"job:{j2}",
               S.ReviewResolvePayload(action="link", project_record_id="recAM2"), _owner()))
    assert res["status"] == "resolved"
    assert _run(S.mongo_db.jobs.find_one({"_id": j2}))["project_record_id"] == "recAM2"
    # cleanup
    for jid in (j1, j2, j3):
        _run(S.mongo_db.jobs.delete_one({"_id": jid}))
    _run(S.mongo_db.project_migration_queue.delete_one({"_id": f"job:{j2}"}))
    _cleanup(lid_one, lid_amb)


def test_relink_requires_reason_and_repoints(monkeypatch):
    lid = f"recLEAD{uuid.uuid4().hex[:8]}"
    _run(S._bind_lead_project(lid, "recOLD", "test", None, "test"))
    jid = _insert_job(lead_id=lid, project_record_id="recOLD")
    try:
        _run(S.migration_relink(S.RelinkPayload(lead_id=lid, project_record_id="recNEWX", reason="x"), _owner()))
        assert False
    except S.HTTPException as e:
        assert e.status_code == 422
    out = _run(S.migration_relink(
        S.RelinkPayload(lead_id=lid, project_record_id="recNEWX", reason="merged duplicate"), _owner()))
    assert out["prev"] == "recOLD" and out["project_record_id"] == "recNEWX"
    assert _run(S.mongo_db.jobs.find_one({"_id": jid}))["project_record_id"] == "recNEWX"
    _run(S.mongo_db.jobs.delete_one({"_id": jid}))
    _cleanup(lid)


# small helper: wrap a plain value in an awaitable for monkeypatched async fns
def _async(val):
    async def go():
        return val
    return go()
