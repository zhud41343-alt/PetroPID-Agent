"""5-Agent Adaptive Collaboration Orchestrator (V3.0 Audited & Safety-Gated Edition).

P0 Safety & Scientific Fixes in V3.0:
1. ZERO Ground-Truth Leakage: Never falls back to `meta["true_K"]` when identification fails.
2. Strict Model Validity Gate: Unreliable FOPDT models (val_r2 < 0.80 or fit < 85%) are
   explicitly rejected with `MODEL_VALIDATION_FAILED` (C-000 failed in SafetyVerificationAgent).
3. Deterministic Performance Improvement Gate: If candidate PID worsens or fails to improve
   comparable IAE/OI (e.g., EXTERNAL_DISTURBANCE loops LOOP-028..030), returns
   `PERFORMANCE_NOT_IMPROVED` with disturbance-source / feedforward recommendation.
4. Explicit Valve Maintenance Gate: VALVE_STICTION returns `VALVE_MAINTENANCE_REQUIRED`
   instead of approving DCS deployment.
5. Unified 7-State Machine-Readable Status System (never claims real DCS deployment approval!):
   - HEALTHY_NO_CHANGE
   - MODEL_VALIDATION_FAILED
   - SAFETY_CONSTRAINT_FAILED
   - PERFORMANCE_NOT_IMPROVED
   - VALVE_MAINTENANCE_REQUIRED
   - SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW
   - REJECTED_WITH_REASON
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "05_skills"))
sys.path.insert(0, str(ROOT / "07_agents"))

from petro_pid import (
    PlantParams,
    PIDParams,
    ValveParams,
    simulate_loop,
    diagnose_loop,
    identify_fopdt,
    tune_pid,
    verify_pid_safety,
)
from petro_pid.identification import simulate_fopdt_open_loop
from petro_pid.tuning import _simc_pid
from skill_runner import SkillRunner, _load_loop_metadata, _load_loop_dataframe
from llm_gateway import LLMGateway
from decision_engine import (
    DATASET_VERSION,
    ALGORITHM_VERSION,
    FINAL_STATUS_SPECS,
    DecisionEvidence,
    compute_canonical_hash,
    final_decision_aggregation,
)

VALID_STATUSES = set(FINAL_STATUS_SPECS.keys())


def _get_git_commit() -> str:
    try:
        import subprocess
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT), text=True, stderr=subprocess.DEVNULL
        ).strip()
        return out or "unknown"
    except Exception:
        return "unknown"


CODE_COMMIT = _get_git_commit()


def validate_input_series(
    t: np.ndarray, sp: np.ndarray, pv: np.ndarray, op: np.ndarray
) -> List[str]:
    """Strict input data validator: catches empty, NaN/Inf, length bounds, and unsorted timestamps."""
    errs: List[str] = []
    if len(t) == 0 or len(sp) == 0 or len(pv) == 0 or len(op) == 0:
        return ["INPUT_EMPTY_SERIES"]
    if not (len(t) == len(sp) == len(pv) == len(op)):
        errs.append("INPUT_LENGTH_MISMATCH")
    if len(pv) < 100:
        errs.append(f"INPUT_TOO_SHORT({len(pv)}<100)")
    if len(pv) > 5000:
        errs.append(f"INPUT_TOO_LONG({len(pv)}>5000)")
    for name, arr in (("t", t), ("sp", sp), ("pv", pv), ("op", op)):
        if not np.all(np.isfinite(arr)):
            errs.append(f"INPUT_NON_FINITE_{name.upper()}")
    if len(t) >= 2 and np.all(np.isfinite(t)) and np.any(np.diff(t) <= 0):
        errs.append("INPUT_TIMESTAMPS_NOT_MONOTONIC")
    return errs


def _load_prompt(name: str) -> str:
    p = ROOT / "07_agents" / "prompts" / f"{name}.md"
    return p.read_text(encoding="utf-8") if p.exists() else f"You are {name}."


def _compute_nyquist_locus(plant: PlantParams, pid: PIDParams) -> List[Dict[str, float]]:
    w = np.logspace(-2.4, 0.8, 180)
    jw = 1j * w
    G = plant.K * np.exp(-plant.theta * jw) / (plant.tau * jw + 1.0)
    C = np.full_like(jw, pid.Kc, dtype=complex)
    if pid.Ti > 1e-6:
        C = C + pid.Kc / (pid.Ti * jw)
    if pid.Td > 1e-6:
        C = C + pid.Kc * (pid.Td * jw) / (0.1 * pid.Td * jw + 1.0)
    L = C * G
    pts = []
    for z in L:
        re, im = float(np.real(z)), float(np.imag(z))
        if -2.5 <= re <= 1.5 and -2.2 <= im <= 1.2:
            pts.append({"re": round(re, 4), "im": round(im, 4)})
    return pts


def _extract_phase_portrait(sp: np.ndarray, pv: np.ndarray, op: np.ndarray) -> Dict[str, List[float]]:
    dsp = np.abs(np.diff(sp, prepend=sp[0]))
    step_idxs = np.where(dsp > 0.5)[0]
    boundaries = [0] + list(step_idxs) + [len(sp)]
    best = (20, len(sp))
    best_len = 0
    for i in range(len(boundaries) - 1):
        s0, s1 = boundaries[i] + 35, boundaries[i + 1] - 2
        if s1 - s0 > best_len:
            best_len = s1 - s0
            best = (s0, s1)
    s0, s1 = best if best_len >= 50 else (20, len(sp))
    return {
        "op": np.round(op[s0:s1], 3).tolist(),
        "pv": np.round(pv[s0:s1], 3).tolist(),
    }


class PetroPIDOrchestrator:
    """Deterministic-evidence-gated 5-Agent Swarm Orchestrator."""

    def __init__(self) -> None:
        self.runner = SkillRunner()
        self.llm = LLMGateway()

    def run_loop_workflow(
        self,
        loop_id: str,
        max_overshoot_pct: float = 18.0,
        max_ms: float = 2.2,
        min_gm: float = 1.8,
        min_pm_deg: float = 35.0,
        preferred_strategy: Optional[str] = None,
    ) -> Dict[str, Any]:
        meta = _load_loop_metadata(loop_id)
        df = _load_loop_dataframe(meta)
        return self._execute_pipeline(
            meta=meta,
            t=df["timestamp_s"].to_numpy(),
            sp=df["sp"].to_numpy(),
            pv=df["pv"].to_numpy(),
            op=df["op"].to_numpy(),
            max_overshoot_pct=max_overshoot_pct,
            max_ms=max_ms,
            min_gm=min_gm,
            min_pm_deg=min_pm_deg,
            preferred_strategy=preferred_strategy,
            is_sandbox=False,
        )

    def run_sandbox_workflow(
        self,
        K: float = 1.5,
        tau: float = 16.0,
        theta: float = 5.0,
        init_Kc: float = 2.1,
        init_Ti: float = 8.0,
        stiction_S: float = 0.0,
        stiction_J: float = 0.0,
        disturbance_amp: float = 0.0,
        disturbance_period: float = 55.0,
        max_overshoot_pct: float = 18.0,
        max_ms: float = 2.2,
        preferred_strategy: Optional[str] = None,
    ) -> Dict[str, Any]:
        plant = PlantParams(K=K, tau=tau, theta=theta, pv_bias=200.0, op_bias=50.0)
        pid = PIDParams(Kc=init_Kc, Ti=init_Ti, Td=0.0)
        valve = ValveParams(stiction_S=stiction_S, stiction_J=stiction_J)
        sim = simulate_loop(
            plant=plant, pid=pid, valve=valve, dt=1.0, n_steps=600,
            noise_std=0.06, disturbance_amp=disturbance_amp,
            disturbance_period=disturbance_period, seed=777,
        )
        meta = {
            "loop_id": "SANDBOX-LIVE",
            "tag_name": "TIC-SIM",
            "unit_name": "自定义压力测试沙盒(Live Sandbox)",
            "loop_type": "Temperature",
            "description": f"实时自定义工况 (K={K}, τ={tau}s, θ={theta}s, 粘滞S={stiction_S}%)",
            "pv_unit": "°C",
            "anomaly_type": "CUSTOM_LIVE",
            "true_K": K,
            "true_tau": tau,
            "true_theta": theta,
            "pv_bias": 200.0,
            "op_bias": 50.0,
            "init_Kc": init_Kc,
            "init_Ti": init_Ti,
            "init_Td": 0.0,
            "disturbance_amp": disturbance_amp,
            "disturbance_period": disturbance_period,
            "dt": 1.0,
            "seed": 777,
        }
        return self._execute_pipeline(
            meta=meta,
            t=sim["t"], sp=sim["sp"], pv=sim["pv"], op=sim["op"],
            max_overshoot_pct=max_overshoot_pct,
            max_ms=max_ms,
            min_gm=1.8,
            min_pm_deg=35.0,
            preferred_strategy=preferred_strategy,
            is_sandbox=True,
        )

    def _execute_pipeline(
        self,
        meta: Dict[str, Any],
        t: np.ndarray,
        sp: np.ndarray,
        pv: np.ndarray,
        op: np.ndarray,
        max_overshoot_pct: float,
        max_ms: float,
        min_gm: float,
        min_pm_deg: float,
        preferred_strategy: Optional[str],
        is_sandbox: bool,
    ) -> Dict[str, Any]:
        t_start = time.perf_counter()
        self.runner.reset_session()
        trace: List[Dict[str, Any]] = []
        raw_bytes = int(len(t) * 4 * 16)

        init_pid_dict = {"Kc": meta["init_Kc"], "Ti": meta["init_Ti"], "Td": meta["init_Td"]}
        init_pid_obj = PIDParams(Kc=meta["init_Kc"], Ti=meta["init_Ti"], Td=meta["init_Td"])

        # Gate 0: Strict Input Data Validation (Fail-Closed!)
        input_errors = validate_input_series(t, sp, pv, op)
        if input_errors:
            fd = final_decision_aggregation(DecisionEvidence(
                input_valid=False, input_errors=input_errors,
                decision_detail=f"输入时序校验失败（{', '.join(input_errors)}），拒绝执行辨识与参数推荐。",
            ))
            trace.append({
                "step": 1, "stage": "输入校验", "agent": "FinalDecisionEngine",
                "skill": "input_data_validation", "latency_ms": 0.2, "status": "REJECTED",
                "summary": fd.decision_summary, "metrics": {"errors": input_errors},
            })
            return self._pack_result(
                meta=meta, t=np.arange(max(2, len(t)), dtype=float),
                sp=np.nan_to_num(sp, nan=0.0) if len(sp) else np.zeros(2),
                pv=np.nan_to_num(pv, nan=0.0) if len(pv) else np.zeros(2),
                op=np.nan_to_num(op, nan=0.0) if len(op) else np.zeros(2),
                diag={"anomaly_type": "INPUT_INVALID", "severity": "CRITICAL", "harris_index": 0.0, "oscillation_index": 0.0, "stiction_index": 0.0, "iae": 0.0, "op_travel": 0.0, "overshoot_pct": 0.0},
                ident=None, tuning=None, safety=None, final_pid=init_pid_dict,
                final_decision=fd.to_dict(), trace=trace, elapsed_s=round(time.perf_counter() - t_start, 3),
                raw_bytes=raw_bytes, after_sim=None, kg={"ontology_class": "N/A"}, ident_pred=None,
                nyquist_before=[], nyquist_after=[], max_ms=max_ms, baseline_comparison=None,
            )
        # Ground-truth plant is used ONLY for closed-loop post-simulation evaluation (environment oracle),
        # NEVER exposed to Identification/Tuning/SafetyVerification!
        env_oracle_plant = PlantParams(
            K=meta["true_K"], tau=meta["true_tau"], theta=meta["true_theta"],
            pv_bias=meta["pv_bias"], op_bias=meta["op_bias"],
        )

        # --- Stage 1: DiagnosisAgent ---
        t1 = time.perf_counter()
        if not is_sandbox:
            diag = self.runner.invoke("pid_loop_diagnosis", {"loop_id": meta["loop_id"]})
        else:
            diag = diagnose_loop(
                sp, pv, op, dt=meta["dt"], estimated_delay_s=meta["true_theta"],
                pid_kc=meta["init_Kc"], pid_ti=meta["init_Ti"],
            ).to_dict()
            diag["loop_id"] = meta["loop_id"]

        kg = self.runner.invoke(
            "petro_knowledge_lookup",
            {"anomaly_type": diag["anomaly_type"], "loop_type": meta["loop_type"]},
        )
        diag_llm = self.llm.synthesize_decision(
            agent_role="DiagnosisAgent",
            system_prompt=_load_prompt("diagnosis"),
            structured_state={
                "anomaly_type": diag["anomaly_type"],
                "harris": diag["harris_index"],
                "oi": diag["oscillation_index"],
                "si": diag["stiction_index"],
                "overshoot_pct": diag["overshoot_pct"],
            },
            fallback_text=f"{diag['root_cause_summary']} {kg['engineering_guidance']}",
        )
        trace.append({
            "step": 1,
            "stage": "诊断证据",
            "agent": "DiagnosisAgent",
            "skill": "pid_loop_diagnosis + petro_knowledge_lookup",
            "latency_ms": round((time.perf_counter() - t1) * 1000.0, 2),
            "status": "DONE",
            "summary": diag_llm["reasoning"],
            "metrics": {
                "anomaly_type": diag["anomaly_type"],
                "severity": diag["severity"],
                "harris_index": diag["harris_index"],
                "oscillation_index": diag["oscillation_index"],
                "stiction_index": diag["stiction_index"],
                "iae": diag["iae"],
                "overshoot_pct": diag["overshoot_pct"],
            },
        })

        # Gate 1: Healthy Loop Early Exit (via FinalDecisionEngine)
        if diag["anomaly_type"] == "NORMAL" and preferred_strategy is None:
            fd = final_decision_aggregation(DecisionEvidence(
                input_valid=True, input_errors=[], anomaly_type="NORMAL",
                decision_detail="回路运行健康（现有参数合理，无需变更），已归档例行巡检记录。",
            ))
            elapsed_s = round(time.perf_counter() - t_start, 3)
            trace.append({
                "step": 2,
                "stage": "审批建议",
                "agent": "FinalDecisionEngine",
                "skill": "final_decision_aggregation",
                "latency_ms": 0.1,
                "status": "DONE",
                "summary": fd.decision_summary,
                "metrics": {"final_status": fd.final_status, "reason_codes": fd.reason_codes},
            })
            return self._pack_result(
                meta=meta, t=t, sp=sp, pv=pv, op=op, diag=diag, ident=None, tuning=None, safety=None,
                final_pid=init_pid_dict, final_decision=fd.to_dict(),
                trace=trace, elapsed_s=elapsed_s, raw_bytes=raw_bytes,
                after_sim=None, kg=kg, ident_pred=None,
                nyquist_before=_compute_nyquist_locus(env_oracle_plant, init_pid_obj),
                nyquist_after=_compute_nyquist_locus(env_oracle_plant, init_pid_obj),
                max_ms=max_ms, baseline_comparison=None,
            )

        # --- Stage 2: IdentificationAgent ---
        t2 = time.perf_counter()
        if not is_sandbox:
            ident = self.runner.invoke("fopdt_system_identification", {"loop_id": meta["loop_id"]})
        else:
            ident = identify_fopdt(pv, op, dt=meta["dt"]).to_dict()
            ident["loop_id"] = meta["loop_id"]

        id_llm = self.llm.synthesize_decision(
            agent_role="IdentificationAgent",
            system_prompt=_load_prompt("identification"),
            structured_state={
                "allow_next_stage": ident["allow_next_stage"],
                "K": ident["K"],
                "tau": ident["tau"],
                "theta": ident["theta"],
                "val_r2": ident["val_r2"],
                "val_fit_pct": ident["val_fit_pct"],
                "failure_reason": ident["failure_reason"],
            },
            fallback_text=ident["message"],
        )
        trace.append({
            "step": 2,
            "stage": "模型辨识",
            "agent": "IdentificationAgent",
            "skill": "fopdt_system_identification",
            "latency_ms": round((time.perf_counter() - t2) * 1000.0, 2),
            "status": "DONE" if ident["allow_next_stage"] else "REJECTED",
            "summary": id_llm["reasoning"],
            "metrics": {
                "K": ident["K"],
                "tau": ident["tau"],
                "theta": ident["theta"],
                "val_r2": ident["val_r2"],
                "val_nrmse": ident["val_nrmse"],
                "val_accuracy_pct": ident["val_accuracy_pct"],
                "allow_next_stage": ident["allow_next_stage"],
                "failure_reason": ident["failure_reason"],
            },
        })

        ident_plant = PlantParams(
            K=ident["K"], tau=ident["tau"], theta=ident["theta"],
            pv_bias=ident["pv_bias"], op_bias=ident["op_bias"],
        )
        ident_pred = simulate_fopdt_open_loop(
            op, ident["K"], ident["tau"], ident["theta"], ident["pv_bias"], ident["op_bias"], dt=meta["dt"]
        )

        # Gate 2: Valve Stiction Mechanical Fault -> FinalDecisionEngine
        if diag["anomaly_type"] == "VALVE_STICTION":
            elapsed_s = round(time.perf_counter() - t_start, 3)
            safety_stiction = verify_pid_safety(
                plant=ident_plant,
                candidate_pid=init_pid_obj,
                dt=meta["dt"],
                model_valid=ident["allow_next_stage"],
                model_val_r2=ident["val_r2"],
                model_val_fit_pct=ident["val_fit_pct"],
                min_gm=min_gm, min_pm_deg=min_pm_deg, max_ms=max_ms, max_overshoot_pct=max_overshoot_pct,
            ).to_dict()
            fd = final_decision_aggregation(DecisionEvidence(
                input_valid=True, input_errors=[], anomaly_type="VALVE_STICTION",
                model_evaluated=True, model_valid=ident["allow_next_stage"],
                model_failure_reason=ident["failure_reason"] if not ident["allow_next_stage"] else None,
                safety_evaluated=True, safety_approved=safety_stiction["approved"],
                safety_violations=safety_stiction["violation_tags"],
                multi_regime_evaluated=True, multi_regime_passed=safety_stiction["multi_regime_pass_rate_pct"] >= 80.0,
                decision_detail="调节阀机械粘滞属于执行机构故障，PID 整定无法根除振荡，必须优先安排仪表检维修并保持原参数。",
            ))
            trace.append({
                "step": 3,
                "stage": "安全验证与审批建议",
                "agent": "FinalDecisionEngine",
                "skill": "final_decision_aggregation",
                "latency_ms": round((time.perf_counter() - t2) * 1000.0, 2),
                "status": "WARNING",
                "summary": fd.decision_summary,
                "metrics": {"final_status": fd.final_status, "reason_codes": fd.reason_codes},
            })
            return self._pack_result(
                meta=meta, t=t, sp=sp, pv=pv, op=op, diag=diag, ident=ident, tuning=None, safety=safety_stiction,
                final_pid=init_pid_dict, final_decision=fd.to_dict(),
                trace=trace, elapsed_s=elapsed_s, raw_bytes=raw_bytes,
                after_sim=None, kg=kg, ident_pred=ident_pred,
                nyquist_before=_compute_nyquist_locus(ident_plant, init_pid_obj),
                nyquist_after=_compute_nyquist_locus(ident_plant, init_pid_obj),
                max_ms=max_ms, baseline_comparison=None,
            )

        # Gate 3: Model Validation Failed -> FinalDecisionEngine (ZERO Ground-Truth Fallback!)
        if not ident["allow_next_stage"]:
            t3 = time.perf_counter()
            safety_fail = verify_pid_safety(
                plant=ident_plant,
                candidate_pid=init_pid_obj,
                dt=meta["dt"],
                model_valid=False,
                model_val_r2=ident["val_r2"],
                model_val_fit_pct=ident["val_fit_pct"],
                min_gm=min_gm, min_pm_deg=min_pm_deg, max_ms=max_ms, max_overshoot_pct=max_overshoot_pct,
            ).to_dict()
            fd = final_decision_aggregation(DecisionEvidence(
                input_valid=True, input_errors=[], anomaly_type=diag["anomaly_type"],
                model_evaluated=True, model_valid=False, model_failure_reason=ident["failure_reason"],
                safety_evaluated=True, safety_approved=False, safety_violations=safety_fail["violation_tags"],
                multi_regime_evaluated=True, multi_regime_passed=safety_fail["multi_regime_pass_rate_pct"] >= 80.0,
                decision_detail=f"过程模型独立验证未通过 ({ident['failure_reason']})，存在未测负载偏移或激励不足，拒绝推荐新参数并保持原参数。",
            ))
            trace.append({
                "step": 3,
                "stage": "安全验证与审批建议",
                "agent": "FinalDecisionEngine",
                "skill": "final_decision_aggregation",
                "latency_ms": round((time.perf_counter() - t3) * 1000.0, 2),
                "status": "REJECTED",
                "summary": fd.decision_summary,
                "metrics": {"final_status": fd.final_status, "reason_codes": fd.reason_codes},
            })
            elapsed_s = round(time.perf_counter() - t_start, 3)
            return self._pack_result(
                meta=meta, t=t, sp=sp, pv=pv, op=op, diag=diag, ident=ident, tuning=None, safety=safety_fail,
                final_pid=init_pid_dict, final_decision=fd.to_dict(),
                trace=trace, elapsed_s=elapsed_s, raw_bytes=raw_bytes,
                after_sim=None, kg=kg, ident_pred=ident_pred,
                nyquist_before=_compute_nyquist_locus(ident_plant, init_pid_obj),
                nyquist_after=_compute_nyquist_locus(ident_plant, init_pid_obj),
                max_ms=max_ms, baseline_comparison=None,
            )

        # --- Stage 3: TuningAgent (strictly using identified model, NEVER ground truth!) ---
        t3 = time.perf_counter()
        tuning = tune_pid(
            plant=ident_plant,
            current_pid=init_pid_obj,
            anomaly_type=diag["anomaly_type"],
            dt=meta["dt"],
        ).to_dict()

        chosen_strategy = preferred_strategy or tuning["recommended_strategy"]
        chosen_cand = next((c for c in tuning["candidates"] if c["strategy"] == chosen_strategy), tuning["candidates"][1])
        rec_pid = {"Kc": chosen_cand["Kc"], "Ti": chosen_cand["Ti"], "Td": chosen_cand["Td"]}

        tune_llm = self.llm.synthesize_decision(
            agent_role="TuningAgent",
            system_prompt=_load_prompt("tuning"),
            structured_state={"strategy": chosen_strategy, **rec_pid},
            fallback_text=f"基于已验证 FOPDT 模型采用 {chosen_strategy} 策略生成候选参数 Kc={rec_pid['Kc']}, Ti={rec_pid['Ti']}s, Td={rec_pid['Td']}s。",
        )
        trace.append({
            "step": 3,
            "stage": "整定候选",
            "agent": "TuningAgent",
            "skill": "adaptive_pid_tuning",
            "latency_ms": round((time.perf_counter() - t3) * 1000.0, 2),
            "status": "DONE",
            "summary": tune_llm["reasoning"],
            "metrics": {"strategy": chosen_strategy, **rec_pid},
        })

        # --- Stage 4: SafetyVerificationAgent (with closed-loop conservative fallback) ---
        t4 = time.perf_counter()
        safety = verify_pid_safety(
            plant=ident_plant,
            candidate_pid=PIDParams(Kc=rec_pid["Kc"], Ti=rec_pid["Ti"], Td=rec_pid["Td"]),
            dt=meta["dt"],
            model_valid=True,
            model_val_r2=ident["val_r2"],
            model_val_fit_pct=ident["val_fit_pct"],
            min_gm=min_gm, min_pm_deg=min_pm_deg, max_ms=max_ms, max_overshoot_pct=max_overshoot_pct,
        ).to_dict()

        fallback_triggered = False
        if not safety["approved"] and chosen_strategy != "conservative":
            trace.append({
                "step": 4,
                "stage": "安全验证",
                "agent": "SafetyVerificationAgent",
                "skill": "safety_constraint_verification",
                "latency_ms": round((time.perf_counter() - t4) * 1000.0, 2),
                "status": "REJECTED",
                "summary": f"拦截 {chosen_strategy} 候选参数！触发安全违规：{', '.join(safety['violation_tags'])}。OrchestratorAgent 自动回退至保守策略重新校验。",
                "metrics": {"approved": False, "violation_tags": safety["violation_tags"]},
            })
            fallback_triggered = True
            cons = next((c for c in tuning["candidates"] if c["strategy"] == "conservative"), None)
            if cons is not None:
                chosen_strategy = "conservative"
                rec_pid = {"Kc": cons["Kc"], "Ti": cons["Ti"], "Td": cons["Td"]}
                t4b = time.perf_counter()
                safety = verify_pid_safety(
                    plant=ident_plant,
                    candidate_pid=PIDParams(Kc=rec_pid["Kc"], Ti=rec_pid["Ti"], Td=rec_pid["Td"]),
                    dt=meta["dt"],
                    model_valid=True,
                    model_val_r2=ident["val_r2"],
                    model_val_fit_pct=ident["val_fit_pct"],
                    min_gm=min_gm, min_pm_deg=min_pm_deg, max_ms=max_ms, max_overshoot_pct=max_overshoot_pct,
                ).to_dict()
                t4 = t4b

        trace.append({
            "step": len(trace) + 1,
            "stage": "安全验证",
            "agent": "SafetyVerificationAgent",
            "skill": "safety_constraint_verification",
            "latency_ms": round((time.perf_counter() - t4) * 1000.0, 2),
            "status": "CONSTRAINTS_PASS" if safety["approved"] else "REJECTED",
            "fallback_triggered": fallback_triggered,
            "summary": ("【回退二次校验】" if fallback_triggered else "") + safety["summary"] + ("（注：仅表示 11 项安全硬约束通过，最终是否推荐变更仍需经由性能净改善门控终裁）" if safety["approved"] else ""),
            "metrics": {
                "approved": safety["approved"],
                "constraint_coverage_pct": safety["constraint_coverage_pct"],
                "gain_margin": safety["gain_margin"],
                "phase_margin_deg": safety["phase_margin_deg"],
                "max_sensitivity_ms": safety["max_sensitivity_ms"],
                "multi_regime_pass_rate_pct": safety["multi_regime_pass_rate_pct"],
                "violation_tags": safety["violation_tags"],
            },
        })

        # --- Stage 5: Comparable Closed-Loop Evaluation + Fair Baseline + Performance Improvement Gate ---
        t5 = time.perf_counter()
        final_pid_obj = PIDParams(Kc=rec_pid["Kc"], Ti=rec_pid["Ti"], Td=rec_pid["Td"])
        simc_pid_obj = _simc_pid(ident["K"], ident["tau"], ident["theta"], tau_c_factor=1.0)

        sim_after = simulate_loop(
            plant=env_oracle_plant, pid=final_pid_obj, valve=ValveParams(),
            dt=meta["dt"], n_steps=len(t), noise_std=0.06,
            disturbance_amp=meta["disturbance_amp"], disturbance_period=meta["disturbance_period"],
            seed=meta.get("seed", 42),
        )
        after_diag = diagnose_loop(
            sim_after["sp"], sim_after["pv"], sim_after["op"],
            dt=meta["dt"], estimated_delay_s=ident["theta"],
            pid_kc=rec_pid["Kc"], pid_ti=rec_pid["Ti"],
        ).to_dict()

        sim_simc = simulate_loop(
            plant=env_oracle_plant, pid=simc_pid_obj, valve=ValveParams(),
            dt=meta["dt"], n_steps=len(t), noise_std=0.06,
            disturbance_amp=meta["disturbance_amp"], disturbance_period=meta["disturbance_period"],
            seed=meta.get("seed", 42),
        )
        simc_diag = diagnose_loop(
            sim_simc["sp"], sim_simc["pv"], sim_simc["op"],
            dt=meta["dt"], estimated_delay_s=ident["theta"],
            pid_kc=simc_pid_obj.Kc, pid_ti=simc_pid_obj.Ti,
        ).to_dict()

        baseline_comparison = {
            "original_pid": {
                "Kc": init_pid_dict["Kc"], "Ti": init_pid_dict["Ti"],
                "iae": diag["iae"], "oi": diag["oscillation_index"],
                "harris": diag["harris_index"], "overshoot_pct": diag["overshoot_pct"],
                "op_travel": diag["op_travel"],
            },
            "traditional_simc": {
                "Kc": simc_pid_obj.Kc, "Ti": simc_pid_obj.Ti,
                "iae": simc_diag["iae"], "oi": simc_diag["oscillation_index"],
                "harris": simc_diag["harris_index"], "overshoot_pct": simc_diag["overshoot_pct"],
                "op_travel": simc_diag["op_travel"],
            },
            "optimized_candidate": {
                "strategy": chosen_strategy, "Kc": rec_pid["Kc"], "Ti": rec_pid["Ti"],
                "iae": after_diag["iae"], "oi": after_diag["oscillation_index"],
                "harris": after_diag["harris_index"], "overshoot_pct": after_diag["overshoot_pct"],
                "op_travel": after_diag["op_travel"],
            },
        }

        # Deterministic Final Approval Status Derivation via Independent FinalDecisionEngine
        iae_improved = after_diag["iae"] < diag["iae"] * 0.95
        oi_improved = (diag["oscillation_index"] > 0.25) and (after_diag["oscillation_index"] < diag["oscillation_index"] * 0.85)
        iae_worsened = after_diag["iae"] > diag["iae"] * 1.01

        detail_msg = (
            f"仿真闭环验证有效且通过全部 {safety['total_constraints']} 项安全硬约束（策略：{chosen_strategy}）："
            f"IAE {diag['iae']:.2f} → {after_diag['iae']:.2f}，OI {diag['oscillation_index']:.2f} → {after_diag['oscillation_index']:.2f}，"
            f"阀位磨损 {diag['op_travel']:.2f} → {after_diag['op_travel']:.2f}%/s。仅仿真校验通过，待自控工程师人工复核（严禁未审批写入真实 DCS）。"
            if (safety["approved"] and not iae_worsened and (iae_improved or oi_improved) and diag["anomaly_type"] != "EXTERNAL_DISTURBANCE")
            else (
                f"安全约束未通过（{', '.join(safety['violation_tags'])}），已拦截变更并保持原参数。"
                if not safety["approved"]
                else f"候选参数未带来净性能改善（IAE: {diag['iae']:.2f} → {after_diag['iae']:.2f}），属 {diag['anomaly_type']}，保持原参数并建议排查上游扰动源/前馈补偿。"
            )
        )
        fd = final_decision_aggregation(DecisionEvidence(
            input_valid=True, input_errors=[], anomaly_type=diag["anomaly_type"],
            model_evaluated=True, model_valid=True,
            safety_evaluated=True, safety_approved=safety["approved"], safety_violations=safety["violation_tags"],
            multi_regime_evaluated=True, multi_regime_passed=safety["multi_regime_pass_rate_pct"] >= 80.0,
            performance_evaluated=True, performance_improved=(iae_improved or oi_improved), performance_worsened=iae_worsened,
            decision_detail=detail_msg,
        ))
        final_status = fd.final_status
        final_pid_out = rec_pid if fd.parameter_recommended else init_pid_dict

        trace.append({
            "step": len(trace) + 1,
            "stage": "审批建议",
            "agent": "FinalDecisionEngine",
            "skill": "final_decision_aggregation",
            "latency_ms": round((time.perf_counter() - t5) * 1000.0, 2),
            "status": "DONE" if fd.candidate_eligible_for_review else "WARNING",
            "summary": fd.decision_summary,
            "metrics": {
                "final_status": fd.final_status,
                "candidate_eligible_for_review": fd.candidate_eligible_for_review,
                "deployment_authorized": fd.deployment_authorized,
                "reason_codes": fd.reason_codes,
            },
        })

        elapsed_s = round(time.perf_counter() - t_start, 3)
        use_after_sim = sim_after if fd.candidate_eligible_for_review else None
        return self._pack_result(
            meta=meta, t=t, sp=sp, pv=pv, op=op, diag=diag, ident=ident, tuning=tuning, safety=safety,
            final_pid=final_pid_out, final_decision=fd.to_dict(), trace=trace, elapsed_s=elapsed_s, raw_bytes=raw_bytes,
            after_sim=use_after_sim, kg=kg, ident_pred=ident_pred,
            nyquist_before=_compute_nyquist_locus(ident_plant, init_pid_obj),
            nyquist_after=_compute_nyquist_locus(ident_plant, PIDParams(Kc=final_pid_out["Kc"], Ti=final_pid_out["Ti"], Td=final_pid_out["Td"])),
            max_ms=max_ms, after_diag=after_diag if use_after_sim is not None else diag,
            baseline_comparison=baseline_comparison,
        )

    def _pack_result(
        self,
        meta: Dict[str, Any],
        t: np.ndarray,
        sp: np.ndarray,
        pv: np.ndarray,
        op: np.ndarray,
        diag: Dict[str, Any],
        ident: Dict[str, Any] | None,
        tuning: Dict[str, Any] | None,
        safety: Dict[str, Any] | None,
        final_pid: Dict[str, float],
        final_decision: Dict[str, Any],
        trace: List[Dict[str, Any]],
        elapsed_s: float,
        raw_bytes: int,
        after_sim: Dict[str, Any] | None,
        kg: Dict[str, Any],
        ident_pred: np.ndarray | None,
        nyquist_before: List[Dict[str, float]],
        nyquist_after: List[Dict[str, float]],
        max_ms: float,
        after_diag: Dict[str, Any] | None = None,
        baseline_comparison: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        final_status = final_decision["final_status"]
        decision_reason = final_decision["decision_summary"]
        compact_state_bytes = len(json.dumps(trace, ensure_ascii=False).encode("utf-8"))
        step = max(1, len(t) // 180)
        split_idx = int(len(t) * 0.65)

        waveforms = {
            "t": np.round(t[::step], 1).tolist(),
            "sp": np.round(sp[::step], 3).tolist(),
            "pv_before": np.round(pv[::step], 3).tolist(),
            "op_before": np.round(op[::step], 3).tolist(),
            "pv_after": np.round(after_sim["pv"][::step], 3).tolist() if after_sim is not None else np.round(pv[::step], 3).tolist(),
            "op_after": np.round(after_sim["op"][::step], 3).tolist() if after_sim is not None else np.round(op[::step], 3).tolist(),
        }
        id_plot = None
        if ident_pred is not None:
            id_plot = {
                "t": np.round(t[::step], 1).tolist(),
                "pv_actual": np.round(pv[::step], 3).tolist(),
                "pv_predicted": np.round(ident_pred[::step], 3).tolist(),
                "split_t": float(t[split_idx]),
            }

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        in_hash = compute_canonical_hash({
            "loop_id": meta["loop_id"], "init_pid": {"Kc": meta["init_Kc"], "Ti": meta["init_Ti"], "Td": meta["init_Td"]},
            "max_ms": max_ms, "n_samples": len(t),
        })
        out_hash = compute_canonical_hash({
            "final_status": final_status, "final_pid": final_pid,
            "reason_codes": final_decision["reason_codes"],
            "gate_matrix": final_decision["gate_matrix"],
        })
        run_id = f"RUN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{out_hash[:8]}"

        return {
            "audit_meta": {
                "run_id": run_id,
                "timestamp": now_str,
                "input_hash": in_hash,
                "output_hash": out_hash,
                "input_sha256": in_hash[:12],
                "output_sha256": out_hash[:12],
                "dataset_version": DATASET_VERSION,
                "algorithm_version": ALGORITHM_VERSION,
                "code_commit": CODE_COMMIT,
                "runtime_mode": self.llm.mode,
                "final_status": final_status,
                "reason_codes": final_decision["reason_codes"],
            },
            "final_decision": final_decision,
            "candidate_eligible_for_review": final_decision["candidate_eligible_for_review"],
            "engineering_approval_status": final_decision["engineering_approval_status"],
            "deployment_authorized": False,
            "loop_meta": meta,
            "final_status": final_status,
            "decision_reason": decision_reason,
            "elapsed_s": elapsed_s,
            "llm_mode": self.llm.mode,
            "simulation_disclaimer": "所有结果均基于本地机理仿真/历史脱敏数据计算，未连接或写入真实 DCS/PLC。",
            "anti_bloat_metrics": {
                "raw_timeseries_bytes": raw_bytes,
                "compact_handoff_bytes": compact_state_bytes,
                "compression_ratio_pct": round((1.0 - compact_state_bytes / max(raw_bytes, 1)) * 100.0, 1),
                "duplicate_tool_calls_prevented": self.runner.duplicate_calls_prevented,
                "total_tool_calls": len(self.runner.call_history),
            },
            "initial_pid": {"Kc": meta["init_Kc"], "Ti": meta["init_Ti"], "Td": meta["init_Td"]},
            "final_pid": final_pid,
            "diagnosis": diag,
            "knowledge": kg,
            "identification": ident,
            "tuning": tuning,
            "safety": safety,
            "after_diagnosis": after_diag,
            "baseline_comparison": baseline_comparison,
            "trace": trace,
            "waveforms": waveforms,
            "identification_plot": id_plot,
            "phase_portrait": _extract_phase_portrait(sp, pv, op),
            "nyquist_plot": {
                "before": nyquist_before,
                "after": nyquist_after,
                "ms_radius": round(1.0 / max(max_ms, 1.05), 3),
                "max_ms": max_ms,
            },
        }
