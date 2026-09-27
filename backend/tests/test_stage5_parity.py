"""Stage 5 acceptance — EXACT parity proof.

Proves that making the estimating engine "learnable" (threading estimating
parameters EP through the JS engine + adding the Python work model) changes
NOTHING about today's quotes.

Four checks, per the approved spec:
  1. JS 3-way: engine-with-seeded-EP === engine-with-NO-EP === a FROZEN copy of
     the engine captured before Stage 5. Identical rounded dollars (0 cent),
     man-hours within 0.01, unchanged crew / truck / blocker recommendations.
  2. Recompute === originally-saved dollars for every REPLAYABLE saved scope.
  3. Python predict_work_mh === JS schedMH within 0.01 MAN-HOURS (every case).
  4. Python predict_work_mh === originally-saved schedMH where the scope stored it.

Saved scopes with no stored pricing snapshot are listed as UNREPLAYABLE and are
NOT counted as passes (their dollars were never engine-generated).

Run: python -m pytest backend/tests/test_stage5_parity.py -s
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
import scope_engine  # noqa: E402

REPO = BACKEND.parent
NODE_SCRIPT = REPO / "frontend" / "scripts" / "stage5-parity.mjs"
DATA_JSON = Path("/tmp/stage5_data.json")
JS_RESULTS = Path("/tmp/stage5_js_results.json")
HR_TOL = 0.01


def _mongo():
    from pymongo import MongoClient
    env = (BACKEND / ".env").read_text()
    url = re.search(r'MONGO_URL="?([^"\n]+)', env).group(1)
    dbn = re.search(r'DB_NAME="?([^"\n]+)', env).group(1)
    return MongoClient(url)[dbn]


def _live_rates(db):
    doc = db.settings.find_one({"_id": "calculator_rates"}) or {}
    return dict(doc.get("pricing_v2") or {})


# survey pricing = every monetary key zeroed (mirrors frontend NO_PRICING)
def _survey_pricing(live):
    keep = {"roundingIncrement", "minHoursTruck", "minHoursLabor", "mileageFreeMiles",
            "hardFloorBedrooms", "hardFloorHours", "maxCrewPerDay", "targetHoursOnSite",
            "maxHoursOnSite", "pkgStudioCrew", "pkgStudioHours", "pkg2brCrew", "pkg2brHours",
            "pkg3brCrew", "pkg3brHours", "pkg4brCrew", "pkg4brHours", "serviceStates"}
    return {k: (live.get(k, 0) if k in keep else (v if isinstance(v, str) else 0))
            for k, v in live.items()}


def _edge_cases(live):
    """Representative package / override / model / survey / floor / blocker cases."""
    r21 = float(live.get("manHoursPer100CuFt", 2.1))
    base = dict(jobType="truck", rate=r21, pack=0, miles=30, pickupState="NJ", dropoffState="NJ")
    return [
        # model-driven: rooms only, crew from schedMH
        {"id": "edge-model", "label": "EDGE model (rooms only)", "kind": "edge", "replayable": False,
         "pricing": live, "inputs": {**base, "dens": {"primary": 2, "living": 2, "kitchen": 2, "bath": 2}, "cnt": {}, "qty": {"fridge": 1}, "acc": {"stairsO": 1}}},
        # package: 3BR quick-start (crew/hours overrides written by the package) → hard 6-hr floor
        {"id": "edge-package", "label": "EDGE package (3BR quick-start)", "kind": "edge", "replayable": False,
         "pricing": live, "inputs": {**base, "pkg": "br3", "crewOverride": int(live.get("pkg3brCrew", 4)), "hoursOverride": float(live.get("pkg3brHours", 6.5)), "dens": {"primary": 2, "stdbed": 2}, "cnt": {"stdbed": 2}}},
        # override: explicit rep crew + hours
        {"id": "edge-override", "label": "EDGE rep override (crew 5 / 8h)", "kind": "edge", "replayable": False,
         "pricing": live, "inputs": {**base, "crewOverride": 5, "hoursOverride": 8, "dens": {"primary": 2, "living": 3, "family": 2, "kitchen": 2}, "cnt": {}}},
        # survey: zeroed pricing, hours must still match
        {"id": "edge-survey", "label": "EDGE survey (no pricing)", "kind": "edge", "replayable": False,
         "pricing": _survey_pricing(live), "inputs": {**base, "dens": {"primary": 2, "living": 2}, "cnt": {}, "acc": {"stairsO": 2, "carryO": 1}}},
        # floor: tiny labor-only job → min-hours + price floor bind
        {"id": "edge-floor", "label": "EDGE floor (labor-only, tiny)", "kind": "edge", "replayable": False,
         "pricing": live, "inputs": {"jobType": "labor", "rate": r21, "pack": 0, "miles": 0, "qty": {"washer": 1}, "dens": {}, "cnt": {}}},
        # blocker: 800lb+ custom item → assessment required, price suppressed
        {"id": "edge-blocker", "label": "EDGE blocker (800lb+ custom)", "kind": "edge", "replayable": False,
         "pricing": live, "inputs": {**base, "dens": {}, "cnt": {}, "custom": [{"name": "Vault", "band": "w800plus", "qty": 1}]}},
    ]


def _build_cases():
    db = _mongo()
    live = _live_rates(db)
    assert live, "live pricing_v2 not seeded"
    cases = []
    for s in db.lead_scopes.find({}).sort("created_at", 1):
        snap = dict(s.get("pricing") or {})
        replayable = len(snap) > 0
        pricing = {**live, **snap} if replayable else live
        res = s.get("result") or {}
        saved = {k: res.get(k) for k in ("bandLo", "bandHi", "finalTotal", "deposit", "schedMH", "billMH", "onsite", "crew")}
        cases.append({
            "id": s["_id"], "label": (s.get("label") or s["_id"][:8]) + f" [{s.get('tier') or 'legacy'}/{res.get('mode')}]",
            "kind": "saved", "replayable": replayable,
            "inputs": s.get("inputs") or {}, "pricing": pricing, "saved": saved,
        })
    cases += _edge_cases(live)
    return cases, scope_engine.estimating_defaults()


def _run_node(cases, seeded_ep):
    DATA_JSON.write_text(json.dumps({"cases": cases, "seededEP": seeded_ep}))
    proc = subprocess.run(["node", str(NODE_SCRIPT)], capture_output=True, text=True)
    print(proc.stdout)
    if proc.stderr.strip():
        print("NODE STDERR:\n" + proc.stderr)
    return proc.returncode


def test_stage5_exact_parity():
    cases, seeded_ep = _build_cases()
    saved = [c for c in cases if c["kind"] == "saved"]
    with_snap = [c for c in saved if c["replayable"]]

    print("\n" + "=" * 78)
    print("STAGE 5 ACCEPTANCE — EXACT PARITY")
    print("=" * 78)
    print(f"saved scopes: {len(saved)}  (with pricing snapshot {len(with_snap)} · without {len(saved) - len(with_snap)})")
    print(f"edge cases:   {len([c for c in cases if c['kind'] == 'edge'])}  (package / override / model / survey / floor / blocker)")
    print(f"seeded EP: packingMult={seeded_ep['packingMult']} itemMult={seeded_ep['itemMult']}")
    print("-" * 78)

    # checks 1 + 2 (JS 3-way + recompute===saved dollars) — node exits non-zero on any mismatch
    rc = _run_node(cases, seeded_ep)
    assert rc == 0, "JS-side parity FAILED (see node output above)"

    # checks 3 + 4 (Python work model === JS schedMH, and === saved schedMH where replayable)
    js = {r["id"]: r for r in json.loads(JS_RESULTS.read_text())}
    py_js_fail, py_saved_fail, checked_saved = [], [], 0
    for c in cases:
        j = js[c["id"]]
        py_mh = scope_engine.predict_work_mh(c["inputs"], seeded_ep)
        if abs(py_mh - float(j["schedMH"])) > HR_TOL:
            py_js_fail.append(f"{c['label']}: python {py_mh:.4f} vs js schedMH {j['schedMH']:.4f}")
        # only replayable (frozen-reproducible) saved scopes get the saved-schedMH check
        if c["kind"] == "saved" and j.get("replayable") and (c.get("saved") or {}).get("schedMH") is not None:
            checked_saved += 1
            sv = float(c["saved"]["schedMH"])
            if abs(py_mh - sv) > HR_TOL:
                py_saved_fail.append(f"{c['label']}: python {py_mh:.4f} vs saved schedMH {sv:.4f}")

    print("-" * 78)
    print(f"Python work-model === JS schedMH (<=0.01 mh): {len(cases) - len(py_js_fail)}/{len(cases)}")
    for f in py_js_fail:
        print("  ✗ " + f)
    print(f"Python work-model === originally-saved schedMH (replayable only): {checked_saved - len(py_saved_fail)}/{checked_saved}")
    for f in py_saved_fail:
        print("  ✗ " + f)
    print("=" * 78)

    assert not py_js_fail, "Python vs JS man-hour parity FAILED"
    assert not py_saved_fail, "Python vs saved man-hour parity FAILED"


if __name__ == "__main__":
    sys.exit(0 if pytest.main([__file__, "-s", "-q"]) == 0 else 1)
