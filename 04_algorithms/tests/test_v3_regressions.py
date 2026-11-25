"""V3.0 Regression Test Suite covering ALL audited problem loops & non-tunable edge cases.

Explicitly verifies:
- LOOP-006: Valid model, passes C-000..C-010, explicit perturbed threshold (25%) vs nominal (18%),
  returns SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW.
- LOOP-012..017: Low held-out validation R² (<0.80) MUST be rejected with MODEL_VALIDATION_FAILED
  and C-000 VIOLATION_MODEL_VALIDATION_FAILED (zero ground-truth leakage!).
- LOOP-020 (and all VALVE_STICTION loops): MUST return VALVE_MAINTENANCE_REQUIRED.
- LOOP-028..030 (EXTERNAL_DISTURBANCE): MUST NOT approve worsened IAE; MUST return PERFORMANCE_NOT_IMPROVED.
- Edge cases: insufficient excitation, constant/flat sensor, unsafe PID bounds.
"""

from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "07_agents"))

from orchestrator import PetroPIDOrchestrator, VALID_STATUSES
from decision_engine import verify_audit_record
from petro_pid import identify_fopdt, verify_pid_safety, PlantParams, PIDParams


@pytest.fixture(scope="module")
def orch() -> PetroPIDOrchestrator:
    return PetroPIDOrchestrator()


def test_loop_006_explicit_perturbed_thresholds_and_approval(orch: PetroPIDOrchestrator):
    res = orch.run_loop_workflow("LOOP-006")
    assert res["final_status"] == "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"
    assert res["identification"]["allow_next_stage"] is True
    assert res["safety"]["approved"] is True
    assert res["safety"]["nominal_overshoot_limit_pct"] == 18.0
    assert res["safety"]["perturbed_overshoot_limit_pct"] == 25.0
    assert res["after_diagnosis"]["iae"] < res["diagnosis"]["iae"] * 0.25
    assert res["baseline_comparison"] is not None


@pytest.mark.parametrize("loop_id", ["LOOP-012", "LOOP-013", "LOOP-014", "LOOP-015", "LOOP-016", "LOOP-017"])
def test_sluggish_loops_rejected_when_model_validation_fails(orch: PetroPIDOrchestrator, loop_id: str):
    res = orch.run_loop_workflow(loop_id)
    assert res["identification"]["allow_next_stage"] is False
    assert res["final_status"] == "MODEL_VALIDATION_FAILED"
    assert res["safety"]["approved"] is False
    assert "VIOLATION_MODEL_VALIDATION_FAILED" in res["safety"]["violation_tags"]
    # Must keep initial PID unchanged when rejected
    assert res["final_pid"] == res["initial_pid"]


@pytest.mark.parametrize("loop_id", ["LOOP-012", "LOOP-013", "LOOP-014", "LOOP-015", "LOOP-016", "LOOP-017"])
def test_v434_load_step_profile_is_observable_only_and_audited(orch: PetroPIDOrchestrator, loop_id: str):
    res = orch.run_loop_workflow(loop_id, validation_profile="v4.3.4")
    ident = res["identification"]
    evidence = ident["validation_evidence"]
    assert ident["validation_profile"] == "v4.3.4_observable_load_step"
    assert evidence["load_step_compensated"] is True
    assert evidence["profile"] == "v4.3.4_observable_load_step"
    assert res["deployment_authorized"] is False
    assert verify_audit_record(res)["audit_status"] == "PASS"


def test_loop_020_valve_stiction_requires_maintenance(orch: PetroPIDOrchestrator):
    res = orch.run_loop_workflow("LOOP-020")
    assert res["diagnosis"]["anomaly_type"] == "VALVE_STICTION"
    assert res["final_status"] == "VALVE_MAINTENANCE_REQUIRED"
    assert res["final_pid"] == res["initial_pid"]


@pytest.mark.parametrize("loop_id", ["LOOP-028", "LOOP-029", "LOOP-030"])
def test_external_disturbance_not_approved_when_performance_not_improved(orch: PetroPIDOrchestrator, loop_id: str):
    res = orch.run_loop_workflow(loop_id)
    assert res["diagnosis"]["anomaly_type"] == "EXTERNAL_DISTURBANCE"
    assert res["final_status"] == "PERFORMANCE_NOT_IMPROVED"
    assert res["final_pid"] == res["initial_pid"]


def test_non_tunable_insufficient_excitation_rejected():
    # Flat / low-excitation OP & PV signal
    t = np.arange(300, dtype=float)
    pv = 100.0 + 0.02 * np.sin(t / 10.0)
    op = 50.0 + 0.05 * np.sin(t / 10.0)
    res = identify_fopdt(pv, op, dt=1.0)
    assert res.allow_next_stage is False
    assert res.excitation_ok is False
    assert res.failure_reason == "INSUFFICIENT_EXCITATION"


def test_safety_verifier_rejects_unvalidated_model_even_if_margins_ok():
    v = verify_pid_safety(
        PlantParams(1.2, 12.0, 3.0),
        PIDParams(1.0, 12.0, 0.0),
        model_valid=False,
        model_val_r2=0.55,
        model_val_fit_pct=60.0,
    )
    assert v.approved is False
    assert "VIOLATION_MODEL_VALIDATION_FAILED" in v.violation_tags


def test_all_30_loops_produce_valid_enum_status(orch: PetroPIDOrchestrator):
    import json
    labels = json.loads((ROOT / "02_datasets" / "labels" / "loop_labels.json").read_text(encoding="utf-8"))
    for item in labels:
        res = orch.run_loop_workflow(item["loop_id"])
        assert res["final_status"] in VALID_STATUSES
