"""Live Render Public HTTPS End-to-End HTTP Verification Script (V4.2)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx

BASE = "https://petropid-agent.onrender.com"
OUT = Path(__file__).resolve().parents[1] / "competition_v4" / "render_live_http_verification.json"


def _timed(fn):
    t0 = time.perf_counter()
    r = fn()
    return r, round((time.perf_counter() - t0) * 1000.0, 1)


def main() -> None:
    report = {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE,
        "checks": {},
    }
    with httpx.Client(timeout=45.0) as client:
        # Wait up to 90s for Render to finish rolling over to 4.2.0
        for _ in range(12):
            r, ms = _timed(lambda: client.get(f"{BASE}/healthz"))
            if r.status_code == 200 and r.json().get("version") == "4.2.0":
                break
            time.sleep(8.0)

        # 1. /healthz + live LLM probe
        r, ms = _timed(lambda: client.get(f"{BASE}/healthz?probe_llm=true"))
        report["checks"]["healthz_probe"] = {"status_code": r.status_code, "latency_ms": ms, "body": r.json()}

        # 2. /api/loops
        r, ms = _timed(lambda: client.get(f"{BASE}/api/loops"))
        report["checks"]["api_loops"] = {"status_code": r.status_code, "latency_ms": ms, "count": r.json().get("count")}

        # 3. /api/benchmark
        r, ms = _timed(lambda: client.get(f"{BASE}/api/benchmark"))
        bd = r.json()
        report["checks"]["api_benchmark"] = {
            "status_code": r.status_code, "latency_ms": ms,
            "version": bd.get("version"),
            "independent_evaluation": bd.get("independent_evaluation"),
        }

        # 4. /api/openjiuwen
        r, ms = _timed(lambda: client.get(f"{BASE}/api/openjiuwen"))
        report["checks"]["api_openjiuwen"] = {"status_code": r.status_code, "latency_ms": ms, "sdk_version": r.json().get("sdk_version")}

        # 5. Key 4 loops: LOOP-006, LOOP-012, LOOP-021, LOOP-029
        key_runs = {}
        for lid in ("LOOP-006", "LOOP-012", "LOOP-021", "LOOP-029"):
            r, ms = _timed(lambda l=lid: client.post(f"{BASE}/api/run/{l}"))
            d = r.json()
            key_runs[lid] = {
                "status_code": r.status_code,
                "latency_ms": ms,
                "run_id": d["audit_meta"]["run_id"],
                "request_id": d["audit_meta"]["request_id"],
                "code_commit": d["audit_meta"]["code_commit"],
                "input_hash": d["audit_meta"]["input_hash"],
                "output_hash": d["audit_meta"]["output_hash"],
                "llm_mode": d["llm_mode"],
                "final_status": d["final_status"],
                "deployment_authorized": d["deployment_authorized"],
                "audit_verification": d["audit_meta"].get("audit_verification"),
            }
        report["checks"]["key_loops"] = key_runs

        # 6. P0-02 Strict approval & export_bundle binding on live Render
        rid6 = key_runs["LOOP-006"]["run_id"]
        r_ok, ms_ok = _timed(lambda: client.get(f"{BASE}/api/approval/LOOP-006?run_id={rid6}"))
        r_cross, ms_cross = _timed(lambda: client.get(f"{BASE}/api/approval/LOOP-012?run_id={rid6}"))
        r_miss, ms_miss = _timed(lambda: client.get(f"{BASE}/api/approval/LOOP-006?run_id=RUN-NO-SUCH-ID"))
        r_bun, ms_bun = _timed(lambda: client.get(f"{BASE}/api/export_bundle/LOOP-006?run_id={rid6}"))
        report["checks"]["p0_02_strict_binding"] = {
            "approval_valid_200": r_ok.status_code,
            "approval_has_5regime_table": "5 工况鲁棒性跨工况验证明细" in r_ok.text,
            "approval_cross_loop_409": r_cross.status_code,
            "approval_missing_404": r_miss.status_code,
            "export_bundle_200": r_bun.status_code,
            "bundle_run_id_match": r_bun.json().get("audit_meta", {}).get("run_id") == rid6 if r_bun.status_code == 200 else False,
        }

        # 7. /api/sandbox
        r_sb, ms_sb = _timed(lambda: client.post(f"{BASE}/api/sandbox", json={"K": 1.6, "tau": 16.0, "theta": 5.5, "init_Kc": 2.1, "init_Ti": 8.0}))
        dsb = r_sb.json()
        report["checks"]["api_sandbox"] = {
            "status_code": r_sb.status_code, "latency_ms": ms_sb,
            "run_id": dsb["audit_meta"]["run_id"], "final_status": dsb["final_status"],
        }

        # 8. /api/upload_csv (P0-06 unknown plant truth boundary)
        csv_lines = ["timestamp_s,sp,pv,op"] + [f"{i},50.0,{50.0 + 0.1 * (i % 5):.2f},50.0" for i in range(150)]
        r_csv, ms_csv = _timed(lambda: client.post(f"{BASE}/api/upload_csv", json={"filename": "render_test.csv", "csv_text": "\n".join(csv_lines)}))
        dcsv = r_csv.json()
        report["checks"]["api_upload_csv"] = {
            "status_code": r_csv.status_code, "latency_ms": ms_csv,
            "data_source_type": dcsv["audit_meta"]["data_source_type"],
            "has_known_plant_truth": dcsv["audit_meta"]["has_known_plant_truth"],
            "final_status": dcsv["final_status"],
            "candidate_eligible_for_review": dcsv["candidate_eligible_for_review"],
        }

        # 9. /api/copilot (grounded DeepSeek Q&A)
        r_cop, ms_cop = _timed(lambda: client.post(f"{BASE}/api/copilot", json={"message": "请结合指标说明为什么 LOOP-012 被拒批", "current_loop_id": "LOOP-012"}))
        dcop = r_cop.json()
        report["checks"]["api_copilot"] = {
            "status_code": r_cop.status_code, "latency_ms": ms_cop,
            "llm_telemetry": dcop.get("llm_telemetry"),
            "reply_preview": dcop.get("reply", "")[:160],
        }

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
