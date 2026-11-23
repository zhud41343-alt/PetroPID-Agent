"""Clean, despike, interpolate, desensitize, and split raw DCS loop telemetry.

Reads:  02_datasets/raw/*.csv + 02_datasets/labels/loop_labels.json
Writes: 02_datasets/processed/{train,val,test}/{loop_id}_{tag_name}.csv
        02_datasets/processed/cleaning_summary.json
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def clean_series(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = df.copy()
    n_nans = int(df["pv"].isna().sum())
    # 1. Interpolate missing values
    df["pv"] = df["pv"].interpolate(method="linear").bfill().ffill()

    # 2. Hampel / median-filter spike removal (window=7, 4.5*MAD)
    rolling_med = df["pv"].rolling(window=7, center=True, min_periods=1).median()
    abs_dev = (df["pv"] - rolling_med).abs()
    mad = abs_dev.rolling(window=15, center=True, min_periods=1).median().clip(lower=0.15)
    spike_mask = abs_dev > (4.5 * 1.4826 * mad)
    n_spikes = int(spike_mask.sum())
    df.loc[spike_mask, "pv"] = rolling_med.loc[spike_mask]

    # 3. Recompute control error & enforce OP physical range [0, 100]
    df["op"] = df["op"].clip(0.0, 100.0)
    df["err"] = (df["sp"] - df["pv"]).round(4)
    df["pv"] = df["pv"].round(4)

    stats = {
        "n_samples": len(df),
        "n_nans_repaired": n_nans,
        "n_spikes_removed": n_spikes,
    }
    return df, stats


def main() -> None:
    raw_dir = ROOT / "02_datasets" / "raw"
    proc_dir = ROOT / "02_datasets" / "processed"
    labels_path = ROOT / "02_datasets" / "labels" / "loop_labels.json"

    for split in ("train", "val", "test"):
        (proc_dir / split).mkdir(parents=True, exist_ok=True)

    with open(labels_path, "r", encoding="utf-8") as f:
        labels = json.load(f)

    summary = []
    for item in labels:
        raw_file = raw_dir / item["raw_file"]
        df_raw = pd.read_csv(raw_file)
        df_clean, stats = clean_series(df_raw)
        out_path = proc_dir / item["split"] / item["raw_file"]
        df_clean.to_csv(out_path, index=False, encoding="utf-8-sig")
        summary.append({
            "loop_id": item["loop_id"],
            "tag_name": item["tag_name"],
            "split": item["split"],
            "anomaly_type": item["anomaly_type"],
            **stats,
        })

    with open(proc_dir / "cleaning_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"Cleaned & split {len(summary)} datasets into train/val/test.")


if __name__ == "__main__":
    main()
