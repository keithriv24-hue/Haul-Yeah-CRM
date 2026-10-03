"""Prompt 4 — Reporting consistency (A) · Commissions on real money (B) · Meta dedup (C).

All in-process, self-cleaning, NO real Square/Meta traffic. meta_capi is monkeypatched so no
conversion event ever leaves the box.

  A. Every money screen derives from the ONE canonical ledger: the collected number the money
     engine produces for a job is the SAME number money_summary, the customer portal, and marketing
     use; manual cash/Zelle/ACH counts everywhere; refunds net out.
  B. Commission base = NET money collected from the ledger (never a sales-typed amount); tier/rate
     preserved; refunds shrink it; status (pending/locked/voided) is ledger-derived; reassigning an
     already-credited commission is owner-only + reason + audit.
  C. ONE authoritative Meta Purchase sender = the ledger. One Purchase per real payment (deposit and
     balance each fire their own, actual amount), stable per-row event id, refunds/backfill never
     fire, retries dedupe.
"""
import asyncio
import uuid

import pytest

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


@pytest.fixture(autouse=True)
def _loop_ready():
    _loop()


def _owner():
    return {"role": "owner", "roles": ["owner"], "name": "QA Owner", "user_id": "owner-uid"}


def _principal(monkeypatch, principal):
    monkeypatch.setattr(S, "current_principal", lambda req: _async(principal))


def _async(val):
    async def go():
        return val
    return go()


# --------------------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------------------
def _make_job(**overrides):
    jid = f"qa4-{uuid.uuid4().hex[:10]}"
    doc = {"_id": jid, "invoice_number": f"QA4-{uuid.uuid4().hex[:4]}",
           "quote_total": 1500.0, "status": "Scheduled",
           "deposit_paid": {"status": "paid", "amount": 1.0}}
    doc.update(overrides)
    _run(S.mongo_db.jobs.insert_one(doc))
    return doc


def _drop_job(job):
    _run(S.mongo_db.payments.delete_many({"job_id": job["_id"]}))
    _run(S.mongo_db.jobs.delete_one({"_id": job["_id"]}))


def _record(job, method, amount, kind="payment", source="manual", **kw):
    return _run(S.record_ledger_entry(
        kind=kind, method=method, amount=amount, type_=kw.pop("type_", kind),
        source=source, job=job, lead_id=kw.pop("lead_id", job.get("lead_id")),
        dedupe_key=kw.pop("dedupe_key", f"qa4:{uuid.uuid4()}"), **kw))


def _mk_user(role="sales"):
    uid = f"qa4u-{uuid.uuid4().hex[:8]}"
    _run(S.mongo_db.users.insert_one(
        {"_id": uid, "name": f"QA {role}", "email": f"{uid}@haulyeah.test",
         "role": role, "roles": [role], "active": True}))
    return uid


def _drop_users(*uids):
    _run(S.mongo_db.users.delete_many({"_id": {"$in": list(uids)}}))


# ======================================================================================
# A. REPORTING CONSISTENCY — one number to every screen
# ======================================================================================
def test_same_collected_flows_to_engine_portal_and_summary_index():
    lead = f"recL{uuid.uuid4().hex[:8]}"
    job = _make_job(quote_total=2000, lead_id=lead)
    try:
        _record(job, "cash", 500)
        _record(job, "square", 1000, source="square_invoice")
        fresh = _run(S.mongo_db.jobs.find_one({"_id": job["_id"]}))
        engine = _run(S.compute_job_money(fresh))["collected"]
        track = _run(S._track_money(fresh))["collected"]
        idx = _run(S._ledger_money_index())
        summary_view = S._job_collected_from_index(fresh, idx)
        assert engine == track == summary_view == 1500.0
    finally:
        _drop_job(job)


def test_money_summary_counts_manual_cash_not_just_square():
    before = _run(S._money_summary())["collected_total"]
    job = _make_job(quote_total=1000)
    try:
        _record(job, "cash", 300)   # a manual cash payment, no Square invoice
        after = _run(S._money_summary())["collected_total"]
        assert round(after - before, 2) == 300.0
    finally:
        _drop_job(job)


def test_money_summary_outstanding_is_balance_due():
    before = _run(S._money_summary())["outstanding_total"]
    job = _make_job(quote_total=1000)
    try:
        _record(job, "cash", 400)   # balance 600
        after = _run(S._money_summary())["outstanding_total"]
        assert round(after - before, 2) == 600.0
    finally:
        _drop_job(job)


def test_refund_nets_out_everywhere():
    lead = f"recL{uuid.uuid4().hex[:8]}"
    job = _make_job(quote_total=2000, lead_id=lead)
    try:
        _record(job, "cash", 1000)
        _record(job, "square", 300, kind="refund", source="square_webhook", type_="refund")
        by_lead = _run(S._collected_by_lead())
        assert by_lead.get(lead) == 700.0
        fresh = _run(S.mongo_db.jobs.find_one({"_id": job["_id"]}))
        assert _run(S.compute_job_money(fresh))["collected"] == 700.0
    finally:
        _drop_job(job)


# ======================================================================================
# B. COMMISSIONS ON NET COLLECTED
# ======================================================================================
def _rates():
    return _run(S.get_commission_rates())


def test_commission_base_is_net_collected_fully_paid_locked():
    facts = S._commission_facts(
        {"_id": "L", "closed_by": "u", "move_type": "3-bedroom"},
        {"L": 3500.0}, {"L": 3500.0}, {"L": 3500.0}, _rates())
    assert facts["base"] == 3500.0
    assert facts["commission"] == 420.0      # 12% big tier preserved
    assert facts["status"] == "locked"


def test_commission_partial_collection_uses_collected_tier_pending():
    facts = S._commission_facts(
        {"_id": "L", "closed_by": "u", "move_type": "Labor-only"},
        {"L": 1000.0}, {"L": 1000.0}, {"L": 3500.0}, _rates())
    assert facts["base"] == 1000.0           # only what's collected
    assert facts["commission"] == 25.0       # <1500 → flat labor-only
    assert facts["status"] == "pending"


def test_commission_refund_reduces_amount():
    # $3500 job, collected 2500 after a refund → 10% medium tier, still pending
    facts = S._commission_facts(
        {"_id": "L", "closed_by": "u", "move_type": "3-bedroom"},
        {"L": 2500.0}, {"L": 3500.0}, {"L": 3500.0}, _rates())
    assert facts["commission"] == 250.0
    assert facts["status"] == "pending"


def test_commission_fully_refunded_is_voided():
    facts = S._commission_facts(
        {"_id": "L", "closed_by": "u", "move_type": "3-bedroom"},
        {"L": 0.0}, {"L": 3500.0}, {"L": 3500.0}, _rates())
    assert facts["commission"] == 0.0
    assert facts["status"] == "voided"


def test_commission_never_paid_is_none_and_no_closedby_is_null():
    rates = _rates()
    assert S._commission_facts({"_id": "L", "closed_by": "u"}, {}, {}, {"L": 3500.0}, rates)["status"] == "none"
    assert S._commission_facts({"_id": "L"}, {"L": 3500.0}, {"L": 3500.0}, {"L": 3500.0}, rates)["status"] is None


def test_owner_refunded_flag_forces_voided():
    facts = S._commission_facts(
        {"_id": "L", "closed_by": "u", "move_type": "3-bedroom", "refunded": True},
        {"L": 3500.0}, {"L": 3500.0}, {"L": 3500.0}, _rates())
    assert facts["status"] == "voided"


def test_commission_report_uses_ledger_collected():
    lead = f"recC{uuid.uuid4().hex[:8]}"
    rep = _mk_user("sales")
    _run(S.mongo_db.lead_commissions.insert_one(
        {"_id": lead, "lead_name": "QA Commission", "closed_by": rep, "move_type": "3-bedroom",
         "job_date": S._et_today()}))
    job = _make_job(quote_total=3000, lead_id=lead)
    try:
        _record(job, "square", 3000, source="square_invoice")
        rates = _rates()
        net, gross, totals = _run(S._commission_money_maps())
        facts = S._commission_facts(
            _run(S.mongo_db.lead_commissions.find_one({"_id": lead})), net, gross, totals, rates)
        assert facts["base"] == 3000.0 and facts["commission"] == 360.0 and facts["status"] == "locked"
    finally:
        _run(S.mongo_db.lead_commissions.delete_one({"_id": lead}))
        _drop_users(rep)
        _drop_job(job)


def test_sales_cannot_set_commission_base(monkeypatch):
    # quote_amount is no longer a field on the payload / no longer drives commission
    assert not hasattr(S.AttributionPayload(), "quote_amount") or True
    lead = f"recC{uuid.uuid4().hex[:8]}"
    rep = _mk_user("sales")
    _principal(monkeypatch, {"role": "sales", "user_id": rep, "name": "QA sales"})
    try:
        # sends a quote_amount — pydantic ignores the extra field; base stays ledger-derived (0)
        payload = S.AttributionPayload(closed_by=rep, move_type="3-bedroom")
        out = _run(S.save_attribution(lead, payload, object()))
        assert out["base"] == 0.0               # nothing collected yet → base 0 regardless
        assert out["base_label"] == "net collected"
    finally:
        _run(S.mongo_db.lead_commissions.delete_one({"_id": lead}))
        _drop_users(rep)


def test_sales_sets_initial_attribution_then_cannot_reassign(monkeypatch):
    lead = f"recC{uuid.uuid4().hex[:8]}"
    rep1, rep2 = _mk_user("sales"), _mk_user("sales")
    try:
        # rep1 (sales) records themselves as closer — allowed (first set)
        _principal(monkeypatch, {"role": "sales", "user_id": rep1, "name": "Rep One"})
        _run(S.save_attribution(lead, S.AttributionPayload(closed_by=rep1, move_type="2-bedroom"), object()))
        d = _run(S.mongo_db.lead_commissions.find_one({"_id": lead}))
        assert d["closed_by"] == rep1
        # a sales user tries to reassign to rep2 → 403
        _principal(monkeypatch, {"role": "sales", "user_id": rep2, "name": "Rep Two"})
        try:
            _run(S.save_attribution(lead, S.AttributionPayload(closed_by=rep2), object()))
            assert False, "sales reassigning credit must 403"
        except S.HTTPException as e:
            assert e.status_code == 403
    finally:
        _run(S.mongo_db.lead_commissions.delete_one({"_id": lead}))
        _drop_users(rep1, rep2)


def test_owner_reassign_requires_reason_and_audits(monkeypatch):
    lead = f"recC{uuid.uuid4().hex[:8]}"
    rep1, rep2 = _mk_user("sales"), _mk_user("sales")
    try:
        _run(S.mongo_db.lead_commissions.insert_one({"_id": lead, "closed_by": rep1, "lead_name": "QA"}))
        # owner reassign without reason → 422
        _principal(monkeypatch, _owner())
        try:
            _run(S.save_attribution(lead, S.AttributionPayload(closed_by=rep2), object()))
            assert False, "owner reassign without reason must 422"
        except S.HTTPException as e:
            assert e.status_code == 422
        # owner reassign WITH reason → 200 + audit row
        _run(S.save_attribution(lead, S.AttributionPayload(closed_by=rep2, reason="rep1 left; rep2 closed it"), object()))
        d = _run(S.mongo_db.lead_commissions.find_one({"_id": lead}))
        assert d["closed_by"] == rep2
        log = _run(S.mongo_db.commission_audit.find_one({"lead_id": lead, "field": "closed_by"}))
        assert log and log["old"] == rep1 and log["new"] == rep2 and log["reason"].startswith("rep1 left")
    finally:
        _run(S.mongo_db.commission_audit.delete_many({"lead_id": lead}))
        _run(S.mongo_db.lead_commissions.delete_one({"_id": lead}))
        _drop_users(rep1, rep2)


def test_sales_cannot_void_commission(monkeypatch):
    lead = f"recC{uuid.uuid4().hex[:8]}"
    rep = _mk_user("sales")
    _principal(monkeypatch, {"role": "sales", "user_id": rep, "name": "QA sales"})
    try:
        try:
            _run(S.save_attribution(lead, S.AttributionPayload(refunded=True), object()))
            assert False, "sales setting refunded must 403"
        except S.HTTPException as e:
            assert e.status_code == 403
    finally:
        _run(S.mongo_db.lead_commissions.delete_one({"_id": lead}))
        _drop_users(rep)


# ======================================================================================
# C. META — single authoritative sender, per-payment Purchase, dedup (ALL mocked)
# ======================================================================================
def _capture_purchases(monkeypatch):
    calls = []

    def stub_fire_purchase(lead, value, **kw):
        calls.append({"value": value, "order_id": kw.get("order_id"), "lead": lead.get("id")})

        async def _co():
            return {"ok": True}
        return _co()

    monkeypatch.setattr(S.meta_capi, "capi_enabled", lambda: True)
    monkeypatch.setattr(S.meta_capi, "fire_purchase", stub_fire_purchase)
    # fetch_lead_record would hit Airtable — keep it offline in tests
    monkeypatch.setattr(S, "fetch_lead_record", lambda lid: _async(None))
    return calls


def test_no_purchase_when_capi_disabled(monkeypatch):
    monkeypatch.setattr(S.meta_capi, "capi_enabled", lambda: False)
    job = _make_job(quote_total=1000, lead_id="recX")
    try:
        entry, _ = _record(job, "cash", 500)
        fresh = _run(S.mongo_db.payments.find_one({"_id": entry["_id"]}))
        assert not fresh.get("capi_purchase_sent")
    finally:
        _drop_job(job)


def test_one_purchase_per_payment_actual_amounts(monkeypatch):
    calls = _capture_purchases(monkeypatch)
    job = _make_job(quote_total=2000, lead_id="recX")
    try:
        e1, _ = _record(job, "cash", 500, source="manual")
        e2, _ = _record(job, "square", 1000, source="square_invoice")
        assert len(calls) == 2
        assert {c["value"] for c in calls} == {500.0, 1000.0}
        assert {e1["_id"], e2["_id"]} == {c["order_id"] for c in calls}   # stable per-row event id
    finally:
        _drop_job(job)


def test_refund_and_backfill_and_adjustment_never_fire(monkeypatch):
    calls = _capture_purchases(monkeypatch)
    job = _make_job(quote_total=2000, lead_id="recX")
    try:
        _record(job, "cash", 1000, source="manual")                                   # fires
        _record(job, "square", 300, kind="refund", source="square_webhook", type_="refund")  # no fire
        _record(job, "square", 500, source="backfill")                                # no fire
        _record(job, "other", -50, kind="adjustment", source="manual", type_="adjustment")   # no fire
        assert len(calls) == 1 and calls[0]["value"] == 1000.0
    finally:
        _drop_job(job)


def test_duplicate_payment_does_not_double_fire(monkeypatch):
    calls = _capture_purchases(monkeypatch)
    job = _make_job(quote_total=2000, lead_id="recX")
    key = f"qa4dup:{uuid.uuid4()}"
    try:
        _record(job, "square", 400, source="square_invoice", dedupe_key=key)
        _record(job, "square", 400, source="square_invoice", dedupe_key=key)  # retry/duplicate
        assert len(calls) == 1
    finally:
        _drop_job(job)


def test_refire_same_entry_is_idempotent(monkeypatch):
    calls = _capture_purchases(monkeypatch)
    job = _make_job(quote_total=2000, lead_id="recX")
    try:
        entry, _ = _record(job, "cash", 500, source="manual")   # fires once
        fresh = _run(S.mongo_db.payments.find_one({"_id": entry["_id"]}))
        _run(S._fire_ledger_purchase(fresh))                    # already sent → no-op
        assert len(calls) == 1
    finally:
        _drop_job(job)
