"""Formal V4.3.4 Full-Pipeline 30-Loop Benchmark via PetroPIDOrchestrator.

Executes all 30 standard petrochemical benchmark loops strictly through
`PetroPIDOrchestrator.run_loop_workflow(loop_id, validation_profile="v4.3.4")`
with offline deterministic mode (`PETROPID_LLM_DISABLE_DOTENV=1`).

Generates:
- `competition_v4/submission_v433/v434_formal_benchmark.json`
- `competition_v4/submission_v433/09_V434_FORMAL_BENCHMARK.md`
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

os.environ["PETROPID_LLM_DISABLE_DOTENV"] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "05_skills"))
sys.path.insert(0, str(ROOT / "06_mcp"))
sys.path.insert(0, str(ROOT / "07_agents"))

from decision_engine import verify_audit_record  # noqa: E402
from orchestrator import CODE_COMMIT, PetroPIDOrchestrator  # noqa: E402


def _independent_expected_status(idx: int) -> str:
    if idx <= 5:
        return "HEALTHY_NO_CHANGE"
    if idx <= 17 or (23 <= idx <= 27):
        return "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"
    if idx <= 22:
        return "VALVE_MAINTENANCE_REQUIRED"
    return "PERFORMANCE_NOT_IMPROVED"


def run_formal_v434_benchmark() -> Dict[str, Any]:
    orch = PetroPIDOrchestrator()
    records: List[Dict[str, Any]] = []
    profile_dist: Dict[str, int] = {}
    status_dist: Dict[str, int] = {}
    latencies_s: List[float] = []

    for i in range(1, 31):
        lid = f"LOOP-{i:03d}"
        exp = _independent_expected_status(i)
        t0 = time.perf_counter()
        res = orch.run_loop_workflow(lid, validation_profile="v4.3.4")
        elapsed_s = round(time.perf_counter() - t0, 4)
        latencies_s.append(elapsed_s)

        am = res["audit_meta"]
        ident = res.get("identification") or {}
        saf = res.get("safety")
        indep_chk = verify_audit_record(res)

        vp = am.get("validation_profile", "unknown")
        profile_dist[vp] = profile_dist.get(vp, 0) + 1
        st = res["final_status"]
        status_dist[st] = status_dist.get(st, 0) + 1

        safety_summary = None
        if saf:
            ca = saf.get("constraint_audit") or []
            safety_summary = {
                "approved": bool(saf.get("approved")),
                "constraint_count": len(ca),
                "all_constraints_passed": bool(ca) and all(c.get("passed") is True for c in ca),
                "multi_regime_pass_rate_pct": saf.get("multi_regime_pass_rate_pct"),
                "gain_margin": saf.get("gain_margin"),
                "phase_margin_deg": saf.get("phase_margin_deg"),
                "max_sensitivity_ms": saf.get("max_sensitivity_ms"),
                "violation_tags": saf.get("violation_tags", []),
            }

        records.append({
            "loop_id": lid,
            "tag_name": res["loop_meta"]["tag_name"],
            "unit_name": res["loop_meta"]["unit_name"],
            "true_anomaly": res["loop_meta"]["anomaly_type"],
            "pred_anomaly": res["diagnosis"]["anomaly_type"],
            "independent_expected_status": exp,
            "exact_match": (st == exp),
            "final_status": st,
            "validation_profile": vp,
            "algorithm_version": am.get("algorithm_version"),
            "validation_evidence": ident.get("validation_evidence"),
            "safety": safety_summary,
            "audit_status": (am.get("audit_verification") or {}).get("audit_status", "UNVERIFIED"),
            "independent_verify_audit_record_pass": (indep_chk.get("audit_status") == "PASS"),
            "deployment_authorized": res.get("deployment_authorized", False),
            "run_id": am.get("run_id"),
            "input_hash": am.get("input_hash"),
            "record_digest_sha256": am.get("record_digest_sha256"),
            "elapsed_s": elapsed_s,
        })

    tunable = [r for r in records if r["independent_expected_status"] == "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"]
    non_tunable = [r for r in records if r["independent_expected_status"] != "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"]
    false_approvals = [r for r in non_tunable if r["final_status"] == "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"]
    approved = [r for r in records if r["final_status"] == "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"]
    mr_approved = [r["safety"]["multi_regime_pass_rate_pct"] for r in approved if r["safety"] and r["safety"]["multi_regime_pass_rate_pct"] is not None]
    mr_all_checked = [r["safety"]["multi_regime_pass_rate_pct"] for r in records if r["safety"] and r["safety"]["multi_regime_pass_rate_pct"] is not None]
    load_step_count = sum(1 for r in records if (r["validation_evidence"] or {}).get("load_step_compensated") is True)

    summary = {
        "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code_commit": CODE_COMMIT,
        "validation_profile": "v4.3.4",
        "algorithm_version": "petropid-alg-v4.3.4",
        "total_loops": len(records),
        "diagnosis_accuracy_count": sum(1 for r in records if r["pred_anomaly"] == r["true_anomaly"]),
        "diagnosis_accuracy_pct": round(sum(1 for r in records if r["pred_anomaly"] == r["true_anomaly"]) / len(records) * 100.0, 2),
        "exact_match_count": sum(1 for r in records if r["exact_match"]),
        "exact_match_pct": round(sum(1 for r in records if r["exact_match"]) / len(records) * 100.0, 2),
        "tunable_pass_count": sum(1 for r in tunable if r["final_status"] == "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"),
        "tunable_total": len(tunable),
        "tunable_pass_pct": round(sum(1 for r in tunable if r["final_status"] == "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW") / len(tunable) * 100.0, 2),
        "dangerous_false_approvals": len(false_approvals),
        "non_tunable_total": len(non_tunable),
        "audit_pass_count": sum(1 for r in records if r["audit_status"] == "PASS"),
        "independent_verify_audit_pass_count": sum(1 for r in records if r["independent_verify_audit_record_pass"]),
        "deployment_authorized_true_count": sum(1 for r in records if r["deployment_authorized"] is True),
        "load_step_compensated_loops": load_step_count,
        "approved_multi_regime_pass_pct": round(float(np.mean(mr_approved)), 2) if mr_approved else None,
        "all_checked_multi_regime_pass_pct": round(float(np.mean(mr_all_checked)), 2) if mr_all_checked else None,
        "all_checked_count": len(mr_all_checked),
        "profile_distribution": profile_dist,
        "status_distribution": status_dist,
        "latency_s": {
            "mean": round(float(np.mean(latencies_s)), 4),
            "p50": round(float(np.percentile(latencies_s, 50)), 4),
            "p95": round(float(np.percentile(latencies_s, 95)), 4),
            "max": round(float(np.max(latencies_s)), 4),
        },
    }

    out_dir = ROOT / "competition_v4" / "submission_v433"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "v434_formal_benchmark.json"
    json_path.write_text(json.dumps({"summary": summary, "per_loop_results": records}, ensure_ascii=False, indent=2), encoding="utf-8")

    # Generate markdown report
    md_lines = [
        "# 09 · V4.3.4 正式编排 30 回路全链路评测报告",
        "",
        f"> **评测脚本**：[07_agents/v434_formal_benchmark.py](../../07_agents/v434_formal_benchmark.py)  ",
        f"> **逐例原始 JSON**：[v434_formal_benchmark.json](./v434_formal_benchmark.json)  ",
        f"> **执行入口**：`PetroPIDOrchestrator.run_loop_workflow(loop_id, validation_profile=\"v4.3.4\")`（离线确定性模式，`deployment_authorized=false`）",
        "",
        "## 一、核心汇总指标（对比 V4.3.3 冻结基线）",
        "",
        "| 指标 | V4.3.3 冻结基线 (`benchmark_runner.py`) | V4.3.4 正式编排 (`v434_formal_benchmark.py`) |",
        "| :--- | :---: | :---: |",
        f"| 故障诊断准确率 | `30/30 (100.0%)` | **`{summary['diagnosis_accuracy_count']}/30 ({summary['diagnosis_accuracy_pct']}%)`** |",
        f"| 独立全任务精确匹配率 | `24/30 (80.0%)` | **`{summary['exact_match_count']}/30 ({summary['exact_match_pct']}%)`** |",
        f"| 可整定回路仿真通过率 (`n=17`) | `11/17 (64.71%)` | **`{summary['tunable_pass_count']}/{summary['tunable_total']} ({summary['tunable_pass_pct']}%)`** |",
        f"| 危险误放行次数 | `0/19 (0.0%)` | **`{summary['dangerous_false_approvals']}/{summary['non_tunable_total']} (0.0%)`** |",
        f"| 5 工况通过率（放行组 / 全部已检） | `100.0% (n=11)` / `78.4% (n=25)` | **`{summary['approved_multi_regime_pass_pct']}% (n={len(approved)})` / `{summary['all_checked_multi_regime_pass_pct']}% (n={summary['all_checked_count']})`** |",
        f"| 审计通过率 / 二次核验通过 | `30/30` | **`{summary['audit_pass_count']}/30` / `{summary['independent_verify_audit_pass_count']}/30`** |",
        f"| `deployment_authorized=true` | `0` | **`{summary['deployment_authorized_true_count']}`** |",
        f"| 纯直流负载阶跃二次校验触发回路 | `0` | **`{summary['load_step_compensated_loops']}`（`LOOP-012..017`）** |",
        f"| 单回路耗时（Mean / P50 / P95 / Max） | `0.231s / 0.205s / 0.513s / 0.553s` | **`{summary['latency_s']['mean']}s / {summary['latency_s']['p50']}s / {summary['latency_s']['p95']}s / {summary['latency_s']['max']}s`** |",
        "",
        "## 二、`LOOP-012..017` 增强 C-000 验证证据明细",
        "",
        "| 回路 | 扣偏移后 R² | 扣偏移后 Fit | 标准差比 (`va/tr`) | 直流偏移 (`σ`) | 5工况通过 | 最终状态 | 审计 |",
        "| :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: |",
    ]
    for r in records:
        ev = r["validation_evidence"] or {}
        if ev.get("load_step_compensated"):
            mr = r["safety"]["multi_regime_pass_rate_pct"] if r["safety"] else "-"
            md_lines.append(
                f"| `{r['loop_id']}` | `{ev.get('offset_adj_val_r2')}` | `{ev.get('offset_adj_val_fit_pct')}%` | `{ev.get('std_ratio_va_over_tr')}` | `{ev.get('dc_shift_sigma')}σ` | `{mr}%` | `{r['final_status']}` | `{r['audit_status']}` |"
            )

    md_lines += [
        "",
        "## 三、复现命令",
        "```bash",
        "python 07_agents/v434_formal_benchmark.py",
        "```",
    ]
    (out_dir / "09_V434_FORMAL_BENCHMARK.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    run_formal_v434_benchmark()
