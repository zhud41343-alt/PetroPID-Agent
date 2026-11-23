"""V4.3 P0 & P1 Regression Tests:
- P0-02: OOD-20 low-oscillation stiction detection & conflicting evidence guard.
- P0-03: Performance strategy safety rejection (lower nominal IAE MUST still be rejected if robustness fails).
- P1-1: Full record digest tamper detection on in-place valid-format mutations.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "07_agents"))

from petro_pid import PlantParams, PIDParams, ValveParams, verify_pid_safety
from decision_engine import verify_audit_record, compute_full_record_digest
from orchestrator import PetroPIDOrchestrator
from v4_studies import simulate_sopdt_independent


def test_p0_02_ood20_low_oscillation_stiction_never_marked_healthy():
    """P0-02: OOD-20 (STICTION_SOPDT with strong filtering) MUST NOT be misclassified as HEALTHY_NO_CHANGE."""
    orch = PetroPIDOrchestrator()
    sim = simulate_sopdt_independent(
        1.4, 11.0, 2.0, 2.5, PIDParams(0.90, 9.5), ValveParams(4.0, 2.8),
        dist_amp=0.0, dist_period=60.0, noise_std=0.12, seed=9108,
    )
    meta = {
        "loop_id": "OOD-20", "tag_name": "OOD-20", "unit_name": "SOPDT", "loop_type": "Temperature",
        "description": "STICTION_SOPDT", "pv_unit": "C", "anomaly_type": "STICTION_SOPDT",
        "true_K": 1.4, "true_tau": 13.0, "true_theta": 2.5, "pv_bias": 100.0, "op_bias": 50.0,
        "init_Kc": 0.90, "init_Ti": 9.5, "init_Td": 0.0, "disturbance_amp": 0.0, "disturbance_period": 60.0, "dt": 1.0,
    }
    res = orch._execute_pipeline(meta, sim["t"], sim["sp"], sim["pv"], sim["op"], 18.0, 2.2, 1.8, 35.0, None, True)
    assert res["final_status"] != "HEALTHY_NO_CHANGE", "OOD-20 stiction was wrongly classified as HEALTHY!"
    assert res["diagnosis"]["anomaly_type"] == "VALVE_STICTION"
    assert res["final_status"] == "VALVE_MAINTENANCE_REQUIRED"
    assert res["candidate_eligible_for_review"] is False


def test_p0_03_performance_strategy_fails_robustness_and_is_not_approved_directly():
    """P0-03: Performance candidate with lower nominal IAE but failing 5-regime robustness MUST be rejected by verify_pid_safety."""
    orch = PetroPIDOrchestrator()
    res = orch.run_loop_workflow("LOOP-006")
    ident = res["identification"]
    plant = PlantParams(ident["K"], ident["tau"], ident["theta"], ident["pv_bias"], ident["op_bias"])
    perf = next(c for c in res["tuning"]["candidates"] if c["strategy"] == "performance")
    sv_perf = verify_pid_safety(
        plant, PIDParams(perf["Kc"], perf["Ti"], perf["Td"]), dt=1.0,
        model_valid=True, model_val_r2=ident["val_r2"], model_val_fit_pct=ident["val_fit_pct"],
    )
    assert sv_perf.approved is False, "Performance candidate violated robustness and MUST NOT be approved!"
    assert len(sv_perf.violation_tags) > 0


def test_p1_01_full_record_digest_detects_in_place_valid_format_mutations():
    """P1-1: Mutating trace summary, identification metric, or timestamp (while keeping valid format) MUST fail verify_audit_record."""
    orch = PetroPIDOrchestrator()
    rec = orch.run_loop_workflow("LOOP-006")
    assert len(rec["audit_meta"]["record_digest_sha256"]) == 64
    assert verify_audit_record(rec)["audit_status"] == "PASS"

    # 1. Valid-format mutation of trace summary text
    c1 = copy.deepcopy(rec)
    c1["trace"][0]["summary"] = "Tampered summary text with valid format"
    chk1 = verify_audit_record(c1)
    assert chk1["audit_status"] == "FAIL"
    assert "AUDIT_FULL_RECORD_DIGEST_MISMATCH" in chk1["errors"]

    # 2. Valid-format mutation of identification fit %
    c2 = copy.deepcopy(rec)
    c2["identification"]["val_fit_pct"] = 99.99
    chk2 = verify_audit_record(c2)
    assert chk2["audit_status"] == "FAIL"
    assert "AUDIT_FULL_RECORD_DIGEST_MISMATCH" in chk2["errors"]

    # 3. Valid-format mutation of timestamp
    c3 = copy.deepcopy(rec)
    c3["audit_meta"]["timestamp"] = "2099-01-01T00:00:00Z"
    chk3 = verify_audit_record(c3)
    assert chk3["audit_status"] == "FAIL"
    assert "AUDIT_FULL_RECORD_DIGEST_MISMATCH" in chk3["errors"]
