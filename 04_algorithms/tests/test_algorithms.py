"""Unit tests & KPI verification for PetroPID core industrial control algorithms."""

from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "04_algorithms"))

from petro_pid import (
    PlantParams,
    PIDParams,
    ValveParams,
    simulate_loop,
    get_standard_chemical_loops,
    diagnose_loop,
    identify_fopdt,
    tune_pid,
    verify_pid_safety,
)


def test_simulator_runs_cleanly():
    plant = PlantParams(K=1.2, tau=15.0, theta=4.0, pv_bias=100.0, op_bias=50.0)
    pid = PIDParams(Kc=1.2, Ti=15.0, Td=0.0)
    sim = simulate_loop(plant, pid, ValveParams(), dt=1.0, n_steps=400, seed=42)
    assert len(sim["pv"]) == 400
    assert np.all(np.isfinite(sim["pv"]))
    assert np.all((sim["op"] >= 0.0) & (sim["op"] <= 100.0))


def test_diagnosis_accuracy_across_30_loops():
    loops = get_standard_chemical_loops()
    correct = 0
    for cfg in loops:
        sim = simulate_loop(
            cfg.plant, cfg.pid, cfg.valve, dt=cfg.dt, n_steps=600,
            noise_std=cfg.noise_std, disturbance_amp=cfg.disturbance_amp,
            disturbance_period=cfg.disturbance_period, seed=cfg.seed,
        )
        res = diagnose_loop(
            sim["sp"], sim["pv"], sim["op"], dt=cfg.dt,
            estimated_delay_s=cfg.plant.theta, pid_kc=cfg.pid.Kc, pid_ti=cfg.pid.Ti,
        )
        if res.anomaly_type == cfg.anomaly_type:
            correct += 1
    acc = correct / len(loops)
    assert acc >= 0.85, f"Diagnosis accuracy {acc:.2%} below 85% KPI"


def test_identification_independent_validation_accuracy():
    plant = PlantParams(K=1.4, tau=16.0, theta=5.0, pv_bias=505.0, op_bias=50.0)
    pid = PIDParams(Kc=2.85, Ti=6.5, Td=0.0)
    sim = simulate_loop(plant, pid, ValveParams(), dt=1.0, n_steps=600, noise_std=0.06, seed=201)
    res = identify_fopdt(sim["pv"], sim["op"], dt=1.0)
    assert res.success
    assert res.val_accuracy_pct >= 90.0, f"Val accuracy {res.val_accuracy_pct}% < 90%"


def test_tuning_improves_aggressive_and_sluggish_loops():
    # Aggressive loop
    plant = PlantParams(K=1.4, tau=16.0, theta=5.0, pv_bias=505.0, op_bias=50.0)
    bad_pid = PIDParams(Kc=2.85, Ti=6.5, Td=0.0)
    t_res = tune_pid(plant, bad_pid, anomaly_type="AGGRESSIVE_TUNING")
    assert t_res.success
    assert t_res.improved_metrics["iae_reduction_pct"] >= 15.0
    assert t_res.improved_metrics["oi_reduction_pct"] >= 20.0

    # Safety verifier must approve recommended PID
    rec = t_res.recommended_pid
    v_res = verify_pid_safety(plant, PIDParams(Kc=rec["Kc"], Ti=rec["Ti"], Td=rec["Td"]))
    assert v_res.constraint_coverage_pct == 100.0
    assert v_res.approved
    assert v_res.multi_regime_pass_rate_pct >= 85.0


def test_safety_verifier_flags_unsafe_pid_100_percent():
    plant = PlantParams(K=1.6, tau=16.0, theta=6.0, pv_bias=200.0, op_bias=50.0)
    unsafe_pid = PIDParams(Kc=9.5, Ti=1.0, Td=25.0)
    v_res = verify_pid_safety(plant, unsafe_pid)
    assert v_res.constraint_coverage_pct == 100.0
    assert not v_res.approved
    assert "VIOLATION_KC_OUT_OF_BOUNDS" in v_res.violation_tags
    assert "VIOLATION_TI_OUT_OF_BOUNDS" in v_res.violation_tags
    assert "VIOLATION_TD_OUT_OF_BOUNDS" in v_res.violation_tags
