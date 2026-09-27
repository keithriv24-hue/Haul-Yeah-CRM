"""Stage 5 — Python mirror of the JS scope engine's WORK MODEL (man-hours only).

This is NOT a second pricing engine. It reproduces the man-hour side of
frontend/src/lib/scopeEngine.js (computeScope, shift=0) so the backend can:
  - record a learnable feature breakdown on each saved scope, and
  - (Stage 7) evaluate candidate estimating parameters without re-running JavaScript.

The work model per spec:
  predicted_work_MH = volume_units * manHoursPer100CuFt * packingMult[pack]
                      + sum(access_units[key] * accessPer[key])
                      + item_mh_base * itemMult
where volume_units = cf/100, access_units[key] = acc[key] * (scale ? sc : 1),
      sc = max(1, cf/800), item_mh_base = item + custom-band + fit-work man-hours.

Constants below are copied verbatim from scopeEngine.js — keep the two in sync.
Nothing monetary lives here.
"""
from typing import Any, Dict, List, Optional

# room key -> (cu-ft at Light/Avg/Packed, lbs-per-cf, risky, is_bedroom)
ROOMS = {
    "primary": ([180, 250, 340], 6, False, True), "stdbed": ([130, 190, 260], 6, False, True),
    "smallbed": ([90, 130, 180], 6, False, True), "living": ([180, 275, 400], 6, False, False),
    "family": ([220, 330, 480], 6, False, False), "dining": ([120, 200, 290], 8, False, False),
    "kitchen": ([90, 140, 220], 9, False, False), "office": ([80, 130, 200], 10, False, False),
    "bath": ([15, 25, 40], 8, False, False), "laundry": ([30, 60, 100], 7, False, False),
    "misc": ([30, 60, 110], 7, False, False), "basefin": ([200, 350, 550], 7, True, False),
    "baseunfin": ([150, 350, 700], 10, True, False), "attic": ([80, 200, 400], 6, True, False),
    "gar1": ([150, 300, 500], 10, True, False), "gar2": ([300, 550, 900], 10, True, False),
    "shed": ([60, 130, 240], 10, True, False), "patio": ([60, 120, 220], 8, False, False),
    "closet": ([30, 60, 100], 5, False, False), "unit10": ([400, 600, 800], 8, True, False),
    "unit5": ([200, 300, 400], 8, True, False),
}

# item key -> (cu-ft, added man-hours each)
ITEMS = {
    "fridge": (60, 0.75), "fridge2": (75, 1.25), "washer": (25, 0.5), "dryer": (25, 0.5),
    "range": (30, 0.5), "freezer": (35, 0.75), "upright": (60, 1.5), "grand": (100, 2.5),
    "safe1": (25, 1.0), "safe2": (30, 1.25), "safe3": (35, 1.5), "pool": (90, 2.5),
    "tread": (40, 0.75), "gym": (70, 1.25), "plates": (20, 0.75), "mower": (60, 1.0),
    "moto": (80, 1.5), "hutch": (60, 0.75), "tv": (25, 0.5), "marble": (30, 0.75),
    "sleeper": (90, 0.5), "tank": (25, 1.0),
}

# custom band key -> (cf, mh, removeMh, placeMh, blocked)
CUSTOM_BANDS = {
    "under150": (20, 0.5, 0.25, 0.25, False), "w150_299": (30, 1.0, 0.5, 0.5, False),
    "w300_499": (45, 1.5, 0.75, 1.0, False), "w500_799": (60, 2.0, 1.0, 1.5, False),
    "w800plus": (0, 0, 0, 0, True),
}

# access key -> (per man-hours, scales-with-volume)
ACCESS = {
    "stairsO": (1.5, True), "stairsD": (1.5, True), "elevO": (2.0, True), "carryO": (1.5, True),
    "carryD": (1.5, True), "ladder": (2.0, False), "tight": (2.0, True), "noPark": (3.0, True),
    "disasm": (0.75, False), "stops": (1.0, False),
}

PACKING_MULT = [1.0, 1.12, 1.3, 1.6]
ACCESS_KEYS = list(ACCESS.keys())


def _num(v: Any, d: float = 0.0) -> float:
    try:
        f = float(v)
        return f if f == f else d  # NaN guard
    except (TypeError, ValueError):
        return d


def estimating_defaults() -> Dict[str, Any]:
    """Engine-only learnable constants at their CURRENT defaults (seed for estimating_params).
    manHoursPer100CuFt + packageHours are seeded from live rates in server.get_estimating_params."""
    return {
        "packingMult": list(PACKING_MULT),
        "accessPer": {k: ACCESS[k][0] for k in ACCESS_KEYS},
        "itemMult": 1.0,
        "crewEfficiency": {"2": 1.0, "3": 1.0, "4": 1.0, "5plus": 1.0},
        "avgDriveMph": 25.0, "travelInHours": 0.75, "travelOutHours": 0.5,
    }


def feature_registry() -> List[Dict[str, Any]]:
    """Every learnable feature from the engine's own PACKING/ACCESS/ITEMS/CUSTOM_BANDS,
    each at its current default. Adding a selection later surfaces here automatically."""
    reg: List[Dict[str, Any]] = [{"type": "volume_rate", "key": "manHoursPer100CuFt", "name": "Man-hours per 100 cu ft", "default": None}]
    for i, m in enumerate(PACKING_MULT):
        reg.append({"type": "packing", "key": f"pack{i}", "name": f"Packing tier {i}", "default": m})
    for k, (per, _scale) in ACCESS.items():
        reg.append({"type": "access", "key": k, "name": k, "default": per})
    for k, (_cf, mh) in ITEMS.items():
        reg.append({"type": "item", "key": k, "name": k, "default_mh": mh})
    for k, (_cf, mh, rm, pl, blk) in CUSTOM_BANDS.items():
        if not blk:
            reg.append({"type": "custom_band", "key": k, "name": k, "default_mh": mh})
    reg.append({"type": "item_mult", "key": "itemMult", "name": "Item man-hour multiplier", "default": 1.0})
    return reg


def compute_scope_features(inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """Man-hour breakdown mirroring computeScope(inputs, P, shift=0). Non-monetary only.
    `params` supplies manHoursPer100CuFt, packingMult, accessPer, itemMult (falls back to defaults)."""
    inputs = inputs or {}
    dens = inputs.get("dens") or {}
    cnt = inputs.get("cnt") or {}
    qty = inputs.get("qty") or {}
    acc = inputs.get("acc") or {}
    custom = inputs.get("custom") if isinstance(inputs.get("custom"), list) else []
    pack = int(inputs.get("pack") or 0)

    pack_mults = params.get("packingMult") if isinstance(params.get("packingMult"), list) and len(params["packingMult"]) == len(PACKING_MULT) else PACKING_MULT
    access_per = params.get("accessPer") or {}
    item_mult = _num(params.get("itemMult"), 1.0)
    base_rate = _num(params.get("manHoursPer100CuFt"), 2.1)
    rate = _num(inputs.get("rate"), base_rate)  # What-if / replayed snapshot wins, else the param base

    cf = 0.0
    item_mh = 0.0
    for k, (v3, _w, _risky, _bed) in ROOMS.items():
        lvl = int(dens.get(k) or 0)
        if not lvl:
            continue
        n = _num(cnt.get(k), 1) or 1
        cf += v3[lvl - 1] * n
    for k, (icf, imh) in ITEMS.items():
        n = _num(qty.get(k), 0)
        if not n:
            continue
        cf += icf * n
        item_mh += imh * n
    fit_mh = 0.0
    for c in custom:
        band = CUSTOM_BANDS.get((c or {}).get("band"))
        if not band:
            continue
        bcf, bmh, brm, bpl, blocked = band
        if blocked:
            continue
        units = 2 if (c or {}).get("isSwap") else 1
        fw = (c or {}).get("fitWork") or "none"
        fit_per = (brm if fw in ("removeOnly", "both") else 0) + (bpl if fw in ("placeOnly", "both") else 0)
        n = max(1, round(_num((c or {}).get("qty"), 1)) or 1)
        cf += bcf * n * units
        item_mh += (bmh + fit_per) * n * units
        fit_mh += fit_per * n * units

    sc = max(1.0, cf / 800.0)
    vol_mh = (cf / 100.0) * rate * (pack_mults[pack] if 0 <= pack < len(pack_mults) else 1.0)
    access_units: Dict[str, float] = {}
    acc_mh = 0.0
    for k, (per_def, scale) in ACCESS.items():
        v = _num(acc.get(k), 0)
        if not v:
            continue
        units = v * (sc if scale else 1)
        access_units[k] = round(units, 6)
        acc_mh += _num(access_per.get(k), per_def) * units
    item_mh_eff = item_mh * item_mult
    sched_mh = vol_mh + item_mh_eff + acc_mh
    return {
        "cf": round(cf, 4), "volume_units": round(cf / 100.0, 6), "sc": round(sc, 6),
        "item_mh_base": round(item_mh, 6), "fit_mh": round(fit_mh, 6),
        "access_units": access_units, "vol_mh": round(vol_mh, 6), "item_mh": round(item_mh_eff, 6),
        "access_mh": round(acc_mh, 6), "rate_used": rate, "pack": pack,
        "predicted_work_mh": round(sched_mh, 6), "model_sched_mh": round(sched_mh, 6),
    }


def predict_work_mh(inputs: Dict[str, Any], params: Dict[str, Any]) -> float:
    """The single work-model number (== JS engine schedMH at shift=0)."""
    return compute_scope_features(inputs, params)["predicted_work_mh"]
