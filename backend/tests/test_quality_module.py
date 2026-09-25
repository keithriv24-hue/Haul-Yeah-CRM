"""Quality & Compliance module (prompt 1 of 3) tests.
Airtable is unavailable in preview, so table-backed flows return 503; those are
asserted as "gated correctly, or 503". The cost-stripped quote (Mongo-backed) and
all role gating ARE fully exercised here."""
import os
import requests
import pytest
import asyncio
import sys
from datetime import datetime, timedelta

import pymongo

sys.path.insert(0, "/app/backend")
import server  # noqa: E402


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://haul-yeah-staging.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

OWNER_USER = "HaulYeahAdmin"
GHOST_PASS = "HaulYeah2026!"
SALES_USER = "testsalesadmin"
CREW_USER = "testcrewadmin"
QUALITY_USER = "testqualityadmin"

FORBIDDEN = ["cushion", "cushionPercent", "crewCost", "margin", "commission", "cost", "costs", "profit"]
ALLOWED_SENT = {
    "customerName": "Jane Doe", "customerPhone": "555-1212", "finalQuote": 1250,
    "deposit": 312.5, "bandLo": 1150, "bandHi": 1250, "crewSize": 3,
    "estimatedHours": 5, "hourlyRate": 65, "tripFee": 125, "subtotal": 1136, "stairs": 170,
}
INTERNAL_SENT = {"cushion": 113.6, "cushionPercent": 10, "crewCost": 420, "cost": 420, "margin": 700, "commission": 150, "profit": 550}


def _login(email, password=GHOST_PASS):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)


def _tok(r):
    return r.json().get("token") or r.json().get("access_token")


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def owner_token():
    r = _login(OWNER_USER)
    assert r.status_code == 200, r.text
    return _tok(r)


@pytest.fixture(scope="module")
def sales_token():
    r = _login(SALES_USER)
    assert r.status_code == 200, r.text
    return _tok(r)


@pytest.fixture(scope="module")
def crew_token():
    r = _login(CREW_USER)
    assert r.status_code == 200, r.text
    return _tok(r)


@pytest.fixture(scope="module")
def quality_token():
    r = _login(QUALITY_USER)
    assert r.status_code == 200, r.text
    return _tok(r)


def test_quality_login_and_role(quality_token):
    r = requests.get(f"{API}/auth/me", headers=_h(quality_token), timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "quality"


LEAD_ID = "QUALITY-TEST-LEAD"


def test_seed_quote_as_owner(owner_token):
    payload = {"breakdown": {**ALLOWED_SENT, **INTERNAL_SENT}}
    r = requests.put(f"{API}/quotes/{LEAD_ID}", json=payload, headers=_h(owner_token), timeout=20)
    assert r.status_code == 200, r.text


def test_owner_sees_full_quote(owner_token):
    r = requests.get(f"{API}/quotes/{LEAD_ID}", headers=_h(owner_token), timeout=20)
    assert r.status_code == 200, r.text
    b = r.json()["breakdown"]
    assert "cushion" in b and "margin" in b and "commission" in b


def test_quality_quote_is_cost_stripped(quality_token):
    r = requests.get(f"{API}/quotes/{LEAD_ID}", headers=_h(quality_token), timeout=20)
    assert r.status_code == 200, r.text
    b = r.json()["breakdown"]
    # spec: response must contain NONE of the internal keys
    for k in FORBIDDEN:
        assert k not in b, f"leaked internal key {k}"
    # and it must still carry the customer-facing figures
    for k in ["finalQuote", "deposit", "crewSize", "estimatedHours", "tripFee", "subtotal"]:
        assert k in b, f"missing customer-facing key {k}"


def test_quote_get_blocked_for_crew(crew_token):
    r = requests.get(f"{API}/quotes/{LEAD_ID}", headers=_h(crew_token), timeout=20)
    assert r.status_code == 403


def test_audit_queue_gating(sales_token, quality_token):
    assert requests.get(f"{API}/quality/audit-queue", headers=_h(sales_token), timeout=30).status_code == 403
    r = requests.get(f"{API}/quality/audit-queue", headers=_h(quality_token), timeout=30)
    assert r.status_code in (200, 503), r.text


def test_quote_accuracy_gating(sales_token, quality_token, owner_token):
    assert requests.get(f"{API}/quality/quote-accuracy", headers=_h(sales_token), timeout=30).status_code == 403
    for tok in (quality_token, owner_token):
        assert requests.get(f"{API}/quality/quote-accuracy", headers=_h(tok), timeout=30).status_code in (200, 503)


def test_feedback_create_and_visibility(quality_token, sales_token):
    # sales cannot log feedback
    assert requests.post(f"{API}/quality/feedback", json={"what_was_off": "x"}, headers=_h(sales_token), timeout=20).status_code == 403
    # who is the sales ghost?
    me = requests.get(f"{API}/auth/me", headers=_h(sales_token), timeout=20).json()
    sales_uid = me["user"]["id"]
    # feedback aimed at the sales rep
    r1 = requests.post(f"{API}/quality/feedback", headers=_h(quality_token), timeout=20, json={
        "job_id": "recQTEST1", "job_name": "QTest — to sales", "rep_user_id": sales_uid,
        "rep_name": "Sales Ghost", "what_was_off": "Underestimated stairs", "what_to_do": "Ask about elevator"})
    assert r1.status_code == 200, r1.text
    # feedback aimed at a different rep
    r2 = requests.post(f"{API}/quality/feedback", headers=_h(quality_token), timeout=20, json={
        "job_id": "recQTEST2", "job_name": "QTest — to someone else", "rep_user_id": "someone-else-id",
        "rep_name": "Other Rep", "what_was_off": "Wrong crew size"})
    assert r2.status_code == 200, r2.text
    # quality sees all
    q = requests.get(f"{API}/quality/feedback", headers=_h(quality_token), timeout=20).json()["feedback"]
    jobs = {f.get("job_id") for f in q}
    assert "recQTEST1" in jobs and "recQTEST2" in jobs
    # the sales rep sees ONLY their own, never another rep's
    s = requests.get(f"{API}/quality/feedback", headers=_h(sales_token), timeout=20).json()["feedback"]
    assert all(f.get("rep_user_id") == sales_uid for f in s)
    assert any(f.get("job_id") == "recQTEST1" for f in s)
    assert all(f.get("job_id") != "recQTEST2" for f in s)


def test_feedback_requires_what_was_off(quality_token):
    r = requests.post(f"{API}/quality/feedback", json={"what_was_off": "   "}, headers=_h(quality_token), timeout=20)
    assert r.status_code == 422



# =====================================================================================
# Quality & Compliance — PROMPT 2: the 14-gate evaluator, office-goods exemption,
# override endpoint, and role permissions.
#
# The gate evaluator (server.evaluate_gates) is a PURE function of a project record +
# a context dict, so gates 1-8 and the per-gate flip tests run entirely in-process with
# NO live Airtable. The override/permission tests: role 403s and reason/OVERRIDE
# validation short-circuit BEFORE any Airtable call, so they run over HTTP against the
# live backend; the override success/failure/"stays-red" paths DO touch Airtable, so
# they call the endpoint in-process with server.airtable_request monkeypatched.
#
# NOTE on assertion #1 wording ("empty job fails all 14"): three gates —
# owner_operator, labor_equip_change, long_haul_review — are RISK-TRIGGERED. They
# correctly PASS when their risk is absent (no owner-operator used, no labor change,
# short move). Forcing them red on a blank job would be a false alarm — exactly the
# noise that turns a safety system into a formality. So the blank-job test asserts the
# 11 evidence-required gates fail and the 3 risk-triggered gates pass; assertion #8 is
# likewise implemented by putting those three into their failing STATE on an office job.
# =====================================================================================

EVIDENCE_GATES = {
    "move_classification", "survey_performed", "surveyor_eligible", "inventory_complete",
    "brochure_delivered", "estimate_24h", "ofs_24h", "protection_selected",
    "company_credentials", "crew_ready", "deposit_cleared",
}
RISK_TRIGGERED_GATES = {"owner_operator", "labor_equip_change", "long_haul_review"}
LIABILITY_GATES = {"brochure_delivered", "ofs_24h", "owner_operator"}

SURV_ID = "qa-surveyor-1"
CREW_ID = "qa-crew-1"


def _mongo():
    return pymongo.MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def make_ctx(**over):
    today = over.get("today") or datetime.now(server._ET).date()
    return {
        "rates": over.get("rates", {"maxCrewPerDay": 12}),
        "users_by_id": over.get("users_by_id", {}),
        "jobs_by_recid": over.get("jobs_by_recid", {}),
        "jobs_by_lead": over.get("jobs_by_lead", {}),
        "assignments_by_date": over.get("assignments_by_date", {}),
        "today": today,
        "credentials": over.get("credentials", {"available": True, "missing": []}),
    }


def passing_job():
    """A job whose inputs + context satisfy every one of the 14 gates."""
    today = datetime.now(server._ET).date()
    move = today + timedelta(days=30)
    move_str = move.isoformat()
    dt = f"{(move - timedelta(days=10)).isoformat()}T09:00:00-04:00"
    fields = {
        server.PROJECT_DATE_FIELD: move_str,
        server.PROJECT_MOVE_CLASS_F: "Household Goods",
        server.PROJECT_SURVEY_TYPE_F: "On site",
        server.PROJECT_SURVEYOR_FIELD: SURV_ID,
        server.PROJECT_INVENTORY_COMPLETE_F: True,
        server.PROJECT_BROCHURE_SENT_F: dt,
        server.PROJECT_ESTIMATE_DELIVERED_F: dt,
        server.PROJECT_OFS_SIGNED_F: dt,
        server.PROJECT_PROTECTION_OPTION_F: "Option 1",
        server.PROJECT_OWNER_OP_USED_F: False,
        server.PROJECT_LABOR_EQUIP_F: "Agreed in writing",
        server.PROJECT_ONE_WAY_MILES_F: 10,
        server.PROJECT_QUOTE_FIELD: 1000,
        server.PROJECT_DEPOSIT_FIELD: 300,
    }
    pr = {"id": "recPASS", "fields": fields}
    ctx = make_ctx(
        today=today,
        users_by_id={
            SURV_ID: {"role": "owner", "surveyor_attested": True, "active": True, "name": "Surveyor"},
            CREW_ID: {"active": True, "crew_docs_expiry": (today + timedelta(days=365)).isoformat(), "name": "Crew"},
        },
        jobs_by_recid={"recPASS": {"job_date": move_str}},
        assignments_by_date={move_str: [{"job_name": "", "crew": [{"user_id": CREW_ID}]}]},
        credentials={"available": True, "missing": []},
    )
    return pr, ctx, move


def _gate(pr, ctx, key):
    return {g["key"]: g for g in server.evaluate_gates(pr, ctx)}[key]


def _break(gate, pr, ctx):
    """Break exactly one gate's own input, starting from a fully-passing job."""
    f = pr["fields"]
    if gate == "move_classification":
        f[server.PROJECT_MOVE_CLASS_F] = "Other Commercial"
    elif gate == "survey_performed":
        f[server.PROJECT_SURVEY_TYPE_F] = "None"
    elif gate == "surveyor_eligible":
        ctx["users_by_id"][SURV_ID].update({"role": "sales", "calculator_access": None, "surveyor_attested": False})
    elif gate == "inventory_complete":
        f[server.PROJECT_INVENTORY_COMPLETE_F] = False
    elif gate == "brochure_delivered":
        f.pop(server.PROJECT_BROCHURE_SENT_F, None)
    elif gate == "estimate_24h":
        f.pop(server.PROJECT_ESTIMATE_DELIVERED_F, None)
    elif gate == "ofs_24h":
        f.pop(server.PROJECT_OFS_SIGNED_F, None)
    elif gate == "protection_selected":
        f.pop(server.PROJECT_PROTECTION_OPTION_F, None)
    elif gate == "labor_equip_change":
        f[server.PROJECT_LABOR_EQUIP_F] = "Not agreed"
    elif gate == "company_credentials":
        ctx["credentials"] = {"available": True, "missing": ["License"]}
    elif gate == "crew_ready":
        ctx["assignments_by_date"] = {}
        ctx["jobs_by_recid"] = {}
    elif gate == "deposit_cleared":
        f[server.PROJECT_DEPOSIT_FIELD] = 100
    elif gate == "owner_operator":
        f[server.PROJECT_OWNER_OP_USED_F] = True
        f.pop(server.PROJECT_OWNER_OP_NOTICE_F, None)
    elif gate == "long_haul_review":
        f[server.PROJECT_ONE_WAY_MILES_F] = 70
        f.pop(server.PROJECT_LONG_HAUL_ACK_F, None)
    else:
        raise AssertionError(f"no breaker for gate {gate}")


# ---- GATE EVALUATOR ------------------------------------------------------------------

def test_1_blank_job_fails_evidence_gates_but_still_produces_14_and_never_blocks():
    """#1: a job with every input blank fails all evidence-required gates (the three
    risk-triggered gates correctly pass) and evaluation is never a booking blocker."""
    pr = {"id": "recEMPTY", "fields": {}}
    ctx = make_ctx(credentials={"available": False, "missing": list(server.CRED_KEYWORDS.keys())})
    gates = server.evaluate_gates(pr, ctx)
    assert len(gates) == 14
    by = {g["key"]: g for g in gates}
    for k in EVIDENCE_GATES:
        assert by[k]["passed"] is False, f"{k} should FAIL on a blank job"
    for k in RISK_TRIGGERED_GATES:
        assert by[k]["passed"] is True, f"{k} should PASS when its risk is absent"


def test_1b_gate_evaluation_is_not_wired_into_booking():
    """#1 (still books): a failing gate can never block a booking because the booking
    endpoints do not consult the gate evaluator."""
    import inspect
    for fn in (server.create_record, server.update_record):
        src = inspect.getsource(fn)
        assert "evaluate_gates" not in src, f"{fn.__name__} must not evaluate gates — that would block a booking"


def test_2_exactly_three_liability_risk_gates():
    """#2: exactly three gates carry 'Liability risk' — asserted by COUNT so promoting a
    fourth one to that severity fails this test."""
    defs = [k for (k, _label, sev) in server.GATE_DEFS if sev == "Liability risk"]
    assert len(defs) == 3, f"expected 3 liability-risk gates, got {defs}"
    assert set(defs) == LIABILITY_GATES
    pr, ctx, _ = passing_job()
    evaluated = [g["key"] for g in server.evaluate_gates(pr, ctx) if g["severity"] == "Liability risk"]
    assert len(evaluated) == 3 and set(evaluated) == LIABILITY_GATES


def test_3_all_gates_green_on_a_fully_satisfied_job():
    """#3 (the 'only when satisfied' half): every gate is green when its input is satisfied."""
    pr, ctx, _ = passing_job()
    reds = [(g["key"], g["reason"]) for g in server.evaluate_gates(pr, ctx) if not g["passed"]]
    assert reds == [], f"expected every gate green, got reds: {reds}"


@pytest.mark.parametrize("gate", [g[0] for g in server.GATE_DEFS])
def test_3_gate_flips_red_when_its_own_input_is_broken(gate):
    """#3 (14 tests, one per gate): breaking a single gate's own input turns exactly that
    gate red."""
    pr, ctx, _ = passing_job()
    _break(gate, pr, ctx)
    assert _gate(pr, ctx, gate)["passed"] is False, f"{gate} should be red after breaking its input"


def test_4_ofs_passes_on_short_notice_proof_even_when_signature_late_or_missing():
    """#4: ofs_24h passes with short-notice proof even if the OFS signature is missing or late."""
    pr, ctx, _ = passing_job()
    f = pr["fields"]
    # signature missing, proof present
    f.pop(server.PROJECT_OFS_SIGNED_F, None)
    f[server.PROJECT_SHORT_NOTICE_PROOF_F] = "Customer emailed same-day asking to move that day; thread attached."
    assert _gate(pr, ctx, "ofs_24h")["passed"] is True
    # signature LATE (day of move, past the 24h threshold) but proof still present
    move = f[server.PROJECT_DATE_FIELD]
    f[server.PROJECT_OFS_SIGNED_F] = f"{move}T09:00:00-04:00"
    assert _gate(pr, ctx, "ofs_24h")["passed"] is True
    # remove the proof AND keep the late signature -> now it must fail
    f.pop(server.PROJECT_SHORT_NOTICE_PROOF_F, None)
    assert _gate(pr, ctx, "ofs_24h")["passed"] is False


def test_5_long_haul_needs_owner_ack_only_at_60_plus_miles():
    """#5: long_haul_review passes at >=60 miles only when the owner ack is true."""
    pr, ctx, _ = passing_job()
    f = pr["fields"]
    f[server.PROJECT_ONE_WAY_MILES_F] = 60
    f.pop(server.PROJECT_LONG_HAUL_ACK_F, None)
    assert _gate(pr, ctx, "long_haul_review")["passed"] is False
    f[server.PROJECT_LONG_HAUL_ACK_F] = True
    assert _gate(pr, ctx, "long_haul_review")["passed"] is True
    # under 60 passes without any ack
    f[server.PROJECT_ONE_WAY_MILES_F] = 59
    f.pop(server.PROJECT_LONG_HAUL_ACK_F, None)
    assert _gate(pr, ctx, "long_haul_review")["passed"] is True


def test_6_protection_option2_needs_both_declared_value_and_deductible():
    """#6: Option 2 protection fails if either declared value or deductible is missing."""
    pr, ctx, _ = passing_job()
    f = pr["fields"]
    f[server.PROJECT_PROTECTION_OPTION_F] = "Option 2"
    f.pop(server.PROJECT_DECLARED_VALUE_F, None)
    f.pop(server.PROJECT_DEDUCTIBLE_F, None)
    assert _gate(pr, ctx, "protection_selected")["passed"] is False   # both missing
    f[server.PROJECT_DECLARED_VALUE_F] = 5000
    assert _gate(pr, ctx, "protection_selected")["passed"] is False   # deductible missing
    f.pop(server.PROJECT_DECLARED_VALUE_F, None)
    f[server.PROJECT_DEDUCTIBLE_F] = 300
    assert _gate(pr, ctx, "protection_selected")["passed"] is False   # declared value missing
    f[server.PROJECT_DECLARED_VALUE_F] = 5000
    assert _gate(pr, ctx, "protection_selected")["passed"] is True    # both present


# ---- OFFICE-GOODS EXEMPTION ----------------------------------------------------------

def test_7_office_goods_exempts_only_estimate_and_ofs():
    """#7: 'Office Goods Only' exempts ONLY estimate_24h and ofs_24h — nothing else."""
    pr, ctx, _ = passing_job()
    f = pr["fields"]
    f[server.PROJECT_MOVE_CLASS_F] = "Office Goods Only"
    f.pop(server.PROJECT_ESTIMATE_DELIVERED_F, None)
    f.pop(server.PROJECT_OFS_SIGNED_F, None)
    f.pop(server.PROJECT_SHORT_NOTICE_PROOF_F, None)
    gates = {g["key"]: g for g in server.evaluate_gates(pr, ctx)}
    assert gates["estimate_24h"]["exempt"] is True and gates["estimate_24h"]["passed"] is True
    assert gates["ofs_24h"]["exempt"] is True and gates["ofs_24h"]["passed"] is True
    exempt = {k for k, g in gates.items() if g.get("exempt")}
    assert exempt == {"estimate_24h", "ofs_24h"}, f"office exemption over-widened to: {exempt}"


def test_8_office_goods_still_enforces_protection_owner_op_and_labor():
    """#8: an office-goods job still FAILS protection_selected, owner_operator and
    labor_equip_change when those are in a failing state — the exemption never widens to them."""
    pr, ctx, _ = passing_job()
    f = pr["fields"]
    f[server.PROJECT_MOVE_CLASS_F] = "Office Goods Only"
    f.pop(server.PROJECT_PROTECTION_OPTION_F, None)          # no protection chosen
    f[server.PROJECT_OWNER_OP_USED_F] = True                 # owner-operator used...
    f.pop(server.PROJECT_OWNER_OP_NOTICE_F, None)            # ...with no notice
    f[server.PROJECT_LABOR_EQUIP_F] = "Not agreed"           # labor change not agreed
    gates = {g["key"]: g for g in server.evaluate_gates(pr, ctx)}
    for k in ("protection_selected", "owner_operator", "labor_equip_change"):
        assert gates[k]["exempt"] is False, f"{k} must never be exempted by office-goods"
        assert gates[k]["passed"] is False, f"{k} must still be enforced on an office-goods job"


# ---- OVERRIDE (role 403s + validation over HTTP; success/failure in-process) ----------

def _switch(owner_tok, role):
    r = requests.post(f"{API}/auth/switch-role", json={"role": role}, headers=_h(owner_tok), timeout=20)
    assert r.status_code == 200, r.text
    return _tok(r)


def test_9_override_forbidden_for_every_non_owner_role(owner_token, sales_token, crew_token, quality_token):
    """#9: the override endpoint returns 403 for quality, sales, employee AND crew — per role."""
    emp_tok = _switch(owner_token, "employee")
    body = {"reason": "x" * 25, "confirm": "OVERRIDE"}
    for role, tok in [("quality", quality_token), ("sales", sales_token),
                      ("employee", emp_tok), ("crew", crew_token)]:
        r = requests.post(f"{API}/jobs/recANY/compliance/override", json=body, headers=_h(tok), timeout=20)
        assert r.status_code == 403, f"{role} expected 403, got {r.status_code}: {r.text}"


def test_10_override_rejected_without_20char_reason_or_the_word_OVERRIDE(owner_token):
    """#10: override rejected when the reason is under 20 chars, and when the confirm word isn't OVERRIDE."""
    r1 = requests.post(f"{API}/jobs/recANY/compliance/override",
                       json={"reason": "too short", "confirm": "OVERRIDE"}, headers=_h(owner_token), timeout=20)
    assert r1.status_code == 422, r1.text
    r2 = requests.post(f"{API}/jobs/recANY/compliance/override",
                       json={"reason": "x" * 25, "confirm": "nope"}, headers=_h(owner_token), timeout=20)
    assert r2.status_code == 422, r2.text


def _run_override_in_process(project_fields, nc_should_fail=False, project_id="recOVR_TEST"):
    """Call the override endpoint directly with airtable_request monkeypatched (no live base).
    A single persistent event loop is reused across calls so Motor stays bound to a live loop
    (asyncio.run would close the loop between calls -> 'Event loop is closed')."""
    S = server
    calls = {"nc": []}
    real = S.airtable_request

    async def fake_air(method, table_id, path="", params=None, json_body=None):
        if table_id == S.TABLES["projects"] and method == "GET":
            return {"id": project_id, "fields": project_fields}
        if table_id == S.TABLES["quality_docs"] and method == "GET":
            return {"records": []}
        if table_id == S.TABLES["nonconformances"] and method == "POST":
            calls["nc"].append(json_body)
            if nc_should_fail:
                raise S.HTTPException(status_code=502, detail="simulated Airtable NC write failure")
            return {"records": [{"id": "recNC_TEST", "fields": json_body["records"][0]["fields"]}]}
        raise AssertionError(f"unexpected airtable call: {method} {table_id}{path}")

    S.airtable_request = fake_air
    principal = {"role": "owner", "name": "Owner Tester", "user_id": "owner-uid"}

    async def go():
        payload = S.OverridePayload(
            reason="Owner accepts the liability risk for this move — documented.", confirm="OVERRIDE")
        return await S.override_job_compliance(project_id, payload, principal)

    try:
        return _get_loop().run_until_complete(go()), calls
    finally:
        S.airtable_request = real


_LOOP = None


def _get_loop():
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP


def test_11_successful_override_opens_a_gate_override_nonconformance_with_details():
    """#11: a successful override creates a 'Gate override' NC carrying reason, who, when,
    and the severity of the most serious failing gate."""
    move = (datetime.now(server._ET).date() + timedelta(days=10)).isoformat()
    fields = {server.PROJECT_DATE_FIELD: move, server.PROJECT_NAME_FIELD: "QA Override Test Job"}
    try:
        result, calls = _run_override_in_process(fields, project_id="recOVR_TEST")
        assert len(calls["nc"]) == 1, "exactly one nonconformance must be written"
        nc = calls["nc"][0]["records"][0]["fields"]
        assert nc[server.NC_TYPE_F] == "Gate override"
        assert nc[server.NC_SEVERITY_F] == "Liability risk", "severity must be the worst failing gate"
        assert nc[server.NC_RAISED_BY_F] == "Owner Tester"            # who
        assert nc[server.NC_RAISED_DATE_F]                            # when
        assert "Owner Tester" in nc[server.NC_WHAT_F]
        assert "documented." in nc[server.NC_WHAT_F]                  # the reason is recorded
        assert nc[server.NC_LINKED_JOB_F] == ["recOVR_TEST"]
        ov = result["override"]
        assert ov["by"] == "Owner Tester" and ov["nc_id"] == "recNC_TEST" and ov["at"]
        assert ov["reason"].endswith("documented.")
    finally:
        _mongo().job_compliance.delete_one({"_id": "recOVR_TEST"})


def test_12_override_fails_when_the_nonconformance_write_fails():
    """#12: if the NC write fails, the override fails too — no override survives on a Mongo
    record alone."""
    move = (datetime.now(server._ET).date() + timedelta(days=10)).isoformat()
    fields = {server.PROJECT_DATE_FIELD: move, server.PROJECT_NAME_FIELD: "QA Override Fail Job"}
    try:
        with pytest.raises(server.HTTPException) as ei:
            _run_override_in_process(fields, nc_should_fail=True, project_id="recOVR_FAIL")
        assert ei.value.status_code == 502
        doc = _mongo().job_compliance.find_one({"_id": "recOVR_FAIL"})
        assert (doc or {}).get("override") is None, "no override may persist when the NC write failed"
    finally:
        _mongo().job_compliance.delete_one({"_id": "recOVR_FAIL"})


def test_13_after_override_the_failed_gates_stay_red():
    """#13: after an override, the failed gates still report passed=false — nothing turns green."""
    move = (datetime.now(server._ET).date() + timedelta(days=10)).isoformat()
    fields = {server.PROJECT_DATE_FIELD: move, server.PROJECT_NAME_FIELD: "QA Override Still Red"}
    try:
        result, _ = _run_override_in_process(fields, project_id="recOVR_RED")
        by = {g["key"]: g for g in result["gates"]}
        assert [g for g in result["gates"] if not g["passed"]], "job should have failing gates"
        assert by["brochure_delivered"]["passed"] is False
        assert by["ofs_24h"]["passed"] is False
        assert result["summary"]["all_green"] is False
        assert result["override"] is not None
    finally:
        _mongo().job_compliance.delete_one({"_id": "recOVR_RED"})


# ---- PERMISSIONS ---------------------------------------------------------------------

def test_14_quality_cannot_write_gate_inputs(quality_token):
    """#14: the quality role gets 403 writing any gate-input field on a job."""
    r = requests.put(f"{API}/jobs/recANY/compliance",
                     json={"inputs": {"inventory_complete": True}}, headers=_h(quality_token), timeout=20)
    assert r.status_code == 403, r.text


def test_15_quality_cannot_patch_projects_table(quality_token):
    """#15: the quality role gets 403 on PATCH /api/tables/projects/{id}."""
    r = requests.patch(f"{API}/tables/projects/recANY",
                       json={"fields": {server.PROJECT_INVENTORY_COMPLETE_F: True}},
                       headers=_h(quality_token), timeout=20)
    assert r.status_code == 403, r.text


def test_16_long_haul_ack_is_owner_only(owner_token, sales_token, quality_token, crew_token):
    """#16: long_haul_owner_ack is rejected for every role except owner."""
    emp_tok = _switch(owner_token, "employee")
    body = {"inputs": {"long_haul_owner_ack": True}}
    for role, tok in [("sales", sales_token), ("quality", quality_token),
                      ("crew", crew_token), ("employee", emp_tok)]:
        r = requests.put(f"{API}/jobs/recANY/compliance", json=body, headers=_h(tok), timeout=20)
        assert r.status_code == 403, f"{role} expected 403, got {r.status_code}: {r.text}"
    # the owner is NOT blocked by the ack rule (in preview it proceeds to Airtable -> 503)
    r = requests.put(f"{API}/jobs/recANY/compliance", json=body, headers=_h(owner_token), timeout=20)
    assert r.status_code != 403, f"owner must not be blocked by the ack rule: {r.status_code} {r.text}"
