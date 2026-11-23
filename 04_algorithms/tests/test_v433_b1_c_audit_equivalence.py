"""V4.3.3 P0-01 Equivalent Audit Verification Test: Identical 8 Tamper Faults on BOTH B1 and C."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "07_agents"))

from decision_engine import verify_audit_record
from orchestrator import PetroPIDOrchestrator
from v433_ablation import run_factored_trial


def test_p0_01_b1_and_c_pass_identical_8_tamper_faults_under_same_verifier():
    """Both B1 (Single-Agent) and C (5-Agent) MUST pass clean verification and catch all 8 identical tamper faults."""
    b1_trial = run_factored_trial(
        "LOOP-006",
        system_name="B1_single_agent_monolithic_real_audit",
        enable_retry=True, enable_cache=True, enable_real_audit=True,
        context_mode="monolithic", fail_first_diag=False, duplicate_diag=False,
        max_ms=2.2, experiment_id="TEST-B1", scenario="normal", return_record=True,
    )
    b1_rec = b1_trial["_record"]
    c_rec = PetroPIDOrchestrator().run_loop_workflow("LOOP-006")

    assert verify_audit_record(b1_rec)["audit_status"] == "PASS"
    assert verify_audit_record(c_rec)["audit_status"] == "PASS"

    tamper_ops = [
        ("delete_digest", lambda d: d["audit_meta"].pop("record_digest_sha256", None)),
        ("mutate_diagnosis", lambda d: d["diagnosis"].__setitem__("anomaly_type", "NORMAL")),
        ("mutate_model_fit", lambda d: d["identification"].__setitem__("val_fit_pct", 99.99)),
        ("mutate_safety", lambda d: d["safety"].__setitem__("approved", False)),
        ("mutate_final_status", lambda d: d.__setitem__("final_status", "HEALTHY_NO_CHANGE")),
        ("mutate_trace", lambda d: d["trace"][0].__setitem__("summary", "tampered")),
        ("mutate_input_hash", lambda d: d["audit_meta"].__setitem__("input_hash", "c" * 64)),
        ("mutate_version", lambda d: d["audit_meta"].__setitem__("algorithm_version", "forged-v9")),
    ]

    for label, fn in tamper_ops:
        b1_clone = copy.deepcopy(b1_rec)
        c_clone = copy.deepcopy(c_rec)
        fn(b1_clone)
        fn(c_clone)
        assert verify_audit_record(b1_clone)["audit_status"] == "FAIL", f"B1 failed to catch {label}"
        assert verify_audit_record(c_clone)["audit_status"] == "FAIL", f"C failed to catch {label}"
