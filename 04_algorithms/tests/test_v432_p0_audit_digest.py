"""V4.3.2 P0-01 Exhaustive 12-Case Mandatory Audit Digest & Legacy Rejection Tests."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "07_agents"))
sys.path.insert(0, str(ROOT / "08_demo_web"))

from decision_engine import verify_audit_record
from orchestrator import PetroPIDOrchestrator
import app as web_app


def test_p0_01_all_12_mandatory_digest_and_tamper_scenarios():
    """Verify all 12 required negative scenarios fail verify_audit_record and HTTP 422 on /api/approval."""
    orch = PetroPIDOrchestrator()
    base = orch.run_loop_workflow("LOOP-006")
    assert verify_audit_record(base)["audit_status"] == "PASS"

    cases = [
        ("01_delete_record_digest", lambda d: d["audit_meta"].pop("record_digest_sha256", None)),
        ("02_null_record_digest", lambda d: d["audit_meta"].__setitem__("record_digest_sha256", None)),
        ("03_wrong_hex64_digest", lambda d: d["audit_meta"].__setitem__("record_digest_sha256", "a" * 64)),
        ("04_mutate_trace_content", lambda d: d["trace"][0].__setitem__("summary", "forged summary")),
        ("05_mutate_model_accuracy", lambda d: d["identification"].__setitem__("val_fit_pct", 99.98)),
        ("06_mutate_input_hash", lambda d: d["audit_meta"].__setitem__("input_hash", "b" * 64)),
        ("07_mutate_safety_result", lambda d: d["safety"].__setitem__("multi_regime_pass_rate_pct", 40.0)),
        ("08_mutate_final_status", lambda d: d.__setitem__("final_status", "HEALTHY_NO_CHANGE")),
        ("09_mutate_algorithm_version", lambda d: d["audit_meta"].__setitem__("algorithm_version", "petropid-alg-v9.9")),
        ("10_mutate_exported_waveform_point", lambda d: d["waveforms"]["pv_after"].__setitem__(5, d["waveforms"]["pv_after"][5] + 0.05)),
        ("11_delete_safety_object", lambda d: d.__setitem__("safety", None)),
        ("12_legacy_record_without_digest_via_http", lambda d: d["audit_meta"].pop("record_digest_sha256", None)),
    ]

    for name, fn in cases:
        clone = copy.deepcopy(base)
        fn(clone)
        res = verify_audit_record(clone)
        assert res["audit_status"] == "FAIL", f"Scenario {name} wrongly returned PASS!"
        assert len(res["errors"]) > 0

    # Verify legacy record loaded into RUN_STORE (simulating container restart loading old SQLite row) -> HTTP 422
    c = TestClient(web_app.app)
    legacy = copy.deepcopy(base)
    legacy["audit_meta"].pop("record_digest_sha256", None)
    legacy_rid = "RUN-LEGACY-V42-0001"
    legacy["audit_meta"]["run_id"] = legacy_rid
    web_app.RUN_STORE[legacy_rid] = legacy
    try:
        r_app = c.get(f"/api/approval/LOOP-006?run_id={legacy_rid}")
        r_bun = c.get(f"/api/export_bundle/LOOP-006?run_id={legacy_rid}")
        assert r_app.status_code == 422, f"Legacy record must be rejected with 422, got {r_app.status_code}"
        assert r_bun.status_code == 422, f"Legacy bundle must be rejected with 422, got {r_bun.status_code}"
    finally:
        web_app.RUN_STORE.pop(legacy_rid, None)
