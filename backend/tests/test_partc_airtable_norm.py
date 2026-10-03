"""Prompt 1 Part C — Airtable normalization layer (Problems #2, #24, #25).

The preview Airtable PAT is READ-ONLY (writes 403), so these drive the server's
create/update handlers IN-PROCESS with server.airtable_request + server._schema_fields
monkeypatched (same discipline as test_quality_module). They prove the one canonical
representation (field-ID keys) on writes, permission stripping regardless of whether the
client sent field IDs or names, partial updates, role-filtered save responses, and that
the failed-audit -> Nonconformance hook reads the id-keyed saved record.
"""
import asyncio

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


FAKE_SCHEMA = {
    "projects": [
        {"id": S.PROJECT_REVENUE_FIELD, "name": "Final Revenue", "type": "currency"},
        {"id": S.PROJECT_DEPOSIT_FIELD, "name": "Deposit Collected", "type": "currency"},
        {"id": S.PROJECT_QUOTE_FIELD, "name": "Quote", "type": "currency"},
        {"id": S.PROJECT_STATUS_FIELD, "name": "Status", "type": "singleSelect"},
    ],
    "leads": [
        {"id": S.LEAD_STATUS_F, "name": "Status"},
        {"id": S.LEAD_NAME_F, "name": "Name"},
    ],
    "job_audits": [],
}


def _patch_schema(monkeypatch, fail=False):
    async def fake_schema_fields(table_key):
        if fail:
            raise S.HTTPException(status_code=503, detail="no schema")
        return FAKE_SCHEMA.get(table_key, [])
    monkeypatch.setattr(S, "_schema_fields", fake_schema_fields)


class _Req:  # minimal stand-in for fastapi Request (unused on these code paths)
    pass


# --------------------------------------------------------------------------------------
# normalization helper
# --------------------------------------------------------------------------------------
def test_write_body_envelope_is_canonical():
    body = S._airtable_write_body([{"fields": {"a": 1}}])
    assert body["typecast"] is True
    assert body["returnFieldsByFieldId"] is True
    assert body["records"] == [{"fields": {"a": 1}}]


def test_normalize_converts_names_keeps_ids_passes_unknown(monkeypatch):
    _patch_schema(monkeypatch)
    out = _run(S.normalize_write_fields("projects", {
        "Final Revenue": 5000,              # name -> id
        S.PROJECT_QUOTE_FIELD: 1200,        # already an id
        "Totally Unknown": 7,               # unknown -> pass through
    }))
    assert out[S.PROJECT_REVENUE_FIELD] == 5000
    assert out[S.PROJECT_QUOTE_FIELD] == 1200
    assert out["Totally Unknown"] == 7
    assert "Final Revenue" not in out  # the name key was rewritten to its field id


def test_normalize_passthrough_when_schema_unavailable(monkeypatch):
    _patch_schema(monkeypatch, fail=True)
    src = {S.PROJECT_QUOTE_FIELD: 1, "Final Revenue": 2}
    out = _run(S.normalize_write_fields("projects", src))
    assert out == src  # best-effort: no conversion, nothing dropped


# --------------------------------------------------------------------------------------
# update_record: canonical envelope, partial update, permission strip regardless of
# representation, and role-filtered save response
# --------------------------------------------------------------------------------------
def test_update_strips_name_keyed_money_and_returns_id_keyed_filtered(monkeypatch):
    _patch_schema(monkeypatch)
    captured = {}

    async def fake_air(method, table_id, path="", params=None, json_body=None):
        if table_id == S.TABLES["projects"] and method == "PATCH":
            captured["body"] = json_body
            saved = dict(json_body["records"][0]["fields"])
            # Airtable echoes the whole record (incl. money) keyed by field id
            saved[S.PROJECT_REVENUE_FIELD] = 9999
            return {"records": [{"id": json_body["records"][0]["id"], "fields": saved}]}
        raise AssertionError(f"unexpected airtable call: {method} {table_id}{path}")

    monkeypatch.setattr(S, "airtable_request", fake_air)
    payload = S.RecordPayload(fields={"Final Revenue": 1, S.PROJECT_STATUS_FIELD: "In Progress"})
    rec = _run(S.update_record("projects", "recJOB1", _Req(), payload, role="employee"))

    body = captured["body"]
    # canonical write envelope
    assert body["returnFieldsByFieldId"] is True and body["typecast"] is True
    sent = body["records"][0]["fields"]
    # money field, sent by NAME, is normalized then stripped for employee -> never written
    assert S.PROJECT_REVENUE_FIELD not in sent
    # partial update: only the remaining (allowed) field is sent, nothing else invented
    assert sent == {S.PROJECT_STATUS_FIELD: "In Progress"}
    # save response is role-filtered (employee never sees revenue back)
    assert S.PROJECT_REVENUE_FIELD not in rec["fields"]
    assert rec["fields"].get(S.PROJECT_STATUS_FIELD) == "In Progress"


def test_update_partial_only_sends_submitted_fields(monkeypatch):
    _patch_schema(monkeypatch)
    captured = {}

    async def fake_air(method, table_id, path="", params=None, json_body=None):
        if table_id == S.TABLES["projects"] and method == "PATCH":
            captured["body"] = json_body
            return {"records": [{"id": "recJOB2", "fields": dict(json_body["records"][0]["fields"])}]}
        raise AssertionError(f"unexpected airtable call: {method} {table_id}{path}")

    monkeypatch.setattr(S, "airtable_request", fake_air)
    payload = S.RecordPayload(fields={S.PROJECT_STATUS_FIELD: "Scheduled"})
    _run(S.update_record("projects", "recJOB2", _Req(), payload, role="owner"))
    # exactly one field in the PATCH — untouched fields are never sent (no wipe)
    assert list(captured["body"]["records"][0]["fields"].keys()) == [S.PROJECT_STATUS_FIELD]


# --------------------------------------------------------------------------------------
# failed Quality audit -> Nonconformance (reads the id-keyed saved record)
# --------------------------------------------------------------------------------------
def _run_create_audit(monkeypatch, audit_response_fields):
    _patch_schema(monkeypatch)
    calls = {"nc": [], "patch": []}

    async def fake_air(method, table_id, path="", params=None, json_body=None):
        if table_id == S.TABLES["job_audits"] and method == "POST":
            assert json_body["returnFieldsByFieldId"] is True
            return {"records": [{"id": "recAUD", "fields": dict(audit_response_fields)}]}
        if table_id == S.TABLES["nonconformances"] and method == "POST":
            calls["nc"].append(json_body["records"][0]["fields"])
            return {"records": [{"id": "recNC", "fields": json_body["records"][0]["fields"]}]}
        if table_id == S.TABLES["job_audits"] and method == "PATCH":
            calls["patch"].append(json_body)
            return {"records": [{"id": "recAUD", "fields": {}}]}
        raise AssertionError(f"unexpected airtable call: {method} {table_id}{path}")

    async def fake_principal(request):
        return {"role": "owner", "name": "QA Owner", "user_id": "owner-uid", "roles": ["owner"]}

    monkeypatch.setattr(S, "airtable_request", fake_air)
    monkeypatch.setattr(S, "current_principal", fake_principal)
    payload = S.RecordPayload(fields={
        S.JA_RESULT_F: "Fail", S.JA_LINKED_JOB_F: ["recJOB"], S.JA_FINDINGS_F: "crew late, box crushed",
    })
    rec = _run(S.create_record("job_audits", _Req(), payload, role="owner"))
    return rec, calls


def test_failed_audit_opens_nonconformance_from_id_keyed_record(monkeypatch):
    # saved record comes back id-keyed (the canonical envelope guarantees this)
    _, calls = _run_create_audit(monkeypatch, {
        S.JA_RESULT_F: "Fail", S.JA_LINKED_JOB_F: ["recJOB"], S.JA_FINDINGS_F: "crew late, box crushed",
    })
    assert len(calls["nc"]) == 1, "a Fail audit must open exactly one nonconformance"
    nc = calls["nc"][0]
    assert nc[S.NC_TYPE_F] == "Audit finding"
    assert nc[S.NC_SEVERITY_F] == "Major"  # Fail -> Major
    assert calls["patch"], "the audit should be linked back to the new NC"


def test_name_keyed_audit_response_would_miss_nc(monkeypatch):
    # Demonstrates WHY the id-keyed save response matters: if Airtable had returned the
    # record keyed by field NAME (the pre-fix behavior), the id-keyed result lookup finds
    # nothing and NO nonconformance is created — the exact #24/#25 data-loss bug.
    _, calls = _run_create_audit(monkeypatch, {"Result": "Fail", "Findings": "x"})
    assert calls["nc"] == []
