"""Read-only, zero-tuning external industrial evaluation on ISDB (Jelali & Huang, 2010).

Evaluates the FROZEN PetroPID-Agent V4.3.3 diagnosis & Fail-Closed decision pipeline
on the 76 real chemical/refinery control loops (`cdata.chemicals.loop1..loop76`) from
the official University of Alberta International Stiction Data Base (`isdb10.mat`).

STRICT SCIENTIFIC RULES:
1. ZERO modifications to frozen diagnosis/identification/safety thresholds or code.
2. Does NOT redistribute copyrighted `isdb10.mat`; reads local path `--mat-path`.
3. Clearly separates:
   - Confirmed ground-truth labels (binary stiction vs confirmed non-stiction)
   - Likely/tentative labels
   - Unlabeled real refinery loops (evaluated strictly for Fail-Closed safety behavior)
4. Never claims closed-loop real-plant PID tuning improvement from offline historical data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import scipy.io as sio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "05_skills"))
sys.path.insert(0, str(ROOT / "06_mcp"))
sys.path.insert(0, str(ROOT / "07_agents"))

from petro_pid.diagnosis import diagnose_loop  # noqa: E402
from orchestrator import PetroPIDOrchestrator  # noqa: E402


def classify_isdb_label(brief: str, comments: str) -> str:
    txt = f"{brief} {comments}".lower()
    if "no stiction" in txt:
        return "CONFIRMED_NON_STICTION"
    if "with stiction (likely)" in txt or "stiction (likely)" in txt:
        return "LIKELY_STICTION"
    if "has a stiction problem" in txt or "has valve stiction problem" in txt or "with stiction" in txt:
        return "CONFIRMED_STICTION"
    if any(k in txt for k in ("tuning issue", "tuning problem", "quantisation", "faulty steam sensor", "disturbance (likely)", "marginal stability")):
        return "CONFIRMED_NON_STICTION"
    return "UNLABELED_REFINERY"


def _to_1d_float(arr: Any) -> np.ndarray:
    a = np.asarray(arr, dtype=float).reshape(-1)
    return a


def run_isdb_eval(mat_path: Path, out_dir: Path) -> Dict[str, Any]:
    mat = sio.loadmat(str(mat_path), simplify_cells=True)
    chem = mat["cdata"]["chemicals"]
    orch = PetroPIDOrchestrator()

    rows: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []

    for i in range(1, 77):
        key = f"loop{i}"
        v = chem[key]
        brief = str(v.get("BriefComments", "")).replace("\n", " ").strip()
        comments = str(v.get("Comments", "")).replace("\n", " ").strip()
        gt_group = classify_isdb_label(brief, comments)

        try:
            sp = _to_1d_float(v.get("SP", []))
            pv = _to_1d_float(v.get("PV", []))
            op = _to_1d_float(v.get("OP", []))
            n = min(len(sp), len(pv), len(op))
            if n < 100:
                excluded.append({"loop": f"CHEM-{i:02d}", "reason": f"too_short (n={n})"})
                continue
            sp, pv, op = sp[:n], pv[:n], op[:n]
            if not (np.all(np.isfinite(sp)) and np.all(np.isfinite(pv)) and np.all(np.isfinite(op))):
                excluded.append({"loop": f"CHEM-{i:02d}", "reason": "non_finite_values"})
                continue
            ts_raw = v.get("Ts", 1.0)
            dt = float(ts_raw) if np.isfinite(float(ts_raw)) and float(ts_raw) > 0 else 1.0
            # Cap at 1500 samples to match online CSV envelope without altering signal shape
            if n > 1500:
                sp, pv, op = sp[:1500], pv[:1500], op[:1500]
                n = 1500
            t = np.arange(n, dtype=float) * dt

            diag = diagnose_loop(sp, pv, op, dt=dt)

            # Run full frozen uploaded-CSV Fail-Closed pipeline (unknown real plant)
            safe_pv_bias = float(np.nanmean(pv[:15])) if np.any(np.isfinite(pv[:15])) else 50.0
            safe_op_bias = float(np.nanmean(op[:15])) if np.any(np.isfinite(op[:15])) else 50.0
            meta = {
                "loop_id": f"ISDB-CHEM-{i:02d}",
                "tag_name": f"CHEM-{i:02d}",
                "unit_name": "ISDB 外部工业化工回路",
                "loop_type": "Industrial",
                "description": brief or f"ISDB chemical loop {i}",
                "pv_unit": "",
                "anomaly_type": "EXTERNAL_REAL_INDUSTRIAL",
                "data_source_type": "UPLOADED_HISTORICAL_CSV",
                "has_known_plant_truth": False,
                "true_K": None, "true_tau": None, "true_theta": None,
                "pv_bias": safe_pv_bias, "op_bias": safe_op_bias,
                "init_Kc": 1.0, "init_Ti": 10.0, "init_Td": 0.0,
                "disturbance_amp": 0.0, "disturbance_period": 0.0, "dt": dt, "seed": 42,
            }
            wf = orch._execute_pipeline(
                meta=meta, t=t, sp=sp, pv=pv, op=op,
                max_overshoot_pct=18.0, max_ms=2.2, min_gm=1.8, min_pm_deg=35.0,
                preferred_strategy=None, is_sandbox=True,
            )

            rows.append(
                {
                    "loop_id": f"CHEM-{i:02d}",
                    "isdb_key": key,
                    "n_samples": n,
                    "dt_s": dt,
                    "brief_comments": brief,
                    "ground_truth_group": gt_group,
                    "pred_anomaly": diag.anomaly_type,
                    "oscillation_index": round(float(diag.oscillation_index), 4),
                    "stiction_index": round(float(diag.stiction_index), 4),
                    "harris_index": round(float(diag.harris_index), 4),
                    "op_travel": round(float(diag.op_travel), 4),
                    "final_status": wf["final_status"],
                    "deployment_authorized": wf.get("deployment_authorized", False),
                    "audit_status": (wf.get("audit_meta", {}).get("audit_verification", {}) or {}).get("audit_status", "UNVERIFIED"),
                }
            )
        except Exception as exc:
            excluded.append({"loop": f"CHEM-{i:02d}", "reason": f"exception: {exc}"})

    # Compute strict confusion matrix on CONFIRMED labeled loops only
    conf_pos = [r for r in rows if r["ground_truth_group"] == "CONFIRMED_STICTION"]
    conf_neg = [r for r in rows if r["ground_truth_group"] == "CONFIRMED_NON_STICTION"]
    likely_pos = [r for r in rows if r["ground_truth_group"] == "LIKELY_STICTION"]
    unlabeled = [r for r in rows if r["ground_truth_group"] == "UNLABELED_REFINERY"]

    tp = sum(1 for r in conf_pos if r["pred_anomaly"] == "VALVE_STICTION")
    fn = len(conf_pos) - tp
    fp = sum(1 for r in conf_neg if r["pred_anomaly"] == "VALVE_STICTION")
    tn = len(conf_neg) - fp

    # Also compute abnormal detection rate on confirmed stiction loops (flagged as non-NORMAL)
    stiction_flagged_abnormal = sum(1 for r in conf_pos if r["pred_anomaly"] != "NORMAL")
    likely_tp = sum(1 for r in likely_pos if r["pred_anomaly"] == "VALVE_STICTION")
    likely_abnormal = sum(1 for r in likely_pos if r["pred_anomaly"] != "NORMAL")

    # Fail-Closed safety check across ALL 76 real industrial loops:
    # NEVER recklessly claim SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW on unknown real plant CSV!
    status_counts: Dict[str, int] = {}
    for r in rows:
        status_counts[r["final_status"]] = status_counts.get(r["final_status"], 0) + 1
    blind_approvals = status_counts.get("SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW", 0)
    any_deploy_auth = sum(1 for r in rows if r["deployment_authorized"] is True)
    audit_pass = sum(1 for r in rows if r["audit_status"] == "PASS")

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0

    summary = {
        "dataset": "ISDB (International Stiction Data Base, Jelali & Huang, Springer 2010)",
        "source_url": "https://sites.ualberta.ca/~bhuang/ISDB.zip",
        "sector": "cdata.chemicals (CHEM-01..CHEM-76)",
        "total_loops_inspected": 76,
        "evaluated_loops": len(rows),
        "excluded_loops": excluded,
        "group_counts": {
            "CONFIRMED_STICTION": len(conf_pos),
            "LIKELY_STICTION": len(likely_pos),
            "CONFIRMED_NON_STICTION": len(conf_neg),
            "UNLABELED_REFINERY": len(unlabeled),
        },
        "confirmed_binary_stiction_metrics": {
            "TP": tp,
            "FN": fn,
            "FP": fp,
            "TN": tn,
            "precision_pct": round(prec * 100.0, 2),
            "recall_pct": round(rec * 100.0, 2),
            "f1_pct": round(f1 * 100.0, 2),
            "confirmed_stiction_flagged_abnormal_count": stiction_flagged_abnormal,
            "confirmed_stiction_flagged_abnormal_pct": round(stiction_flagged_abnormal / max(1, len(conf_pos)) * 100.0, 2),
        },
        "likely_stiction_metrics": {
            "total": len(likely_pos),
            "pred_valve_stiction": likely_tp,
            "flagged_abnormal": likely_abnormal,
        },
        "fail_closed_safety_metrics_all_evaluated": {
            "status_distribution": status_counts,
            "blind_tuning_approvals_on_unknown_plant": blind_approvals,
            "deployment_authorized_true_count": any_deploy_auth,
            "audit_verified_pass_count": audit_pass,
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "isdb_external_raw_results.json"
    raw_path.write_text(json.dumps({"summary": summary, "per_loop_results": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return {"summary": summary, "per_loop_results": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mat-path", required=True, type=Path)
    parser.add_argument("--out-dir", default=ROOT / "competition_v4" / "submission_v433", type=Path)
    args = parser.parse_args()
    run_isdb_eval(args.mat_path, args.out_dir)
