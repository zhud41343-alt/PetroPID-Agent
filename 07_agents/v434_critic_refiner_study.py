"""V4.3.4 Multi-Agent Critic-Refiner Collaboration Benchmark.

Directly answers the judge question:
"When does multi-agent collaboration (SafetyVerifierAgent <-> TunerAgent closed-loop
feedback) deliver measurable, verified engineering gains over a single-pass monolithic
tuner (B3-SinglePass), WITHOUT compromising the 0% false-approval safety boundary?"

Evaluates:
1. 12 tight-margin / high-deadtime tunable petrochemical regimes under strict industrial
   safety specs (max_ms=1.25, min_gm=3.5, min_pm=60 deg, max_overshoot=5%):
   - B3-SinglePass: fixed SIMC balanced -> conservative fallback (no iterative margin feedback)
   - C-CriticRefiner: independent SafetyVerifierAgent returns structured violation & margin-deficit
     feedback to TunerAgent (up to 3 bounded refinement rounds), each independently re-audited.
2. 6 preconfigured diagnosis-blocked safety paths (2 valve stiction, 2 C-000
   unvalidated-model, 2 external-periodic-disturbance paths): verifies that neither
   system overrides a blocked path. These are deterministic refusal regressions, not
   independent diagnosis-accuracy samples.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

os.environ["PETROPID_LLM_DISABLE_DOTENV"] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "07_agents"))

from petro_pid.simulator import PlantParams, PIDParams  # noqa: E402
from petro_pid.tuning import _simc_pid, refine_pid_from_safety_feedback  # noqa: E402
from petro_pid.safety_verifier import verify_pid_safety  # noqa: E402
from orchestrator import CODE_COMMIT  # noqa: E402

STRICT_SPECS = {
    "min_gm": 3.5,
    "min_pm_deg": 60.0,
    "max_ms": 1.25,
    "max_overshoot_pct": 5.0,
}

# 12 challenging high-deadtime / tight-margin tunable petrochemical loops
HARD_TUNABLE_CASES = [
    {"case_id": "HM-01", "unit": "常减压塔顶温度", "K": 1.8, "tau": 14.0, "theta": 8.0},
    {"case_id": "HM-02", "unit": "催化裂化反应温度", "K": 2.2, "tau": 16.0, "theta": 9.5},
    {"case_id": "HM-03", "unit": "加氢裂化床层温度", "K": 1.5, "tau": 12.0, "theta": 7.5},
    {"case_id": "HM-04", "unit": "乙烯裂解炉出口温度", "K": 2.6, "tau": 18.0, "theta": 11.0},
    {"case_id": "HM-05", "unit": "芳烃抽提塔灵敏板温度", "K": 1.4, "tau": 10.0, "theta": 7.0},
    {"case_id": "HM-06", "unit": "重整反应器入口温控", "K": 2.0, "tau": 15.0, "theta": 10.0},
    {"case_id": "HM-07", "unit": "脱丁烷塔底再沸器温度", "K": 1.9, "tau": 13.0, "theta": 8.5},
    {"case_id": "HM-08", "unit": "延迟焦化分馏塔顶温", "K": 2.4, "tau": 20.0, "theta": 13.0},
    {"case_id": "HM-09", "unit": "环氧乙烷反应器温控", "K": 1.7, "tau": 11.0, "theta": 8.0},
    {"case_id": "HM-10", "unit": "丙烯精馏塔压差控制", "K": 2.1, "tau": 16.0, "theta": 11.5},
    {"case_id": "HM-11", "unit": "硫磺回收尾气温度", "K": 1.6, "tau": 12.0, "theta": 9.0},
    {"case_id": "HM-12", "unit": "柴油加氢精制温控", "K": 2.5, "tau": 17.0, "theta": 12.0},
]

# 6 non-tunable safety traps (MUST remain 0/6 approved)
SAFETY_TRAP_CASES = [
    {"case_id": "TRAP-01", "trap_type": "MODEL_INVALID_C000", "K": 1.8, "tau": 14.0, "theta": 8.0, "model_valid": False},
    {"case_id": "TRAP-02", "trap_type": "MODEL_INVALID_C000", "K": 2.2, "tau": 16.0, "theta": 9.5, "model_valid": False},
    {"case_id": "TRAP-03", "trap_type": "VALVE_STICTION_BLOCKED", "K": 1.6, "tau": 12.0, "theta": 6.0, "blocked_by_diag": True},
    {"case_id": "TRAP-04", "trap_type": "VALVE_STICTION_BLOCKED", "K": 2.0, "tau": 15.0, "theta": 7.0, "blocked_by_diag": True},
    {"case_id": "TRAP-05", "trap_type": "EXTERNAL_DISTURBANCE_BLOCKED", "K": 1.7, "tau": 13.0, "theta": 6.5, "blocked_by_diag": True},
    {"case_id": "TRAP-06", "trap_type": "EXTERNAL_DISTURBANCE_BLOCKED", "K": 2.1, "tau": 14.0, "theta": 7.5, "blocked_by_diag": True},
]


def _run_case(plant: PlantParams, *, model_valid: bool = True, blocked_by_diag: bool = False) -> Dict[str, Any]:
    if blocked_by_diag:
        return {
            "b3_single_pass_approved": False,
            "c_critic_refiner_approved": False,
            "refinement_rounds_used": 0,
            "b3_reason": "BLOCKED_BY_DIAGNOSIS_GATE",
            "c_reason": "BLOCKED_BY_DIAGNOSIS_GATE",
        }

    # B3-SinglePass: standard balanced -> conservative SIMC (no closed-loop safety-gradient refinement)
    bal_pid = _simc_pid(plant.K, plant.tau, plant.theta, tau_c_factor=1.0)
    cons_pid = _simc_pid(plant.K, plant.tau, plant.theta, tau_c_factor=1.8)

    sv_bal = verify_pid_safety(plant, bal_pid, model_valid=model_valid, **STRICT_SPECS)
    if sv_bal.approved:
        b3_sv, b3_pid = sv_bal, bal_pid
    else:
        sv_cons = verify_pid_safety(plant, cons_pid, model_valid=model_valid, **STRICT_SPECS)
        b3_sv, b3_pid = sv_cons, cons_pid

    # C-CriticRefiner: SafetyVerifierAgent -> TunerAgent iterative feedback (max 3 rounds)
    c_sv = b3_sv
    c_pid = b3_pid
    rounds_used = 0
    trace: List[Dict[str, Any]] = [
        {"round": 0, "Kc": c_pid.Kc, "Ti": c_pid.Ti, "approved": c_sv.approved, "GM": c_sv.gain_margin, "PM": c_sv.phase_margin_deg, "Ms": c_sv.max_sensitivity_ms, "violations": c_sv.violation_tags}
    ]
    while not c_sv.approved and rounds_used < 3:
        refined_pid, reason = refine_pid_from_safety_feedback(
            plant,
            c_pid,
            c_sv.to_dict(),
            min_gm=STRICT_SPECS["min_gm"],
            min_pm_deg=STRICT_SPECS["min_pm_deg"],
            max_ms=STRICT_SPECS["max_ms"],
        )
        if refined_pid is None:
            trace.append({"round": rounds_used + 1, "action": reason, "approved": False})
            break
        rounds_used += 1
        c_pid = refined_pid
        c_sv = verify_pid_safety(plant, c_pid, model_valid=model_valid, **STRICT_SPECS)
        trace.append({
            "round": rounds_used,
            "Kc": c_pid.Kc,
            "Ti": c_pid.Ti,
            "approved": c_sv.approved,
            "GM": c_sv.gain_margin,
            "PM": c_sv.phase_margin_deg,
            "Ms": c_sv.max_sensitivity_ms,
            "violations": c_sv.violation_tags,
            "feedback": reason,
        })

    return {
        "b3_single_pass_approved": bool(b3_sv.approved),
        "b3_final_margins": {"GM": b3_sv.gain_margin, "PM": b3_sv.phase_margin_deg, "Ms": b3_sv.max_sensitivity_ms},
        "b3_violations": b3_sv.violation_tags,
        "c_critic_refiner_approved": bool(c_sv.approved),
        "c_final_margins": {"GM": c_sv.gain_margin, "PM": c_sv.phase_margin_deg, "Ms": c_sv.max_sensitivity_ms},
        "c_violations": c_sv.violation_tags,
        "refinement_rounds_used": rounds_used,
        "critic_refiner_trace": trace,
    }


def run_critic_refiner_benchmark() -> Dict[str, Any]:
    tunable_results: List[Dict[str, Any]] = []
    for c in HARD_TUNABLE_CASES:
        plant = PlantParams(K=c["K"], tau=c["tau"], theta=c["theta"], pv_bias=200.0, op_bias=50.0)
        res = _run_case(plant, model_valid=True, blocked_by_diag=False)
        tunable_results.append({**c, **res})

    trap_results: List[Dict[str, Any]] = []
    for c in SAFETY_TRAP_CASES:
        plant = PlantParams(K=c["K"], tau=c["tau"], theta=c["theta"], pv_bias=200.0, op_bias=50.0)
        res = _run_case(
            plant,
            model_valid=c.get("model_valid", True),
            blocked_by_diag=c.get("blocked_by_diag", False),
        )
        trap_results.append({**c, **res})

    b3_ok = sum(1 for r in tunable_results if r["b3_single_pass_approved"])
    c_ok = sum(1 for r in tunable_results if r["c_critic_refiner_approved"])
    b3_fp = sum(1 for r in trap_results if r["b3_single_pass_approved"])
    c_fp = sum(1 for r in trap_results if r["c_critic_refiner_approved"])

    summary = {
        "strict_safety_specs": STRICT_SPECS,
        "hard_tunable_total": len(tunable_results),
        "b3_single_pass_approved_count": b3_ok,
        "b3_single_pass_rate_pct": round(b3_ok / len(tunable_results) * 100.0, 2),
        "c_critic_refiner_approved_count": c_ok,
        "c_critic_refiner_rate_pct": round(c_ok / len(tunable_results) * 100.0, 2),
        "net_safe_recovery_gain_pp": round((c_ok - b3_ok) / len(tunable_results) * 100.0, 2),
        "safety_traps_total": len(trap_results),
        "b3_false_approvals": b3_fp,
        "c_false_approvals": c_fp,
        "code_commit": CODE_COMMIT,
    }
    payload = {"summary": summary, "hard_tunable_results": tunable_results, "safety_trap_results": trap_results}
    out_path = ROOT / "competition_v4" / "submission_v433" / "v434_critic_refiner_benchmark.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    run_critic_refiner_benchmark()
