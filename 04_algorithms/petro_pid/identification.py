"""Closed-Loop / Step-Response FOPDT System Identification & Quality Diagnostics (V3.0).

Upgrades in V3.0:
- Strictly separates 65% training segment and 35% held-out independent validation segment (zero overlap).
- Reports R², NRMSE, Fit% = (1 - NRMSE)*100 (clearly separated from R²), residual lag-1 autocorrelation,
  OP excitation adequacy, and unmeasured disturbance bias diagnostics.
- Deterministic `allow_next_stage` model validity gate (no ground-truth fallback allowed downstream!).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Tuple
import numpy as np
from scipy.optimize import least_squares


@dataclass
class IdentificationResult:
    success: bool
    allow_next_stage: bool
    K: float
    tau: float
    theta: float
    pv_bias: float
    op_bias: float
    train_r2: float
    val_r2: float
    val_nrmse: float
    val_fit_pct: float        # (1 - NRMSE) * 100 on held-out 35% validation segment
    val_accuracy_pct: float   # Primary validation accuracy metric = val_fit_pct (when val_r2 > 0)
    val_rmse: float
    val_bias_offset: float    # Mean residual on validation segment (detects unmeasured load step)
    resid_lag1_autocorr: float
    excitation_ok: bool
    excitation_op_std: float
    failure_reason: str
    closed_loop_bias_note: str
    message: str
    validation_profile: str = "v4.3.3"
    validation_evidence: Dict[str, object] | None = None

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["success"] = bool(d["success"])
        d["allow_next_stage"] = bool(d["allow_next_stage"])
        d["excitation_ok"] = bool(d["excitation_ok"])
        return d


def simulate_fopdt_open_loop(
    op: np.ndarray,
    K: float,
    tau: float,
    theta: float,
    pv_bias: float,
    op_bias: float,
    dt: float = 1.0,
) -> np.ndarray:
    """Simulate open-loop FOPDT PV response given input OP sequence."""
    n = len(op)
    pv_hat = np.zeros(n, dtype=float)
    d = max(1, int(round(theta / dt)))
    alpha = np.exp(-dt / max(tau, 0.2))
    y_dev = 0.0

    for k in range(n):
        pv_hat[k] = pv_bias + y_dev
        u_idx = k - d
        u_delayed = op[u_idx] if u_idx >= 0 else op_bias
        y_dev = alpha * y_dev + K * (1.0 - alpha) * (u_delayed - op_bias)
    return pv_hat


def _compute_validation_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Tuple[float, float, float, float, float, float]:
    """Return (R2, RMSE, NRMSE, fit_pct, bias_offset, lag1_autocorr)."""
    err = y_true - y_pred
    rmse = float(np.sqrt(np.mean(err ** 2)))
    bias_offset = float(np.mean(err))
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2)) + 1e-12
    r2 = float(1.0 - ss_res / ss_tot)
    y_range = float(np.max(y_true) - np.min(y_true)) + 1e-9
    nrmse = rmse / y_range
    fit_pct = float(np.clip((1.0 - nrmse) * 100.0, 0.0, 100.0))

    # Residual lag-1 autocorrelation (high value indicates unmodeled dynamics or disturbance)
    e0 = err - np.mean(err)
    denom = float(np.sum(e0 ** 2)) + 1e-12
    lag1 = float(np.sum(e0[:-1] * e0[1:]) / denom) if len(e0) > 2 else 0.0
    return round(r2, 4), round(rmse, 4), round(nrmse, 4), round(fit_pct, 2), round(bias_offset, 4), round(lag1, 4)


def identify_fopdt(
    pv: np.ndarray,
    op: np.ndarray,
    dt: float = 1.0,
    train_ratio: float = 0.65,
    max_delay_s: float = 12.0,
    min_val_r2: float = 0.80,
    min_val_fit_pct: float = 85.0,
) -> IdentificationResult:
    """Identify FOPDT parameters (K, tau, theta) with strict independent validation & failure gating."""
    pv = np.asarray(pv, dtype=float)
    op = np.asarray(op, dtype=float)
    n = len(pv)
    closed_loop_note = (
        "闭环历史数据辨识存在反馈相关偏差风险（尤其当存在未测负载阶跃或调节阀非线性粘滞时），"
        "必须通过后 35% 独立留出时段验证及残差自相关审查后方可进入整定阶段。"
    )

    if n < 100:
        return IdentificationResult(
            success=False, allow_next_stage=False,
            K=1.0, tau=10.0, theta=3.0, pv_bias=float(pv[0]) if n else 0.0, op_bias=float(op[0]) if n else 50.0,
            train_r2=0.0, val_r2=0.0, val_nrmse=1.0, val_fit_pct=0.0, val_accuracy_pct=0.0,
            val_rmse=999.0, val_bias_offset=0.0, resid_lag1_autocorr=0.0,
            excitation_ok=False, excitation_op_std=0.0,
            failure_reason="INSUFFICIENT_SAMPLE_LENGTH",
            closed_loop_bias_note=closed_loop_note,
            message="数据长度不足（需 >= 100 个采样点），拒绝进入整定阶段。",
        )

    op_std = float(np.std(op))
    pv_std = float(np.std(pv))
    if op_std < 0.30 or pv_std < 0.12:
        return IdentificationResult(
            success=False, allow_next_stage=False,
            K=1.0, tau=10.0, theta=3.0,
            pv_bias=float(np.mean(pv[:15])), op_bias=float(np.mean(op[:15])),
            train_r2=0.0, val_r2=0.0, val_nrmse=1.0, val_fit_pct=0.0, val_accuracy_pct=0.0,
            val_rmse=999.0, val_bias_offset=0.0, resid_lag1_autocorr=0.0,
            excitation_ok=False, excitation_op_std=round(op_std, 4),
            failure_reason="INSUFFICIENT_EXCITATION",
            closed_loop_bias_note=closed_loop_note,
            message=f"历史数据激励不足（OP 标准差={op_std:.3f}% < 0.30%），无法保证闭环辨识可靠性，建议在安全前提下施加小幅阶跃激励后重新辨识。",
        )

    split_idx = int(n * train_ratio)
    pv_train = pv[:split_idx]
    op_train = op[:split_idx]
    pv_bias_init = float(np.mean(pv[:15]))
    op_bias_init = float(np.mean(op[:15]))

    max_d = max(2, int(round(max_delay_s / dt)))
    best_cost = np.inf
    best_params = (1.0, 12.0, 3.0, pv_bias_init)

    for d_step in range(1, max_d + 1):
        theta_cand = d_step * dt

        def residuals(x: np.ndarray) -> np.ndarray:
            K_c, tau_c, pv_b = x[0], x[1], x[2]
            pred = simulate_fopdt_open_loop(
                op_train, K_c, tau_c, theta_cand, pv_b, op_bias_init, dt=dt
            )
            return pred[d_step + 5 :] - pv_train[d_step + 5 :]

        res = least_squares(
            residuals,
            x0=np.array([1.2, 12.0, pv_bias_init]),
            bounds=([-15.0, 1.0, pv_bias_init - 20.0], [15.0, 120.0, pv_bias_init + 20.0]),
            max_nfev=100,
        )
        if res.cost < best_cost:
            best_cost = res.cost
            best_params = (float(res.x[0]), float(res.x[1]), float(theta_cand), float(res.x[2]))

    K_hat, tau_hat, theta_hat, pv_bias_hat = best_params

    # Simulate across entire sequence so validation state is strictly causal (no data leakage)
    pv_pred_full = simulate_fopdt_open_loop(
        op, K_hat, tau_hat, theta_hat, pv_bias_hat, op_bias_init, dt=dt
    )
    train_r2, _, _, _, _, _ = _compute_validation_metrics(pv_train[15:], pv_pred_full[15:split_idx])
    val_r2, val_rmse, val_nrmse, val_fit_pct, val_bias_offset, lag1_ac = _compute_validation_metrics(
        pv[split_idx:], pv_pred_full[split_idx:]
    )

    # Strict independent validation gate
    reasons = []
    if abs(K_hat) <= 0.05:
        reasons.append("INVALID_PROCESS_GAIN")
    if val_r2 < min_val_r2:
        reasons.append(f"LOW_VAL_R2({val_r2:.3f}<{min_val_r2})")
    if val_fit_pct < min_val_fit_pct:
        reasons.append(f"LOW_VAL_FIT({val_fit_pct:.1f}%<{min_val_fit_pct}%)")

    model_valid = len(reasons) == 0
    failure_reason = "; ".join(reasons) if reasons else "NONE"
    # Note: val_accuracy_pct is strictly reported as val_fit_pct = (1-NRMSE)*100 (or 0 if val_r2 <= 0)
    # and NEVER conflates R2 with Fit%
    val_acc_pct = round(val_fit_pct if val_r2 > 0 else 0.0, 2)

    if model_valid:
        msg = (
            f"模型辨识通过独立验证：FOPDT K={K_hat:.3f}, τ={tau_hat:.2f}s, θ={theta_hat:.1f}s；"
            f"留出验证集 R²={val_r2:.4f}，NRMSE={val_nrmse:.4f}，Fit准确率={val_acc_pct:.2f}%，残差自相关={lag1_ac:.2f}。"
        )
    else:
        bias_hint = (
            f"（检测到验证段存在明显均值偏移 {val_bias_offset:+.3f}，可能受未测负载阶跃或慢动态激励不足影响）"
            if abs(val_bias_offset) > 0.20
            else ""
        )
        msg = (
            f"模型辨识未通过独立验证门控 [{failure_reason}]：留出验证集 R²={val_r2:.4f}，"
            f"NRMSE={val_nrmse:.4f}，Fit准确率={val_acc_pct:.2f}%{bias_hint}，禁止基于不可信模型直接推荐参数。"
        )

    return IdentificationResult(
        success=model_valid,
        allow_next_stage=model_valid,
        K=round(K_hat, 4),
        tau=round(tau_hat, 3),
        theta=round(theta_hat, 2),
        pv_bias=round(pv_bias_hat, 3),
        op_bias=round(op_bias_init, 3),
        train_r2=train_r2,
        val_r2=val_r2,
        val_nrmse=val_nrmse,
        val_fit_pct=val_fit_pct,
        val_accuracy_pct=val_acc_pct,
        val_rmse=val_rmse,
        val_bias_offset=val_bias_offset,
        resid_lag1_autocorr=lag1_ac,
        excitation_ok=True,
        excitation_op_std=round(op_std, 4),
        failure_reason=failure_reason,
        closed_loop_bias_note=closed_loop_note,
        message=msg,
    )


def identify_fopdt_with_observable_load_step_check(
    pv: np.ndarray,
    op: np.ndarray,
    dt: float = 1.0,
    train_ratio: float = 0.65,
    max_delay_s: float = 12.0,
    min_val_r2: float = 0.80,
    min_val_fit_pct: float = 85.0,
) -> IdentificationResult:
    """Apply a conservative observable-only load-step validation fallback.

    The standard independent holdout gate always runs first. The fallback can
    only upgrade a failed result when residual variance remains stable, lag-1
    residual autocorrelation is low, the validation residual has a statistically
    large constant offset, and subtracting only that scalar offset clears a
    stricter holdout gate. It never refits process parameters or bypasses the
    excitation and model-quality checks.
    """
    base = identify_fopdt(
        pv=pv,
        op=op,
        dt=dt,
        train_ratio=train_ratio,
        max_delay_s=max_delay_s,
        min_val_r2=min_val_r2,
        min_val_fit_pct=min_val_fit_pct,
    )
    evidence: Dict[str, object] = {
        "profile": "v4.3.4_observable_load_step",
        "load_step_compensated": False,
        "load_step_detected": False,
        "offset_adj_val_r2": None,
        "offset_adj_val_fit_pct": None,
        "std_ratio_va_over_tr": None,
        "dc_shift_sigma": None,
        "gate_conditions": {
            "train_r2": 0.92,
            "resid_lag1_autocorr_max": 0.45,
            "std_ratio_max": 1.5,
            "dc_shift_sigma_min": 2.5,
            "offset_adj_val_r2": 0.92,
            "offset_adj_val_fit_pct": 92.0,
        },
    }
    if base.allow_next_stage or not base.excitation_ok:
        base.validation_profile = "v4.3.4_observable_load_step"
        base.validation_evidence = evidence
        return base

    pv_arr = np.asarray(pv, dtype=float)
    op_arr = np.asarray(op, dtype=float)
    split_idx = int(len(pv_arr) * train_ratio)
    pred = simulate_fopdt_open_loop(
        op_arr,
        base.K,
        base.tau,
        base.theta,
        base.pv_bias,
        base.op_bias,
        dt=dt,
    )
    train_resid = pv_arr[:split_idx] - pred[:split_idx]
    val_resid = pv_arr[split_idx:] - pred[split_idx:]
    std_train = float(np.std(train_resid))
    std_val = float(np.std(val_resid))
    dc_shift = abs(float(np.mean(val_resid)) - float(np.mean(train_resid)))
    dc_shift_sigma = dc_shift / max(std_train, 1e-9)
    std_ratio = std_val / max(std_train, 1e-9)
    adjusted_resid = val_resid - float(np.mean(val_resid))
    val_actual = pv_arr[split_idx:]
    ss_total = float(np.sum((val_actual - np.mean(val_actual)) ** 2)) + 1e-12
    adjusted_r2 = 1.0 - float(np.sum(adjusted_resid ** 2)) / ss_total
    y_range = float(np.max(val_actual) - np.min(val_actual)) + 1e-9
    adjusted_rmse = float(np.sqrt(np.mean(adjusted_resid ** 2)))
    adjusted_fit = float(np.clip((1.0 - adjusted_rmse / y_range) * 100.0, 0.0, 100.0))
    evidence.update({
        "load_step_detected": bool(dc_shift_sigma >= 2.5),
        "offset_adj_val_r2": round(adjusted_r2, 4),
        "offset_adj_val_fit_pct": round(adjusted_fit, 2),
        "std_ratio_va_over_tr": round(std_ratio, 3),
        "dc_shift_sigma": round(dc_shift_sigma, 2),
    })
    passed = (
        base.train_r2 >= 0.92
        and base.resid_lag1_autocorr <= 0.45
        and std_val <= (1.5 * std_train + 0.02)
        and dc_shift_sigma >= 2.5
        and adjusted_r2 >= 0.92
        and adjusted_fit >= 92.0
    )
    if not passed:
        base.validation_profile = "v4.3.4_observable_load_step"
        base.validation_evidence = evidence
        return base

    evidence["load_step_compensated"] = True
    return IdentificationResult(
        success=True,
        allow_next_stage=True,
        K=base.K,
        tau=base.tau,
        theta=base.theta,
        pv_bias=base.pv_bias,
        op_bias=base.op_bias,
        train_r2=base.train_r2,
        val_r2=round(adjusted_r2, 4),
        val_nrmse=round(adjusted_rmse / y_range, 4),
        val_fit_pct=round(adjusted_fit, 2),
        val_accuracy_pct=round(adjusted_fit, 2),
        val_rmse=round(adjusted_rmse, 4),
        val_bias_offset=base.val_bias_offset,
        resid_lag1_autocorr=base.resid_lag1_autocorr,
        excitation_ok=base.excitation_ok,
        excitation_op_std=base.excitation_op_std,
        failure_reason="",
        closed_loop_bias_note=base.closed_loop_bias_note,
        message=(
            f"验证段检出纯直流负载阶跃偏移，未重新拟合模型参数。扣除常值偏移后留出验证 "
            f"R²={adjusted_r2:.4f}、Fit={adjusted_fit:.2f}% 通过增强 C-000 门控。"
        ),
        validation_profile="v4.3.4_observable_load_step",
        validation_evidence=evidence,
    )
