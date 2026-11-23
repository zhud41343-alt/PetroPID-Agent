"""V4.0 P0 Exhaustive Safety Negative, Fault-Injection, Audit Integrity & Concurrency Tests."""

from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "07_agents"))
sys.path.insert(0, str(ROOT / "08_demo_web"))

from decision_engine import (
    DecisionEvidence,
    FINAL_STATUS_SPECS,
    compute_canonical_hash,
    compute_canonical_output_hash,
    final_decision_aggregation,
)
from orchestrator import PetroPIDOrchestrator
from app import app


def test_all_9_states_never_authorize_real_dcs_deployment():
    cases = [
        DecisionEvidence(input_valid=False, input_errors=["INPUT_NON_FINITE_PV"], audit_status="PASS"),
        DecisionEvidence(input_valid=True, input_errors=[], timed_out=True, audit_status="PASS"),
        DecisionEvidence(input_valid=True, input_errors=[], audit_status="FAIL", audit_hash_verified=False),
        DecisionEvidence(input_valid=True, input_errors=[], anomaly_type="NORMAL", audit_status="PASS"),
        DecisionEvidence(input_valid=True, input_errors=[], anomaly_type="VALVE_STICTION", audit_status="PASS"),
        DecisionEvidence(input_valid=True, input_errors=[], anomaly_type="SLUGGISH_TUNING", model_evaluated=True, model_valid=False, audit_status="PASS"),
        DecisionEvidence(input_valid=True, input_errors=[], anomaly_type="AGGRESSIVE_TUNING", model_evaluated=True, model_valid=True, safety_evaluated=True, safety_approved=False, audit_status="PASS"),
        DecisionEvidence(input_valid=True, input_errors=[], anomaly_type="EXTERNAL_DISTURBANCE", model_evaluated=True, model_valid=True, safety_evaluated=True, safety_approved=True, multi_regime_evaluated=True, multi_regime_passed=True, performance_evaluated=True, performance_improved=False, performance_worsened=True, audit_status="PASS"),
        DecisionEvidence(input_valid=True, input_errors=[], anomaly_type="AGGRESSIVE_TUNING", model_evaluated=True, model_valid=True, safety_evaluated=True, safety_approved=True, multi_regime_evaluated=True, multi_regime_passed=True, performance_evaluated=True, performance_improved=True, performance_worsened=False, audit_status="PASS"),
    ]
    seen = set()
    for ev in cases:
        fd = final_decision_aggregation(ev)
        seen.add(fd.final_status)
        assert fd.deployment_authorized is False
        assert fd.final_status in FINAL_STATUS_SPECS
    assert seen == set(FINAL_STATUS_SPECS.keys())


def test_missing_evidence_never_defaults_to_pass():
    # Audit not evaluated -> MUST fail-closed as AUDIT_INCOMPLETE (P0-04)
    fd0 = final_decision_aggregation(DecisionEvidence(input_valid=True, input_errors=[], anomaly_type="NORMAL"))
    assert fd0.final_status == "AUDIT_INCOMPLETE"
    assert fd0.gate_matrix["audit_integrity_gate"] == "NOT_EVALUATED"

    # Model not evaluated -> MUST fail-closed as MODEL_VALIDATION_FAILED
    fd1 = final_decision_aggregation(DecisionEvidence(input_valid=True, input_errors=[], anomaly_type="AGGRESSIVE_TUNING", model_evaluated=False, audit_status="PASS"))
    assert fd1.final_status == "MODEL_VALIDATION_FAILED"
    assert fd1.gate_matrix["model_validity_gate"] == "NOT_EVALUATED"
    assert fd1.candidate_eligible_for_review is False

    # Safety not evaluated -> MUST fail-closed as SAFETY_REJECTED
    fd2 = final_decision_aggregation(DecisionEvidence(input_valid=True, input_errors=[], anomaly_type="AGGRESSIVE_TUNING", model_evaluated=True, model_valid=True, safety_evaluated=False, audit_status="PASS"))
    assert fd2.final_status == "SAFETY_REJECTED"
    assert fd2.gate_matrix["safety_constraints_gate"] == "NOT_EVALUATED"

    # Multi-regime not evaluated -> MUST fail-closed as SAFETY_REJECTED
    fd3 = final_decision_aggregation(DecisionEvidence(input_valid=True, input_errors=[], anomaly_type="AGGRESSIVE_TUNING", model_evaluated=True, model_valid=True, safety_evaluated=True, safety_approved=True, multi_regime_evaluated=False, audit_status="PASS"))
    assert fd3.final_status == "SAFETY_REJECTED"
    assert fd3.gate_matrix["multi_regime_gate"] == "NOT_EVALUATED"


def test_concurrent_multiple_failures_preserve_all_reason_codes():
    fd = final_decision_aggregation(DecisionEvidence(
        input_valid=True, input_errors=[], anomaly_type="VALVE_STICTION",
        model_evaluated=True, model_valid=False, model_failure_reason="LOW_VAL_R2",
        safety_evaluated=True, safety_approved=False, safety_violations=["VIOLATION_LOW_GAIN_MARGIN"],
        multi_regime_evaluated=True, multi_regime_passed=False,
        audit_status="PASS",
    ))
    assert fd.final_status == "VALVE_MAINTENANCE_REQUIRED"
    assert "VALVE_STICTION_MECHANICAL_FAULT" in fd.reason_codes
    assert "LOW_VAL_R2" in fd.reason_codes
    assert "VIOLATION_LOW_GAIN_MARGIN" in fd.reason_codes
    assert "MULTI_REGIME_ROBUSTNESS_FAILED" in fd.reason_codes


def test_input_fault_injection_nan_unsorted_short_empty():
    orch = PetroPIDOrchestrator()
    meta = {
        "loop_id": "FAULT-TEST", "tag_name": "TIC-ERR", "unit_name": "Test", "loop_type": "Temperature",
        "description": "Fault", "pv_unit": "C", "anomaly_type": "FAULT",
        "true_K": 1.0, "true_tau": 10.0, "true_theta": 2.0, "pv_bias": 50.0, "op_bias": 50.0,
        "init_Kc": 1.0, "init_Ti": 10.0, "init_Td": 0.0, "disturbance_amp": 0.0, "disturbance_period": 0.0, "dt": 1.0,
    }
    # 1. Empty
    r1 = orch._execute_pipeline(meta, np.array([]), np.array([]), np.array([]), np.array([]), 18.0, 2.2, 1.8, 35.0, None, True)
    assert r1["final_status"] == "INPUT_DATA_INVALID"

    # 2. NaN in PV
    t = np.arange(200, dtype=float)
    pv = np.full(200, 50.0); pv[10] = np.nan
    r2 = orch._execute_pipeline(meta, t, np.full(200, 50.0), pv, np.full(200, 50.0), 18.0, 2.2, 1.8, 35.0, None, True)
    assert r2["final_status"] == "INPUT_DATA_INVALID"
    assert "INPUT_NON_FINITE_PV" in r2["audit_meta"]["reason_codes"]

    # 3. Unsorted timestamps
    t_bad = np.arange(200, dtype=float); t_bad[50] = 10.0
    r3 = orch._execute_pipeline(meta, t_bad, np.full(200, 50.0), np.full(200, 50.0), np.full(200, 50.0), 18.0, 2.2, 1.8, 35.0, None, True)
    assert r3["final_status"] == "INPUT_DATA_INVALID"
    assert "INPUT_TIMESTAMPS_NOT_MONOTONIC" in r3["audit_meta"]["reason_codes"]

    # 4. Too short (<100)
    r4 = orch._execute_pipeline(meta, np.arange(50, dtype=float), np.full(50, 50.0), np.full(50, 50.0), np.full(50, 50.0), 18.0, 2.2, 1.8, 35.0, None, True)
    assert r4["final_status"] == "INPUT_DATA_INVALID"


def test_run_id_single_source_of_truth_and_csv_security():
    c = TestClient(app)
    r = c.post("/api/run/LOOP-006").json()
    rid = r["audit_meta"]["run_id"]
    assert r["deployment_authorized"] is False
    assert r["candidate_eligible_for_review"] is True

    # Approval sheet & Audit Bundle MUST reference the EXACT same run_id & hashes!
    html = c.get(f"/api/approval/LOOP-006?run_id={rid}").text
    assert rid in html
    assert r["audit_meta"]["output_sha256"] in html

    bundle = c.get(f"/api/export_bundle/LOOP-006?run_id={rid}").json()
    assert bundle["audit_meta"]["run_id"] == rid
    assert bundle["audit_meta"]["output_hash"] == r["audit_meta"]["output_hash"]
    assert bundle["deployment_authorized"] is False

    # Recompute canonical output hash to prove tamper-evidence
    recomputed = compute_canonical_output_hash(
        final_status=bundle["final_status"],
        final_pid=bundle["final_pid"],
        reason_codes=bundle["final_decision"]["reason_codes"],
        gate_matrix=bundle["final_decision"]["gate_matrix"],
    )
    assert recomputed == bundle["audit_meta"]["output_hash"]

    # CSV upload guardrails: missing column -> 400; NaN values -> INPUT_DATA_INVALID; >512KB -> 413
    assert c.post("/api/upload_csv", json={"filename": "bad.csv", "csv_text": "a,b\n1,2"}).status_code == 400
    nan_csv = "timestamp_s,sp,pv,op\n" + "\n".join(f"{i},50,{'nan' if i==5 else 50},50" for i in range(150))
    r_nan = c.post("/api/upload_csv", json={"filename": "nan.csv", "csv_text": nan_csv}).json()
    assert r_nan["final_status"] == "INPUT_DATA_INVALID"
    big_csv = "sp,pv,op\n" + ("50,50,50\n" * 70000)
    assert c.post("/api/upload_csv", json={"filename": "big.csv", "csv_text": big_csv}).status_code == 413
