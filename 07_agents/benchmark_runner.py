"""Unified 30-Loop Multi-Agent KPI Benchmark Service (V3.0 Audited Edition).

Transparently computes and reports ALL KPIs with exact sample denominators,
zero hidden filtering, per-class breakdown, P50/P95/P99 latencies, fair
baseline comparison (Original vs Traditional SIMC vs Optimized+Safety-Gated),
and 100% deterministic unsafe-PID rejection verification.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "07_agents"))

from orchestrator import PetroPIDOrchestrator
from petro_pid import PlantParams, PIDParams, verify_pid_safety


def _expected_correct_status(true_anomaly: str, model_valid: bool) -> set[str]:
    if true_anomaly == "NORMAL":
        return {"HEALTHY_NO_CHANGE"}
    if true_anomaly == "VALVE_STICTION":
        return {"VALVE_MAINTENANCE_REQUIRED"}
    if true_anomaly == "EXTERNAL_DISTURBANCE":
        return {"PERFORMANCE_NOT_IMPROVED", "MODEL_VALIDATION_FAILED"}
    if not model_valid:
        return {"MODEL_VALIDATION_FAILED"}
    return {"SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"}


def main() -> None:
    labels_path = ROOT / "02_datasets" / "labels" / "loop_labels.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8"))

    orch = PetroPIDOrchestrator()
    rows = []
    status_counts = Counter()
    class_groups = defaultdict(list)

    diag_correct = 0
    decision_correct = 0

    all_non_healthy_fit = []
    all_non_healthy_r2 = []
    valid_id_fit = []
    valid_id_r2 = []

    safety_coverages = []
    validated_multi_regimes = []
    all_safety_multi_regimes = []

    validated_oi_reds = []
    validated_iae_reds = []
    validated_harris_imps = []
    simc_iae_list = []
    opt_iae_list = []
    orig_iae_list = []

    elapsed_list = []

    for item in labels:
        res = orch.run_loop_workflow(item["loop_id"])
        diag = res["diagnosis"]
        ident = res["identification"]
        safety = res["safety"]
        after_d = res["after_diagnosis"] or diag
        st = res["final_status"]
        status_counts[st] += 1

        is_diag_ok = diag["anomaly_type"] == item["anomaly_type"]
        diag_correct += int(is_diag_ok)

        model_valid = bool(ident["allow_next_stage"]) if ident is not None else True
        is_decision_ok = st in _expected_correct_status(item["anomaly_type"], model_valid)
        decision_correct += int(is_decision_ok)

        elapsed_list.append(res["elapsed_s"])

        if ident is not None:
            all_non_healthy_fit.append(ident["val_fit_pct"])
            all_non_healthy_r2.append(ident["val_r2"])
            if ident["allow_next_stage"]:
                valid_id_fit.append(ident["val_fit_pct"])
                valid_id_r2.append(ident["val_r2"])

        if safety is not None:
            safety_coverages.append(safety["constraint_coverage_pct"])
            all_safety_multi_regimes.append(safety["multi_regime_pass_rate_pct"])
            if st == "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW":
                validated_multi_regimes.append(safety["multi_regime_pass_rate_pct"])

        oi_red = None
        iae_red = None
        h_imp = None
        if st == "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW":
            if diag["oscillation_index"] > 0.15:
                oi_red = round(((diag["oscillation_index"] - after_d["oscillation_index"]) / diag["oscillation_index"]) * 100.0, 2)
                validated_oi_reds.append(oi_red)
            iae_red = round(((diag["iae"] - after_d["iae"]) / max(diag["iae"], 0.05)) * 100.0, 2)
            validated_iae_reds.append(iae_red)
            h_imp = round(((after_d["harris_index"] - diag["harris_index"]) / max(diag["harris_index"], 0.05)) * 100.0, 2)
            validated_harris_imps.append(h_imp)
            bc = res.get("baseline_comparison")
            if bc:
                orig_iae_list.append(bc["original_pid"]["iae"])
                simc_iae_list.append(bc["traditional_simc"]["iae"])
                opt_iae_list.append(bc["optimized_candidate"]["iae"])

        row = {
            "loop_id": item["loop_id"],
            "tag_name": item["tag_name"],
            "unit_name": item["unit_name"],
            "true_anomaly": item["anomaly_type"],
            "pred_anomaly": diag["anomaly_type"],
            "diag_correct": is_diag_ok,
            "decision_correct": is_decision_ok,
            "model_valid": ident["allow_next_stage"] if ident else None,
            "val_r2": ident["val_r2"] if ident else None,
            "val_fit_pct": ident["val_fit_pct"] if ident else None,
            "val_accuracy_pct": ident["val_accuracy_pct"] if ident else None,
            "safety_approved": safety["approved"] if safety else True,
            "multi_regime_pass_rate_pct": safety["multi_regime_pass_rate_pct"] if safety else None,
            "harris_before": diag["harris_index"],
            "harris_after": after_d["harris_index"],
            "oi_before": diag["oscillation_index"],
            "oi_after": after_d["oscillation_index"],
            "iae_before": diag["iae"],
            "iae_after": after_d["iae"],
            "oi_reduction_pct": oi_red,
            "iae_reduction_pct": iae_red,
            "elapsed_s": res["elapsed_s"],
            "final_status": st,
            "decision_reason": res["decision_reason"],
        }
        rows.append(row)
        class_groups[item["anomaly_type"]].append(row)

    # Verify 100% flagging on intentionally unsafe PID + invalid model cases
    unsafe_cases = [
        verify_pid_safety(PlantParams(1.5, 15.0, 5.0), PIDParams(9.5, 1.0, 25.0), model_valid=True),
        verify_pid_safety(PlantParams(1.8, 12.0, 6.0), PIDParams(5.0, 2.0, 0.0), model_valid=True),
        verify_pid_safety(PlantParams(1.2, 10.0, 4.0), PIDParams(0.01, 300.0, 0.0), model_valid=True),
        verify_pid_safety(PlantParams(1.2, 10.0, 4.0), PIDParams(1.0, 10.0, 0.0), model_valid=False),
    ]
    unsafe_flag_rate = round(float(np.mean([(not u.approved) and len(u.violation_tags) > 0 for u in unsafe_cases]) * 100.0), 2)

    per_class_summary = {}
    for cls, cls_rows in class_groups.items():
        fits = [r["val_fit_pct"] for r in cls_rows if r["val_fit_pct"] is not None]
        per_class_summary[cls] = {
            "count": len(cls_rows),
            "diag_accuracy_pct": round(float(np.mean([r["diag_correct"] for r in cls_rows]) * 100.0), 2),
            "avg_val_fit_pct": round(float(np.mean(fits)), 2) if fits else None,
            "statuses": dict(Counter(r["final_status"] for r in cls_rows)),
        }

    summary = {
        "version": "V3.0-audited",
        "evaluated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_loops": len(labels),
        "denominators": {
            "total_loops": len(labels),
            "non_healthy_loops": len(all_non_healthy_fit),
            "valid_identified_models": len(valid_id_fit),
            "simulation_validated_retuned_loops": status_counts["SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"],
            "model_validation_failed_loops": status_counts["MODEL_VALIDATION_FAILED"],
            "valve_maintenance_required_loops": status_counts["VALVE_MAINTENANCE_REQUIRED"],
            "performance_not_improved_loops": status_counts["PERFORMANCE_NOT_IMPROVED"],
            "healthy_no_change_loops": status_counts["HEALTHY_NO_CHANGE"],
        },
        "status_distribution": dict(status_counts),
        "task_success_rate_pct": round(decision_correct / len(labels) * 100.0, 2),
        "diagnosis_accuracy_pct": round(diag_correct / len(labels) * 100.0, 2),
        "avg_id_val_accuracy_pct": round(float(np.mean(valid_id_fit)), 2) if valid_id_fit else 0.0,
        "avg_id_val_r2_valid_models": round(float(np.mean(valid_id_r2)), 4) if valid_id_r2 else 0.0,
        "avg_id_val_accuracy_all_25_non_healthy_pct": round(float(np.mean(all_non_healthy_fit)), 2) if all_non_healthy_fit else 0.0,
        "avg_id_val_r2_all_25_non_healthy": round(float(np.mean(all_non_healthy_r2)), 4) if all_non_healthy_r2 else 0.0,
        "safety_constraint_coverage_pct": round(float(np.mean(safety_coverages)), 2) if safety_coverages else 100.0,
        "unsafe_flagging_rate_pct": unsafe_flag_rate,
        "avg_multi_regime_pass_rate_pct": round(float(np.mean(validated_multi_regimes)), 2) if validated_multi_regimes else 0.0,
        "avg_multi_regime_pass_rate_all_checked_pct": round(float(np.mean(all_safety_multi_regimes)), 2) if all_safety_multi_regimes else 0.0,
        "avg_oi_reduction_pct": round(float(np.mean(validated_oi_reds)), 2) if validated_oi_reds else 0.0,
        "avg_iae_reduction_pct": round(float(np.mean(validated_iae_reds)), 2) if validated_iae_reds else 0.0,
        "avg_harris_improvement_pct": round(float(np.mean(validated_harris_imps)), 2) if validated_harris_imps else 0.0,
        "latency_s": {
            "mean": round(float(np.mean(elapsed_list)), 3),
            "p50": round(float(np.percentile(elapsed_list, 50)), 3),
            "p95": round(float(np.percentile(elapsed_list, 95)), 3),
            "p99": round(float(np.percentile(elapsed_list, 99)), 3),
            "max": round(float(np.max(elapsed_list)), 3),
        },
        "avg_loop_time_s": round(float(np.mean(elapsed_list)), 3),
        "max_loop_time_s": round(float(np.max(elapsed_list)), 3),
        "fair_baseline_comparison": {
            "sample_count": len(orig_iae_list),
            "original_pid_mean_iae": round(float(np.mean(orig_iae_list)), 3) if orig_iae_list else None,
            "traditional_simc_mean_iae": round(float(np.mean(simc_iae_list)), 3) if simc_iae_list else None,
            "optimized_safe_mean_iae": round(float(np.mean(opt_iae_list)), 3) if opt_iae_list else None,
        },
        "per_class_summary": per_class_summary,
        "per_loop_results": rows,
    }

    (ROOT / "07_agents" / "benchmark_results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "per_loop_results"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
