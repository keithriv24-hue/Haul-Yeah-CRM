"""Stage 7 — guarded estimating optimizer (PURE math; no DB, no pricing, no I/O).

Learns NON-MONETARY work-model parameters from completed-job outcomes and returns bounded,
movement-capped candidates that must clear an accuracy gate before they are applied. It never
touches money, never re-prices saved quotes, and is a no-op on unchanged data.

Supported factors + their rules (from the approved Stage 7 spec):
  base_rate      mh/100cuft   eligible from job 1 · shrink toward 2.1 (w=n/(n+10)) · ±3%/run · bounds 1.6–2.8
  package_hours  per size     eligible from job 1/size · shrink toward baseline (w=n/(n+5)) · ±0.25h/run · ±40% of baseline
  multipliers    packing/access/item  JOINT ridge fit only when ≥30 valid jobs AND ≥8 appearances/factor · ±5%/run · 0.6–1.6× baseline
  crew_efficiency per crew size  ≥15 valid jobs/size · ±5%/run · bounds 0.8–1.2 (normalized so the LEVEL stays in base_rate — no double count)
  drive_speed    scheduling   ≥8 tapped drive segments · learned only from observed miles/drive-hours · ±10%/run · bounds 10–45 mph
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

BASELINE_RATE = 2.1
RATE_CLIP = (1.2, 3.5)
RATE_BOUNDS = (1.6, 2.8)
RATE_MAX_STEP_PCT = 0.03
RATE_SHRINK_K = 10.0

PKG_MAX_STEP = 0.25
PKG_SHRINK_K = 5.0
PKG_BOUND_PCT = 0.40

MULT_MAX_STEP_PCT = 0.05
MULT_BOUND_LO, MULT_BOUND_HI = 0.6, 1.6      # × baseline
JOINT_MIN_JOBS = 30
JOINT_MIN_APPEAR = 8

CREW_EFF_BOUNDS = (0.8, 1.2)
CREW_EFF_MAX_STEP_PCT = 0.05
CREW_EFF_MIN_JOBS = 15

DRIVE_MIN_JOBS = 8
DRIVE_BOUNDS = (10.0, 45.0)
DRIVE_MAX_STEP_PCT = 0.10


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def move_cap(current: float, candidate: float, max_abs: Optional[float] = None,
             max_pct: Optional[float] = None) -> float:
    """Limit how far one run may move from the CURRENTLY ACTIVE value."""
    lo, hi = -math.inf, math.inf
    if max_abs is not None:
        lo, hi = current - max_abs, current + max_abs
    if max_pct is not None:
        step = abs(current) * max_pct
        lo = max(lo, current - step)
        hi = min(hi, current + step)
    return clamp(candidate, lo, hi)


def weighted_median(pairs: List[Tuple[float, float]]) -> Optional[float]:
    pairs = [(float(v), float(w)) for v, w in pairs if w and w > 0 and v is not None]
    if not pairs:
        return None
    pairs.sort(key=lambda x: x[0])
    total = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= total / 2:
            return v
    return pairs[-1][0]


def trimmed_weighted_mean(pairs: List[Tuple[float, float]], trim: float = 0.1) -> Optional[float]:
    pairs = sorted([(float(v), float(w)) for v, w in pairs if w and w > 0 and v is not None], key=lambda x: x[0])
    if not pairs:
        return None
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
    cut = total * trim
    lo_acc, kept = 0.0, []
    for v, w in pairs:                       # trim `cut` weight off each tail
        take = w
        if lo_acc < cut:
            drop = min(w, cut - lo_acc)
            lo_acc += drop
            take = w - drop
        kept.append((v, take))
    kept.reverse()
    hi_acc, kept2 = 0.0, []
    for v, w in kept:
        take = w
        if hi_acc < cut:
            drop = min(w, cut - hi_acc)
            hi_acc += drop
            take = w - drop
        kept2.append((v, take))
    num = sum(v * w for v, w in kept2)
    den = sum(w for _, w in kept2)
    return num / den if den > 0 else weighted_median(pairs)


def _eff_n(jobs: List[Dict[str, Any]]) -> float:
    return sum(float(j.get("weight") or 0) for j in jobs)


# ---------- accuracy gate ----------
def _mae_bias(jobs: List[Dict[str, Any]], predict) -> Tuple[Optional[float], Optional[float]]:
    errs = []
    for j in jobs:
        actual = j.get("actual")
        if actual is None:
            continue
        pred = predict(j)
        if pred is None:
            continue
        errs.append(pred - actual)
    if not errs:
        return None, None
    mae = sum(abs(e) for e in errs) / len(errs)
    bias = abs(sum(errs) / len(errs))
    return round(mae, 4), round(bias, 4)


def accuracy_gate(jobs: List[Dict[str, Any]], predict_current, predict_candidate) -> Dict[str, Any]:
    """Under 30 jobs: in-sample error must not worsen. At 30+: fit-implied candidate is validated on the
    newest 20% (train = oldest 80%). Typical error (MAE) decides; absolute bias breaks ties."""
    n = len(jobs)
    if n >= JOINT_MIN_JOBS:
        ordered = sorted(jobs, key=lambda j: j.get("date") or "")
        split = int(round(n * 0.8))
        val = ordered[split:] or ordered[-max(1, n // 5):]
        eval_set = val
        mode = "holdout_20"
    else:
        eval_set = jobs
        mode = "in_sample"
    mae_cur, bias_cur = _mae_bias(eval_set, predict_current)
    mae_cand, bias_cand = _mae_bias(eval_set, predict_candidate)
    if mae_cur is None or mae_cand is None:
        return {"pass": False, "mode": mode, "reason": "no_evaluable_jobs",
                "mae_current": mae_cur, "mae_candidate": mae_cand}
    eps = 1e-9
    better = (mae_cand < mae_cur - eps) or (abs(mae_cand - mae_cur) <= 1e-6 and bias_cand < bias_cur - eps)
    not_worse = mae_cand <= mae_cur + 1e-6
    passed = not_worse if not better else True
    return {"pass": bool(passed), "mode": mode, "mae_current": mae_cur, "mae_candidate": mae_cand,
            "bias_current": bias_cur, "bias_candidate": bias_cand, "eval_jobs": len(eval_set)}


# ---------- base rate ----------
def implied_base_rate(job: Dict[str, Any]) -> Optional[float]:
    denom = float(job.get("volume_units") or 0) * float(job.get("packing_mult") or 0)
    if denom <= 0:
        return None
    r = (float(job["work_mh"]) - float(job.get("access_mh") or 0) - float(job.get("item_mh") or 0)) / denom
    if r != r or math.isinf(r):
        return None
    return clamp(r, *RATE_CLIP)


def _base_rate_predict(rate: float):
    return lambda j: (float(j.get("access_mh") or 0) + float(j.get("item_mh") or 0)
                      + float(j.get("volume_units") or 0) * float(j.get("packing_mult") or 0) * rate)


def base_rate_run(jobs: List[Dict[str, Any]], current: float, baseline: float = BASELINE_RATE) -> Dict[str, Any]:
    obs = []
    for j in jobs:
        ir = implied_base_rate(j)
        if ir is not None:
            j["_implied"] = ir
            j["actual"] = float(j["work_mh"])
            obs.append((ir, float(j.get("weight") or 0)))
    n_eff = sum(w for _, w in obs)
    usable = [j for j in jobs if j.get("_implied") is not None]
    if n_eff <= 0 or not usable:
        return {"factor": "base_rate", "eligible": False, "usable_jobs": 0, "n_eff": 0.0,
                "current": current, "baseline": baseline}
    data_est = weighted_median(obs) if n_eff < 10 else trimmed_weighted_mean(obs, 0.1)
    w = n_eff / (n_eff + RATE_SHRINK_K)
    raw_candidate = w * data_est + (1 - w) * baseline
    capped = move_cap(current, raw_candidate, max_pct=RATE_MAX_STEP_PCT)
    bounded = round(clamp(capped, *RATE_BOUNDS), 4)
    gate = accuracy_gate(usable, _base_rate_predict(current), _base_rate_predict(bounded))
    changed = abs(bounded - current) > 1e-6
    return {"factor": "base_rate", "eligible": True, "usable_jobs": len(usable), "n_eff": round(n_eff, 2),
            "data_estimate": round(data_est, 4), "shrink_w": round(w, 3), "raw_candidate": round(raw_candidate, 4),
            "current": current, "candidate": bounded, "baseline": baseline, "changed": changed, "gate": gate,
            "apply": bool(changed and gate.get("pass"))}


# ---------- package hours ----------
def _pkg_predict(hours: float):
    return lambda j: hours


def package_hours_run(jobs: List[Dict[str, Any]], current: float, baseline: float) -> Dict[str, Any]:
    obs = []
    for j in jobs:
        a = j.get("actual_hours")
        if a is not None and a == a:
            j["actual"] = float(a)
            obs.append((float(a), float(j.get("weight") or 0)))
    n_eff = sum(w for _, w in obs)
    usable = [j for j in jobs if j.get("actual") is not None]
    if n_eff <= 0 or not usable:
        return {"factor": "package_hours", "eligible": False, "usable_jobs": 0, "n_eff": 0.0,
                "current": current, "baseline": baseline}
    data_est = weighted_median(obs)
    w = n_eff / (n_eff + PKG_SHRINK_K)
    raw_candidate = w * data_est + (1 - w) * baseline
    capped = move_cap(current, raw_candidate, max_abs=PKG_MAX_STEP)
    bounded = round(clamp(capped, baseline * (1 - PKG_BOUND_PCT), baseline * (1 + PKG_BOUND_PCT)), 3)
    gate = accuracy_gate(usable, _pkg_predict(current), _pkg_predict(bounded))
    changed = abs(bounded - current) > 1e-6
    return {"factor": "package_hours", "eligible": True, "usable_jobs": len(usable), "n_eff": round(n_eff, 2),
            "data_estimate": round(data_est, 3), "shrink_w": round(w, 3), "raw_candidate": round(raw_candidate, 3),
            "current": current, "candidate": bounded, "baseline": baseline, "changed": changed, "gate": gate,
            "apply": bool(changed and gate.get("pass"))}


# ---------- crew efficiency (per crew size; normalized so the LEVEL stays in base_rate) ----------
def crew_efficiency_run(by_crew: Dict[str, List[Dict[str, Any]]], current: Dict[str, float]) -> Dict[str, Any]:
    """Each job carries model_onsite (schedMH/crew at eff=1, current base rate) and actual_onsite (crew-adjusted
    work hours). Observed efficiency = model_onsite/actual_onsite. Observations are normalized by the weighted
    geometric mean across ALL crew sizes so the overall level (already learned by base_rate) is NOT double-counted."""
    obs_by_crew: Dict[str, List[Tuple[float, float]]] = {}
    all_log, all_w = [], []
    for c, jobs in by_crew.items():
        pairs = []
        for j in jobs:
            mo, ao, wt = j.get("model_onsite"), j.get("actual_onsite"), float(j.get("weight") or 0)
            if mo and ao and ao > 0 and wt > 0:
                e = mo / ao
                if e > 0:
                    pairs.append((e, wt))
                    all_log.append(math.log(e) * wt)
                    all_w.append(wt)
        if pairs:
            obs_by_crew[c] = pairs
    level = math.exp(sum(all_log) / sum(all_w)) if all_w else 1.0   # weighted geometric mean = the base level
    out = {}
    for c in ("2", "3", "4", "5plus"):
        pairs = obs_by_crew.get(c, [])
        n_eff = sum(w for _, w in pairs)
        cur = float(current.get(c, 1.0))
        if n_eff < CREW_EFF_MIN_JOBS:
            out[c] = {"eligible": False, "usable_jobs": len(pairs), "n_eff": round(n_eff, 2),
                      "current": cur, "candidate": cur, "changed": False, "apply": False}
            continue
        med = weighted_median(pairs) or 1.0
        normalized = med / level if level else med          # strip the base-rate level → per-crew relative only
        capped = move_cap(cur, normalized, max_pct=CREW_EFF_MAX_STEP_PCT)
        bounded = round(clamp(capped, *CREW_EFF_BOUNDS), 4)
        changed = abs(bounded - cur) > 1e-6
        out[c] = {"eligible": True, "usable_jobs": len(pairs), "n_eff": round(n_eff, 2),
                  "observed": round(med, 4), "normalized": round(normalized, 4), "level": round(level, 4),
                  "current": cur, "candidate": bounded, "changed": changed, "apply": bool(changed)}
    return {"factor": "crew_efficiency", "by_crew": out}


# ---------- drive speed (scheduling only) ----------
def drive_speed_run(jobs: List[Dict[str, Any]], current: float) -> Dict[str, Any]:
    obs = []
    for j in jobs:
        if j.get("drive_source") == "taps" and j.get("miles") and j.get("drive_hours"):
            mph = float(j["miles"]) / float(j["drive_hours"])
            if DRIVE_BOUNDS[0] * 0.3 <= mph <= DRIVE_BOUNDS[1] * 2:
                obs.append((mph, float(j.get("weight") or 1)))
    n = len(obs)
    if n < DRIVE_MIN_JOBS:
        return {"factor": "drive_speed", "eligible": False, "usable_jobs": n, "current": current,
                "candidate": current, "apply": False}
    med = weighted_median(obs)
    capped = move_cap(current, med, max_pct=DRIVE_MAX_STEP_PCT)
    bounded = round(clamp(capped, *DRIVE_BOUNDS), 2)
    changed = abs(bounded - current) > 1e-6
    return {"factor": "drive_speed", "eligible": True, "usable_jobs": n, "observed": round(med, 2),
            "current": current, "candidate": bounded, "changed": changed, "apply": bool(changed)}


# ---------- joint multiplier fit (packing / access / item) ----------
def multiplier_joint_run(jobs: List[Dict[str, Any]], current: Dict[str, Any], baseline: Dict[str, Any],
                         access_keys: List[str]) -> Dict[str, Any]:
    """Held at baseline until ≥30 valid jobs AND ≥8 appearances per factor. When eligible, a single
    ridge-regularized least-squares fit (toward baseline) distributes residual work-hours across the
    factors jointly — never assigning the whole per-job error to each factor independently."""
    n = len(jobs)
    pack_tiers = [0, 1, 2, 3]
    appear = {f"pack{t}": 0 for t in pack_tiers}
    appear.update({f"acc:{k}": 0 for k in access_keys})
    appear["item"] = 0
    for j in jobs:
        appear[f"pack{int(j.get('pack') or 0)}"] = appear.get(f"pack{int(j.get('pack') or 0)}", 0) + 1
        for k in access_keys:
            if float((j.get("access_units") or {}).get(k) or 0) > 0:
                appear[f"acc:{k}"] += 1
        if float(j.get("item_mh_base") or 0) > 0:
            appear["item"] += 1
    factors_ready = {f: v >= JOINT_MIN_APPEAR for f, v in appear.items()}
    eligible = n >= JOINT_MIN_JOBS and any(factors_ready.values())
    result = {"factor": "multipliers", "eligible": eligible, "jobs": n, "min_jobs": JOINT_MIN_JOBS,
              "appearances": appear, "min_appearances": JOINT_MIN_APPEAR, "held_at_baseline": not eligible,
              "candidates": {}, "apply": False}
    if not eligible:
        return result
    try:
        import numpy as np
    except ImportError:
        result["error"] = "numpy_unavailable"
        return result
    cols = [f"pack{t}" for t in pack_tiers] + [f"acc:{k}" for k in access_keys] + ["item"]
    rows, target = [], []
    for j in jobs:
        rate = float(j.get("rate_used") or BASELINE_RATE)
        vol = float(j.get("volume_units") or 0)
        row = []
        for t in pack_tiers:
            row.append(rate * vol if int(j.get("pack") or 0) == t else 0.0)
        for k in access_keys:
            row.append(float((j.get("access_units") or {}).get(k) or 0))
        row.append(float(j.get("item_mh_base") or 0))
        rows.append(row)
        target.append(float(j["work_mh"]))
    X = np.array(rows, dtype=float)
    y = np.array(target, dtype=float)
    base_coef = np.array([float((baseline.get("packingMult") or [1, 1, 1, 1])[t]) for t in pack_tiers]
                         + [float((baseline.get("accessPer") or {}).get(k, 0)) for k in access_keys]
                         + [float(baseline.get("itemMult", 1))], dtype=float)
    lam = 1.0
    A = X.T @ X + lam * np.eye(X.shape[1])
    b = X.T @ y + lam * base_coef
    try:
        coef = np.linalg.solve(A, b)
    except Exception:
        result["error"] = "singular"
        return result
    cands = {}
    for idx, name in enumerate(cols):
        if not factors_ready.get(name):
            continue
        raw = float(coef[idx])
        if name.startswith("pack"):
            t = int(name[4:])
            base = float((baseline.get("packingMult") or [1, 1, 1, 1])[t])
            cur = float((current.get("packingMult") or [1, 1, 1, 1])[t])
        elif name.startswith("acc:"):
            k = name[4:]
            base = float((baseline.get("accessPer") or {}).get(k, 0))
            cur = float((current.get("accessPer") or {}).get(k, base))
        else:
            base = float(baseline.get("itemMult", 1))
            cur = float(current.get("itemMult", 1))
        if base <= 0:
            continue
        capped = move_cap(cur, raw, max_pct=MULT_MAX_STEP_PCT)
        bounded = round(clamp(capped, base * MULT_BOUND_LO, base * MULT_BOUND_HI), 4)
        cands[name] = {"current": cur, "candidate": bounded, "baseline": base,
                       "changed": abs(bounded - cur) > 1e-6}
    result["candidates"] = cands
    result["apply"] = any(c["changed"] for c in cands.values())
    return result
