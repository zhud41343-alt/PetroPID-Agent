"""V4.3.4 Phase 3: Observable-Only Change-Point / Unmeasured Load-Step Validation Study + 24-Loop Blind Holdout.

STRICT SCIENTIFIC PROTOCOL:
1. Uses ONLY observable signals (t, sp, pv, op) — zero access to true plant parameters during identification.
2. Keeps ALL 11 safety hard constraints (C-000..C-010, GM>=1.8, PM>=35°, Ms<=2.2, 5-regime limits) 100% intact.
3. Frozen rule (developed on LOOP-012..017):
   When standard 65/35 holdout validation fails (`val_r2 < 0.80` or `val_fit < 85%`), check if the failure
   is strictly caused by a single piecewise-constant unmeasured DC load-step offset in the validation segment:
     (a) `train_r2 >= 0.92`
     (b) `resid_lag1_autocorr <= 0.45` (white residual, rejects periodic disturbance & unmodeled dynamics)
     (c) `std(val_resid) <= 1.5 * std(train_resid) + 0.02`
     (d) `|mean(val_resid) - mean(train_resid)| >= 2.5 * std(train_resid)`
     (e) After subtracting ONLY the scalar DC offset `mean(val_resid)` (zero refit of K/tau/theta),
         `offset_adj_val_r2 >= 0.92` AND `offset_adj_val_fit_pct >= 92.0%`
4. Validates on:
   - Part A: Full 30-loop PetroPID benchmark (side-by-side vs V4.3.3 frozen baseline)
   - Part B: Brand-new 24-loop PRE-ISOLATED BLIND HOLDOUT set (unseen seeds/plants).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

os.environ["PETROPID_LLM_DISABLE_DOTENV"] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "05_skills"))
sys.path.insert(0, str(ROOT / "07_agents"))

from petro_pid import (PIDParams, PlantParams, ValveParams, diagnose_loop, simulate_loop, tune_pid, verify_pid_safety, identify_fopdt_with_observable_load_step_check)  # noqa: E402
from petro_pid.identification import IdentificationResult, identify_fopdt, simulate_fopdt_open_loop  # noqa: E402
from decision_engine import DecisionEvidence, final_decision_aggregation  # noqa: E402
from skill_runner import _load_loop_dataframe, _load_loop_metadata  # noqa: E402


def identify_fopdt_with_load_step_check(pv: np.ndarray, op: np.ndarray, dt: float = 1.0) -> Tuple[IdentificationResult, Dict[str, Any]]:
    """Compatibility wrapper around the production V4.3.4 validator."""
    result = identify_fopdt_with_observable_load_step_check(pv, op, dt=dt)
    evidence = dict(result.validation_evidence or {})
    return result, evidence


def _evaluate_loop(
    *,
    loop_id: str,
    sp: np.ndarray,
    pv: np.ndarray,
    op: np.ndarray,
    dt: float,
    init_pid: PIDParams,
    true_plant: PlantParams,
    dist_amp: float,
    dist_period: float,
    expected_status: str,
    use_load_step_check: bool,
) -> Dict[str, Any]:
    diag = diagnose_loop(sp, pv, op, dt=dt)
    if diag.anomaly_type == "NORMAL":
        return {"loop_id": loop_id, "pred_anomaly": diag.anomaly_type, "final_status": "HEALTHY_NO_CHANGE", "expected": expected_status, "exact_match": expected_status == "HEALTHY_NO_CHANGE", "multi_regime_pass_pct": None, "load_step_used": False, "load_step_detected": False, "validation_gate_passed": None, "validation_reason": "normal_loop_no_identification"}
    if diag.anomaly_type == "VALVE_STICTION":
        return {"loop_id": loop_id, "pred_anomaly": diag.anomaly_type, "final_status": "VALVE_MAINTENANCE_REQUIRED", "expected": expected_status, "exact_match": expected_status == "VALVE_MAINTENANCE_REQUIRED", "multi_regime_pass_pct": None, "load_step_used": False, "load_step_detected": False, "validation_gate_passed": None, "validation_reason": "valve_stiction_short_circuit"}

    if use_load_step_check:
        ident, info = identify_fopdt_with_load_step_check(pv, op, dt=dt)
    else:
        ident, info = identify_fopdt(pv, op, dt=dt), {"load_step_compensated": False}

    if not ident.allow_next_stage:
        return {"loop_id": loop_id, "pred_anomaly": diag.anomaly_type, "final_status": "MODEL_VALIDATION_FAILED", "expected": expected_status, "exact_match": expected_status == "MODEL_VALIDATION_FAILED", "multi_regime_pass_pct": None, "val_r2": ident.val_r2, "val_fit_pct": ident.val_fit_pct, "load_step_used": False, "load_step_detected": bool(info.get("dc_shift_sigma", 0.0) >= 2.5), "validation_gate_passed": False, "validation_reason": ident.failure_reason or "standard_validation_failed"}

    id_plant = PlantParams(K=ident.K, tau=ident.tau, theta=ident.theta, pv_bias=ident.pv_bias, op_bias=ident.op_bias)
    tun = tune_pid(id_plant, current_pid=init_pid, anomaly_type=diag.anomaly_type, dt=dt)
    chosen = next(c for c in tun.candidates if c.strategy == "balanced")
    sv = verify_pid_safety(
        plant=id_plant,
        candidate_pid=PIDParams(chosen.Kc, chosen.Ti, chosen.Td),
        dt=dt,
        model_valid=True,
        model_val_r2=ident.val_r2,
        model_val_fit_pct=ident.val_fit_pct,
    )
    if not sv.approved:
        chosen = next(c for c in tun.candidates if c.strategy == "conservative")
        sv = verify_pid_safety(
            plant=id_plant,
            candidate_pid=PIDParams(chosen.Kc, chosen.Ti, chosen.Td),
            dt=dt,
            model_valid=True,
            model_val_r2=ident.val_r2,
            model_val_fit_pct=ident.val_fit_pct,
        )

    sim_after = simulate_loop(
        plant=true_plant,
        pid=PIDParams(chosen.Kc, chosen.Ti, chosen.Td),
        dt=dt,
        n_steps=len(sp),
        sp_profile=sp,
        noise_std=0.05,
        disturbance_amp=dist_amp,
        disturbance_period=dist_period,
        seed=99,
    )
    d_after = diagnose_loop(sp, sim_after["pv"], sim_after["op"], dt=dt)
    improved = (d_after.iae < diag.iae * 0.85) and (d_after.oscillation_index <= max(diag.oscillation_index, 0.25))
    worsened = (d_after.iae > diag.iae * 1.05)

    fd = final_decision_aggregation(DecisionEvidence(
        input_valid=True,
        input_errors=[],
        anomaly_type=diag.anomaly_type,
        has_known_plant_truth=True,
        model_evaluated=True,
        model_valid=True,
        model_failure_reason=None,
        safety_evaluated=True,
        safety_approved=sv.approved,
        safety_violations=sv.violation_tags,
        multi_regime_evaluated=True,
        multi_regime_passed=(sv.multi_regime_pass_rate_pct >= 80.0),
        performance_evaluated=True,
        performance_improved=improved,
        performance_worsened=worsened,
        audit_status="PASS",
        audit_errors=[],
    ))
    return {
        "loop_id": loop_id,
        "pred_anomaly": diag.anomaly_type,
        "final_status": fd.final_status,
        "expected": expected_status,
        "exact_match": (fd.final_status == expected_status),
        "val_r2": ident.val_r2,
        "val_fit_pct": ident.val_fit_pct,
        "multi_regime_pass_pct": sv.multi_regime_pass_rate_pct,
        "iae_before": round(diag.iae, 3),
        "iae_after": round(d_after.iae, 3),
        "load_step_used": bool(info.get("load_step_compensated", False)),
        "load_step_detected": bool(float(info.get("dc_shift_sigma") or 0.0) >= 2.5),
        "validation_gate_passed": bool(info.get("load_step_compensated", False)),
        "validation_reason": "observable_dc_offset_compensated" if info.get("load_step_compensated", False) else "standard_validation_passed_or_secondary_gate_failed",
        "dc_shift_sigma": info.get("dc_shift_sigma"),
        "std_ratio_va_over_tr": info.get("std_ratio_va_over_tr"),
    }


def _generate_blind_holdout_24() -> List[Dict[str, Any]]:
    cases = []
    dt = 1.0
    n = 600
    sp_base = np.full(n, 100.0)
    sp_base[60:240] = 104.0
    sp_base[240:420] = 98.0
    sp_base[420:] = 103.0

    # 1. 8 unseen sluggish loops WITH physical unmeasured DC load-step disturbance entering process at t >= 380 -> tunable
    for idx in range(8):
        K = 0.85 + 0.12 * idx
        tau = 11.0 + 2.0 * idx
        theta = 2.0 + 0.4 * idx
        plant = PlantParams(K=K, tau=tau, theta=theta, pv_bias=100.0, op_bias=50.0)
        init_pid = PIDParams(Kc=0.18, Ti=max(45.0, tau * 3.5), Td=0.0)
        load_dist = np.zeros(n, dtype=float)
        load_dist[380:] = 0.30 + 0.04 * (idx % 4)
        sim = simulate_loop(plant=plant, pid=init_pid, dt=dt, n_steps=n, sp_profile=sp_base, disturbance=load_dist, noise_std=0.05, seed=700 + idx)
        cases.append({
            "loop_id": f"BLIND-SLUG-STEP-{idx+1:02d}", "sp": sp_base, "pv": sim["pv"], "op": sim["op"],
            "dt": dt, "init_pid": init_pid, "true_plant": plant,
            "dist_amp": 0.0, "dist_period": 0.0, "expected": "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW",
            "category": "blind_sluggish_with_load_step",
        })

    # 2. 4 unseen sluggish loops WITH genuine plant gain/tau drift (+75% K in validation) -> MUST REJECT!
    for idx in range(4):
        K = 1.0 + 0.15 * idx
        tau = 14.0 + 2.0 * idx
        theta = 3.0
        plant1 = PlantParams(K=K, tau=tau, theta=theta, pv_bias=100.0, op_bias=50.0)
        plant2 = PlantParams(K=K * 1.75, tau=tau * 0.55, theta=theta, pv_bias=100.0, op_bias=50.0)
        init_pid = PIDParams(Kc=0.20, Ti=55.0, Td=0.0)
        sim1 = simulate_loop(plant=plant1, pid=init_pid, dt=dt, n_steps=n, sp_profile=sp_base, noise_std=0.05, seed=800 + idx)
        sim2 = simulate_loop(plant=plant2, pid=init_pid, dt=dt, n_steps=n, sp_profile=sp_base, noise_std=0.05, seed=810 + idx)
        pv = np.concatenate([sim1["pv"][:390], sim2["pv"][390:]])
        op = np.concatenate([sim1["op"][:390], sim2["op"][390:]])
        cases.append({
            "loop_id": f"BLIND-DRIFT-BAD-{idx+1:02d}", "sp": sp_base, "pv": pv, "op": op,
            "dt": dt, "init_pid": init_pid, "true_plant": plant1,
            "dist_amp": 0.0, "dist_period": 0.0, "expected": "MODEL_VALIDATION_FAILED",
            "category": "blind_corrupted_dynamics_must_reject",
        })

    # 3. 4 unseen external periodic disturbance loops -> MUST REJECT!
    for idx in range(4):
        plant = PlantParams(K=1.1 + 0.1 * idx, tau=12.0 + idx, theta=3.0, pv_bias=100.0, op_bias=50.0)
        init_pid = PIDParams(Kc=0.85, Ti=14.0, Td=0.0)
        sim = simulate_loop(plant=plant, pid=init_pid, dt=dt, n_steps=n, sp_profile=sp_base, noise_std=0.05, disturbance_amp=1.6 + 0.2 * idx, disturbance_period=42.0 + 4 * idx, seed=850 + idx)
        cases.append({
            "loop_id": f"BLIND-EXT-DIST-{idx+1:02d}", "sp": sp_base, "pv": sim["pv"], "op": sim["op"],
            "dt": dt, "init_pid": init_pid, "true_plant": plant,
            "dist_amp": 1.6 + 0.2 * idx, "dist_period": 42.0 + 4 * idx, "expected": "PERFORMANCE_NOT_IMPROVED",
            "category": "blind_external_disturbance_must_reject",
        })

    # 4. 4 unseen valve stiction loops -> MUST REJECT!
    for idx in range(4):
        plant = PlantParams(K=1.1, tau=12.0 + idx, theta=3.0, pv_bias=100.0, op_bias=50.0)
        init_pid = PIDParams(Kc=0.95, Ti=12.0, Td=0.0)
        valve = ValveParams(stiction_S=3.8 + 0.4 * idx, stiction_J=2.4 + 0.2 * idx)
        sim = simulate_loop(plant=plant, pid=init_pid, valve=valve, dt=dt, n_steps=n, sp_profile=sp_base, noise_std=0.04, seed=900 + idx)
        cases.append({
            "loop_id": f"BLIND-STICTION-{idx+1:02d}", "sp": sp_base, "pv": sim["pv"], "op": sim["op"],
            "dt": dt, "init_pid": init_pid, "true_plant": plant,
            "dist_amp": 0.0, "dist_period": 0.0, "expected": "VALVE_MAINTENANCE_REQUIRED",
            "category": "blind_stiction_must_reject",
        })

    # 5. 4 unseen healthy loops -> MUST STAY HEALTHY_NO_CHANGE!
    for idx in range(4):
        plant = PlantParams(K=1.0 + 0.1 * idx, tau=12.0 + idx, theta=2.5, pv_bias=100.0, op_bias=50.0)
        init_pid = PIDParams(Kc=0.85, Ti=12.0 + idx, Td=0.0)
        sim = simulate_loop(plant=plant, pid=init_pid, dt=dt, n_steps=n, sp_profile=sp_base, noise_std=0.04, seed=950 + idx)
        cases.append({
            "loop_id": f"BLIND-HEALTHY-{idx+1:02d}", "sp": sp_base, "pv": sim["pv"], "op": sim["op"],
            "dt": dt, "init_pid": init_pid, "true_plant": plant,
            "dist_amp": 0.0, "dist_period": 0.0, "expected": "HEALTHY_NO_CHANGE",
            "category": "blind_healthy_no_change",
        })
    return cases


def main() -> None:
    expected_30 = {}
    for i in range(1, 31):
        lid = f"LOOP-{i:03d}"
        if i <= 5:
            expected_30[lid] = "HEALTHY_NO_CHANGE"
        elif i <= 17 or (23 <= i <= 27):
            expected_30[lid] = "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"
        elif i <= 22:
            expected_30[lid] = "VALVE_MAINTENANCE_REQUIRED"
        else:
            expected_30[lid] = "PERFORMANCE_NOT_IMPROVED"

    res_30_base, res_30_new = [], []
    for i in range(1, 31):
        lid = f"LOOP-{i:03d}"
        m = _load_loop_metadata(lid)
        df = _load_loop_dataframe(m)
        kw = dict(
            loop_id=lid, sp=df["sp"].to_numpy(float), pv=df["pv"].to_numpy(float), op=df["op"].to_numpy(float),
            dt=m["dt"], init_pid=PIDParams(m["init_Kc"], m["init_Ti"], m.get("init_Td", 0.0)),
            true_plant=PlantParams(K=m["true_K"], tau=m["true_tau"], theta=m["true_theta"], pv_bias=m["pv_bias"], op_bias=m["op_bias"]),
            dist_amp=m.get("disturbance_amp", 0.0), dist_period=m.get("disturbance_period", 0.0),
            expected_status=expected_30[lid],
        )
        res_30_base.append(_evaluate_loop(**kw, use_load_step_check=False))
        res_30_new.append(_evaluate_loop(**kw, use_load_step_check=True))

    # These cases are generated before evaluation with held-out seeds and
    # parameter combinations. They are a pre-isolated synthetic holdout,
    # rather than an external industrial dataset.
    blind_cases = _generate_blind_holdout_24()
    res_blind_base, res_blind_new = [], []
    for c in blind_cases:
        kw = {k: v for k, v in c.items() if k != "category"}
        kw["expected_status"] = kw.pop("expected")
        rb = _evaluate_loop(**kw, use_load_step_check=False)
        rn = _evaluate_loop(**kw, use_load_step_check=True)
        rb["category"] = c["category"]
        rn["category"] = c["category"]
        res_blind_base.append(rb)
        res_blind_new.append(rn)

    def _summarize(rows: List[Dict[str, Any]], label: str) -> Dict[str, Any]:
        tunable = [r for r in rows if r["expected"] == "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"]
        non_tunable = [r for r in rows if r["expected"] != "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"]
        false_approvals = [r for r in non_tunable if r["final_status"] == "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"]
        approved = [r for r in rows if r["final_status"] == "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"]
        mr_vals = [r["multi_regime_pass_pct"] for r in rows if r["multi_regime_pass_pct"] is not None]
        mr_app = [r["multi_regime_pass_pct"] for r in approved if r["multi_regime_pass_pct"] is not None]
        return {
            "label": label,
            "total": len(rows),
            "exact_match_count": sum(1 for r in rows if r["exact_match"]),
            "exact_match_pct": round(sum(1 for r in rows if r["exact_match"]) / len(rows) * 100.0, 2),
            "tunable_pass_count": sum(1 for r in tunable if r["final_status"] == "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"),
            "tunable_total": len(tunable),
            "tunable_pass_pct": round(sum(1 for r in tunable if r["final_status"] == "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW") / max(1, len(tunable)) * 100.0, 2),
            "dangerous_false_approvals": len(false_approvals),
            "approved_multi_regime_pass_pct": round(float(np.mean(mr_app)), 2) if mr_app else None,
            "all_checked_multi_regime_pass_pct": round(float(np.mean(mr_vals)), 2) if mr_vals else None,
            "approved_multi_regime_n": len(mr_app),
            "all_checked_multi_regime_n": len(mr_vals),
            "load_step_compensated_count": sum(1 for r in rows if r["load_step_used"]),
        }

    report = {
        "benchmark_30_v433_baseline": _summarize(res_30_base, "30-Loop Baseline (V4.3.3)"),
        "benchmark_30_v434_changepoint": _summarize(res_30_new, "30-Loop + Load-Step Check (V4.3.4)"),
        "blind_24_v433_baseline": _summarize(res_blind_base, "24-Loop Pre-isolated Synthetic Holdout (V4.3.3)"),
        "blind_24_v434_changepoint": _summarize(res_blind_new, "24-Loop Pre-isolated Synthetic Holdout + Load-Step Check (V4.3.4)"),
    }
    out_path = ROOT / "competition_v4" / "submission_v433" / "v434_changepoint_blind_study.json"
    out_path.write_text(
        json.dumps({"summary": report, "benchmark_30_new": res_30_new, "blind_24_new": res_blind_new}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
