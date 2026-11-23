"""V4.2 P0 Exhaustive Audit Architecture & Data Boundary Tests (P0-01 through P0-06)."""

from __future__ import annotations

import copy
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "07_agents"))
sys.path.insert(0, str(ROOT / "08_demo_web"))

from decision_engine import (
    DecisionEvidence,
    compute_canonical_input_hash,
    final_decision_aggregation,
    verify_audit_record,
)
from orchestrator import PetroPIDOrchestrator
import app as web_app


def test_p0_01_run_id_uniqueness_under_high_concurrency_and_same_second():
    """P0-01: Identical & concurrent runs in the same second MUST produce globally unique run_ids."""
    orch = PetroPIDOrchestrator()

    def _run(lid: str):
        return orch.run_loop_workflow(lid)

    targets = ["LOOP-006"] * 8 + ["LOOP-012"] * 4 + ["LOOP-021"] * 4
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(_run, targets))

    run_ids = [r["audit_meta"]["run_id"] for r in results]
    req_ids = [r["audit_meta"]["request_id"] for r in results]
    assert len(set(run_ids)) == len(targets), "run_id collision detected!"
    assert len(set(req_ids)) == len(targets), "request_id collision detected!"

    # Identical inputs share input_hash and cache_key, yet each execution has its own run_id
    l6_hashes = {r["audit_meta"]["input_hash"] for r in results[:8]}
    l6_keys = {r["audit_meta"]["cache_key"] for r in results[:8]}
    assert len(l6_hashes) == 1
    assert len(l6_keys) == 1
    assert all(r["audit_meta"]["cache_hit"] is False for r in results)


def test_p0_02_strict_cross_loop_and_missing_run_id_binding():
    """P0-02: Approval sheet & audit bundle MUST reject wrong loop_id (409), missing (404), evicted (410), tampered (422)."""
    c = TestClient(web_app.app)
    r6 = c.post("/api/run/LOOP-006").json()
    rid6 = r6["audit_meta"]["run_id"]

    # 1. Correct loop_id + run_id -> 200
    assert c.get(f"/api/approval/LOOP-006?run_id={rid6}").status_code == 200
    assert c.get(f"/api/export_bundle/LOOP-006?run_id={rid6}").status_code == 200

    # 2. Cross-loop binding (LOOP-006 run_id queried on LOOP-012) -> 409 Conflict
    assert c.get(f"/api/approval/LOOP-012?run_id={rid6}").status_code == 409
    assert c.get(f"/api/export_bundle/LOOP-012?run_id={rid6}").status_code == 409

    # 3. Non-existent run_id -> 404 Not Found (NEVER silently falls back or reruns!)
    assert c.get("/api/approval/LOOP-006?run_id=RUN-NONEXISTENT-999").status_code == 404
    assert c.get("/api/export_bundle/LOOP-006?run_id=RUN-NONEXISTENT-999").status_code == 404

    # 4. Evicted run_id -> 410 Gone
    web_app.EVICTED_RUN_IDS.add("RUN-EVICTED-TEST-001")
    try:
        assert c.get("/api/approval/LOOP-006?run_id=RUN-EVICTED-TEST-001").status_code == 410
    finally:
        web_app.EVICTED_RUN_IDS.discard("RUN-EVICTED-TEST-001")

    # 5. Tampered audit record in RUN_STORE -> 422 Unprocessable Entity
    tampered = copy.deepcopy(r6)
    tampered["final_status"] = "HEALTHY_NO_CHANGE"
    bad_rid = "RUN-TAMPERED-TEST-001"
    tampered["audit_meta"]["run_id"] = bad_rid
    web_app.RUN_STORE[bad_rid] = tampered
    try:
        assert c.get(f"/api/approval/LOOP-006?run_id={bad_rid}").status_code == 422
        assert c.get(f"/api/export_bundle/LOOP-006?run_id={bad_rid}").status_code == 422
    finally:
        web_app.RUN_STORE.pop(bad_rid, None)

    # 6. Unrun loop with no run_id -> 404 (NEVER auto-reruns to fabricate an approval sheet!)
    web_app.LATEST_LOOP_RUN.pop("LOOP-030", None)
    assert c.get("/api/approval/LOOP-030").status_code == 404


def test_p0_03_complete_canonical_input_hash_sensitivity():
    """P0-03: Modifying ANY critical input (single PV/SP/OP/t point, safety threshold, strategy, PID) MUST change input_hash."""
    base_kwargs = dict(
        loop_id="LOOP-006",
        t=np.arange(120, dtype=float),
        sp=np.full(120, 50.0),
        pv=np.linspace(49.0, 51.0, 120),
        op=np.full(120, 45.0),
        init_pid={"Kc": 1.5, "Ti": 10.0, "Td": 0.0},
        safety_config={"max_overshoot_pct": 18.0, "max_ms": 2.2, "min_gm": 1.8, "min_pm_deg": 35.0},
        preferred_strategy=None,
        data_source_type="SIMULATOR_BENCHMARK_30LOOPS",
        plant_context={"dt": 1.0, "true_K": 1.5},
    )
    h0 = compute_canonical_input_hash(**base_kwargs)
    assert h0 == compute_canonical_input_hash(**base_kwargs)  # Deterministic

    mutations = []
    # Single PV point
    pv2 = base_kwargs["pv"].copy(); pv2[42] += 0.001
    mutations.append(("pv_point", {**base_kwargs, "pv": pv2}))
    # Single SP point
    sp2 = base_kwargs["sp"].copy(); sp2[10] += 0.5
    mutations.append(("sp_point", {**base_kwargs, "sp": sp2}))
    # Single OP point
    op2 = base_kwargs["op"].copy(); op2[99] -= 0.1
    mutations.append(("op_point", {**base_kwargs, "op": op2}))
    # Timestamp shift
    t2 = base_kwargs["t"].copy(); t2[5] += 0.25
    mutations.append(("timestamp", {**base_kwargs, "t": t2}))
    # Safety threshold
    mutations.append(("safety_max_ms", {**base_kwargs, "safety_config": {**base_kwargs["safety_config"], "max_ms": 1.8}}))
    # Strategy
    mutations.append(("strategy", {**base_kwargs, "preferred_strategy": "conservative"}))
    # Initial PID
    mutations.append(("init_pid", {**base_kwargs, "init_pid": {"Kc": 1.6, "Ti": 10.0, "Td": 0.0}}))
    # Plant context
    mutations.append(("plant_ctx", {**base_kwargs, "plant_context": {"dt": 1.0, "true_K": 1.6}}))

    for name, kw in mutations:
        hm = compute_canonical_input_hash(**kw)
        assert hm != h0, f"input_hash failed to change on mutation: {name}"

    # NaN / Inf canonicalization must succeed deterministically without crashing
    pv_nan = base_kwargs["pv"].copy(); pv_nan[0] = np.nan; pv_nan[1] = np.inf
    h_nan = compute_canonical_input_hash(**{**base_kwargs, "pv": pv_nan})
    assert len(h_nan) == 64 and h_nan != h0


def test_p0_04_audit_gate_never_defaults_pass_and_detects_tampering():
    """P0-04: Default DecisionEvidence MUST fail-closed (NOT_EVALUATED -> AUDIT_INCOMPLETE); tampering MUST be caught."""
    fd_default = final_decision_aggregation(DecisionEvidence(input_valid=True, input_errors=[], anomaly_type="NORMAL"))
    assert fd_default.final_status == "AUDIT_INCOMPLETE"
    assert fd_default.gate_matrix["audit_integrity_gate"] == "NOT_EVALUATED"

    orch = PetroPIDOrchestrator()
    rec = orch.run_loop_workflow("LOOP-006")
    assert verify_audit_record(rec)["audit_status"] == "PASS"

    # Tamper each required audit field and confirm verify_audit_record catches ALL of them
    tamper_ops = [
        ("dataset_version", lambda d: d["audit_meta"].pop("dataset_version")),
        ("input_hash", lambda d: d["audit_meta"].__setitem__("input_hash", "short")),
        ("output_hash", lambda d: d["audit_meta"].__setitem__("output_hash", "0" * 64)),
        ("run_id", lambda d: d["audit_meta"].__setitem__("run_id", "")),
        ("timestamp", lambda d: d["audit_meta"].__setitem__("timestamp", "")),
        ("trace", lambda d: d.__setitem__("trace", [])),
        ("identification", lambda d: d.__setitem__("identification", None)),
        ("safety", lambda d: d.__setitem__("safety", None)),
        ("deployment_authorized", lambda d: d.__setitem__("deployment_authorized", True)),
    ]
    for label, fn in tamper_ops:
        clone = copy.deepcopy(rec)
        fn(clone)
        chk = verify_audit_record(clone)
        assert chk["audit_status"] == "FAIL", f"Failed to detect tampering of: {label}"


def test_p0_06_unknown_uploaded_csv_never_claims_validated_plant_improvement():
    """P0-06: Unknown uploaded CSV has no ground-truth plant; MUST NOT emit SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW."""
    c = TestClient(web_app.app)
    # Generate a clean, well-excited FOPDT-like CSV series
    n = 250
    t = np.arange(n, dtype=float)
    sp = np.where(t < 40, 50.0, np.where(t < 140, 55.0, 50.0))
    op = np.clip(50.0 + 1.2 * (sp - 50.0) + 2.0 * np.sin(t / 12.0), 5.0, 95.0)
    pv = np.zeros(n)
    pv[0] = 50.0
    for k in range(1, n):
        pv[k] = pv[k - 1] + (1.4 * (op[max(0, k - 3)] - 50.0) - (pv[k - 1] - 50.0)) / 10.0
    csv_lines = ["timestamp_s,sp,pv,op"] + [f"{t[i]:.1f},{sp[i]:.3f},{pv[i]:.3f},{op[i]:.3f}" for i in range(n)]
    r = c.post("/api/upload_csv", json={"filename": "plant_hist.csv", "csv_text": "\n".join(csv_lines), "init_Kc": 1.2, "init_Ti": 12.0})
    assert r.status_code == 200
    d = r.json()
    assert d["audit_meta"]["data_source_type"] == "UPLOADED_HISTORICAL_CSV"
    assert d["audit_meta"]["has_known_plant_truth"] is False
    assert d["loop_meta"]["true_K"] is None
    assert d["final_status"] != "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"
    assert d["candidate_eligible_for_review"] is False
    assert d["deployment_authorized"] is False
