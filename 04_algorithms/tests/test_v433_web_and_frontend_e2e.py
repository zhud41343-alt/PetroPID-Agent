"""V4.3.3 Web API, Approval Sheet, CSV Fail-Closed & Frontend Contract E2E Tests."""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "08_demo_web" / "app.py"
STATIC_DIR = ROOT / "08_demo_web" / "static"


def _load_web_app():
    mod_name = "petropid_demo_web_app"
    spec = importlib.util.spec_from_file_location(mod_name, APP_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod.app


client = TestClient(_load_web_app())


def test_healthz_and_safety_boundary():
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["deployment_authorized"] is False
    assert body["algorithm_version"].startswith("petropid-alg-")
    assert body["dataset_version"].startswith("petropid-sim-")


def test_frontend_html_and_fail_closed_js_contract():
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert "离线仿真基准" in html
    assert "SIMULATION ONLY" in html
    for banned in ("评委 5 步导览", "现场救场", "MCP 14/14 PASS"):
        assert banned not in html, f"Banned demo/judge phrase found in index.html: {banned}"

    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "|| 'PASS'" not in js, "Fail-Closed violation: audit_status must never default to PASS"
    assert "'UNVERIFIED'" in js
    assert "if (!res.ok)" in js
    assert "function escHtml(" in js
    assert "HEALTHY_NO_CHANGE" in js


def test_four_canonical_loop_decision_branches_and_cross_loop_binding():
    expected = {
        "LOOP-006": "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW",
        "LOOP-012": "MODEL_VALIDATION_FAILED",
        "LOOP-021": "VALVE_MAINTENANCE_REQUIRED",
        "LOOP-029": "PERFORMANCE_NOT_IMPROVED",
    }
    run_ids = {}
    for loop_id, exp_status in expected.items():
        res = client.post(f"/api/run/{loop_id}", json={})
        assert res.status_code == 200, f"{loop_id} failed: {res.text}"
        data = res.json()
        assert data["final_status"] == exp_status
        am = data["audit_meta"]
        assert am["audit_verification"]["audit_status"] == "PASS"
        run_ids[loop_id] = am["run_id"]

    # Matching run_id renders printable MOC approval sheet with deployment_authorized=false
    ok_sheet = client.get(f"/api/approval/LOOP-006?run_id={run_ids['LOOP-006']}")
    assert ok_sheet.status_code == 200
    assert "deployment_authorized=<b>false</b>" in ok_sheet.text
    assert run_ids["LOOP-006"] in ok_sheet.text

    # Cross-loop run_id mismatch MUST be rejected (HTTP 409 Conflict)
    bad_sheet = client.get(f"/api/approval/LOOP-001?run_id={run_ids['LOOP-006']}")
    assert bad_sheet.status_code == 409


def test_sandbox_and_csv_valid_plus_malformed_fail_closed():
    sb = client.post(
        "/api/sandbox",
        json={
            "K": 1.6,
            "tau": 16.0,
            "theta": 5.5,
            "init_Kc": 2.1,
            "init_Ti": 8.0,
            "stiction_S": 0.0,
            "stiction_J": 0.0,
            "max_overshoot_pct": 18.0,
        },
    )
    assert sb.status_code == 200
    sb_data = sb.json()
    assert sb_data["audit_meta"]["run_id"]
    assert len(sb_data["safety"]["constraint_audit"]) == 11

    # Valid CSV upload
    rows = ["t,sp,pv,op"]
    for i in range(250):
        sp = 500.0 if i < 40 else 505.0
        pv = sp + 1.8 * math.sin(i * 0.28)
        op = 50.0 + 4.0 * math.cos(i * 0.28)
        rows.append(f"{i * 2},{sp:.2f},{pv:.3f},{op:.3f}")
    ok_csv = client.post(
        "/api/upload_csv",
        json={"filename": "ci_valid.csv", "csv_text": "\n".join(rows), "init_Kc": 1.8, "init_Ti": 10.0},
    )
    assert ok_csv.status_code == 200
    assert ok_csv.json()["audit_meta"]["run_id"]

    # Malformed CSV (missing op column) MUST fail closed with HTTP 400
    bad_csv = client.post(
        "/api/upload_csv",
        json={"filename": "ci_bad.csv", "csv_text": "t,sp,pv\n0,500,499\n1,500,501\n", "init_Kc": 1.5, "init_Ti": 10.0},
    )
    assert bad_csv.status_code == 400
