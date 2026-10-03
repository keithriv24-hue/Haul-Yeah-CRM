"""Prompt 3 — ONE canonical payment ledger + ONE money engine.

Everything runs IN-PROCESS. NO real Square traffic, NO real payments/refunds, NO live
Airtable. Square webhooks are exercised by calling the server's own event handlers with
mocked event payloads. These prove the owner-confirmed Prompt 3 acceptance criteria:

  - collected / balance_due / paid_in_full are COMPUTED from the ledger (never inferred
    from an invoice title or purpose).
  - job total source: job.quote_total for an active job, Final Revenue for a completed one.
  - manual cash / Zelle / ACH entries land in the SAME ledger and combine into collected.
  - refunds are negative entries (original row preserved); guarded against $0/negative and
    against exceeding the money actually collected.
  - a duplicate Square invoice payment / refund webhook never double-counts money.
  - the ledger is tied to job_id and resolves by project_record_id when one is present.
  - finance (money) controls are owner-only unless the owner grants finance_access; everyone
    else is 403.
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
    """Make our loop the default BEFORE any test builds a motor coroutine, so Mongo
    operations and run_until_complete share one event loop (motor binds lazily)."""
    _loop()


def _async(val):
    async def go():
        return val
    return go()


def _owner():
    return {"role": "owner", "roles": ["owner"], "name": "QA Owner", "user_id": "owner-uid"}


# --------------------------------------------------------------------------------------
# job + ledger fixtures (real Mongo, always cleaned up)
# --------------------------------------------------------------------------------------
def _make_job(**overrides):
    """Insert a throwaway job container and return it. Caller MUST _drop_job() in finally."""
    jid = f"qa3-{uuid.uuid4().hex[:10]}"
    doc = {"_id": jid, "invoice_number": f"QA3-{uuid.uuid4().hex[:4]}",
           "quote_total": 1500.0, "status": "Scheduled"}
    doc.update(overrides)
    _run(S.mongo_db.jobs.insert_one(doc))
    return doc


def _drop_job(job):
    pid = job.get("project_record_id")
    ors = [{"job_id": job["_id"]}]
    if pid:
        ors.append({"project_record_id": pid})
    _run(S.mongo_db.payments.delete_many({"$or": ors}))
    _run(S.mongo_db.jobs.delete_one({"_id": job["_id"]}))


def _money(job):
    fresh = _run(S.mongo_db.jobs.find_one({"_id": job["_id"]})) or job
    return _run(S.compute_job_money(fresh))


# ======================================================================================
# A. MONEY MATH — pure, computed from the ledger (no inference)
# ======================================================================================
def _entry(kind, amount, status="completed"):
    return {"kind": kind, "amount": amount, "status": status}


def test_signed_amount_payment_refund_adjustment():
    assert S._signed_amount(_entry("payment", 500)) == 500
    assert S._signed_amount(_entry("refund", 200)) == -200
    assert S._signed_amount({"kind": "adjustment", "amount": -75}) == -75
    assert S._signed_amount({"kind": "adjustment", "amount": 75}) == 75


def test_job_total_active_uses_quote_total():
    assert S._job_total_for_money({"quote_total": 1500}) == 1500.0


def test_job_total_completed_uses_final_revenue():
    # Final Revenue, where recorded, is the authoritative total for a completed job.
    assert S._job_total_for_money({"quote_total": 1500, "final_revenue": 1800}) == 1800.0


def test_single_partial_payment_balance_and_status():
    m = S.compute_money_from_entries([_entry("payment", 500)], 1500)
    assert m["collected"] == 500
    assert m["balance_due"] == 1000
    assert m["paid_in_full"] is False


def test_multiple_partial_payments_combine():
    m = S.compute_money_from_entries(
        [_entry("payment", 300), _entry("payment", 400), _entry("payment", 500)], 1500)
    assert m["collected"] == 1200
    assert m["balance_due"] == 300
    assert m["paid_in_full"] is False


def test_two_methods_combine_into_one_collected_total():
    # a cash entry and an ACH entry are the same ledger — they add up.
    m = S.compute_money_from_entries([_entry("payment", 600), _entry("payment", 900)], 1500)
    assert m["collected"] == 1500
    assert m["paid_in_full"] is True


def test_refund_reduces_collected_and_raises_balance():
    m = S.compute_money_from_entries(
        [_entry("payment", 1000), _entry("refund", 250)], 1500)
    assert m["collected"] == 750
    assert m["balance_due"] == 750


def test_paid_in_full_only_at_or_above_total():
    assert S.compute_money_from_entries([_entry("payment", 1499)], 1500)["paid_in_full"] is False
    assert S.compute_money_from_entries([_entry("payment", 1500)], 1500)["paid_in_full"] is True
    over = S.compute_money_from_entries([_entry("payment", 1600)], 1500)
    assert over["paid_in_full"] is True and over["overpaid"] is True


def test_refunding_paid_in_full_job_flips_back_to_not_paid():
    m = S.compute_money_from_entries(
        [_entry("payment", 1500), _entry("refund", 300)], 1500)
    assert m["collected"] == 1200
    assert m["paid_in_full"] is False
    assert m["balance_due"] == 300


def test_only_completed_entries_count():
    m = S.compute_money_from_entries(
        [_entry("payment", 1500, status="pending"), _entry("payment", 500)], 1500)
    assert m["collected"] == 500


def test_zero_total_job_is_never_paid_in_full():
    assert S.compute_money_from_entries([], 0)["paid_in_full"] is False


# ======================================================================================
# B. MANUAL LEDGER ENTRIES — cash / Zelle / ACH land in the SAME ledger
# ======================================================================================
def _record(job, method, amount, kind="payment", **kw):
    return _run(S.record_ledger_entry(
        kind=kind, method=method, amount=amount, type_=kw.pop("type_", kind),
        source="manual", job=job, dedupe_key=f"manual:{uuid.uuid4()}", **kw))


def test_cash_manual_entry_updates_collected():
    job = _make_job(quote_total=1000)
    try:
        _record(job, "cash", 400)
        assert _money(job)["collected"] == 400
    finally:
        _drop_job(job)


def test_zelle_manual_entry_updates_collected():
    job = _make_job(quote_total=1000)
    try:
        _record(job, "zelle", 250)
        assert _money(job)["collected"] == 250
    finally:
        _drop_job(job)


def test_ach_manual_entry_updates_collected():
    job = _make_job(quote_total=1000)
    try:
        _record(job, "ach", 1000)
        m = _money(job)
        assert m["collected"] == 1000 and m["paid_in_full"] is True
    finally:
        _drop_job(job)


def test_cash_plus_zelle_plus_ach_combine():
    job = _make_job(quote_total=1500)
    try:
        _record(job, "cash", 500)
        _record(job, "zelle", 500)
        _record(job, "ach", 500)
        m = _money(job)
        assert m["collected"] == 1500 and m["paid_in_full"] is True and m["entry_count"] == 3
    finally:
        _drop_job(job)


def test_duplicate_dedupe_key_never_double_counts():
    job = _make_job(quote_total=1000)
    try:
        key = f"manual:{uuid.uuid4()}"
        e1, new1 = _run(S.record_ledger_entry(
            kind="payment", method="cash", amount=400, type_="payment",
            source="manual", job=job, dedupe_key=key))
        e2, new2 = _run(S.record_ledger_entry(
            kind="payment", method="cash", amount=400, type_="payment",
            source="manual", job=job, dedupe_key=key))
        assert new1 is True and new2 is False
        assert e1["_id"] == e2["_id"]
        assert _money(job)["collected"] == 400
    finally:
        _drop_job(job)


def test_refund_entry_reduces_collected_in_db():
    job = _make_job(quote_total=1500)
    try:
        _record(job, "cash", 1000)
        _record(job, "square", 300, kind="refund", type_="refund")
        m = _money(job)
        assert m["collected"] == 700 and m["balance_due"] == 800
    finally:
        _drop_job(job)


# ======================================================================================
# C. LEDGER KEYING — job_id and project_record_id
# ======================================================================================
def test_entry_is_tied_to_job_id():
    job = _make_job(quote_total=800)
    try:
        entry, _ = _record(job, "cash", 100)
        assert entry["job_id"] == job["_id"]
    finally:
        _drop_job(job)


def test_entry_carries_project_record_id_when_present():
    pid = f"recQA{uuid.uuid4().hex[:8]}"
    job = _make_job(quote_total=800, project_record_id=pid)
    try:
        entry, _ = _record(job, "cash", 100)
        assert entry["project_record_id"] == pid
    finally:
        _drop_job(job)


def test_entries_resolve_by_project_record_id_even_without_job_id():
    """A row written with only the canonical project link still counts toward that job."""
    pid = f"recQA{uuid.uuid4().hex[:8]}"
    job = _make_job(quote_total=1000, project_record_id=pid)
    try:
        # simulate a Square payment captured under the project link but not the job _id
        _run(S.mongo_db.payments.insert_one({
            "_id": str(uuid.uuid4()), "job_id": None, "project_record_id": pid,
            "kind": "payment", "method": "square", "amount": 600.0, "type": "deposit",
            "status": "completed", "source": "square_invoice",
            "dedupe_key": f"qa:{uuid.uuid4()}", "occurred_at": S.now_iso()}))
        assert _money(job)["collected"] == 600
    finally:
        _drop_job(job)


# ======================================================================================
# D. SQUARE WEBHOOK IDEMPOTENCY — mocked events, NO real Square traffic
# ======================================================================================
def test_square_invoice_payment_is_idempotent():
    """Replaying the same PAID invoice never books the dollars twice."""
    job = _make_job(quote_total=1500)
    inv = {"invoice_id": f"inv_{uuid.uuid4().hex[:8]}", "amount": 375.0,
           "lead_id": None, "purpose": "deposit", "paid_at": S.now_iso()}
    # link the invoice to this job so _resolve_job_for_payment finds it by deposit invoice
    _run(S.mongo_db.jobs.update_one(
        {"_id": job["_id"]}, {"$set": {"deposit_invoice_id": inv["invoice_id"]}}))
    try:
        _run(S._sync_square_invoice_payment_to_ledger(inv))
        _run(S._sync_square_invoice_payment_to_ledger(inv))  # retry / duplicate webhook
        m = _money(job)
        assert m["collected"] == 375.0 and m["entry_count"] == 1
    finally:
        _drop_job(job)


def test_square_refund_webhook_is_idempotent(monkeypatch):
    job = _make_job(quote_total=1500)
    try:
        # a known Square payment of $1000 captured on the job
        _run(S.record_ledger_entry(
            kind="payment", method="square", amount=1000, type_="deposit", source="square_webhook",
            job=job, external_id="pay_qa_1", dedupe_key="sqpay:pay_qa_1"))
        refund = {"id": f"rf_{uuid.uuid4().hex[:8]}", "status": "COMPLETED",
                  "payment_id": "pay_qa_1", "amount_money": {"amount": 25000, "currency": "USD"}}
        event = {"type": "refund.updated", "created_at": S.now_iso()}
        _run(S._handle_refund_event(refund, event))
        _run(S._handle_refund_event(refund, event))  # duplicate webhook
        m = _money(job)
        assert m["collected"] == 750.0        # 1000 - 250, counted once
        assert m["balance_due"] == 750.0
    finally:
        _drop_job(job)


def test_square_refund_pending_is_ignored():
    job = _make_job(quote_total=1500)
    try:
        _run(S.record_ledger_entry(
            kind="payment", method="square", amount=1000, type_="deposit", source="square_webhook",
            job=job, external_id="pay_qa_2", dedupe_key="sqpay:pay_qa_2"))
        refund = {"id": f"rf_{uuid.uuid4().hex[:8]}", "status": "PENDING",
                  "payment_id": "pay_qa_2", "amount_money": {"amount": 25000}}
        _run(S._handle_refund_event(refund, {"created_at": S.now_iso()}))
        assert _money(job)["collected"] == 1000.0   # pending refund changes nothing
    finally:
        _drop_job(job)


def test_invoice_webhook_books_money_once(monkeypatch):
    """Full invoice.payment webhook path: a PAID invoice books one ledger entry; a replay is a no-op.
    Airtable / job-creation / alert side-effects are stubbed so only the money ledger is exercised."""
    monkeypatch.setattr(S, "ensure_job_for_deposit", lambda *a, **k: _async(None))
    monkeypatch.setattr(S, "_alert_payment_landed", lambda *a, **k: _async(None))
    monkeypatch.setattr(S, "_maybe_fire_capi_purchase", lambda *a, **k: _async(None))

    job = _make_job(quote_total=1500)
    inv_id = f"inv_{uuid.uuid4().hex[:8]}"
    _run(S.mongo_db.jobs.update_one(
        {"_id": job["_id"]}, {"$set": {"deposit_invoice_id": inv_id}}))
    _run(S.mongo_db.square_invoices.insert_one({
        "invoice_id": inv_id, "invoice_number": "QA-INV", "amount": 375.0, "lead_id": None,
        "purpose": "deposit", "status": "PAYMENT_PENDING", "created_at": S.now_iso(),
        "checked_at": 0}))
    invoice_payload = {"id": inv_id, "status": "PAID", "invoice_number": "QA-INV"}
    event = {"type": "invoice.payment_made", "event_id": f"evt_{uuid.uuid4().hex[:8]}",
             "created_at": S.now_iso()}
    try:
        _run(S._handle_invoice_event(invoice_payload, event))
        _run(S._handle_invoice_event(invoice_payload, event))  # duplicate delivery
        m = _money(job)
        assert m["collected"] == 375.0 and m["entry_count"] == 1
    finally:
        _run(S.mongo_db.square_invoices.delete_one({"invoice_id": inv_id}))
        _drop_job(job)


def test_handle_square_event_routes_refund(monkeypatch):
    seen = {}

    async def _fake_refund(refund, event):
        seen["refund"] = refund.get("id")

    monkeypatch.setattr(S, "_handle_refund_event", _fake_refund)
    rid = f"rf_{uuid.uuid4().hex[:6]}"
    _run(S.handle_square_event(
        {"type": "refund.updated", "data": {"object": {"refund": {"id": rid, "status": "COMPLETED"}}}}))
    assert seen.get("refund") == rid


# ======================================================================================
# E. MANUAL ENDPOINT GUARDS (called in-process with a resolved principal)
# ======================================================================================
def test_manual_payment_rejects_zero_and_negative():
    job = _make_job()
    try:
        for bad in (0, -50):
            try:
                _run(S.record_manual_payment(
                    job["_id"], S.ManualPaymentPayload(method="cash", amount=bad), _owner()))
                assert False, "non-positive payment must 422"
            except S.HTTPException as e:
                assert e.status_code == 422
    finally:
        _drop_job(job)


def test_manual_payment_rejects_bad_method():
    job = _make_job()
    try:
        _run(S.record_manual_payment(
            job["_id"], S.ManualPaymentPayload(method="bitcoin", amount=100), _owner()))
        assert False, "unknown method must 422"
    except S.HTTPException as e:
        assert e.status_code == 422
    finally:
        _drop_job(job)


def test_manual_payment_happy_path_returns_money_block():
    job = _make_job(quote_total=1000)
    try:
        out = _run(S.record_manual_payment(
            job["_id"], S.ManualPaymentPayload(method="zelle", amount=400, note="conf #123"), _owner()))
        assert out["money"]["collected"] == 400
        assert out["money"]["balance_due"] == 600
        assert out["entry"]["method"] == "zelle"
    finally:
        _drop_job(job)


def test_manual_payment_unknown_job_404():
    try:
        _run(S.record_manual_payment(
            "no-such-job", S.ManualPaymentPayload(method="cash", amount=100), _owner()))
        assert False, "unknown job must 404"
    except S.HTTPException as e:
        assert e.status_code == 404


def test_refund_rejects_zero_negative_and_short_reason():
    job = _make_job()
    try:
        _record(job, "cash", 500)
        try:
            _run(S.record_manual_refund(
                job["_id"], S.ManualRefundPayload(amount=0, reason="customer cancelled"), _owner()))
            assert False
        except S.HTTPException as e:
            assert e.status_code == 422
        try:
            _run(S.record_manual_refund(
                job["_id"], S.ManualRefundPayload(amount=50, reason="x"), _owner()))
            assert False, "reason under 3 chars must 422"
        except S.HTTPException as e:
            assert e.status_code == 422
    finally:
        _drop_job(job)


def test_refund_cannot_exceed_collected():
    job = _make_job(quote_total=1500)
    try:
        _record(job, "cash", 500)
        try:
            _run(S.record_manual_refund(
                job["_id"], S.ManualRefundPayload(amount=600, reason="too much"), _owner()))
            assert False, "refund over collected must 422"
        except S.HTTPException as e:
            assert e.status_code == 422
    finally:
        _drop_job(job)


def test_refund_against_no_collected_money_is_rejected():
    job = _make_job(quote_total=1500)
    try:
        _run(S.record_manual_refund(
            job["_id"], S.ManualRefundPayload(amount=50, reason="nothing collected"), _owner()))
        assert False, "refund with $0 collected must 422"
    except S.HTTPException as e:
        assert e.status_code == 422
    finally:
        _drop_job(job)


def test_refund_happy_path_reduces_collected():
    job = _make_job(quote_total=1500)
    try:
        _record(job, "cash", 1000)
        out = _run(S.record_manual_refund(
            job["_id"], S.ManualRefundPayload(amount=250, reason="cancelled add-on"), _owner()))
        assert out["money"]["collected"] == 750
        assert out["money"]["balance_due"] == 750
        assert out["entry"]["kind"] == "refund"
    finally:
        _drop_job(job)


# ======================================================================================
# F. FINANCE (money) PERMISSION — owner + granted users only
# ======================================================================================
def _as_principal(monkeypatch, principal):
    monkeypatch.setattr(S, "current_principal", lambda req: _async(principal))


def test_require_finance_allows_owner(monkeypatch):
    _as_principal(monkeypatch, _owner())
    p = _run(S.require_finance(object()))
    assert p["role"] == "owner"


def test_require_finance_allows_granted_user(monkeypatch):
    uid = f"qa-fin-{uuid.uuid4().hex[:6]}"
    _run(S.mongo_db.users.insert_one(
        {"_id": uid, "name": "QA Finance", "email": f"{uid}@haulyeah.test",
         "role": "sales", "roles": ["sales"], "finance_access": True, "active": True}))
    try:
        _as_principal(monkeypatch, {"role": "sales", "user_id": uid, "name": "QA Finance"})
        p = _run(S.require_finance(object()))
        assert p["user_id"] == uid
    finally:
        _run(S.mongo_db.users.delete_one({"_id": uid}))


def test_require_finance_blocks_user_without_access(monkeypatch):
    uid = f"qa-nofin-{uuid.uuid4().hex[:6]}"
    _run(S.mongo_db.users.insert_one(
        {"_id": uid, "name": "QA Crew", "email": f"{uid}@haulyeah.test",
         "role": "crew", "roles": ["crew"], "active": True}))
    try:
        _as_principal(monkeypatch, {"role": "crew", "user_id": uid, "name": "QA Crew"})
        try:
            _run(S.require_finance(object()))
            assert False, "crew without finance_access must 403"
        except S.HTTPException as e:
            assert e.status_code == 403
    finally:
        _run(S.mongo_db.users.delete_one({"_id": uid}))


def test_require_finance_blocks_principal_with_no_user(monkeypatch):
    _as_principal(monkeypatch, {"role": "sales", "user_id": None})
    try:
        _run(S.require_finance(object()))
        assert False, "no user_id must 403"
    except S.HTTPException as e:
        assert e.status_code == 403


def test_grant_and_revoke_finance_access_roundtrip():
    uid = f"qa-grant-{uuid.uuid4().hex[:6]}"
    _run(S.mongo_db.users.insert_one(
        {"_id": uid, "name": "QA Grantee", "email": f"{uid}@haulyeah.test",
         "role": "sales", "roles": ["sales"], "active": True}))
    try:
        _run(S.grant_finance_access(uid, _owner()))
        assert uid in _run(S.list_finance_access(_owner()))["access"]
        u = _run(S.mongo_db.users.find_one({"_id": uid}))
        assert u.get("finance_access") is True

        _run(S.revoke_finance_access(uid, _owner()))
        assert uid not in _run(S.list_finance_access(_owner()))["access"]
        u = _run(S.mongo_db.users.find_one({"_id": uid}))
        assert not u.get("finance_access")
    finally:
        _run(S.mongo_db.users.delete_one({"_id": uid}))


def test_grant_finance_access_unknown_user_404():
    try:
        _run(S.grant_finance_access("no-such-user", _owner()))
        assert False, "unknown user must 404"
    except S.HTTPException as e:
        assert e.status_code == 404
