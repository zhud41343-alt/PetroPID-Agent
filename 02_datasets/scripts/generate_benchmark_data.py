"""Generate 30 high-fidelity desensitized petrochemical PID loop datasets.

Outputs:
- 02_datasets/raw/{loop_id}_{tag_name}.csv (raw telemetry with realistic noise & occasional spikes)
- 02_datasets/labels/loop_labels.json & loop_labels.csv (ground-truth loop metadata & anomaly labels)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "04_algorithms"))

from petro_pid.simulator import get_standard_chemical_loops, simulate_loop


def main() -> None:
    raw_dir = ROOT / "02_datasets" / "raw"
    labels_dir = ROOT / "02_datasets" / "labels"
    raw_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    loops = get_standard_chemical_loops()
    labels = []

    for idx, cfg in enumerate(loops):
        sim = simulate_loop(
            plant=cfg.plant,
            pid=cfg.pid,
            valve=cfg.valve,
            dt=cfg.dt,
            n_steps=600,
            noise_std=cfg.noise_std,
            disturbance_amp=cfg.disturbance_amp,
            disturbance_period=cfg.disturbance_period,
            seed=cfg.seed,
        )
        rng = np.random.default_rng(cfg.seed + 9000)
        pv_raw = sim["pv"].copy()
        # Inject realistic DCS sensor glitches (2 single-point spikes + 2 NaNs) for cleaning script to handle
        spike_pos = rng.choice(np.arange(30, 570), size=2, replace=False)
        pv_raw[spike_pos] += rng.choice([-1, 1], size=2) * 18.0
        nan_pos = rng.choice(np.arange(30, 570), size=2, replace=False)
        pv_raw[nan_pos] = np.nan

        df = pd.DataFrame({
            "timestamp_s": sim["t"],
            "loop_id": cfg.loop_id,
            "tag_name": cfg.tag_name,
            "sp": np.round(sim["sp"], 4),
            "pv": np.round(pv_raw, 4),
            "op": np.round(sim["op"], 4),
            "err": np.round(sim["sp"] - pv_raw, 4),
        })
        csv_name = f"{cfg.loop_id}_{cfg.tag_name}.csv"
        df.to_csv(raw_dir / csv_name, index=False, encoding="utf-8-sig")

        # Deterministic train/val/test split (18 train / 6 val / 6 test) stratified across anomaly classes
        split = "train" if (idx % 5 in (0, 1, 2)) else ("val" if idx % 5 == 3 else "test")
        labels.append({
            "loop_id": cfg.loop_id,
            "tag_name": cfg.tag_name,
            "unit_name": cfg.unit_name,
            "loop_type": cfg.loop_type,
            "description": cfg.description,
            "pv_unit": cfg.pv_unit,
            "anomaly_type": cfg.anomaly_type,
            "split": split,
            "raw_file": csv_name,
            "true_K": cfg.plant.K,
            "true_tau": cfg.plant.tau,
            "true_theta": cfg.plant.theta,
            "pv_bias": cfg.plant.pv_bias,
            "op_bias": cfg.plant.op_bias,
            "init_Kc": cfg.pid.Kc,
            "init_Ti": cfg.pid.Ti,
            "init_Td": cfg.pid.Td,
            "stiction_S": cfg.valve.stiction_S,
            "stiction_J": cfg.valve.stiction_J,
            "disturbance_amp": cfg.disturbance_amp,
            "disturbance_period": cfg.disturbance_period,
            "dt": cfg.dt,
            "n_samples": len(df),
            "desensitized": True,
        })

    with open(labels_dir / "loop_labels.json", "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)
    pd.DataFrame(labels).to_csv(labels_dir / "loop_labels.csv", index=False, encoding="utf-8-sig")
    print(f"Generated {len(labels)} raw loop datasets in {raw_dir}")


if __name__ == "__main__":
    main()
