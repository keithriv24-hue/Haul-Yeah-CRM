"""Prompt 7 — Outcome data quality · Compliance Depart gate · Customer acknowledgment · Crons.

Everything runs IN-PROCESS (no real SMS / Square / Meta / production Airtable). Airtable reads
and writes are monkeypatched; httpx is faked for the brochure check. These prove the Prompt 7
acceptance criteria the owner confirmed:

  A. Outcome quality  — zero / negative / implausibly-short durations are flagged `invalid` and set
     learning_eligible = False; a clean outcome stays eligible; the optimizer training builder NEVER
     feeds a non-eligible outcome into calibration (the bad record is preserved, just excluded).
  B. Compliance Depart gate — a failing CRITICAL gate blocks Depart; enforcement off / an owner
     compliance override lets it through; a MISSING Project link or an unreadable Project does NOT
     fail open — it blocks as "unverifiable". The compliance-panel override opens an NC (write mocked).
  C. Customer acknowledgment — no brochure on file or broken/404 content -> 422; a temporary fetch
     failure / host 5xx -> 503 (paperwork state unknown, never falsely acknowledged).
  D. Crons / observability — _tracked_cron records start/success/failure (never raises); /cron/health
     is owner-only; rescheduling a job clears reminder_sent_at + paperwork-alert state while PRESERVING
     real paperwork completion (gates).
"""
import asyncio
import uuid

import server as S
import scope_engine


_LOOP = None


def _loop():
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP


def _run(coro):
    return _loop().run_until_complete(coro)


def _async(val):
    async def go():
        return val
    return go()


def _owner():
    return {"role": "owner", "roles": ["owner"], "name": "QA Owner", "user_id": "owner-uid"}


# ======================================================================================
# A. OUTCOME DATA QUALITY
# ======================================================================================
def _assign_with_taps(arrived=None, complete=None):
    taps = {}
    if arrived:
        taps["arrived"] = {"at": arrived}
    if complete:
        taps["complete"] = {"at": complete}
    return {"_id": f"a{uuid.uuid4().hex[:6]}", "crew_lead": {"taps": taps}}


def test_negative_duration_is_flagged_invalid():
    a = _assign_with_taps(arrived="2026-06-01T09:00:00", complete="2026-06-01T08:00:00")
    flags = S._outcome_validity_flags([a], on_site_hours=-1.0, total_day_hours=4.0)
    assert "negative_duration" in flags


def test_zero_duration_is_flagged_invalid():
    a = _assign_with_taps(arrived="2026-06-01T09:00:00", complete="2026-06-01T09:00:00")
    flags = S._outcome_validity_flags([a], on_site_hours=0.0, total_day_hours=4.0)
    assert "zero_duration" in flags


def test_implausibly_short_onsite_with_real_day_is_flagged():
    # 6-minute Arrived->Complete window while the crew clocked a 5-hour day = impossible.
    a = _assign_with_taps(arrived="2026-06-01T09:00:00", complete="2026-06-01T09:06:00")
    flags = S._outcome_validity_flags([a], on_site_hours=0.1, total_day_hours=5.0)
    assert "implausible_short_onsite" in flags


def test_zero_onsite_with_activity_is_flagged():
    flags = S._outcome_validity_flags([_assign_with_taps()], on_site_hours=0.0, total_day_hours=3.0)
    assert "zero_duration_with_activity" in flags


def test_clean_outcome_has_no_validity_flags():
    a = _assign_with_taps(arrived="2026-06-01T08:00:00", complete="2026-06-01T13:00:00")
    flags = S._outcome_validity_flags([a], on_site_hours=5.0, total_day_hours=6.0)
    assert flags == []


def _outcome(elig: bool, oid: str):
    return {"_id": oid, "learning_eligible": elig,
            "errors": {"model_work_mh_error": 1.0},
            "quote": {"inputs": {}, "crew_rec": 3},
            "actuals": {"work_man_hours": 10.0, "on_site_hours": 3.0,
                        "crew_adjusted_work_hours": 9.0},
            "job_date": "2026-06-01"}


def test_optimizer_training_excludes_non_eligible_outcomes():
    params = scope_engine.estimating_defaults()
    eligible = _outcome(True, "o-good")
    invalid = _outcome(False, "o-bad")        # exactly the same shape, only learning_eligible flips
    data = S._optimizer_training_data([eligible, invalid], params)
    assert "o-good" in data["job_keys"]
    assert "o-bad" not in data["job_keys"], "a non-eligible (invalid) outcome must never train the optimizer"
    assert data["usable_count"] == 1


def test_invalid_outcome_is_preserved_not_dropped():
    # The builder keeps the invalid record (for audit/history); it is excluded from LEARNING, not deleted.
    params = scope_engine.estimating_defaults()
    invalid = _outcome(False, "o-keep")
    data = S._optimizer_training_data([invalid], params)
    assert data["usable_count"] == 0
    # the record object itself is untouched by the training pass
    assert invalid["_id"] == "o-keep" and invalid["learning_eligible"] is False


# ======================================================================================
# B. COMPLIANCE DEPART GATE
# ======================================================================================
_CRIT_KEY = sorted(S.CRITICAL_GATE_KEYS)[0]


def _failing_crit_gate():
    return [{"key": _CRIT_KEY, "label": "Company credentials on file", "severity": "Regulatory",
             "passed": False, "exempt": False, "reason": "missing"}]


def _passing_gate():
    return [{"key": _CRIT_KEY, "label": "Company credentials on file", "severity": "Regulatory",
             "passed": True, "exempt": False, "reason": ""}]


def test_verdict_enforcement_off_never_blocks(monkeypatch):
    monkeypatch.setattr(S, "_compliance_config", lambda: _async({"block_depart_on_critical": False}))
    v = _run(S._compliance_depart_verdict({"_id": "x"}))   # even with no project link
    assert v["block"] is False


def test_verdict_missing_project_link_blocks_unverifiable(monkeypatch):
    monkeypatch.setattr(S, "_compliance_config", lambda: _async({"block_depart_on_critical": True}))
    v = _run(S._compliance_depart_verdict({"_id": "x"}))   # no project_id
    assert v["block"] is True and v["kind"] == "unverifiable"
    assert "verified" in v["reason"]


def test_verdict_failing_critical_gate_blocks(monkeypatch):
    pid = f"recP{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(S, "_compliance_config", lambda: _async({"block_depart_on_critical": True}))
    monkeypatch.setattr(S, "_fetch_project", lambda p: _async({"id": p, "fields": {}}))
    monkeypatch.setattr(S, "_compliance_context", lambda recs: _async({}))
    monkeypatch.setattr(S, "evaluate_gates", lambda rec, ctx: _failing_crit_gate())
    v = _run(S._compliance_depart_verdict({"project_id": pid}))
    assert v["block"] is True and v["kind"] == "gate"
    assert "Company credentials on file" in v["failed_labels"]


def test_verdict_all_gates_pass_allows_depart(monkeypatch):
    pid = f"recP{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(S, "_compliance_config", lambda: _async({"block_depart_on_critical": True}))
    monkeypatch.setattr(S, "_fetch_project", lambda p: _async({"id": p, "fields": {}}))
    monkeypatch.setattr(S, "_compliance_context", lambda recs: _async({}))
    monkeypatch.setattr(S, "evaluate_gates", lambda rec, ctx: _passing_gate())
    v = _run(S._compliance_depart_verdict({"project_id": pid}))
    assert v["block"] is False


def test_verdict_owner_override_allows_depart(monkeypatch):
    pid = f"recP{uuid.uuid4().hex[:8]}"
    _run(S.mongo_db.job_compliance.insert_one(
        {"_id": pid, "override": {"reason": "owner authorized", "by": "QA Owner", "at": S.now_iso()}}))
    monkeypatch.setattr(S, "_compliance_config", lambda: _async({"block_depart_on_critical": True}))
    try:
        v = _run(S._compliance_depart_verdict({"project_id": pid}))
        assert v["block"] is False
    finally:
        _run(S.mongo_db.job_compliance.delete_one({"_id": pid}))


def test_verdict_unreadable_project_blocks_unverifiable(monkeypatch):
    pid = f"recP{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(S, "_compliance_config", lambda: _async({"block_depart_on_critical": True}))

    def boom(p):
        raise S.HTTPException(status_code=503, detail="airtable down")
    monkeypatch.setattr(S, "_fetch_project", boom)
    v = _run(S._compliance_depart_verdict({"project_id": pid}))
    assert v["block"] is True and v["kind"] == "unverifiable"


# ---- compliance-panel override opens an NC (Airtable write mocked) ----
async def _fake_air_nc(method, table_id, path="", params=None, json_body=None):
    if table_id == S.TABLES["nonconformances"] and method == "POST":
        return {"records": [{"id": "recNCQA", "fields": json_body["records"][0]["fields"]}]}
    raise AssertionError(f"unexpected airtable call {method} {table_id}{path}")


def test_compliance_override_opens_nc_and_records(monkeypatch):
    pid = f"recP{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(S, "_fetch_project", lambda p: _async({"id": p, "fields": {}}))
    monkeypatch.setattr(S, "_compliance_context", lambda recs: _async({}))
    monkeypatch.setattr(S, "evaluate_gates", lambda rec, ctx: _failing_crit_gate())
    monkeypatch.setattr(S, "airtable_request", _fake_air_nc)
    try:
        out = _run(S.override_job_compliance(
            pid, S.OverridePayload(reason="Owner authorized departure despite the missing doc",
                                   confirm="OVERRIDE"), _owner()))
        assert out["override"]["nc_id"] == "recNCQA"
        doc = _run(S.mongo_db.job_compliance.find_one({"_id": pid}))
        assert doc["override"]["reason"].startswith("Owner authorized")
        assert doc["override"]["by"] == "QA Owner"
    finally:
        _run(S.mongo_db.job_compliance.delete_one({"_id": pid}))


def test_compliance_override_requires_reason_and_confirm(monkeypatch):
    pid = f"recP{uuid.uuid4().hex[:8]}"
    # short reason -> 422
    try:
        _run(S.override_job_compliance(pid, S.OverridePayload(reason="nope", confirm="OVERRIDE"), _owner()))
        assert False, "short reason must 422"
    except S.HTTPException as e:
        assert e.status_code == 422
    # wrong confirm word -> 422
    try:
        _run(S.override_job_compliance(
            pid, S.OverridePayload(reason="A fully written twenty-plus character reason", confirm="yes"), _owner()))
        assert False, "bad confirm must 422"
    except S.HTTPException as e:
        assert e.status_code == 422


def test_compliance_override_nothing_to_override(monkeypatch):
    pid = f"recP{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(S, "_fetch_project", lambda p: _async({"id": p, "fields": {}}))
    monkeypatch.setattr(S, "_compliance_context", lambda recs: _async({}))
    monkeypatch.setattr(S, "evaluate_gates", lambda rec, ctx: _passing_gate())
    try:
        _run(S.override_job_compliance(
            pid, S.OverridePayload(reason="Trying to override a clean job on purpose", confirm="OVERRIDE"), _owner()))
        assert False, "override with all gates green must 422"
    except S.HTTPException as e:
        assert e.status_code == 422


# ---- owner depart-override logs who/when/reason + the failed gate it cleared ----
def test_depart_override_audits_and_clears_blocker(monkeypatch):
    aid = f"asn{uuid.uuid4().hex[:8]}"
    blocker = {"kind": "compliance", "failed_labels": ["Company credentials on file"],
               "at": S.now_iso(), "by": "QA Crew"}
    _run(S.mongo_db.assignments.insert_one(
        {"_id": aid, "job_name": "QA Depart Override", "crew": [],
         "crew_lead": {"taps": {}, "depart_blocker": blocker}}))
    try:
        try:
            _run(S.depart_override(aid, S.DepartOverridePayload(reason="short"), _owner()))
            assert False, "reason under 10 chars must 422"
        except S.HTTPException as e:
            assert e.status_code == 422
        _run(S.depart_override(
            aid, S.DepartOverridePayload(reason="Owner authorized this departure", resolution="override"), _owner()))
        a = _run(S.mongo_db.assignments.find_one({"_id": aid}))
        cl = a["crew_lead"]
        assert cl["depart_blocker"] is None
        ov = cl["depart_override"]
        assert ov["by"] == "QA Owner" and ov["at"] and ov["reason"].startswith("Owner authorized")
        assert ov["cleared_blocker"]["failed_labels"] == ["Company credentials on file"]
    finally:
        _run(S.mongo_db.assignments.delete_one({"_id": aid}))


# ======================================================================================
# C. CUSTOMER ACKNOWLEDGMENT
# ======================================================================================
class _FakeResp:
    def __init__(self, status_code, content=b"%PDF-brochure"):
        self.status_code = status_code
        self.content = content


class _FakeClient:
    def __init__(self, resp=None, exc=None):
        self._resp, self._exc = resp, exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        if self._exc:
            raise self._exc
        return self._resp


class _FakeReq:
    client = type("C", (), {"host": "1.2.3.4"})()
    headers = {"user-agent": "pytest"}


def _ack_job():
    return {"_id": f"job{uuid.uuid4().hex[:8]}", "invoice_number": "QA-ACK", "gates": {},
            "customer": {"name": "Dana"}}


def _set_portal(monkeypatch, brochure_url=None):
    monkeypatch.setattr(S, "_portal_settings",
                        lambda: _async({"brochure_url": brochure_url} if brochure_url else {}))


def test_ack_no_brochure_on_file_422(monkeypatch):
    job = _ack_job()
    monkeypatch.setattr(S, "_job_by_token", lambda t: _async(job))
    _set_portal(monkeypatch, brochure_url=None)
    try:
        _run(S.portal_acknowledge_paperwork("tok", S.PaperworkAckPayload(name="Dana Q"), _FakeReq()))
        assert False, "no brochure must 422"
    except S.HTTPException as e:
        assert e.status_code == 422
    assert _run(S.mongo_db.paperwork_acks.find_one({"job_id": job["_id"]})) is None


def test_ack_broken_brochure_link_422(monkeypatch):
    job = _ack_job()
    monkeypatch.setattr(S, "_job_by_token", lambda t: _async(job))
    _set_portal(monkeypatch, brochure_url="https://files.example/brochure.pdf")
    monkeypatch.setattr(S.httpx, "AsyncClient", lambda *a, **k: _FakeClient(resp=_FakeResp(404)))
    try:
        _run(S.portal_acknowledge_paperwork("tok", S.PaperworkAckPayload(name="Dana Q"), _FakeReq()))
        assert False, "404 brochure must 422"
    except S.HTTPException as e:
        assert e.status_code == 422
    assert _run(S.mongo_db.paperwork_acks.find_one({"job_id": job["_id"]})) is None


def test_ack_temporary_fetch_failure_503(monkeypatch):
    job = _ack_job()
    monkeypatch.setattr(S, "_job_by_token", lambda t: _async(job))
    _set_portal(monkeypatch, brochure_url="https://files.example/brochure.pdf")
    monkeypatch.setattr(S.httpx, "AsyncClient",
                        lambda *a, **k: _FakeClient(exc=S.httpx.ConnectTimeout("boom")))
    try:
        _run(S.portal_acknowledge_paperwork("tok", S.PaperworkAckPayload(name="Dana Q"), _FakeReq()))
        assert False, "temporary failure must 503, not 422"
    except S.HTTPException as e:
        assert e.status_code == 503
    assert _run(S.mongo_db.paperwork_acks.find_one({"job_id": job["_id"]})) is None


def test_ack_host_5xx_is_503(monkeypatch):
    job = _ack_job()
    monkeypatch.setattr(S, "_job_by_token", lambda t: _async(job))
    _set_portal(monkeypatch, brochure_url="https://files.example/brochure.pdf")
    monkeypatch.setattr(S.httpx, "AsyncClient", lambda *a, **k: _FakeClient(resp=_FakeResp(503)))
    try:
        _run(S.portal_acknowledge_paperwork("tok", S.PaperworkAckPayload(name="Dana Q"), _FakeReq()))
        assert False, "host 5xx must 503"
    except S.HTTPException as e:
        assert e.status_code == 503


def test_ack_valid_brochure_records_and_clears_alert(monkeypatch):
    job = _ack_job()
    _run(S.mongo_db.jobs.insert_one(
        {"_id": job["_id"], "invoice_number": "QA-ACK", "gates": {},
         "paperwork_alert": {"active": True}, "customer": {"name": "Dana"}}))
    monkeypatch.setattr(S, "_job_by_token", lambda t: _async(job))
    _set_portal(monkeypatch, brochure_url="https://files.example/brochure.pdf")
    monkeypatch.setattr(S.httpx, "AsyncClient", lambda *a, **k: _FakeClient(resp=_FakeResp(200)))
    monkeypatch.setattr(S, "_owner_portal_ping", lambda *a, **k: _async(None))
    try:
        out = _run(S.portal_acknowledge_paperwork("tok", S.PaperworkAckPayload(name="Dana Q"), _FakeReq()))
        assert out["ok"] is True and out["name"] == "Dana Q"
        ack = _run(S.mongo_db.paperwork_acks.find_one({"job_id": job["_id"]}))
        assert ack and ack["documents"][0]["sha256"]          # a real document hash was recorded
        fresh = _run(S.mongo_db.jobs.find_one({"_id": job["_id"]}))
        assert fresh["paperwork_alert"]["active"] is False     # only now is the owner alert cleared
    finally:
        _run(S.mongo_db.jobs.delete_one({"_id": job["_id"]}))
        _run(S.mongo_db.paperwork_acks.delete_many({"job_id": job["_id"]}))


# ======================================================================================
# D. CRONS / OBSERVABILITY + RESCHEDULE
# ======================================================================================
def test_tracked_cron_records_success():
    name = f"qa-cron-ok-{uuid.uuid4().hex[:6]}"

    async def work():
        return {"sent": 2, "skipped": 1}
    try:
        _run(S._tracked_cron(name, work))
        d = _run(S.mongo_db.job_health.find_one({"_id": name}))
        assert d["last_status"] == "success"
        assert d["last_result"] == {"sent": 2, "skipped": 1}
        assert d["last_started_at"] and d["last_success_at"]
        assert d["runs"] == 1 and d.get("failures", 0) == 0
        assert S._job_health_status(d) == "healthy"
    finally:
        _run(S.mongo_db.job_health.delete_one({"_id": name}))


def test_tracked_cron_records_failure_without_raising():
    name = f"qa-cron-fail-{uuid.uuid4().hex[:6]}"

    async def boom():
        raise RuntimeError("cron blew up")
    try:
        _run(S._tracked_cron(name, boom))   # must NOT raise — cron already acked 2xx
        d = _run(S.mongo_db.job_health.find_one({"_id": name}))
        assert d["last_status"] == "failure"
        assert "cron blew up" in d["last_error"]
        assert d["failures"] == 1 and d["last_failure_at"]
        assert S._job_health_status(d) == "failing"
    finally:
        _run(S.mongo_db.job_health.delete_one({"_id": name}))


def test_cron_health_reports_all_jobs():
    out = _run(S.cron_health(_owner()))
    names = {j["name"] for j in out["jobs"]}
    assert set(S.CRON_JOB_NAMES).issubset(names)
    assert set(S.LOOP_JOB_NAMES).issubset(names)
    for j in out["jobs"]:
        assert j["status"] in ("healthy", "failing", "unknown")
        assert "last_started_at" in j and "last_success_at" in j and "last_failure_at" in j


def test_cron_health_is_owner_only():
    route = next(r for r in S.app.routes if getattr(r, "path", "") == "/api/cron/health")
    dep_calls = [d.call for d in route.dependant.dependencies]
    assert S.require_owner in dep_calls


def test_reschedule_clears_reminder_latch_but_keeps_paperwork(monkeypatch):
    monkeypatch.setattr(S, "sync_project_for_job", lambda *a, **k: _async(None))
    monkeypatch.setattr(S, "_propagate_job_addresses", lambda *a, **k: _async(None))
    monkeypatch.setattr(S, "geocode", lambda *a, **k: _async(None))
    monkeypatch.setattr(S, "_notify_new_crew_members", lambda *a, **k: _async(None))
    jid = f"job{uuid.uuid4().hex[:8]}"
    _run(S.mongo_db.jobs.insert_one({
        "_id": jid, "invoice_number": "QA-RS", "lead_id": None, "crew": [],
        "customer": {"name": "T"}, "job_date": "2026-11-01",
        "pickup_address": "A St", "dropoff_address": "B St",
        "paid_in_full": {"status": "unpaid"}, "created_at": S.now_iso(),
        "reminder_sent_at": S.now_iso(),
        "paperwork_alert": {"active": True, "tier": "t48"},
        "gates": {"brochure_sent_at": "2026-10-01T10:00:00", "estimate_delivered_at": "2026-10-01T10:05:00"},
    }))
    try:
        _run(S.patch_job(jid, S.JobPatchPayload(job_date="2026-12-20"), _owner()))
        j = _run(S.mongo_db.jobs.find_one({"_id": jid}))
        assert j["job_date"] == "2026-12-20"
        assert "reminder_sent_at" not in j                 # latch cleared -> T-48h recomputes off new date
        assert j["paperwork_alert"]["active"] is False      # scheduling state reset
        # real paperwork COMPLETION is preserved (not erased) for the new-date re-evaluation
        assert j["gates"]["brochure_sent_at"] == "2026-10-01T10:00:00"
        assert j["gates"]["estimate_delivered_at"] == "2026-10-01T10:05:00"
    finally:
        _run(S.mongo_db.jobs.delete_one({"_id": jid}))
        _run(S.mongo_db.job_edit_audit.delete_many({"job_id": jid}))
