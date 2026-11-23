"""Independent, Unbypassable Final Decision Engine (V4.2 P0 Safety Authority).

This module is the SINGLE SOURCE OF TRUTH for final loop approval status.
Neither LLM prose, Agent orchestrators, frontend UI, nor approval sheets may
override or independently derive `final_status`.

V4.2 P0 Hardening:
- P0-03: Full canonical input evidence hashing covering full t/sp/pv/op series,
  control parameters, safety thresholds, strategy, data source, and versions
  (with explicit NaN/Inf canonicalization and fixed float precision).
- P0-04: Audit gate NEVER defaults to PASS (`audit_status` defaults to
  `NOT_EVALUATED`). Only explicit two-phase evidence verification (`verify_audit_evidence`
  & `verify_audit_record`) can produce `PASS`; any missing/tampered field fails closed
  to `AUDIT_INCOMPLETE`.
- P0-06: Strict separation of known-plant simulation truth vs unknown uploaded CSV
  (`has_known_plant_truth=False` can NEVER emit `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW`).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional

DATASET_VERSION = "petropid-sim-30loops-v2.0"
ALGORITHM_VERSION = "petropid-alg-v4.3.2"
INPUT_HASH_SCHEMA = "petropid.input_evidence.v4.2"
OUTPUT_HASH_SCHEMA = "petropid.output_evidence.v4.2"
RECORD_DIGEST_SCHEMA = "petropid.full_record_digest.v4.3.2"
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

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
        "trigger": "缺少 run_id/输入输出哈希/必要门控证据、未执行独立审计校验或哈希重算不一致",
        "eligible_for_review": False,
        "parameter_recommended": False,
    },
    "HEALTHY_NO_CHANGE": {
        "zh_label": "回路健康，保持原参数",
        "trigger": "诊断为 NORMAL 且数据激励/置信度充分，控制品质良好，无需参数变更",
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
        "zh_label": "过程模型独立验证未通过或缺少独立物理真值",
        "trigger": "辨识激励不足、留出验证 R² < 0.80 或 Fit < 85%、诊断证据不足，或外部未知 CSV 缺乏独立过程真值验证",
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
        "trigger": "数据有效、独立审计通过、已知仿真真值环境模型验证通过、11 项硬约束与多工况通过、且仿真性能净改善",
        "eligible_for_review": True,
        "parameter_recommended": True,
    },
}


def _canonicalize_value(val: Any) -> Any:
    """Canonicalize floats/NaN/Inf/containers deterministically across platforms."""
    if val is None or isinstance(val, (bool, str, int)):
        return val
    if isinstance(val, float):
        if math.isnan(val):
            return "__NAN__"
        if math.isinf(val):
            return "__INF__" if val > 0 else "__NEG_INF__"
        # Normalize -0.0 -> 0.0 and fix 6-decimal representation
        r = round(val, 6)
        return 0.0 if r == 0.0 else r
    if hasattr(val, "tolist"):
        return _canonicalize_value(val.tolist())
    if isinstance(val, dict):
        return {str(k): _canonicalize_value(v) for k, v in sorted(val.items(), key=lambda kv: str(kv[0]))}
    if isinstance(val, (list, tuple)):
        return [_canonicalize_value(v) for v in val]
    return str(val)


def compute_canonical_hash(obj: Any) -> str:
    """Deterministic canonical JSON SHA-256 hash for tamper detection & auditability."""
    canon = _canonicalize_value(obj)
    raw = json.dumps(canon, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_canonical_input_payload(
    *,
    loop_id: str,
    t: Iterable[float],
    sp: Iterable[float],
    pv: Iterable[float],
    op: Iterable[float],
    init_pid: Dict[str, Any],
    safety_config: Dict[str, Any],
    preferred_strategy: Optional[str],
    data_source_type: str,
    plant_context: Optional[Dict[str, Any]] = None,
    dataset_version: str = DATASET_VERSION,
    algorithm_version: str = ALGORITHM_VERSION,
) -> Dict[str, Any]:
    """Construct complete canonical input evidence object covering all critical inputs (P0-03)."""
    return {
        "schema": INPUT_HASH_SCHEMA,
        "dataset_version": dataset_version,
        "algorithm_version": algorithm_version,
        "loop_id": str(loop_id),
        "data_source_type": str(data_source_type),
        "init_pid": {
            "Kc": float(init_pid.get("Kc", 0.0)),
            "Ti": float(init_pid.get("Ti", 0.0)),
            "Td": float(init_pid.get("Td", 0.0)),
        },
        "safety_config": {
            "max_overshoot_pct": float(safety_config.get("max_overshoot_pct", 18.0)),
            "max_ms": float(safety_config.get("max_ms", 2.2)),
            "min_gm": float(safety_config.get("min_gm", 1.8)),
            "min_pm_deg": float(safety_config.get("min_pm_deg", 35.0)),
        },
        "preferred_strategy": preferred_strategy,
        "plant_context": plant_context or {},
        "series": {
            "t": _canonicalize_value(list(t)),
            "sp": _canonicalize_value(list(sp)),
            "pv": _canonicalize_value(list(pv)),
            "op": _canonicalize_value(list(op)),
        },
    }


def compute_canonical_input_hash(**kwargs: Any) -> str:
    payload = build_canonical_input_payload(**kwargs)
    return compute_canonical_hash(payload)


def compute_canonical_output_hash(
    final_status: str,
    final_pid: Dict[str, Any],
    reason_codes: List[str],
    gate_matrix: Dict[str, str],
) -> str:
    return compute_canonical_hash({
        "schema": OUTPUT_HASH_SCHEMA,
        "final_status": final_status,
        "final_pid": final_pid,
        "reason_codes": reason_codes,
        "gate_matrix": gate_matrix,
    })


def verify_pre_decision_audit_evidence(
    *,
    run_id: Optional[str],
    request_id: Optional[str],
    input_hash: Optional[str],
    dataset_version: Optional[str],
    algorithm_version: Optional[str],
    code_commit: Optional[str],
    timestamp: Optional[str],
    trace: Optional[List[Dict[str, Any]]],
    require_trace: bool = True,
) -> Dict[str, Any]:
    """Phase-1 independent audit evidence check BEFORE final decision aggregation (P0-04).

    Never defaults to PASS. Every required audit artifact must be non-empty and valid.
    """
    errors: List[str] = []
    if not run_id or not isinstance(run_id, str) or not run_id.startswith("RUN-"):
        errors.append("AUDIT_MISSING_OR_INVALID_RUN_ID")
    if not request_id or not isinstance(request_id, str):
        errors.append("AUDIT_MISSING_REQUEST_ID")
    if not input_hash or not isinstance(input_hash, str) or len(input_hash) != 64:
        errors.append("AUDIT_MISSING_OR_INVALID_INPUT_HASH")
    if not dataset_version:
        errors.append("AUDIT_MISSING_DATASET_VERSION")
    if not algorithm_version:
        errors.append("AUDIT_MISSING_ALGORITHM_VERSION")
    if not code_commit:
        errors.append("AUDIT_MISSING_CODE_COMMIT")
    if not timestamp:
        errors.append("AUDIT_MISSING_TIMESTAMP")
    if require_trace and (not trace or len(trace) == 0):
        errors.append("AUDIT_MISSING_AGENT_TRACE")
    return {
        "audit_status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }


def compute_full_record_digest(record: Dict[str, Any]) -> str:
    """P0-01 (V4.3.2): Mandatory canonical SHA-256 digest covering the COMPLETE auditable record:
    audit_meta bindings + final_decision + final_pid + diagnosis + identification + tuning +
    safety + baseline_comparison + trace + exported waveforms.

    Note on security boundary: Provides deterministic data-integrity and tamper detection within
    isolated simulation; cryptographic non-repudiation requires an external KMS/PKI signing root.
    Display-only auxiliary plots (`identification_plot`, `phase_portrait`, `nyquist_plot`) are
    explicitly excluded from this digest and documented as non-protected display projections.
    """
    am = record.get("audit_meta") or {}
    return compute_canonical_hash({
        "schema": RECORD_DIGEST_SCHEMA,
        "run_id": am.get("run_id"),
        "request_id": am.get("request_id"),
        "timestamp": am.get("timestamp"),
        "input_hash": am.get("input_hash"),
        "output_hash": am.get("output_hash"),
        "dataset_version": am.get("dataset_version"),
        "algorithm_version": am.get("algorithm_version"),
        "code_commit": am.get("code_commit"),
        "data_source_type": am.get("data_source_type"),
        "has_known_plant_truth": am.get("has_known_plant_truth"),
        "final_status": record.get("final_status"),
        "deployment_authorized": record.get("deployment_authorized"),
        "final_pid": record.get("final_pid"),
        "final_decision": record.get("final_decision"),
        "diagnosis": record.get("diagnosis"),
        "identification": record.get("identification"),
        "tuning": record.get("tuning"),
        "safety": record.get("safety"),
        "baseline_comparison": record.get("baseline_comparison"),
        "trace": record.get("trace"),
        "waveforms": record.get("waveforms"),
    })


def verify_audit_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Phase-2 independent tamper & completeness verifier (V4.3.2 P0-01: record_digest_sha256 is MANDATORY)."""
    errors: List[str] = []
    am = record.get("audit_meta")
    fd = record.get("final_decision")
    if not isinstance(am, dict):
        return {"audit_status": "FAIL", "errors": ["AUDIT_META_MISSING"]}
    if not isinstance(fd, dict):
        return {"audit_status": "FAIL", "errors": ["FINAL_DECISION_MISSING"]}

    pre = verify_pre_decision_audit_evidence(
        run_id=am.get("run_id"),
        request_id=am.get("request_id"),
        input_hash=am.get("input_hash"),
        dataset_version=am.get("dataset_version"),
        algorithm_version=am.get("algorithm_version"),
        code_commit=am.get("code_commit"),
        timestamp=am.get("timestamp"),
        trace=record.get("trace"),
        require_trace=True,
    )
    errors.extend(pre["errors"])

    out_hash = am.get("output_hash")
    if not isinstance(out_hash, str) or not _HEX64_RE.match(out_hash):
        errors.append("AUDIT_MISSING_OR_INVALID_OUTPUT_HASH")
    else:
        recomputed = compute_canonical_output_hash(
            final_status=str(record.get("final_status", "")),
            final_pid=record.get("final_pid", {}),
            reason_codes=fd.get("reason_codes", []),
            gate_matrix=fd.get("gate_matrix", {}),
        )
        if not hmac.compare_digest(recomputed, out_hash):
            errors.append("AUDIT_OUTPUT_HASH_MISMATCH")

    # P0-01 (V4.3.2): Full record digest is STRICTLY MANDATORY — NEVER skipped if absent or None!
    rec_digest = am.get("record_digest_sha256")
    if rec_digest is None or rec_digest == "":
        errors.append("AUDIT_MISSING_RECORD_DIGEST_LEGACY_OR_UNVERIFIED")
    elif not isinstance(rec_digest, str) or not _HEX64_RE.match(rec_digest):
        errors.append("AUDIT_MALFORMED_RECORD_DIGEST")
    else:
        expected_digest = compute_full_record_digest(record)
        if not hmac.compare_digest(expected_digest, rec_digest):
            errors.append("AUDIT_FULL_RECORD_DIGEST_MISMATCH")

    if record.get("deployment_authorized") is not False:
        errors.append("AUDIT_UNAUTHORIZED_DEPLOYMENT_FLAG")

    if record.get("final_status") != fd.get("final_status") or am.get("final_status") != fd.get("final_status"):
        errors.append("AUDIT_STATUS_CONSISTENCY_MISMATCH")

    gm = fd.get("gate_matrix") or {}
    if gm.get("model_validity_gate") in ("PASS", "FAIL") and record.get("identification") is None:
        errors.append("AUDIT_MISSING_MODEL_EVIDENCE")
    if gm.get("safety_constraints_gate") in ("PASS", "FAIL") and record.get("safety") is None:
        errors.append("AUDIT_MISSING_SAFETY_EVIDENCE")

    return {
        "audit_status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "digest_schema": RECORD_DIGEST_SCHEMA,
        "integrity_scope": "canonical_sha256_full_record_integrity_without_external_kms",
        "non_protected_display_fields": ["identification_plot", "phase_portrait", "nyquist_plot", "knowledge", "anti_bloat_metrics"],
    }


@dataclass
class DecisionEvidence:
    """Structured, validated evidence bundle consumed by final_decision_aggregation.

    V4.2 P0-04: `audit_status` defaults to "NOT_EVALUATED" (NEVER PASS).
    Callers MUST run independent audit verification and pass `audit_status="PASS"`
    (or `audit_complete=True, audit_hash_verified=True` after verification).
    """
    input_valid: bool
    input_errors: List[str]
    timed_out: bool = False
    runtime_error: Optional[str] = None
    stale_run: bool = False
    anomaly_type: Optional[str] = None
    diagnosis_evidence_sufficient: bool = True
    diagnosis_uncertainty_reason: Optional[str] = None
    has_known_plant_truth: bool = True
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
    audit_status: str = "NOT_EVALUATED"          # PASS | FAIL | NOT_EVALUATED
    audit_errors: Optional[List[str]] = None
    audit_complete: Optional[bool] = None        # Optional legacy hook; None => NOT_EVALUATED
    audit_hash_verified: Optional[bool] = None   # Optional legacy hook; None => NOT_EVALUATED
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


def _resolve_audit_gate(ev: DecisionEvidence) -> tuple[str, List[str]]:
    """Resolve tri-state audit gate (PASS | FAIL | NOT_EVALUATED) without ever defaulting to PASS."""
    errs: List[str] = list(ev.audit_errors or [])
    if ev.audit_complete is False:
        errs.append("AUDIT_EVIDENCE_MISSING")
    if ev.audit_hash_verified is False:
        errs.append("AUDIT_HASH_MISMATCH")
    if errs or ev.audit_status == "FAIL":
        if not errs:
            errs.append("AUDIT_VERIFICATION_FAILED")
        return "FAIL", errs
    if ev.audit_status == "PASS":
        return "PASS", []
    if ev.audit_complete is True and ev.audit_hash_verified is True:
        return "PASS", []
    return "NOT_EVALUATED", ["AUDIT_NOT_EVALUATED"]


def final_decision_aggregation(ev: DecisionEvidence) -> FinalDecision:
    """Unbypassable deterministic final decision engine (V4.2).

    Collects ALL failure reason codes simultaneously, then applies fixed strict priority:
      1. INPUT_DATA_INVALID
      2. SIMULATION_TIMEOUT
      3. AUDIT_INCOMPLETE (both FAIL and NOT_EVALUATED fail closed!)
      4. HEALTHY_NO_CHANGE (only when diagnosis evidence is sufficient)
      5. VALVE_MAINTENANCE_REQUIRED
      6. MODEL_VALIDATION_FAILED (also covers unknown-CSV without plant truth & insufficient diagnosis evidence)
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

    # 3. Audit integrity (P0-04: tri-state, NEVER defaults to PASS)
    g_audit, audit_reasons = _resolve_audit_gate(ev)
    reasons.extend(audit_reasons)

    # 4. Valve health
    if ev.anomaly_type is None:
        g_valve = "NOT_EVALUATED"
    elif ev.anomaly_type == "VALVE_STICTION":
        g_valve = "FAIL"
        reasons.append("VALVE_STICTION_MECHANICAL_FAULT")
    else:
        g_valve = "PASS"

    # 4b. Diagnosis evidence sufficiency (P1 SOPDT low-excitation / ambiguity guard)
    if not ev.diagnosis_evidence_sufficient:
        reasons.append(ev.diagnosis_uncertainty_reason or "DIAGNOSIS_EVIDENCE_INSUFFICIENT")

    # 5. Model validity & independent plant truth boundary (P0-06)
    if not ev.has_known_plant_truth:
        reasons.append("UNVERIFIED_EXTERNAL_CSV_NO_PLANT_TRUTH")
    if not ev.model_evaluated:
        g_model = "NOT_EVALUATED"
    elif ev.model_valid is True and ev.has_known_plant_truth:
        g_model = "PASS"
    else:
        g_model = "FAIL"
        if ev.model_valid is not True:
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
    elif g_audit != "PASS":
        status = "AUDIT_INCOMPLETE"
    elif ev.anomaly_type == "NORMAL" and ev.diagnosis_evidence_sufficient:
        status = "HEALTHY_NO_CHANGE"
        reasons = ["LOOP_HEALTHY_NO_CHANGE_REQUIRED"]
    elif g_valve == "FAIL":
        status = "VALVE_MAINTENANCE_REQUIRED"
    elif not ev.diagnosis_evidence_sufficient:
        status = "MODEL_VALIDATION_FAILED"
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
    approval_state = (
        "PENDING_MANUAL_REVIEW"
        if eligible
        else ("NOT_APPLICABLE" if status == "HEALTHY_NO_CHANGE" else "REJECTED_BY_GATE")
    )
    has_uneval = any(v == "NOT_EVALUATED" for v in gate_matrix.values())
    dedup_reasons = list(dict.fromkeys(reasons))
    summary = ev.decision_detail.strip() or f"{spec['zh_label']}（原因码：{', '.join(dedup_reasons)}）"

    return FinalDecision(
        final_status=status,
        status_zh=spec["zh_label"],
        candidate_eligible_for_review=eligible,
        engineering_approval_status=approval_state,
        deployment_authorized=False,
        parameter_recommended=bool(spec["parameter_recommended"]),
        has_unevaluated_gates=has_uneval,
        reason_codes=dedup_reasons,
        gate_matrix=gate_matrix,
        decision_summary=summary,
    )
