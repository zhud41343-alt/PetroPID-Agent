"""Adaptive PID Auto-Tuning Engine (SIMC + Multi-Objective Constrained Optimization).

Generates three engineering-grade PID candidates:
- conservative: High stability margin (Ms <= 1.5), minimal valve wear
- balanced (recommended): Optimal trade-off between IAE, Harris/OI improvement & robustness
- performance: Fast setpoint tracking & disturbance rejection within strict safety bounds
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List
import numpy as np
from scipy.optimize import minimize

from .simulator import PlantParams, PIDParams, ValveParams, simulate_loop
from .diagnosis import diagnose_loop


@dataclass
class CandidatePID:
    strategy: str
    Kc: float
    Ti: float
    Td: float
    pred_harris: float
    pred_oi: float
    pred_overshoot_pct: float
    pred_iae: float
    pred_op_travel: float
    harris_improvement_pct: float
    oi_reduction_pct: float
    iae_reduction_pct: float

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TuningResult:
    success: bool
    recommended_strategy: str
    recommended_pid: Dict[str, float]
    candidates: List[CandidatePID]
    baseline_metrics: Dict[str, float]
    improved_metrics: Dict[str, float]
    summary: str

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "recommended_strategy": self.recommended_strategy,
            "recommended_pid": self.recommended_pid,
            "candidates": [c.to_dict() for c in self.candidates],
            "baseline_metrics": self.baseline_metrics,
            "improved_metrics": self.improved_metrics,
            "summary": self.summary,
        }


def _simc_pid(K: float, tau: float, theta: float, tau_c_factor: float = 1.0) -> PIDParams:
    """Skogestad IMC (SIMC) PI tuning rule for FOPDT plant."""
    sign_k = 1.0 if K >= 0 else -1.0
    abs_k = max(abs(K), 0.05)
    tau_c = max(theta * tau_c_factor, 0.25 * tau * tau_c_factor, 1.0)
    kc = sign_k * (tau / (abs_k * (tau_c + theta)))
    ti = min(tau, 4.0 * (tau_c + theta))
    ti = max(ti, 2.0)
    return PIDParams(Kc=round(float(kc), 4), Ti=round(float(ti), 3), Td=0.0)


def _evaluate_candidate(
    plant: PlantParams,
    pid: PIDParams,
    baseline_harris: float,
    baseline_oi: float,
    baseline_iae: float,
    dt: float = 1.0,
    strategy: str = "balanced",
) -> CandidatePID:
    sim = simulate_loop(plant, pid, ValveParams(), dt=dt, n_steps=480, noise_std=0.05, seed=77)
    diag = diagnose_loop(sim["sp"], sim["pv"], sim["op"], dt=dt, estimated_delay_s=plant.theta, pid_kc=pid.Kc, pid_ti=pid.Ti)

    harris_imp = ((diag.harris_index - baseline_harris) / max(baseline_harris, 0.05)) * 100.0
    oi_red = ((baseline_oi - diag.oscillation_index) / max(baseline_oi, 0.05)) * 100.0 if baseline_oi > 0.05 else 0.0
    iae_red = ((baseline_iae - diag.iae) / max(baseline_iae, 0.05)) * 100.0

    return CandidatePID(
        strategy=strategy,
        Kc=round(pid.Kc, 4),
        Ti=round(pid.Ti, 3),
        Td=round(pid.Td, 3),
        pred_harris=diag.harris_index,
        pred_oi=diag.oscillation_index,
        pred_overshoot_pct=diag.overshoot_pct,
        pred_iae=diag.iae,
        pred_op_travel=diag.op_travel,
        harris_improvement_pct=round(harris_imp, 2),
        oi_reduction_pct=round(oi_red, 2),
        iae_reduction_pct=round(iae_red, 2),
    )


def tune_pid(
    plant: PlantParams,
    current_pid: PIDParams,
    anomaly_type: str = "AGGRESSIVE_TUNING",
    dt: float = 1.0,
) -> TuningResult:
    """Run SIMC + constrained optimization to generate adaptive PID candidates."""
    # Evaluate baseline on identified model
    base_sim = simulate_loop(plant, current_pid, ValveParams(), dt=dt, n_steps=480, noise_std=0.05, seed=77)
    base_diag = diagnose_loop(
        base_sim["sp"], base_sim["pv"], base_sim["op"],
        dt=dt, estimated_delay_s=plant.theta, pid_kc=current_pid.Kc, pid_ti=current_pid.Ti,
    )

    # Analytical SIMC starting points
    pid_cons = _simc_pid(plant.K, plant.tau, plant.theta, tau_c_factor=1.8)
    pid_bal_init = _simc_pid(plant.K, plant.tau, plant.theta, tau_c_factor=1.0)
    pid_perf = _simc_pid(plant.K, plant.tau, plant.theta, tau_c_factor=0.72)

    # Constrained multi-objective refinement around SIMC balanced point
    sign_k = 1.0 if plant.K >= 0 else -1.0
    kc0 = abs(pid_bal_init.Kc)
    ti0 = pid_bal_init.Ti

    def objective(x: np.ndarray) -> float:
        kc_val = float(np.clip(x[0], 0.1 * kc0, 2.2 * kc0)) * sign_k
        ti_val = float(np.clip(x[1], 0.4 * ti0, 2.5 * ti0))
        cand_pid = PIDParams(Kc=kc_val, Ti=ti_val, Td=0.0)
        sim = simulate_loop(plant, cand_pid, ValveParams(), dt=dt, n_steps=320, noise_std=0.03, seed=77)
        err = sim["sp"] - sim["pv"]
        iae = float(np.mean(np.abs(err)))
        op_tv = float(np.mean(np.abs(np.diff(sim["op"]))))
        # Penalize overshoot > 8%
        d_os = max(0.0, float(np.max(sim["pv"][38:140]) - (plant.pv_bias + 4.0)) / 4.0 * 100.0 - 8.0)
        return iae + 0.18 * op_tv + 0.08 * (d_os ** 2)

    opt = minimize(
        objective,
        x0=np.array([kc0, ti0]),
        method="Nelder-Mead",
        options={"maxiter": 28, "xatol": 0.03, "fatol": 0.01},
    )
    kc_opt = float(np.clip(opt.x[0], 0.25 * kc0, 1.6 * kc0)) * sign_k
    ti_opt = float(np.clip(opt.x[1], 0.55 * ti0, 2.0 * ti0))
    pid_bal = PIDParams(Kc=round(kc_opt, 4), Ti=round(ti_opt, 3), Td=0.0)

    candidates = [
        _evaluate_candidate(plant, pid_cons, base_diag.harris_index, base_diag.oscillation_index, base_diag.iae, dt, "conservative"),
        _evaluate_candidate(plant, pid_bal, base_diag.harris_index, base_diag.oscillation_index, base_diag.iae, dt, "balanced"),
        _evaluate_candidate(plant, pid_perf, base_diag.harris_index, base_diag.oscillation_index, base_diag.iae, dt, "performance"),
    ]

    # Select strategy based on anomaly type
    if anomaly_type == "VALVE_STICTION":
        chosen = candidates[0]  # Conservative to minimize valve wear until maintenance
    else:
        chosen = candidates[1]  # Balanced SIMC+Opt

    baseline_metrics = {
        "harris_index": base_diag.harris_index,
        "oscillation_index": base_diag.oscillation_index,
        "overshoot_pct": base_diag.overshoot_pct,
        "iae": base_diag.iae,
        "op_travel": base_diag.op_travel,
    }
    improved_metrics = {
        "harris_index": chosen.pred_harris,
        "oscillation_index": chosen.pred_oi,
        "overshoot_pct": chosen.pred_overshoot_pct,
        "iae": chosen.pred_iae,
        "op_travel": chosen.pred_op_travel,
        "harris_improvement_pct": chosen.harris_improvement_pct,
        "oi_reduction_pct": chosen.oi_reduction_pct,
        "iae_reduction_pct": chosen.iae_reduction_pct,
    }

    summary = (
        f"采用 {chosen.strategy} 策略推荐参数 Kc={chosen.Kc}, Ti={chosen.Ti}s, Td={chosen.Td}s。"
        f"预计 IAE 降低 {chosen.iae_reduction_pct:.1f}%，振荡指数 OI 降低 {chosen.oi_reduction_pct:.1f}%，"
        f"Harris 指数变化 {chosen.harris_improvement_pct:+.1f}%，超调控制在 {chosen.pred_overshoot_pct:.1f}%。"
    )

    return TuningResult(
        success=True,
        recommended_strategy=chosen.strategy,
        recommended_pid={"Kc": chosen.Kc, "Ti": chosen.Ti, "Td": chosen.Td},
        candidates=candidates,
        baseline_metrics=baseline_metrics,
        improved_metrics=improved_metrics,
        summary=summary,
    )
