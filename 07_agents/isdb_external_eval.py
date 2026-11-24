"""Read-only, zero-tuning external industrial evaluation on ISDB (Jelali & Huang, 2010).

Evaluates the FROZEN PetroPID-Agent V4.3.3 diagnosis & Fail-Closed decision pipeline
on all 76 real chemical/refinery control loops (`cdata.chemicals.loop1..loop76`) from
the official University of Alberta International Stiction Data Base (`isdb10.mat`),
and compares against two classic scale-invariant industrial stiction detectors
(Horch 1999 cross-correlation test; scale-normalized PV-OP hysteresis area).

STRICT SCIENTIFIC RULES:
1. ZERO modifications to frozen V4.3.3 backend diagnosis/identification/safety code.
2. Runs independent secondary `verify_audit_record()` on every single one of the 76 runs.
3. Explicitly separates 5 label groups (strict 6 `no stiction` vs 12 other-fault heuristic).
4. Never redistributes copyrighted `isdb10.mat`; records exact source SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import scipy.io as sio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "05_skills"))
sys.path.insert(0, str(ROOT / "06_mcp"))
sys.path.insert(0, str(ROOT / "07_agents"))

from petro_pid.diagnosis import diagnose_loop  # noqa: E402
from decision_engine import verify_audit_record  # noqa: E402
from orchestrator import PetroPIDOrchestrator  # noqa: E402


def classify_isdb_label_5way(brief: str, comments: str) -> str:
    b_low = brief.lower()
    txt = f"{brief} {comments}".lower()
    if "no stiction" in b_low:
        return "EXPLICIT_NO_STICTION"
    if "with stiction (likely)" in txt or "stiction (likely)" in txt:
        return "LIKELY_STICTION"
    if "has a stiction problem" in txt or "has valve stiction problem" in txt or "with stiction" in txt:
        return "CONFIRMED_STICTION"
    if "no stiction" in txt or any(
        k in txt
        for k in (
            "tuning issue",
            "tuning problem",
            "quantisation",
            "faulty steam sensor",
            "disturbance (likely)",
            "marginal stability",
        )
    ):
        return "OTHER_FAULT_UNCONFIRMED_STICTION"
    return "UNLABELED_REFINERY"


def _horch_crosscorr_stiction(pv: np.ndarray, op: np.ndarray) -> Tuple[bool, float]:
    """Scale-invariant Horch (1999) cross-correlation odd-function symmetry test.

    In a stiction-induced limit cycle (non-integrating process), OP-PV cross-correlation
    behaves as an odd function (anti-symmetric around lag 0, small |R(0)| relative to peak
    odd component), whereas linear/disturbance oscillations tend to be even-symmetric.
    """
    x = op - np.mean(op)
    y = pv - np.mean(pv)
    sx, sy = float(np.std(x)), float(np.std(y))
    if sx < 1e-9 or sy < 1e-9:
        return False, 0.0
    x, y = x / sx, y / sy
    n = len(x)
    max_lag = min(60, n // 4)
    lags = np.arange(-max_lag, max_lag + 1)
    ccf = np.array(
        [
            float(np.mean(x[: n - abs(k)] * y[abs(k) :])) if k >= 0 else float(np.mean(x[abs(k) :] * y[: n - abs(k)]))
            for k in lags
        ]
    )
    mid = max_lag
    pos = ccf[mid + 1 :]
    neg = ccf[mid - 1 :: -1]
    even_energy = float(np.mean((0.5 * (pos + neg)) ** 2))
    odd_energy = float(np.mean((0.5 * (pos - neg)) ** 2))
    total = even_energy + odd_energy + 1e-12
    odd_ratio = odd_energy / total
    peak_ccf = float(np.max(np.abs(ccf)))
    is_stic = bool(peak_ccf >= 0.25 and odd_ratio >= 0.45)
    return is_stic, round(odd_ratio, 4)


def _scale_norm_hysteresis_stiction(pv: np.ndarray, op: np.ndarray) -> Tuple[bool, float]:
    """Scale-normalized PV-OP hysteresis area + flat-spot stick-slip index."""
    sx, sy = float(np.std(op)), float(np.std(pv))
    if sx < 1e-9 or sy < 1e-9:
        return False, 0.0
    op_n = (op - np.mean(op)) / sx
    pv_n = (pv - np.mean(pv)) / sy
    dop = np.diff(op_n)
    dpv = np.diff(pv_n)
    # Signed normalized phase-plane area (normalized by trajectory length)
    signed_area = abs(float(np.sum(op_n[:-1] * pv_n[1:] - op_n[1:] * pv_n[:-1]))) / (2.0 * len(op_n))
    # Flat-spot stick ratio: OP actively moving while PV barely moves
    op_moving = np.abs(dop) > 0.08
    pv_stuck = np.abs(dpv) < 0.06
    stick_ratio = float(np.mean(pv_stuck[op_moving])) if np.any(op_moving) else 0.0
    score = round(0.55 * min(1.0, signed_area * 2.5) + 0.45 * stick_ratio, 4)
    return bool(score >= 0.32), score


def _binary_metrics(pos_flags: List[bool], neg_flags: List[bool]) -> Dict[str, Any]:
    tp = sum(1 for f in pos_flags if f)
    fn = len(pos_flags) - tp
    fp = sum(1 for f in neg_flags if f)
    tn = len(neg_flags) - fp
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
    return {
        "TP": tp,
        "FN": fn,
        "FP": fp,
        "TN": tn,
        "precision_pct": round(prec * 100.0, 2),
        "recall_pct": round(rec * 100.0, 2),
        "f1_pct": round(f1 * 100.0, 2),
    }


def run_isdb_eval(mat_path: Path, out_dir: Path) -> Dict[str, Any]:
    mat_sha256 = hashlib.sha256(mat_path.read_bytes()).hexdigest()
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
        gt_5way = classify_isdb_label_5way(brief, comments)

        try:
            sp = np.asarray(v.get("SP", []), dtype=float).reshape(-1)
            pv = np.asarray(v.get("PV", []), dtype=float).reshape(-1)
            op = np.asarray(v.get("OP", []), dtype=float).reshape(-1)
            n_orig = min(len(sp), len(pv), len(op))
            if n_orig < 100:
                excluded.append({"loop": f"CHEM-{i:02d}", "reason": f"too_short (n={n_orig})"})
                continue
            n = min(n_orig, 1500)
            sp, pv, op = sp[:n], pv[:n], op[:n]
            if not (np.all(np.isfinite(sp)) and np.all(np.isfinite(pv)) and np.all(np.isfinite(op))):
                excluded.append({"loop": f"CHEM-{i:02d}", "reason": "non_finite_values"})
                continue
            ts_raw = v.get("Ts", 1.0)
            dt = float(ts_raw) if np.isfinite(float(ts_raw)) and float(ts_raw) > 0 else 1.0
            t = np.arange(n, dtype=float) * dt

            # Method 1: Frozen V4.3.3 Heuristic (ZERO modification)
            diag = diagnose_loop(sp, pv, op, dt=dt)

            # Method 2 & 3: Side-by-side scale-invariant external reference detectors
            horch_pred, horch_odd_ratio = _horch_crosscorr_stiction(pv, op)
            norm_pred, norm_score = _scale_norm_hysteresis_stiction(pv, op)

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
                "true_K": None,
                "true_tau": None,
                "true_theta": None,
                "pv_bias": safe_pv_bias,
                "op_bias": safe_op_bias,
                "init_Kc": 1.0,
                "init_Ti": 10.0,
                "init_Td": 0.0,
                "disturbance_amp": 0.0,
                "disturbance_period": 0.0,
                "dt": dt,
                "seed": 42,
            }
            wf = orch._execute_pipeline(
                meta=meta,
                t=t,
                sp=sp,
                pv=pv,
                op=op,
                max_overshoot_pct=18.0,
                max_ms=2.2,
                min_gm=1.8,
                min_pm_deg=35.0,
                preferred_strategy=None,
                is_sandbox=True,
            )

            # Independent secondary cryptographic audit check outside pipeline!
            indep_audit = verify_audit_record(wf)

            rows.append(
                {
                    "loop_id": f"CHEM-{i:02d}",
                    "isdb_key": key,
                    "n_samples_original": n_orig,
                    "n_samples_evaluated": n,
                    "dt_s": dt,
                    "brief_comments": brief,
                    "ground_truth_5way": gt_5way,
                    "pred_anomaly_v433_frozen": diag.anomaly_type,
                    "oscillation_index": round(float(diag.oscillation_index), 4),
                    "stiction_index": round(float(diag.stiction_index), 4),
                    "harris_index": round(float(diag.harris_index), 4),
                    "op_travel": round(float(diag.op_travel), 4),
                    "horch_1999_pred_stiction": horch_pred,
                    "horch_1999_odd_ratio": horch_odd_ratio,
                    "scale_norm_hyst_pred_stiction": norm_pred,
                    "scale_norm_hyst_score": norm_score,
                    "final_status": wf["final_status"],
                    "deployment_authorized": wf.get("deployment_authorized", False),
                    "pipeline_audit_status": (wf.get("audit_meta", {}).get("audit_verification", {}) or {}).get("audit_status", "UNVERIFIED"),
                    "independent_verify_audit_record_pass": bool(indep_audit.get("audit_status") == "PASS"),
                }
            )
        except Exception as exc:
            excluded.append({"loop": f"CHEM-{i:02d}", "reason": f"exception: {exc}"})

    pos = [r for r in rows if r["ground_truth_5way"] == "CONFIRMED_STICTION"]
    neg_strict = [r for r in rows if r["ground_truth_5way"] == "EXPLICIT_NO_STICTION"]
    neg_other = [r for r in rows if r["ground_truth_5way"] == "OTHER_FAULT_UNCONFIRMED_STICTION"]
    neg_all = neg_strict + neg_other
    likely = [r for r in rows if r["ground_truth_5way"] == "LIKELY_STICTION"]
    unlabeled = [r for r in rows if r["ground_truth_5way"] == "UNLABELED_REFINERY"]

    methods = {
        "v433_frozen_heuristic": lambda r: r["pred_anomaly_v433_frozen"] == "VALVE_STICTION",
        "horch_1999_crosscorr_scale_invariant": lambda r: r["horch_1999_pred_stiction"],
        "scale_normalized_pvop_hysteresis": lambda r: r["scale_norm_hyst_pred_stiction"],
    }
    benchmark_comparison = {
        name: {
            "strict_16_loops_10pos_vs_6explicit_no_stiction": _binary_metrics([fn(r) for r in pos], [fn(r) for r in neg_strict]),
            "exploratory_28_loops_10pos_vs_18non_stiction": _binary_metrics([fn(r) for r in pos], [fn(r) for r in neg_all]),
        }
        for name, fn in methods.items()
    }

    status_counts: Dict[str, int] = {}
    for r in rows:
        status_counts[r["final_status"]] = status_counts.get(r["final_status"], 0) + 1

    summary = {
        "dataset": "ISDB (International Stiction Data Base, Jelali & Huang, Springer 2010)",
        "source_url": "https://sites.ualberta.ca/~bhuang/ISDB.zip",
        "source_mat_sha256": mat_sha256,
        "sector": "cdata.chemicals (CHEM-01..CHEM-76)",
        "sample_cap_per_loop": 1500,
        "total_loops_inspected": 76,
        "evaluated_loops": len(rows),
        "excluded_loops": excluded,
        "group_counts_5way": {
            "CONFIRMED_STICTION": len(pos),
            "EXPLICIT_NO_STICTION": len(neg_strict),
            "OTHER_FAULT_UNCONFIRMED_STICTION": len(neg_other),
            "LIKELY_STICTION": len(likely),
            "UNLABELED_REFINERY": len(unlabeled),
        },
        "method_comparison": benchmark_comparison,
        "v433_frozen_abnormal_detection": {
            "confirmed_stiction_non_normal": sum(1 for r in pos if r["pred_anomaly_v433_frozen"] != "NORMAL"),
            "confirmed_stiction_total": len(pos),
            "likely_stiction_non_normal": sum(1 for r in likely if r["pred_anomaly_v433_frozen"] != "NORMAL"),
            "likely_stiction_total": len(likely),
        },
        "unknown_plant_gate_consistency_all_76": {
            "status_distribution": status_counts,
            "simulation_validated_approvals_with_unknown_truth": status_counts.get("SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW", 0),
            "deployment_authorized_true_count": sum(1 for r in rows if r["deployment_authorized"] is True),
            "pipeline_audit_status_pass_count": sum(1 for r in rows if r["pipeline_audit_status"] == "PASS"),
            "independent_verify_audit_record_pass_count": sum(1 for r in rows if r["independent_verify_audit_record_pass"]),
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
