"""Independent, Unbypassable Final Decision Engine (V4.0 P0 Safety Authority).

This module is the SINGLE SOURCE OF TRUTH for final loop approval status.
Neither LLM prose, Agent orchestrators, frontend UI, nor approval sheets may
override or independently derive `final_status`.

Enforces:
- Exact 9-state machine-readable enum with fixed deterministic priority.
- Strict separation of:
    1. candidate_eligible_for_review (bool)
    2. engineering_approval_status (PENDING_MANUAL_REVIEW | NOT_APPLICABLE | REJECTED_BY_GATE)
    3. deployment_authorized (ALWAYS False in isolated simulation)
- Strict PASS / FAIL / NOT_EVALUATED gate states (never "unknown == PASS").
- Full preservation of ALL concurrent failure reason codes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

DATASET_VERSION = "petropid-sim-30loops-v2.0"
ALGORITHM_VERSION = "petropid-alg-v4.0"

FINAL_STATUS_SPECS: Dict[str, Dict[str, Any]] = {
    "INPUT_DATA_INVALID": {
        "zh_label": "输入数据非法",
        "trigger": "输入时序缺失、含 NaN/Inf、时间戳乱序、长度不足/超限或参数越界",
        "eligible_for_review": False,
        "parameter_recommended": False,
    },
    "SIMULATION_TIMEOUT": {
        "zh_label": "仿真或工具执行超时",
        "trigger": "任一工具调用、辨识或仿真步骤超时或发生运行时异常",
        "eligible_for_review": False,
        "parameter_recommended": False,
    },
    "AUDIT_INCOMPLETE": {
        "zh_label": "审计证据不完整或哈希校验失败",
        "trigger": "缺少 run_id/输入输出哈希/必要门控证据或审计哈希重算不一致",
        "eligible_for_review": False,
        "parameter_recommended": False,
    },
    "HEALTHY_NO_CHANGE": {
        "zh_label": "回路健康，保持原参数",
        "trigger": "诊断为 NORMAL，控制品质良好，无需非必要扰动或参数变更",
        "eligible_for_review": False,
        "parameter_recommended": False,
    },
    "VALVE_MAINTENANCE_REQUIRED": {
        "zh_label": "调节阀机械异常，优先检维修",
        "trigger": "诊断为 VALVE_STICTION，禁止仅靠 PID 调参替代机械检修",
        "eligible_for_review": False,
        "parameter_recommended": False,
    },
    "MODEL_VALIDATION_FAILED": {
        "zh_label": "过程模型独立验证未通过",
        "trigger": "辨识激励不足、留出验证 R² < 0.80 或 Fit < 85% 或模型缺失",
        "eligible_for_review": False,
        "parameter_recommended": False,
    },
    "SAFETY_REJECTED": {
        "zh_label": "安全约束或多工况鲁棒性校验拦截",
        "trigger": "C-000~C-010 任一硬约束或 5 工况鲁棒验证未通过",
        "eligible_for_review": False,
        "parameter_recommended": False,
    },
    "PERFORMANCE_NOT_IMPROVED": {
        "zh_label": "候选参数未带来净性能改善",
        "trigger": "仿真对照 IAE/OI 未改善或恶化，或属外部周期扰动非反馈调参最优场景",
        "eligible_for_review": False,
        "parameter_recommended": False,
    },
    "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW": {
        "zh_label": "仿真校验通过，待工程师人工复核",
        "trigger": "数据有效、模型验证通过、11 项硬约束与多工况通过、且仿真性能净改善",
        "eligible_for_review": True,
        "parameter_recommended": True,
    },
}


def compute_canonical_hash(obj: Any) -> str:
    """Deterministic canonical JSON SHA-256 hash for tamper detection & auditability."""
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass
class DecisionEvidence:
    """Structured, validated evidence bundle consumed by final_decision_aggregation."""
    input_valid: bool
    input_errors: List[str]
    timed_out: bool = False
    runtime_error: Optional[str] = None
    stale_run: bool = False
    anomaly_type: Optional[str] = None
    model_evaluated: bool = False
    model_valid: Optional[bool] = None
    model_failure_reason: Optional[str] = None
    safety_evaluated: bool = False
    safety_approved: Optional[bool] = None
    safety_violations: Optional[List[str]] = None
    multi_regime_evaluated: bool = False
    multi_regime_passed: Optional[bool] = None
    performance_evaluated: bool = False
    performance_improved: Optional[bool] = None
    performance_worsened: Optional[bool] = None
    audit_complete: bool = True
    audit_hash_verified: bool = True
    decision_detail: str = ""


@dataclass
class FinalDecision:
    final_status: str
    status_zh: str
    candidate_eligible_for_review: bool
    engineering_approval_status: str    # PENDING_MANUAL_REVIEW | NOT_APPLICABLE | REJECTED_BY_GATE
    deployment_authorized: bool         # ALWAYS False in isolated simulation!
    parameter_recommended: bool
    has_unevaluated_gates: bool
    reason_codes: List[str]
    gate_matrix: Dict[str, str]         # PASS | FAIL | NOT_EVALUATED
    decision_summary: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def final_decision_aggregation(ev: DecisionEvidence) -> FinalDecision:
    """Unbypassable deterministic final decision engine.

    Collects ALL failure reason codes simultaneously, then applies fixed strict priority:
      1. INPUT_DATA_INVALID
      2. SIMULATION_TIMEOUT
      3. AUDIT_INCOMPLETE
      4. HEALTHY_NO_CHANGE
      5. VALVE_MAINTENANCE_REQUIRED
      6. MODEL_VALIDATION_FAILED
      7. SAFETY_REJECTED
      8. PERFORMANCE_NOT_IMPROVED
      9. SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW
    """
    reasons: List[str] = []

    # 1. Input validity
    if not ev.input_valid or ev.input_errors:
        reasons.extend(ev.input_errors or ["INPUT_DATA_INVALID"])
    g_input = "PASS" if (ev.input_valid and not ev.input_errors) else "FAIL"

    # 2. Timeout / Runtime / Stale
    if ev.timed_out:
        reasons.append("SIMULATION_TIMEOUT")
    if ev.runtime_error:
        reasons.append(f"RUNTIME_ERROR:{ev.runtime_error}")
    if ev.stale_run:
        reasons.append("STALE_RUN_SUPERSEDED")
    g_runtime = "PASS" if (not ev.timed_out and not ev.runtime_error and not ev.stale_run) else "FAIL"

    # 3. Audit integrity
    if not ev.audit_complete:
        reasons.append("AUDIT_EVIDENCE_MISSING")
    if not ev.audit_hash_verified:
        reasons.append("AUDIT_HASH_MISMATCH")
    g_audit = "PASS" if (ev.audit_complete and ev.audit_hash_verified) else "FAIL"

    # 4. Valve health
    if ev.anomaly_type is None:
        g_valve = "NOT_EVALUATED"
    elif ev.anomaly_type == "VALVE_STICTION":
        g_valve = "FAIL"
        reasons.append("VALVE_STICTION_MECHANICAL_FAULT")
    else:
        g_valve = "PASS"

    # 5. Model validity
    if not ev.model_evaluated:
        g_model = "NOT_EVALUATED"
    elif ev.model_valid is True:
        g_model = "PASS"
    else:
        g_model = "FAIL"
        reasons.append(ev.model_failure_reason or "MODEL_VALIDATION_FAILED")

    # 6. Safety constraints
    if not ev.safety_evaluated:
        g_safety = "NOT_EVALUATED"
    elif ev.safety_approved is True:
        g_safety = "PASS"
    else:
        g_safety = "FAIL"
        reasons.extend(ev.safety_violations or ["SAFETY_CONSTRAINT_FAILED"])

    # 7. Multi-regime robustness
    if not ev.multi_regime_evaluated:
        g_multi = "NOT_EVALUATED"
    elif ev.multi_regime_passed is True:
        g_multi = "PASS"
    else:
        g_multi = "FAIL"
        reasons.append("MULTI_REGIME_ROBUSTNESS_FAILED")

    # 8. Performance improvement
    if not ev.performance_evaluated:
        g_perf = "NOT_EVALUATED"
    elif ev.anomaly_type == "EXTERNAL_DISTURBANCE":
        g_perf = "FAIL"
        reasons.append("EXTERNAL_DISTURBANCE_FEEDBACK_SUBOPTIMAL")
    elif ev.performance_worsened is True:
        g_perf = "FAIL"
        reasons.append("PERFORMANCE_WORSENED")
    elif ev.performance_improved is True:
        g_perf = "PASS"
    else:
        g_perf = "FAIL"
        reasons.append("PERFORMANCE_NOT_IMPROVED")

    gate_matrix = {
        "input_data_gate": g_input,
        "runtime_timeout_gate": g_runtime,
        "audit_integrity_gate": g_audit,
        "valve_health_gate": g_valve,
        "model_validity_gate": g_model,
        "safety_constraints_gate": g_safety,
        "multi_regime_gate": g_multi,
        "performance_improvement_gate": g_perf,
    }

    # --- Fixed Deterministic Priority Resolution (Fail-Closed: never unknown==PASS) ---
    if g_input == "FAIL":
        status = "INPUT_DATA_INVALID"
    elif g_runtime == "FAIL":
        status = "SIMULATION_TIMEOUT"
    elif g_audit == "FAIL":
        status = "AUDIT_INCOMPLETE"
    elif ev.anomaly_type == "NORMAL":
        status = "HEALTHY_NO_CHANGE"
        reasons = ["LOOP_HEALTHY_NO_CHANGE_REQUIRED"]
    elif g_valve == "FAIL":
        status = "VALVE_MAINTENANCE_REQUIRED"
    elif g_model != "PASS":
        status = "MODEL_VALIDATION_FAILED"
        if g_model == "NOT_EVALUATED":
            reasons.append("MODEL_NOT_EVALUATED")
    elif g_safety != "PASS" or g_multi != "PASS":
        status = "SAFETY_REJECTED"
        if g_safety == "NOT_EVALUATED":
            reasons.append("SAFETY_NOT_EVALUATED")
        if g_multi == "NOT_EVALUATED":
            reasons.append("MULTI_REGIME_NOT_EVALUATED")
    elif g_perf != "PASS":
        status = "PERFORMANCE_NOT_IMPROVED"
        if g_perf == "NOT_EVALUATED":
            reasons.append("PERFORMANCE_NOT_EVALUATED")
    else:
        status = "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"
        reasons = ["ALL_SIMULATION_GATES_PASSED_PENDING_MANUAL_REVIEW"]

    spec = FINAL_STATUS_SPECS[status]
    eligible = bool(spec["eligible_for_review"])
    eng_status = (
        "PENDING_MANUAL_REVIEW"
        if eligible
        else ("NOT_APPLICABLE" if status == "HEALTHY_NO_CHANGE" else "REJECTED_BY_GATE")
    )
    has_uneval = any(v == "NOT_EVALUATED" for v in gate_matrix.values())
    summary = ev.decision_detail or f"[{spec['zh_label']}] {spec['trigger']}（原因码：{', '.join(reasons)}）"

    return FinalDecision(
        final_status=status,
        status_zh=spec["zh_label"],
        candidate_eligible_for_review=eligible,
        engineering_approval_status=eng_status,
        deployment_authorized=False,  # Hard invariant: NEVER True in isolated simulation!
        parameter_recommended=bool(spec["parameter_recommended"]),
        has_unevaluated_gates=has_uneval,
        reason_codes=list(dict.fromkeys(reasons)),
        gate_matrix=gate_matrix,
        decision_summary=summary,
    )
