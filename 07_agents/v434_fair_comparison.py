"""V4.3.4 Phase 2: Fair Paired Comparison — B3 Strong Monolithic (with Equal Conservative Fallback) vs C (5-Stage Blackboard).

Directly addresses the judge question:
"In V4.3.3 ablation, C scored 24/24 vs B2 23/24 only because B2 lacked conservative fallback
on tightened Ms=1.50. What happens when a Strong Monolithic baseline (B3) gets the EXACT SAME
tools, candidate order, 11 hard constraints, conservative fallback, retry, cache, and
verify_audit_record() audit?"

Saves raw per-trial paired JSON to `competition_v4/submission_v433/b3_vs_c_paired_trials.json`
and summary metrics to stdout.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

os.environ["PETROPID_LLM_DISABLE_DOTENV"] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "05_skills"))
sys.path.insert(0, str(ROOT / "07_agents"))

from petro_pid import PIDParams  # noqa: E402
from skill_runner import _load_loop_dataframe, _load_loop_metadata  # noqa: E402
from decision_engine import compute_canonical_input_hash, verify_audit_record  # noqa: E402
from orchestrator import CODE_COMMIT, PetroPIDOrchestrator  # noqa: E402
from v43_studies import FaultInjectedToolbox, run_system_c_petropid_swarm  # noqa: E402
from v433_ablation import INDEPENDENT_EXPECTED, build_equivalent_audit_record  # noqa: E402

LOOPS = ["LOOP-001", "LOOP-006", "LOOP-012", "LOOP-021", "LOOP-025", "LOOP-029"]
SCENARIOS = [
    ("normal", False, False, 2.2),
    ("first_call_timeout", True, False, 2.2),
    ("duplicate_call", False, True, 2.2),
    ("tightened_ms_1.65_fallback", False, False, 1.65),
]


def _check_stage_localizability(trace: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Audit whether the trace isolates distinct stage owners & enables stage-level failure localization."""
    agents = {str(t.get("agent", "")) for t in trace}
    has_distinct_owners = len(agents) >= 2 or (len(trace) == 1 and len(agents) == 1)
    has_structured_stage_field = all(bool(t.get("stage")) for t in trace) if trace else False
    # True stage isolation requires separate agent/role ownership across diagnosis/ident/tuning/safety/decision
    independent_safety_owner = any("Safety" in a or "Decision" in a for a in agents) and any("Diag" in a for a in agents)
    return {
        "distinct_role_count": len(agents),
        "has_stage_field_all_steps": has_structured_stage_field,
        "independent_safety_decision_separation": independent_safety_owner,
        "trace_step_count": len(trace),
    }


def run_b3_strong_monolithic(
    loop_id: str,
    *,
    fail_first_diag: bool,
    duplicate_diag: bool,
    max_ms: float,
    experiment_id: str,
    scenario: str,
) -> Dict[str, Any]:
    """B3 Strong Monolithic: shares IDENTICAL tools, candidate order (balanced -> conservative),
    11 hard constraints, retry, SHA-256 cache, compact context, and verify_audit_record() with C."""
    t0 = time.perf_counter()
    meta = _load_loop_metadata(loop_id)
    df = _load_loop_dataframe(meta)
    t_arr = df["timestamp_s"].to_numpy(float) if "timestamp_s" in df.columns else np.arange(len(df), dtype=float) * meta["dt"]
    sp, pv, op = df["sp"].to_numpy(float), df["pv"].to_numpy(float), df["op"].to_numpy(float)
    tb = FaultInjectedToolbox(fail_first_diag=fail_first_diag)
    cache: Dict[str, Any] = {}
    dup_prevented = 0
    retry_count = 0
    recovered = False
    fallback_triggered = False
    trace: List[Dict[str, Any]] = []
    ctx_obj: Dict[str, Any] = {"loop_id": loop_id, "steps": []}

    def _call_diag():
        nonlocal dup_prevented, retry_count, recovered
        key = hashlib.sha256(f"diag:{loop_id}".encode()).hexdigest()
        if key in cache:
            dup_prevented += 1
            return cache[key]
        try:
            res = tb.diagnose(meta, sp, pv, op)
        except TimeoutError:
            retry_count += 1
            res = tb.diagnose(meta, sp, pv, op)
            recovered = True
        cache[key] = res
        return res

    init_pid = {"Kc": meta["init_Kc"], "Ti": meta["init_Ti"], "Td": meta.get("init_Td", 0.0)}
    in_hash = compute_canonical_input_hash(
        loop_id=loop_id, t=t_arr, sp=sp, pv=pv, op=op, init_pid=init_pid,
        safety_config={"max_overshoot_pct": 18.0, "max_ms": max_ms, "min_gm": 1.8, "min_pm_deg": 35.0, "validation_profile": "v4.3.3"},
        preferred_strategy=None, data_source_type="SIMULATOR_BENCHMARK_30LOOPS",
        plant_context={"dt": meta["dt"], "true_K": meta["true_K"], "true_tau": meta["true_tau"], "true_theta": meta["true_theta"], "disturbance_amp": meta.get("disturbance_amp", 0.0)},
    )

    diag = _call_diag()
    ctx_obj["steps"].append({"tool": "diagnose", "anomaly": diag["anomaly_type"], "oi": diag["oscillation_index"]})
    if duplicate_diag:
        _call_diag()

    ident, tun, sv = None, None, None
    final_pid = dict(init_pid)
    if diag["anomaly_type"] == "NORMAL":
        status = "HEALTHY_NO_CHANGE"
    elif diag["anomaly_type"] == "VALVE_STICTION":
        status = "VALVE_MAINTENANCE_REQUIRED"
    else:
        ident = tb.identify(meta, pv, op)
        ctx_obj["steps"].append({"tool": "identify", "valid": ident["allow_next_stage"], "fit": ident["val_fit_pct"]})
        if not ident["allow_next_stage"]:
            status = "MODEL_VALIDATION_FAILED"
        else:
            tun = tb.tune(ident, meta)
            # IDENTICAL candidate order & conservative fallback as System C!
            bal = next(c for c in tun["candidates"] if c["strategy"] == "balanced")
            cons = next(c for c in tun["candidates"] if c["strategy"] == "conservative")
            sv = tb.verify(ident, PIDParams(bal["Kc"], bal["Ti"], bal["Td"]), meta, max_ms=max_ms)
            chosen = bal
            if not sv["approved"]:
                fallback_triggered = True
                sv = tb.verify(ident, PIDParams(cons["Kc"], cons["Ti"], cons["Td"]), meta, max_ms=max_ms)
                chosen = cons
            ctx_obj["steps"].append({"tool": "tune_verify_fallback", "strategy": chosen["strategy"], "approved": sv["approved"]})
            if diag["anomaly_type"] == "EXTERNAL_DISTURBANCE":
                status = "PERFORMANCE_NOT_IMPROVED"
            elif sv["approved"]:
                status = "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"
                final_pid = {"Kc": chosen["Kc"], "Ti": chosen["Ti"], "Td": chosen["Td"]}
            else:
                status = "SAFETY_REJECTED"

    # Monolithic single-owner trace (single coordinator role owns all actions)
    trace.append({
        "step": 1,
        "agent": "B3_StrongMonolithic",
        "skill": "monolithic_end_to_end_with_fallback",
        "status": "DONE" if status in ("HEALTHY_NO_CHANGE", "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW") else "REJECTED",
        "summary": f"status={status}, fallback={fallback_triggered}",
    })

    full_rec = build_equivalent_audit_record(
        meta=meta, t=t_arr, sp=sp, pv=pv, op=op, max_ms=max_ms,
        diag=diag, ident=ident, tuning=tun, safety=sv,
        final_pid=final_pid, trace=trace, status_override=status,
    )
    chk = verify_audit_record(full_rec)
    loc = _check_stage_localizability(trace)
    handoff_bytes = len(json.dumps(ctx_obj, ensure_ascii=False).encode("utf-8"))
    return {
        "experiment_id": experiment_id,
        "run_id": full_rec["audit_meta"]["run_id"],
        "system": "B3_strong_monolithic_with_fallback",
        "loop_id": loop_id,
        "scenario": scenario,
        "input_hash": in_hash,
        "paired_input_hash": in_hash,
        "final_status": full_rec["final_status"],
        "independent_expected_status": INDEPENDENT_EXPECTED[loop_id],
        "decision_correct": (full_rec["final_status"] == INDEPENDENT_EXPECTED[loop_id]),
        "fallback_triggered": fallback_triggered,
        "tool_call_count": tb.actual_tool_executions,
        "duplicate_prevented": dup_prevented,
        "retry_count": retry_count,
        "recovered_fault": recovered,
        "audit_verified": (chk["audit_status"] == "PASS"),
        "handoff_bytes": handoff_bytes,
        "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        "stage_localization": loc,
        "code_commit": CODE_COMMIT,
    }


def run_paired_comparison() -> Dict[str, Any]:
    orch = PetroPIDOrchestrator()
    b3_trials: List[Dict[str, Any]] = []
    c_trials: List[Dict[str, Any]] = []

    for sc_name, fail_first, dup_call, max_ms in SCENARIOS:
        for lid in LOOPS:
            exp_id = f"PAIR-{sc_name}-{lid}"
            b3 = run_b3_strong_monolithic(
                lid, fail_first_diag=fail_first, duplicate_diag=dup_call,
                max_ms=max_ms, experiment_id=exp_id, scenario=sc_name,
            )
            b3_trials.append(b3)

            c_raw = run_system_c_petropid_swarm(
                orch, lid, fail_first_diag=fail_first, duplicate_diag=dup_call, max_ms=max_ms,
            )
            # Use the actual trace emitted by the orchestrator. Do not infer
            # stage ownership from the loop ID or expected outcome.
            c_trace = c_raw.get("trace", [])
            c_trace_loc = _check_stage_localizability(c_trace)
            c_trials.append({
                "experiment_id": exp_id,
                "run_id": c_raw.get("run_id", f"RUN-C-{uuid.uuid4().hex[:8]}"),
                "system": "C_petropid_5agent_blackboard",
                "loop_id": lid,
                "scenario": sc_name,
                "input_hash": c_raw.get("input_hash"),
                "paired_input_hash": b3["input_hash"],
                "final_status": c_raw["final_status"],
                "independent_expected_status": INDEPENDENT_EXPECTED[lid],
                "decision_correct": (c_raw["final_status"] == INDEPENDENT_EXPECTED[lid]),
                "fallback_triggered": any(bool(step.get("fallback_triggered")) for step in c_trace),
                "tool_call_count": c_raw["actual_tool_executions"],
                "duplicate_prevented": c_raw["duplicate_calls_prevented"],
                "retry_count": 1 if c_raw["recovered_fault"] else 0,
                "recovered_fault": c_raw["recovered_fault"],
                "audit_verified": c_raw["audit_verified"],
                "handoff_bytes": c_raw["handoff_bytes"],
                "latency_ms": c_raw["latency_ms"],
                "stage_localization": c_trace_loc,
                "trace": c_trace,
                "code_commit": CODE_COMMIT,
            })

    def _agg(trials: List[Dict[str, Any]]) -> Dict[str, Any]:
        lats = [t["latency_ms"] for t in trials]
        fault_trials = [t for t in trials if t["scenario"] == "first_call_timeout"]
        return {
            "total_trials": len(trials),
            "decision_correct_count": sum(1 for t in trials if t["decision_correct"]),
            "decision_correct_rate_pct": round(sum(1 for t in trials if t["decision_correct"]) / len(trials) * 100.0, 2),
            "fault_recovery_rate_pct": round(sum(1 for t in fault_trials if t["recovered_fault"]) / max(1, len(fault_trials)) * 100.0, 2),
            "duplicate_prevented_total": sum(t["duplicate_prevented"] for t in trials),
            "total_tool_calls": sum(t["tool_call_count"] for t in trials),
            "audit_verified_rate_pct": round(sum(1 for t in trials if t["audit_verified"]) / len(trials) * 100.0, 2),
            "paired_input_hash_match_rate_pct": round(sum(1 for t in trials if t.get("input_hash") == t.get("paired_input_hash")) / len(trials) * 100.0, 2),
            "independent_stage_separation_rate_pct": round(
                sum(1 for t in trials if t["stage_localization"]["independent_safety_decision_separation"]) / len(trials) * 100.0, 2
            ),
            "mean_handoff_bytes": round(float(np.mean([t["handoff_bytes"] for t in trials])), 1),
            "latency_ms_p50": round(float(np.percentile(lats, 50)), 2),
            "latency_ms_p95": round(float(np.percentile(lats, 95)), 2),
        }

    summary = {
        "B3_strong_monolithic_with_fallback": _agg(b3_trials),
        "C_petropid_5agent_blackboard": _agg(c_trials),
        "head_to_head_decision_tie": (_agg(b3_trials)["decision_correct_count"] == _agg(c_trials)["decision_correct_count"]),
    }
    out_path = ROOT / "competition_v4" / "submission_v433" / "b3_vs_c_paired_trials.json"
    out_path.write_text(
        json.dumps({"summary": summary, "b3_trials": b3_trials, "c_trials": c_trials}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    run_paired_comparison()
