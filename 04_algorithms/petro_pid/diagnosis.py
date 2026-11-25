"""Industrial Control Loop Performance Assessment & Fault Diagnosis.

Computes standard petrochemical loop KPIs:
- Harris Index (minimum variance control benchmark, Desborough & Harris 1992)
- Oscillation Index (OI, autocorrelation decay & spectral regularity)
- Valve Stiction Index (SI, PV-OP phase portrait flatness / stick-slip detector)
- Dynamic tracking metrics (IAE, ISE, max overshoot %, OP total variation)
- Structured root-cause diagnosis with confidence & actionability
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
import numpy as np


@dataclass
class DiagnosisResult:
    anomaly_type: str             # NORMAL | AGGRESSIVE_TUNING | SLUGGISH_TUNING | VALVE_STICTION | EXTERNAL_DISTURBANCE | MODEL_MISMATCH
    severity: str                 # HEALTHY | WARNING | CRITICAL
    confidence: float             # 0.0 - 1.0
    harris_index: float           # 0.0 - 1.0 (higher is better)
    oscillation_index: float      # 0.0 - 1.0 (lower is better)
    oscillation_period_s: float   # Dominant oscillation period (s), 0 if none
    stiction_index: float         # 0.0 - 1.0 (higher means stronger valve stiction)
    iae: float                    # Integral of Absolute Error (normalized per step)
    ise: float                    # Integral of Squared Error (normalized per step)
    overshoot_pct: float          # Maximum step overshoot (%)
    op_travel: float              # Mean |dOP| per step (%)
    needs_retuning: bool          # Whether PID retuning is recommended
    needs_valve_maintenance: bool # Whether mechanical valve maintenance is required
    root_cause_summary: str
    recommended_action: str
    evidence: Dict[str, float]
    evidence_sufficient: bool = True
    uncertainty_reason: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


def compute_harris_index(err: np.ndarray, delay_steps: int = 4, ar_order: int = 12) -> float:
    """Estimate Harris minimum-variance control index in [0, 1].

    Fits an AR(p) model to control error e(t) and computes the impulse-response
    minimum variance over the dead-time horizon d:
        sigma_mv^2 = (1 + sum_{i=1}^{d-1} psi_i^2) * sigma_a^2
        Harris = clip(sigma_mv^2 / var(e), 0, 1)
    """
    e = np.asarray(err, dtype=float)
    e = e - np.mean(e)
    var_e = float(np.var(e))
    if var_e < 1e-8 or len(e) < ar_order + delay_steps + 5:
        return 0.95

    p = min(ar_order, max(2, len(e) // 10))
    d = max(1, min(delay_steps, 12))

    # Build lagged design matrix for AR(p)
    Y = e[p:]
    X = np.column_stack([e[p - i - 1 : len(e) - i - 1] for i in range(p)])
    try:
        phi, _, _, _ = np.linalg.lstsq(X, Y, rcond=None)
    except np.linalg.LinAlgError:
        return 0.5

    resid = Y - X @ phi
    sigma_a2 = float(np.var(resid))

    # Impulse response weights psi_0..psi_{d-1} of 1 / (1 - sum phi_i z^{-i})
    psi = np.zeros(d, dtype=float)
    psi[0] = 1.0
    for k in range(1, d):
        s = 0.0
        for j in range(1, min(k, p) + 1):
            s += phi[j - 1] * psi[k - j]
        psi[k] = s

    sigma_mv2 = float(np.sum(psi ** 2)) * sigma_a2
    harris = float(np.clip(sigma_mv2 / max(var_e, 1e-9), 0.05, 0.99))
    return round(harris, 4)


def compute_oscillation_index(
    signal: np.ndarray, dt: float = 1.0
) -> Tuple[float, float]:
    """Compute Oscillation Index (OI in [0, 1]) and dominant period (seconds).

    Combines normalized autocorrelation peak regularity (Miao-Seborg style)
    and FFT spectral concentration on detrended error signal.
    """
    x = np.asarray(signal, dtype=float)
    x = x - np.mean(x)
    n = len(x)
    std_x = float(np.std(x))
    if n < 30 or std_x < 1e-4:
        return 0.0, 0.0

    # Autocorrelation function (normalized)
    acf = np.correlate(x, x, mode="full")[n - 1 :]
    acf = acf / max(acf[0], 1e-12)

    # Find first minimum and subsequent positive peak in ACF
    max_lag = min(n // 2, 180)
    acf_slice = acf[:max_lag]

    # Locate local peaks and troughs after lag 2
    troughs = []
    peaks = []
    for i in range(2, len(acf_slice) - 1):
        if acf_slice[i] < acf_slice[i - 1] and acf_slice[i] <= acf_slice[i + 1]:
            troughs.append((i, acf_slice[i]))
        if acf_slice[i] > acf_slice[i - 1] and acf_slice[i] >= acf_slice[i + 1]:
            peaks.append((i, acf_slice[i]))

    # Spectral concentration via FFT
    freqs = np.fft.rfftfreq(n, d=dt)
    psd = np.abs(np.fft.rfft(x * np.hanning(n))) ** 2
    # Ignore DC and very low frequencies (step trends, period > n*dt/2.5)
    valid_mask = (freqs >= 2.5 / (n * dt)) & (freqs <= 0.35 / dt)
    if not np.any(valid_mask):
        return 0.0, 0.0

    psd_valid = psd[valid_mask]
    freqs_valid = freqs[valid_mask]
    total_power = float(np.sum(psd_valid)) + 1e-12
    peak_idx = int(np.argmax(psd_valid))
    peak_freq = float(freqs_valid[peak_idx])
    # Energy within +-2 bins of dominant peak
    lo = max(0, peak_idx - 2)
    hi = min(len(psd_valid), peak_idx + 3)
    spectral_ratio = float(np.sum(psd_valid[lo:hi]) / total_power)
    dominant_period = (1.0 / peak_freq) if peak_freq > 1e-6 else 0.0

    # ACF oscillation regularity
    acf_osc = 0.0
    if troughs and peaks:
        first_trough_lag, first_trough_val = troughs[0]
        next_peaks = [p for p in peaks if p[0] > first_trough_lag]
        if next_peaks:
            p1_lag, p1_val = next_peaks[0]
            if first_trough_val < -0.05 and p1_val > 0.05:
                # Peak-to-trough swing indicates sustained oscillation
                acf_osc = float(np.clip((p1_val - first_trough_val) / 1.4, 0.0, 1.0))

    # Blend ACF regularity and spectral peakiness
    oi = float(np.clip(0.65 * acf_osc + 0.35 * spectral_ratio * (1.0 if acf_osc > 0.1 else 0.35), 0.0, 1.0))
    if oi < 0.15:
        dominant_period = 0.0
    return round(oi, 4), round(dominant_period, 2)


def compute_stiction_index(
    sp: np.ndarray, pv: np.ndarray, op: np.ndarray
) -> float:
    """Detect control valve stiction using PV-OP stick-slip waveform & phase features.

    Key physical signatures of Choudhury valve stiction vs sinusoidal disturbance:
    1. Flat-plateau stick ratio: on lightly smoothed PV, |dPV| stays near zero while
       controller OP ramps monotonically (integrator winding up during stick phase).
    2. Triangular/square harmonic distortion (THD) of PV and sawtooth shape of OP
       (stiction produces strong 3rd harmonic / non-sinusoidal jump transitions,
       whereas external sinusoidal disturbance has low harmonic distortion).
    3. Distinct stick-slip step-jump ratio (95th percentile |dPV| / median |dPV|).
    """
    sp = np.asarray(sp, dtype=float)
    pv = np.asarray(pv, dtype=float)
    op = np.asarray(op, dtype=float)

    # Extract the longest constant-SP segment (eliminates DC setpoint-step contamination!)
    dsp = np.abs(np.diff(sp, prepend=sp[0]))
    step_idxs = np.where(dsp > 0.5)[0]
    boundaries = [0] + list(step_idxs) + [len(sp)]
    best_seg = (20, len(sp))
    best_len = 0
    for i in range(len(boundaries) - 1):
        s0 = boundaries[i] + 35
        s1 = boundaries[i + 1] - 2
        if s1 - s0 > best_len:
            best_len = s1 - s0
            best_seg = (s0, s1)

    s0, s1 = best_seg
    if s1 - s0 < 50:
        s0, s1 = 20, len(sp)

    pv_s = pv[s0:s1]
    op_s = op[s0:s1]
    if np.std(op_s) < 0.25 or np.std(pv_s) < 0.12:
        return 0.0

    # 4-point symmetric smoothing preserves stick-slip breakaway impulses while suppressing white sensor noise
    kernel = np.array([0.2, 0.3, 0.3, 0.2])
    pv_sm = np.convolve(pv_s, kernel, mode="valid")
    op_sm = np.convolve(op_s, kernel, mode="valid")
    dpv = np.diff(pv_sm)
    dop = np.diff(op_sm)
    d2pv = np.diff(dpv)

    # Feature 1: Slip-jump acceleration kurtosis (d²PV)
    # Physical basis: Valve breakaway from static friction (Choudhury slip-jump J) creates sharp
    # impulsive acceleration spikes (kurtosis >= 3.7), whereas smooth sinusoidal disturbance stays <= 2.9
    kurt_d2pv = float(np.mean((d2pv / (np.std(d2pv) + 1e-8)) ** 4))

    # Feature 2: Velocity non-sinusoidality kurtosis (dPV)
    # Physical basis: Pure sine wave has theoretical kurtosis = 1.50; stick-slip plateaus + jumps push >= 1.85
    kurt_dpv = float(np.mean((dpv / (np.std(dpv) + 1e-8)) ** 4))

    # Feature 3: Stick-plateau ratio (OP moving steadily while smoothed PV is flat)
    op_moving = np.abs(dop) > max(0.03, 0.25 * np.std(dop))
    pv_flat = np.abs(dpv) < max(0.035, 0.25 * np.std(dpv))
    stick_flat_ratio = float(np.mean(pv_flat[op_moving])) if np.sum(op_moving) >= 15 else 0.0

    # Feature 4: OP-PV phase hysteresis loop area (normalized shoelace area)
    pv_z = (pv_sm - np.mean(pv_sm)) / (np.std(pv_sm) + 1e-8)
    op_z = (op_sm - np.mean(op_sm)) / (np.std(op_sm) + 1e-8)
    hyst_area = float(np.abs(np.mean(op_z[:-1] * pv_z[1:] - op_z[1:] * pv_z[:-1])))

    f_acc = float(np.clip((kurt_d2pv - 2.95) / 1.80, 0.0, 1.0))
    f_vel = float(np.clip((kurt_dpv - 1.68) / 0.55, 0.0, 1.0))
    f_flat = float(np.clip((stick_flat_ratio - 0.15) / 0.30, 0.0, 1.0))
    f_hyst = float(np.clip((hyst_area - 0.08) / 0.22, 0.0, 1.0))

    stiction_idx = float(np.clip(0.45 * f_acc + 0.35 * f_vel + 0.10 * f_flat + 0.10 * f_hyst, 0.0, 1.0))
    return round(stiction_idx, 4)


def compute_scale_invariant_stiction_score(
    pv: np.ndarray, op: np.ndarray, threshold: float = 0.40
) -> Tuple[bool, float, Dict[str, float]]:
    """Scale-invariant physics-fusion valve stiction detector (V4.3.4 Industrial Extension).

    Addresses two fundamental limitations on heterogeneous real industrial loops (e.g., ISDB):
    1. Engineering-unit scale invariance: z-scores PV & OP prior to derivative/plateau checks
       so loops with small engineering units (e.g., MPa, mole fraction, 0-1 OP) are not zeroed out.
    2. Integrating + self-regulating coverage: fuses Horch (1999) OP-PV cross-correlation
       odd-symmetry (self-regulating loops) with normalized stick-plateau ratio (both integrating
       and self-regulating loops) and normalized PV-OP phase-plane hysteresis area.

    Uses fixed equal-scale textbook physical weights (0.50 / 0.30 / 0.20) with no label fitting.
    """
    pv_arr = np.asarray(pv, dtype=float)
    op_arr = np.asarray(op, dtype=float)
    sx, sy = float(np.std(op_arr)), float(np.std(pv_arr))
    if len(pv_arr) < 40 or sx < 1e-9 or sy < 1e-9:
        return False, 0.0, {"stick_flat_ratio": 0.0, "horch_odd_ratio": 0.0, "hyst_area": 0.0, "peak_ccf": 0.0}

    op_z = (op_arr - float(np.mean(op_arr))) / sx
    pv_z = (pv_arr - float(np.mean(pv_arr))) / sy
    n = len(op_z)

    # 1. Horch (1999) OP-PV cross-correlation odd-energy symmetry ratio
    max_lag = min(60, n // 4)
    lags = np.arange(-max_lag, max_lag + 1)
    ccf = np.array(
        [
            float(np.mean(op_z[: n - abs(k)] * pv_z[abs(k) :]))
            if k >= 0
            else float(np.mean(op_z[abs(k) :] * pv_z[: n - abs(k)]))
            for k in lags
        ]
    )
    mid = max_lag
    pos, neg = ccf[mid + 1 :], ccf[mid - 1 :: -1]
    even_e = float(np.mean((0.5 * (pos + neg)) ** 2))
    odd_e = float(np.mean((0.5 * (pos - neg)) ** 2))
    odd_ratio = odd_e / (even_e + odd_e + 1e-12)
    peak_ccf = float(np.max(np.abs(ccf)))

    # 2. Scale-invariant stick-plateau ratio (valid for integrating & self-regulating plants)
    kernel = np.array([0.2, 0.3, 0.3, 0.2])
    pv_sm = np.convolve(pv_z, kernel, mode="valid")
    op_sm = np.convolve(op_z, kernel, mode="valid")
    dpv = np.diff(pv_sm)
    dop = np.diff(op_sm)
    op_moving = np.abs(dop) > 0.25 * float(np.std(dop) + 1e-9)
    pv_flat = np.abs(dpv) < 0.25 * float(np.std(dpv) + 1e-9)
    stick_flat = float(np.mean(pv_flat[op_moving])) if int(np.sum(op_moving)) >= 15 else 0.0

    # 3. Normalized PV-OP phase hysteresis area
    hyst_area = abs(float(np.mean(op_sm[:-1] * pv_sm[1:] - op_sm[1:] * pv_sm[:-1])))

    score = float(
        0.50 * np.clip(stick_flat / 0.40, 0.0, 1.0)
        + 0.30 * np.clip(odd_ratio, 0.0, 1.0)
        + 0.20 * np.clip(hyst_area / 0.15, 0.0, 1.0)
    )
    score = round(score, 4)
    evidence = {
        "stick_flat_ratio": round(stick_flat, 4),
        "horch_odd_ratio": round(odd_ratio, 4),
        "hyst_area": round(hyst_area, 4),
        "peak_ccf": round(peak_ccf, 4),
    }
    return bool(score >= threshold), score, evidence


def compute_step_overshoot(sp: np.ndarray, pv: np.ndarray) -> float:
    """Compute maximum percentage overshoot across setpoint step changes."""
    sp = np.asarray(sp, dtype=float)
    pv = np.asarray(pv, dtype=float)
    dsp = np.diff(sp, prepend=sp[0])
    step_idxs = np.where(np.abs(dsp) > 0.5)[0]
    if len(step_idxs) == 0:
        return 0.0

    max_os = 0.0
    for i, idx in enumerate(step_idxs):
        step_size = sp[idx] - sp[idx - 1]
        end = step_idxs[i + 1] if i + 1 < len(step_idxs) else len(sp)
        seg = pv[idx : min(end, idx + 120)]
        if len(seg) < 5 or abs(step_size) < 1e-3:
            continue
        if step_size > 0:
            os_val = (float(np.max(seg)) - sp[idx]) / abs(step_size) * 100.0
        else:
            os_val = (sp[idx] - float(np.min(seg))) / abs(step_size) * 100.0
        max_os = max(max_os, max(0.0, os_val))
    return round(max_os, 2)


def diagnose_loop(
    sp: np.ndarray,
    pv: np.ndarray,
    op: np.ndarray,
    dt: float = 1.0,
    estimated_delay_s: float = 4.0,
    pid_kc: Optional[float] = None,
    pid_ti: Optional[float] = None,
) -> DiagnosisResult:
    """Perform comprehensive industrial PID loop diagnosis."""
    sp = np.asarray(sp, dtype=float)
    pv = np.asarray(pv, dtype=float)
    op = np.asarray(op, dtype=float)
    err = sp - pv

    delay_steps = max(1, int(round(estimated_delay_s / dt)))
    harris = compute_harris_index(err, delay_steps=delay_steps)

    # Compute OI on steady-SP error segments so SP steps don't inflate OI
    dsp = np.abs(np.diff(sp, prepend=sp[0]))
    step_idxs = np.where(dsp > 0.5)[0]
    steady_mask = np.ones(len(sp), dtype=bool)
    steady_mask[:15] = False
    for idx in step_idxs:
        steady_mask[max(0, idx) : min(len(sp), idx + 35)] = False
    err_steady = err[steady_mask] if np.sum(steady_mask) >= 80 else err

    oi, osc_period = compute_oscillation_index(err_steady, dt=dt)
    stiction_idx = compute_stiction_index(sp, pv, op)
    overshoot = compute_step_overshoot(sp, pv)

    iae = round(float(np.mean(np.abs(err))), 4)
    ise = round(float(np.mean(err ** 2)), 4)
    op_travel = round(float(np.mean(np.abs(np.diff(op)))), 4)

    # Check step-response sluggishness (settling error 45 steps after step)
    sluggish_score = 0.0
    if len(step_idxs) > 0:
        residual_ratios = []
        for i, idx in enumerate(step_idxs):
            step_size = abs(sp[idx] - sp[idx - 1])
            end = step_idxs[i + 1] if i + 1 < len(step_idxs) else len(sp)
            if end - idx > 55 and step_size > 0.5:
                tail_err = float(np.mean(np.abs(err[idx + 35 : idx + 55])))
                residual_ratios.append(tail_err / step_size)
        if residual_ratios:
            sluggish_score = float(np.mean(residual_ratios))

    # Also check PV oscillation vs OP excitation ratio for external disturbance detection
    op_std_steady = float(np.std(op[steady_mask])) if np.sum(steady_mask) >= 80 else float(np.std(op))
    pv_std_steady = float(np.std(err_steady))
    # Cross-correlation at lag 0..5 between err_steady and op_steady
    if len(err_steady) > 20 and op_std_steady > 1e-4 and pv_std_steady > 1e-4:
        e_z = (err_steady - np.mean(err_steady)) / pv_std_steady
        op_s = op[steady_mask] if np.sum(steady_mask) >= 80 else op
        o_z = (op_s - np.mean(op_s)) / op_std_steady
        op_err_corr = float(np.max(np.abs([np.corrcoef(e_z[:-lag], o_z[lag:])[0, 1] for lag in range(1, 6)])))
    else:
        op_err_corr = 0.0

    # --- Diagnostic decision logic (with V4.2 excitation & ambiguity confidence guards) ---
    evidence_sufficient = True
    uncertainty_reason: Optional[str] = None
    op_total_std = float(np.std(op))
    pv_total_std = float(np.std(pv))
    has_excitation = (len(step_idxs) > 0) or (op_total_std >= 0.30) or (pv_total_std >= 0.25)

    if (stiction_idx >= 0.35 and oi >= 0.35 and op_travel < 1.2) or (stiction_idx >= 0.45 and op_travel < 1.2 and sluggish_score < 0.24):
        anomaly_type = "VALVE_STICTION"
        severity = "CRITICAL" if oi >= 0.35 else "WARNING"
        confidence = round(min(0.97, (0.78 if oi >= 0.35 else 0.70) + 0.20 * stiction_idx), 3)
        needs_retuning = False
        needs_valve_maintenance = True
        if oi < 0.35:
            uncertainty_reason = "LOW_OSC_FILTERED_VALVE_STICTION"
            root_cause = (
                f"检测到强滤波/弱振荡条件下的调节阀粘滞非线性特征：粘滞指数 SI={stiction_idx:.2f}（>=0.45），"
                f"虽受高阶过程滤波影响 PV 振荡指数较低（OI={oi:.2f}），但仍存在明显静摩擦突破与 PV-OP 滞回迹象，禁止误判为健康。"
            )
        else:
            root_cause = (
                f"检测到典型调节阀粘滞-滑移(Stick-Slip)非线性振荡：粘滞指数 SI={stiction_idx:.2f}，"
                f"振荡指数 OI={oi:.2f}（主周期 {osc_period:.1f}s），PV 加速度峰度显著超标（滑跳冲击特征）且 PV-OP 呈明显滞回环。"
            )
        action = "建议安排仪表检维修（检查阀杆填料、定位器与执行机构）；检修前可临时启用保守降增益缓冲参数以减小阀门磨损。"
    elif oi >= 0.35:
        # Distinguish between EXTERNAL_DISTURBANCE vs AGGRESSIVE_TUNING vs MODEL_MISMATCH
        if op_travel < 0.75 and osc_period >= 42.0 and stiction_idx < 0.35:
            anomaly_type = "EXTERNAL_DISTURBANCE"
            severity = "WARNING"
            if stiction_idx >= 0.20:
                # Borderline stiction vs sinusoidal disturbance (e.g., heavily filtered SOPDT plant)
                evidence_sufficient = False
                uncertainty_reason = "DIAGNOSIS_AMBIGUOUS_STICTION_VS_DISTURBANCE"
                confidence = round(max(0.45, 0.65 - 0.5 * stiction_idx), 3)
            else:
                confidence = round(min(0.94, 0.75 + 0.20 * oi), 3)
            needs_retuning = True
            needs_valve_maintenance = False
            root_cause = (
                f"回路存在周期性振荡（主周期 {osc_period:.1f}s，OI={oi:.2f}，SI={stiction_idx:.2f}），"
                f"OP 动作平稳（平均步幅 {op_travel:.2f}%）。"
                + ("注意：粘滞指数处于临界模糊带（0.20–0.35），在二阶强滤波对象下需结合阀位回讯排查是否存在轻中度粘滞。" if not evidence_sufficient else "主要源于上游工艺脉动耦合。")
            )
            action = "建议排查上游压机/泵组周期脉动源并核查调节阀定位器回讯，禁止直接激进调参。"
        elif pid_kc is not None and pid_kc < 1.75:
            anomaly_type = "MODEL_MISMATCH"
            severity = "CRITICAL"
            confidence = round(min(0.95, 0.77 + 0.18 * oi), 3)
            needs_retuning = True
            needs_valve_maintenance = False
            root_cause = (
                f"工况漂移导致过程增益/滞后与原 PID 参数失配：振荡指数 OI={oi:.2f}，"
                f"阶跃超调达 {overshoot:.1f}%，Harris 指数降至 {harris:.2f}。"
            )
            action = "建议触发在线模型辨识，按当前新工况重新执行自适应 PID 整定并通过多工况鲁棒性校验。"
        else:
            anomaly_type = "AGGRESSIVE_TUNING"
            severity = "CRITICAL"
            confidence = round(min(0.96, 0.78 + 0.18 * oi), 3)
            needs_retuning = True
            needs_valve_maintenance = False
            root_cause = (
                f"PID 参数过于激进（增益偏高或积分时间过短）：振荡指数 OI={oi:.2f}，"
                f"阶跃超调达 {overshoot:.1f}%，OP 频繁动作（平均步幅 {op_travel:.2f}%/s），Harris 指数 {harris:.2f}。"
            )
            action = "建议立即执行模型辨识与 SIMC/约束优化 PID 重新整定，降低比例增益并拉长积分时间。"
    elif sluggish_score >= 0.24 or (iae >= 0.85 and overshoot < 5.0 and oi < 0.28):
        anomaly_type = "SLUGGISH_TUNING"
        severity = "WARNING"
        confidence = round(min(0.95, 0.75 + 0.45 * sluggish_score), 3)
        needs_retuning = True
        needs_valve_maintenance = False
        root_cause = (
            f"控制回路响应明显迟缓（参数过于保守）：阶跃后残余偏差比 {sluggish_score:.2f}，"
            f"IAE={iae:.2f}，超调几乎为 0%，抗扰恢复慢。"
        )
        action = "建议重新辨识过程模型并执行自适应 PID 整定，适度提高比例增益、缩短积分时间以提升跟踪速度。"
    else:
        anomaly_type = "NORMAL"
        if not has_excitation:
            severity = "WARNING"
            evidence_sufficient = False
            uncertainty_reason = "DIAGNOSIS_INSUFFICIENT_EXCITATION"
            confidence = 0.35
            needs_retuning = False
            needs_valve_maintenance = False
            root_cause = (
                f"历史数据缺乏有效激励（无设定值阶跃，OP 标准差={op_total_std:.3f}，PV 标准差={pv_total_std:.3f}），"
                f"证据不足，不能据此证明回路健康或推荐参数变更。"
            )
            action = "请在工艺允许窗口内施加小幅阶跃/PRBS 激励测试后重新诊断。"
        elif stiction_idx >= 0.28:
            severity = "WARNING"
            evidence_sufficient = False
            uncertainty_reason = "DIAGNOSIS_CONFLICTING_LOW_OSC_STICTION"
            confidence = 0.42
            needs_retuning = False
            needs_valve_maintenance = True
            root_cause = (
                f"检测到冲突证据：PV 振荡较低（OI={oi:.2f}）但粘滞特征偏高（SI={stiction_idx:.2f}），"
                f"可能存在轻中度调节阀粘滞或定位器死区，禁止直接判定为健康。"
            )
            action = "建议调取阀位回讯 (MV) 核查执行机构死区/粘滞，并补充激励数据复测。"
        else:
            severity = "HEALTHY"
            confidence = round(min(0.96, 0.78 + 0.18 * harris), 3)
            needs_retuning = False
            needs_valve_maintenance = False
            root_cause = (
                f"控制回路运行健康：Harris 指数={harris:.2f}，振荡指数 OI={oi:.2f}，"
                f"阶跃超调={overshoot:.1f}%，未检测到调节阀粘滞或显著参数失配。"
            )
            action = "维持当前 PID 参数运行，纳入常规周期巡检。"

    return DiagnosisResult(
        anomaly_type=anomaly_type,
        severity=severity,
        confidence=confidence,
        harris_index=harris,
        oscillation_index=oi,
        oscillation_period_s=osc_period,
        stiction_index=stiction_idx,
        iae=iae,
        ise=ise,
        overshoot_pct=overshoot,
        op_travel=op_travel,
        needs_retuning=needs_retuning,
        needs_valve_maintenance=needs_valve_maintenance,
        root_cause_summary=root_cause,
        recommended_action=action,
        evidence={
            "sluggish_score": round(sluggish_score, 4),
            "op_err_corr": round(op_err_corr, 4),
            "op_std_steady": round(op_std_steady, 4),
            "pv_std_steady": round(pv_std_steady, 4),
            "op_total_std": round(op_total_std, 4),
            "pv_total_std": round(pv_total_std, 4),
            "n_sp_steps": float(len(step_idxs)),
        },
        evidence_sufficient=evidence_sufficient,
        uncertainty_reason=uncertainty_reason,
    )
