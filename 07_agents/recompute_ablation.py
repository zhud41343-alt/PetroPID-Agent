"""Standalone independent recomputation script for V4.3.3 ablation raw trials."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "competition_v4" / "final_release_v433" / "03_ABLATION_120_RAW_TRIALS.json"


def main() -> None:
    data = json.loads(RAW.read_text(encoding="utf-8"))
    trials = data["raw_trials"]
    assert len(trials) >= 120, f"Expected >=120 raw trials, got {len(trials)}"
    by_sys = defaultdict(list)
    for t in trials:
        by_sys[t["system"]].append(t)

    out = []
    for sys_name, grp in by_sys.items():
        n = len(grp)
        ft = [x for x in grp if x["scenario"] == "transient_timeout_fault"]
        dt = [x for x in grp if x["scenario"] == "duplicate_tool_request"]
        lats = [x["latency_ms"] for x in grp]
        hb = [x["handoff_bytes"] for x in grp]
        out.append({
            "system": sys_name,
            "n": n,
            "decision_correct_pct": round(sum(1 for x in grp if x["decision_correct"]) / n * 100.0, 2),
            "fault_recovery_pct": round(sum(1 for x in ft if x["recovered_fault"]) / max(len(ft), 1) * 100.0, 2),
            "dup_prevented": sum(x["duplicate_prevented"] for x in dt),
            "audit_verified_pct": round(sum(1 for x in grp if x["audit_verified"]) / n * 100.0, 2),
            "mean_handoff_bytes": int(round(float(np.mean(hb)))),
            "p50_ms": round(float(np.percentile(lats, 50)), 2),
            "p95_ms": round(float(np.percentile(lats, 95)), 2),
        })
    print(json.dumps({"total_raw_trials": len(trials), "recomputed_summary": out}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
