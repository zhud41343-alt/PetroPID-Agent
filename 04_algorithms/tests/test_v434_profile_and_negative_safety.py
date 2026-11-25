"""V4.3.4 Formal Profile, Audit Tamper, Fail-Closed & Negative Safety Regression Suite."""
from __future__ import annotations

import copy
import importlib.util
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["PETROPID_LLM_DISABLE_DOTENV"] = "1"

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "05_skills"))
sys.path.insert(0, str(ROOT / "07_agents"))

from decision_engine import verify_audit_record  # noqa: E402
from orchestrator import PetroPIDOrchestrator  # noqa: E402


def _load_web_app():
    mod_name = "petropid_demo_web_app_v434_neg"
    if mod_name in sys.modules:
        return sys.modules[mod_name].app
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / "08_demo_web" / "app.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod.app


client = TestClient(_load_web_app())
orch = PetroPIDOrchestrator()


def test_unsupported_validation_profile_rejected_fail_closed():
    with pytest.raises(ValueError, match="Unsupported validation_profile"):
        orch.run_loop_workflow("LOOP-012", validation_profile="v9.9.9")

    resp = client.post("/api/run/LOOP-012", json={"validation_profile": "v9.9.9"})
    assert resp.status_code in (400, 404, 422)


def test_v434_audit_algorithm_version_and_digest_tamper_detected():
    rec = orch.run_loop_workflow("LOOP-012", validation_profile="v4.3.4")
    assert rec["audit_meta"]["algorithm_version"] == "petropid-alg-v4.3.4"
    assert verify_audit_record(rec)["audit_status"] == "PASS"

    # 1. Tamper algorithm_version -> FAIL
    bad_alg = copy.deepcopy(rec)
    bad_alg["audit_meta"]["algorithm_version"] = "petropid-alg-v4.3.3"
    assert verify_audit_record(bad_alg)["audit_status"] == "FAIL"

    # 2. Tamper / remove validation_evidence -> FAIL
    bad_ev = copy.deepcopy(rec)
    bad_ev["identification"]["validation_evidence"] = None
    assert verify_audit_record(bad_ev)["audit_status"] == "FAIL"

    # 3. Tamper record_digest_sha256 -> FAIL
    bad_dig = copy.deepcopy(rec)
    bad_dig["audit_meta"]["record_digest_sha256"] = "0" * 64
    assert verify_audit_record(bad_dig)["audit_status"] == "FAIL"


def test_deployment_authorized_always_false_across_profiles_and_loops():
    for profile in ("v4.3.3", "v4.3.4"):
        for lid in ("LOOP-001", "LOOP-006", "LOOP-012", "LOOP-021", "LOOP-029"):
            rec = orch.run_loop_workflow(lid, validation_profile=profile)
            assert rec["deployment_authorized"] is False


def test_v434_never_misclassifies_periodic_disturbance_as_dc_load_step():
    for lid in ("LOOP-028", "LOOP-029", "LOOP-030"):
        rec = orch.run_loop_workflow(lid, validation_profile="v4.3.4")
        assert rec["final_status"] == "PERFORMANCE_NOT_IMPROVED"
        ev = (rec.get("identification") or {}).get("validation_evidence") or {}
        assert ev.get("load_step_compensated") is not True


def test_v434_never_falsely_approves_valve_stiction():
    for lid in ("LOOP-018", "LOOP-019", "LOOP-020", "LOOP-021", "LOOP-022"):
        rec = orch.run_loop_workflow(lid, validation_profile="v4.3.4")
        assert rec["final_status"] == "VALVE_MAINTENANCE_REQUIRED"
        assert rec["deployment_authorized"] is False


def test_profile_switch_run_id_input_hash_and_algorithm_version_consistency():
    r3 = client.post("/api/run/LOOP-012", json={"validation_profile": "v4.3.3"})
    r4 = client.post("/api/run/LOOP-012", json={"validation_profile": "v4.3.4"})
    assert r3.status_code == 200 and r4.status_code == 200
    d3, d4 = r3.json(), r4.json()

    assert d3["final_status"] == "MODEL_VALIDATION_FAILED"
    assert d4["final_status"] == "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"
    assert d3["audit_meta"]["algorithm_version"] == "petropid-alg-v4.3.3"
    assert d4["audit_meta"]["algorithm_version"] == "petropid-alg-v4.3.4"
    assert d3["audit_meta"]["run_id"] != d4["audit_meta"]["run_id"]
    assert d3["audit_meta"]["input_hash"] != d4["audit_meta"]["input_hash"]

    # Approval sheet binds strictly to the exact run_id
    sheet4 = client.get(f"/api/approval/LOOP-012?run_id={d4['audit_meta']['run_id']}")
    assert sheet4.status_code == 200
    assert d4["audit_meta"]["run_id"] in sheet4.text
    assert "deployment_authorized=<b>false</b>" in sheet4.text


def test_frontend_profile_selector_and_fail_closed_error_contracts():
    html = (ROOT / "08_demo_web" / "static" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "08_demo_web" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="profileSelect"' in html
    assert '<option value="v4.3.3" selected>' in html
    assert '<option value="v4.3.4">' in html
    assert 'id="profileEvidenceBar"' in html
    # HTTP 500 clears currentData and disables approvalBtn; audit != PASS disables approvalBtn
    assert "currentData = null;" in js
    assert "apBtn.disabled = !(hasValidRunId && auditStatus === 'PASS');" in js


def test_v434_scale_invariant_stiction_score_is_unit_invariant():
    import numpy as np
    from petro_pid.diagnosis import compute_scale_invariant_stiction_score

    t = np.arange(400, dtype=float)
    # Synthetic stick-slip waveform: triangle OP ramping while PV holds flat then jumps
    phase = (t % 40.0) / 40.0
    op = np.where(phase < 0.5, phase * 2.0, 2.0 - phase * 2.0) * 10.0 + 50.0
    pv = np.where((phase < 0.35) | ((phase >= 0.5) & (phase < 0.85)), np.where(phase < 0.5, 0.0, 1.0), np.where(phase < 0.5, (phase - 0.35) / 0.15, 1.0 - (phase - 0.85) / 0.15)) * 4.0 + 100.0

    pred1, sc1, _ = compute_scale_invariant_stiction_score(pv, op)
    # Rescale to MPa / 0-1 normalized engineering units (1000x smaller PV, 100x smaller OP)
    pred2, sc2, _ = compute_scale_invariant_stiction_score(pv * 0.001, op * 0.01)
    assert abs(sc1 - sc2) < 1e-4
    assert pred1 == pred2
    assert pred1 is True


def test_v434_critic_refiner_refuses_c000_model_invalid():
    from petro_pid.simulator import PlantParams, PIDParams
    from petro_pid.tuning import refine_pid_from_safety_feedback

    plant = PlantParams(K=1.8, tau=14.0, theta=8.0, pv_bias=200.0, op_bias=50.0)
    pid = PIDParams(Kc=0.5, Ti=14.0, Td=0.0)
    refined, reason = refine_pid_from_safety_feedback(
        plant,
        pid,
        {"violation_tags": ["VIOLATION_MODEL_VALIDATION_FAILED", "VIOLATION_HIGH_SENSITIVITY_MS"], "max_sensitivity_ms": 1.8},
    )
    assert refined is None
    assert "C000" in reason


def test_v434_critic_refiner_converges_on_tight_margin_plant():
    from petro_pid.simulator import PlantParams
    from petro_pid.tuning import _simc_pid, refine_pid_from_safety_feedback
    from petro_pid.safety_verifier import verify_pid_safety

    plant = PlantParams(K=2.2, tau=16.0, theta=9.5, pv_bias=200.0, op_bias=50.0)
    specs = {"min_gm": 3.5, "min_pm_deg": 60.0, "max_ms": 1.25, "max_overshoot_pct": 5.0}
    pid = _simc_pid(plant.K, plant.tau, plant.theta, tau_c_factor=1.8)
    sv = verify_pid_safety(plant, pid, model_valid=True, **specs)
    assert sv.approved is False
    for _ in range(3):
        pid, _ = refine_pid_from_safety_feedback(plant, pid, sv.to_dict(), min_gm=3.5, min_pm_deg=60.0, max_ms=1.25)
        assert pid is not None
        sv = verify_pid_safety(plant, pid, model_valid=True, **specs)
        if sv.approved:
            break
    assert sv.approved is True
