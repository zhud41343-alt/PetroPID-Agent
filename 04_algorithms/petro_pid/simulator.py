"""High-Fidelity Petrochemical PID Control Loop Simulator.

Implements:
- First-Order Plus Dead Time (FOPDT) plant with exact discrete-time integration & delay buffer
- Choudhury (2005) two-parameter (S, J) industrial control valve stiction model
- ISA-standard PID controller with anti-windup, derivative-on-measurement filter, OP saturation & rate limit
- 30+ realistic petrochemical control loops across CDU, FCC, Ethylene Cracker, CSTR, and Hydrotreater units
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
import numpy as np


@dataclass
class PlantParams:
    """FOPDT process model parameters: G(s) = K * exp(-theta * s) / (tau * s + 1)."""
    K: float          # Process steady-state gain
    tau: float        # Time constant (seconds)
    theta: float      # Dead time / transport delay (seconds)
    pv_bias: float = 50.0  # Nominal operating PV value
    op_bias: float = 50.0  # Nominal operating OP value (%)


@dataclass
class PIDParams:
    """ISA-standard PID parameters: C(s) = Kc * (1 + 1/(Ti*s) + Td*s/(alpha*Td*s + 1))."""
    Kc: float         # Proportional gain
    Ti: float         # Integral time (seconds); <=0 disables integral
    Td: float = 0.0   # Derivative time (seconds)
    op_min: float = 0.0
    op_max: float = 100.0
    op_rate_limit: float = 10.0  # Max |dOP| per sample (%)


@dataclass
class ValveParams:
    """Choudhury (2005) valve stiction model parameters."""
    stiction_S: float = 0.0  # Deadband + stickband (%)
    stiction_J: float = 0.0  # Slip jump (%)


@dataclass
class LoopConfig:
    """Complete petrochemical control loop configuration."""
    loop_id: str
    tag_name: str
    unit_name: str
    loop_type: str        # Temperature / Pressure / Flow / Level
    description: str
    pv_unit: str
    plant: PlantParams
    pid: PIDParams
    valve: ValveParams
    anomaly_type: str     # NORMAL | AGGRESSIVE_TUNING | SLUGGISH_TUNING | VALVE_STICTION | EXTERNAL_DISTURBANCE | MODEL_MISMATCH
    dt: float = 1.0       # Sampling period (seconds)
    noise_std: float = 0.06
    disturbance_amp: float = 0.0
    disturbance_period: float = 0.0
    seed: int = 42

    def to_dict(self) -> Dict:
        return asdict(self)


def _choudhury_valve_step(
    u_cmd: float,
    u_prev: float,
    v_prev: float,
    d_prev: int,
    u_stick: float,
    S: float,
    J: float,
) -> Tuple[float, int, float]:
    """One step of Choudhury two-parameter valve stiction model."""
    if S <= 1e-6:
        return u_cmd, 0, u_cmd

    du = u_cmd - u_prev
    if abs(du) < 1e-9:
        return v_prev, d_prev, u_stick

    d_curr = 1 if du > 0 else -1
    if d_prev != 0 and d_curr != d_prev:
        # Direction reversal: valve sticks at current command
        u_stick = u_prev

    delta = u_cmd - u_stick
    if abs(delta) >= S:
        # Slip-jump occurs, valve moves
        v_curr = u_cmd - np.sign(delta) * ((S - J) / 2.0)
        v_curr = float(np.clip(v_curr, 0.0, 100.0))
        return v_curr, d_curr, u_stick
    else:
        # Stuck
        return v_prev, d_curr, u_stick


def simulate_loop(
    plant: PlantParams,
    pid: PIDParams,
    valve: Optional[ValveParams] = None,
    dt: float = 1.0,
    n_steps: int = 600,
    sp_profile: Optional[np.ndarray] = None,
    disturbance: Optional[np.ndarray] = None,
    noise_std: float = 0.06,
    disturbance_amp: float = 0.0,
    disturbance_period: float = 0.0,
    seed: int = 42,
) -> Dict[str, np.ndarray]:
    """Simulate a closed-loop petrochemical PID control loop.

    Returns dict with arrays: t, sp, pv, op, mv (valve position), err, dist.
    """
    rng = np.random.default_rng(seed)
    valve = valve or ValveParams()

    t = np.arange(n_steps, dtype=float) * dt
    if sp_profile is None:
        sp = np.full(n_steps, plant.pv_bias, dtype=float)
        # Realistic industrial setpoint steps for identification & evaluation
        sp[int(0.12 * n_steps):int(0.45 * n_steps)] = plant.pv_bias + 4.0
        sp[int(0.45 * n_steps):int(0.75 * n_steps)] = plant.pv_bias - 2.0
        sp[int(0.75 * n_steps):] = plant.pv_bias + 3.0
    else:
        sp = np.asarray(sp_profile, dtype=float).copy()
        n_steps = len(sp)
        t = np.arange(n_steps, dtype=float) * dt

    if disturbance is None:
        dist = np.zeros(n_steps, dtype=float)
        if disturbance_amp > 0 and disturbance_period > 0:
            dist += disturbance_amp * np.sin(2.0 * np.pi * t / disturbance_period)
        # Small unmeasured process load step at 60%
        load_step_idx = int(0.60 * n_steps)
        dist[load_step_idx:] += 0.35 * np.sign(plant.K)
    else:
        dist = np.asarray(disturbance, dtype=float).copy()

    pv = np.zeros(n_steps, dtype=float)
    pv_clean = np.zeros(n_steps, dtype=float)
    op = np.zeros(n_steps, dtype=float)
    mv = np.zeros(n_steps, dtype=float)
    err = np.zeros(n_steps, dtype=float)

    delay_steps = max(1, int(round(plant.theta / dt)))
    mv_buffer = [plant.op_bias] * (delay_steps + 2)

    alpha = np.exp(-dt / max(plant.tau, 1e-3))
    y_dev = 0.0  # deviation from pv_bias

    integral = 0.0
    d_filt = 0.0
    u_prev = plant.op_bias
    v_prev = plant.op_bias
    d_dir = 0
    u_stick = plant.op_bias
    pv_prev_meas = plant.pv_bias

    # Derivative filter factor N=10
    tf = max(pid.Td / 10.0, dt * 0.5) if pid.Td > 0 else dt

    for k in range(n_steps):
        noise = rng.normal(0.0, noise_std)
        pv_curr_clean = plant.pv_bias + y_dev + dist[k]
        pv_curr_meas = pv_curr_clean + noise
        pv_clean[k] = pv_curr_clean
        pv[k] = pv_curr_meas

        e = sp[k] - pv_curr_meas
        err[k] = e

        # Derivative on measurement (avoids derivative kick on SP step)
        if pid.Td > 0 and k > 0:
            dpv = (pv_curr_meas - pv_prev_meas) / dt
            d_filt = (tf * d_filt + pid.Td * dpv) / (tf + dt)
        else:
            d_filt = 0.0

        # Ideal ISA PID output
        p_term = pid.Kc * e
        i_term = (pid.Kc / pid.Ti) * integral if pid.Ti > 1e-6 else 0.0
        d_term = -pid.Kc * d_filt
        u_raw = plant.op_bias + p_term + i_term + d_term

        # Rate limit & saturation
        u_rate = np.clip(u_raw, u_prev - pid.op_rate_limit, u_prev + pid.op_rate_limit)
        u_sat = float(np.clip(u_rate, pid.op_min, pid.op_max))

        # Conditional integration anti-windup
        saturated = (u_raw > pid.op_max and e * np.sign(pid.Kc) > 0) or (
            u_raw < pid.op_min and e * np.sign(pid.Kc) < 0
        )
        if not saturated and pid.Ti > 1e-6:
            integral += e * dt

        op[k] = u_sat

        # Valve stiction dynamics
        v_curr, d_dir, u_stick = _choudhury_valve_step(
            u_sat, u_prev, v_prev, d_dir, u_stick, valve.stiction_S, valve.stiction_J
        )
        mv[k] = v_curr

        mv_buffer.append(v_curr)
        delayed_mv = mv_buffer.pop(0)

        # FOPDT state update
        u_dev = delayed_mv - plant.op_bias
        y_dev = alpha * y_dev + plant.K * (1.0 - alpha) * u_dev

        u_prev = u_sat
        v_prev = v_curr
        pv_prev_meas = pv_curr_meas

    return {
        "t": t,
        "sp": sp,
        "pv": pv,
        "pv_clean": pv_clean,
        "op": op,
        "mv": mv,
        "err": err,
        "dist": dist,
    }


def get_standard_chemical_loops() -> List[LoopConfig]:
    """Return 30 realistic petrochemical control loops covering 6 health/anomaly classes."""
    loops: List[LoopConfig] = [
        # --- 1. NORMAL (5 loops) ---
        LoopConfig(
            loop_id="LOOP-001", tag_name="TIC-101", unit_name="常减压精馏塔(CDU)",
            loop_type="Temperature", description="常压塔顶温度控制回路", pv_unit="°C",
            plant=PlantParams(K=1.2, tau=18.0, theta=4.0, pv_bias=120.0, op_bias=50.0),
            pid=PIDParams(Kc=1.45, Ti=18.0, Td=0.0),
            valve=ValveParams(), anomaly_type="NORMAL", seed=101,
        ),
        LoopConfig(
            loop_id="LOOP-002", tag_name="FIC-102", unit_name="常减压精馏塔(CDU)",
            loop_type="Flow", description="常压塔顶回流流量控制回路", pv_unit="t/h",
            plant=PlantParams(K=0.9, tau=6.0, theta=2.0, pv_bias=80.0, op_bias=48.0),
            pid=PIDParams(Kc=1.25, Ti=6.5, Td=0.0),
            valve=ValveParams(), anomaly_type="NORMAL", seed=102,
        ),
        LoopConfig(
            loop_id="LOOP-003", tag_name="PIC-202", unit_name="催化裂化装置(FCC)",
            loop_type="Pressure", description="再生器顶压控制回路", pv_unit="kPa",
            plant=PlantParams(K=1.5, tau=14.0, theta=3.0, pv_bias=210.0, op_bias=52.0),
            pid=PIDParams(Kc=1.15, Ti=14.0, Td=0.0),
            valve=ValveParams(), anomaly_type="NORMAL", seed=103,
        ),
        LoopConfig(
            loop_id="LOOP-004", tag_name="FIC-302", unit_name="乙烯裂解炉(Cracker)",
            loop_type="Flow", description="稀释蒸汽进料流量控制回路", pv_unit="t/h",
            plant=PlantParams(K=1.1, tau=8.0, theta=2.0, pv_bias=45.0, op_bias=55.0),
            pid=PIDParams(Kc=1.35, Ti=8.0, Td=0.0),
            valve=ValveParams(), anomaly_type="NORMAL", seed=104,
        ),
        LoopConfig(
            loop_id="LOOP-005", tag_name="LIC-403", unit_name="连续搅拌反应釜(CSTR)",
            loop_type="Level", description="反应釜液位控制回路", pv_unit="%",
            plant=PlantParams(K=1.0, tau=20.0, theta=3.0, pv_bias=50.0, op_bias=50.0),
            pid=PIDParams(Kc=2.0, Ti=20.0, Td=0.0),
            valve=ValveParams(), anomaly_type="NORMAL", seed=105,
        ),

        # --- 2. AGGRESSIVE_TUNING (6 loops: realistic industrial 35-85% overshoot oscillation) ---
        LoopConfig(
            loop_id="LOOP-006", tag_name="TIC-201", unit_name="催化裂化装置(FCC)",
            loop_type="Temperature", description="提升管反应器出口温度控制回路", pv_unit="°C",
            plant=PlantParams(K=1.4, tau=16.0, theta=5.0, pv_bias=505.0, op_bias=50.0),
            pid=PIDParams(Kc=2.15, Ti=8.5, Td=0.0),
            valve=ValveParams(), anomaly_type="AGGRESSIVE_TUNING", seed=201,
        ),
        LoopConfig(
            loop_id="LOOP-007", tag_name="TIC-301", unit_name="乙烯裂解炉(Cracker)",
            loop_type="Temperature", description="裂解炉出口温度(COT)控制回路", pv_unit="°C",
            plant=PlantParams(K=1.6, tau=20.0, theta=6.0, pv_bias=835.0, op_bias=55.0),
            pid=PIDParams(Kc=1.95, Ti=9.5, Td=0.0),
            valve=ValveParams(), anomaly_type="AGGRESSIVE_TUNING", seed=202,
        ),
        LoopConfig(
            loop_id="LOOP-008", tag_name="PIC-104", unit_name="常减压精馏塔(CDU)",
            loop_type="Pressure", description="减压塔顶真空度压力控制回路", pv_unit="kPa",
            plant=PlantParams(K=1.3, tau=12.0, theta=4.0, pv_bias=15.0, op_bias=45.0),
            pid=PIDParams(Kc=2.10, Ti=6.5, Td=0.0),
            valve=ValveParams(), anomaly_type="AGGRESSIVE_TUNING", seed=203,
        ),
        LoopConfig(
            loop_id="LOOP-009", tag_name="TIC-401", unit_name="连续搅拌反应釜(CSTR)",
            loop_type="Temperature", description="放热反应釜夹套温控回路", pv_unit="°C",
            plant=PlantParams(K=1.8, tau=18.0, theta=5.0, pv_bias=165.0, op_bias=48.0),
            pid=PIDParams(Kc=1.85, Ti=8.5, Td=0.0),
            valve=ValveParams(), anomaly_type="AGGRESSIVE_TUNING", seed=204,
        ),
        LoopConfig(
            loop_id="LOOP-010", tag_name="TIC-501", unit_name="加氢精制装置(Hydrotreater)",
            loop_type="Temperature", description="加氢反应器床层入口温控回路", pv_unit="°C",
            plant=PlantParams(K=1.25, tau=15.0, theta=5.0, pv_bias=340.0, op_bias=50.0),
            pid=PIDParams(Kc=2.25, Ti=7.8, Td=0.0),
            valve=ValveParams(), anomaly_type="AGGRESSIVE_TUNING", seed=205,
        ),
        LoopConfig(
            loop_id="LOOP-011", tag_name="PIC-503", unit_name="加氢精制装置(Hydrotreater)",
            loop_type="Pressure", description="高压分离器压力控制回路", pv_unit="MPa",
            plant=PlantParams(K=1.1, tau=10.0, theta=3.5, pv_bias=8.5, op_bias=50.0),
            pid=PIDParams(Kc=2.20, Ti=5.5, Td=0.0),
            valve=ValveParams(), anomaly_type="AGGRESSIVE_TUNING", seed=206,
        ),

        # --- 3. SLUGGISH_TUNING (6 loops) ---
        LoopConfig(
            loop_id="LOOP-012", tag_name="LIC-103", unit_name="常减压精馏塔(CDU)",
            loop_type="Level", description="常压塔底液位控制回路", pv_unit="%",
            plant=PlantParams(K=1.1, tau=16.0, theta=3.0, pv_bias=55.0, op_bias=50.0),
            pid=PIDParams(Kc=0.22, Ti=85.0, Td=0.0),
            valve=ValveParams(), anomaly_type="SLUGGISH_TUNING", seed=301,
        ),
        LoopConfig(
            loop_id="LOOP-013", tag_name="FIC-203", unit_name="催化裂化装置(FCC)",
            loop_type="Flow", description="原料油预热进料流量回路", pv_unit="t/h",
            plant=PlantParams(K=1.0, tau=10.0, theta=2.5, pv_bias=180.0, op_bias=52.0),
            pid=PIDParams(Kc=0.20, Ti=70.0, Td=0.0),
            valve=ValveParams(), anomaly_type="SLUGGISH_TUNING", seed=302,
        ),
        LoopConfig(
            loop_id="LOOP-014", tag_name="TIC-105", unit_name="常减压精馏塔(CDU)",
            loop_type="Temperature", description="常二线柴油抽出温度回路", pv_unit="°C",
            plant=PlantParams(K=1.3, tau=20.0, theta=4.0, pv_bias=260.0, op_bias=50.0),
            pid=PIDParams(Kc=0.18, Ti=95.0, Td=0.0),
            valve=ValveParams(), anomaly_type="SLUGGISH_TUNING", seed=303,
        ),
        LoopConfig(
            loop_id="LOOP-015", tag_name="FIC-402", unit_name="连续搅拌反应釜(CSTR)",
            loop_type="Flow", description="夹套冷却水流量控制回路", pv_unit="m³/h",
            plant=PlantParams(K=0.95, tau=9.0, theta=2.0, pv_bias=65.0, op_bias=50.0),
            pid=PIDParams(Kc=0.22, Ti=65.0, Td=0.0),
            valve=ValveParams(), anomaly_type="SLUGGISH_TUNING", seed=304,
        ),
        LoopConfig(
            loop_id="LOOP-016", tag_name="FIC-502", unit_name="加氢精制装置(Hydrotreater)",
            loop_type="Flow", description="循环氢流量控制回路", pv_unit="Nm³/h",
            plant=PlantParams(K=1.15, tau=12.0, theta=3.0, pv_bias=320.0, op_bias=48.0),
            pid=PIDParams(Kc=0.18, Ti=80.0, Td=0.0),
            valve=ValveParams(), anomaly_type="SLUGGISH_TUNING", seed=305,
        ),
        LoopConfig(
            loop_id="LOOP-017", tag_name="TIC-303", unit_name="乙烯裂解炉(Cracker)",
            loop_type="Temperature", description="急冷油塔釜温控制回路", pv_unit="°C",
            plant=PlantParams(K=1.2, tau=22.0, theta=4.0, pv_bias=195.0, op_bias=50.0),
            pid=PIDParams(Kc=0.20, Ti=100.0, Td=0.0),
            valve=ValveParams(), anomaly_type="SLUGGISH_TUNING", seed=306,
        ),

        # --- 4. VALVE_STICTION (5 loops) ---
        LoopConfig(
            loop_id="LOOP-018", tag_name="FIC-106", unit_name="常减压精馏塔(CDU)",
            loop_type="Flow", description="重油抽出调节阀流量回路(阀杆粘滞)", pv_unit="t/h",
            plant=PlantParams(K=1.2, tau=8.0, theta=2.0, pv_bias=75.0, op_bias=50.0),
            pid=PIDParams(Kc=0.95, Ti=9.0, Td=0.0),
            valve=ValveParams(stiction_S=4.8, stiction_J=3.2),
            anomaly_type="VALVE_STICTION", seed=401,
        ),
        LoopConfig(
            loop_id="LOOP-019", tag_name="LIC-204", unit_name="催化裂化装置(FCC)",
            loop_type="Level", description="分馏塔油浆液位回路(阀门结焦粘滞)", pv_unit="%",
            plant=PlantParams(K=1.3, tau=12.0, theta=3.0, pv_bias=50.0, op_bias=50.0),
            pid=PIDParams(Kc=1.05, Ti=12.0, Td=0.0),
            valve=ValveParams(stiction_S=5.5, stiction_J=3.8),
            anomaly_type="VALVE_STICTION", seed=402,
        ),
        LoopConfig(
            loop_id="LOOP-020", tag_name="PIC-304", unit_name="乙烯裂解炉(Cracker)",
            loop_type="Pressure", description="燃料气总管压力回路(执行器卡涩)", pv_unit="kPa",
            plant=PlantParams(K=1.1, tau=9.0, theta=2.0, pv_bias=140.0, op_bias=52.0),
            pid=PIDParams(Kc=1.00, Ti=10.0, Td=0.0),
            valve=ValveParams(stiction_S=4.5, stiction_J=3.0),
            anomaly_type="VALVE_STICTION", seed=403,
        ),
        LoopConfig(
            loop_id="LOOP-021", tag_name="FIC-404", unit_name="连续搅拌反应釜(CSTR)",
            loop_type="Flow", description="催化剂进料阀流量回路(填料过紧)", pv_unit="kg/h",
            plant=PlantParams(K=1.25, tau=7.0, theta=2.0, pv_bias=30.0, op_bias=48.0),
            pid=PIDParams(Kc=0.90, Ti=8.0, Td=0.0),
            valve=ValveParams(stiction_S=5.0, stiction_J=3.5),
            anomaly_type="VALVE_STICTION", seed=404,
        ),
        LoopConfig(
            loop_id="LOOP-022", tag_name="TIC-504", unit_name="加氢精制装置(Hydrotreater)",
            loop_type="Temperature", description="冷氢注入调节阀温控回路(阀芯粘滞)", pv_unit="°C",
            plant=PlantParams(K=1.15, tau=11.0, theta=3.0, pv_bias=365.0, op_bias=50.0),
            pid=PIDParams(Kc=1.05, Ti=11.0, Td=0.0),
            valve=ValveParams(stiction_S=5.2, stiction_J=3.6),
            anomaly_type="VALVE_STICTION", seed=405,
        ),

        # --- 5. MODEL_MISMATCH (5 loops: high-load regime drift, realistic 40-85% overshoot) ---
        LoopConfig(
            loop_id="LOOP-023", tag_name="TIC-107", unit_name="常减压精馏塔(CDU)",
            loop_type="Temperature", description="加热炉出口温控(原油换炼工况漂移)", pv_unit="°C",
            plant=PlantParams(K=2.1, tau=15.0, theta=5.0, pv_bias=368.0, op_bias=54.0),
            pid=PIDParams(Kc=1.42, Ti=9.5, Td=0.0),
            valve=ValveParams(), anomaly_type="MODEL_MISMATCH", seed=501,
        ),
        LoopConfig(
            loop_id="LOOP-024", tag_name="TIC-205", unit_name="催化裂化装置(FCC)",
            loop_type="Temperature", description="再生器密相温度(负荷提升参数失配)", pv_unit="°C",
            plant=PlantParams(K=1.9, tau=18.0, theta=6.0, pv_bias=685.0, op_bias=52.0),
            pid=PIDParams(Kc=1.52, Ti=10.5, Td=0.0),
            valve=ValveParams(), anomaly_type="MODEL_MISMATCH", seed=502,
        ),
        LoopConfig(
            loop_id="LOOP-025", tag_name="PIC-405", unit_name="连续搅拌反应釜(CSTR)",
            loop_type="Pressure", description="反应釜气相压力(工况切换增益突变)", pv_unit="kPa",
            plant=PlantParams(K=2.0, tau=12.0, theta=4.0, pv_bias=320.0, op_bias=50.0),
            pid=PIDParams(Kc=1.45, Ti=8.0, Td=0.0),
            valve=ValveParams(), anomaly_type="MODEL_MISMATCH", seed=503,
        ),
        LoopConfig(
            loop_id="LOOP-026", tag_name="TIC-305", unit_name="乙烯裂解炉(Cracker)",
            loop_type="Temperature", description="急冷水塔顶温控(结垢致滞后增大)", pv_unit="°C",
            plant=PlantParams(K=1.7, tau=16.0, theta=6.0, pv_bias=42.0, op_bias=50.0),
            pid=PIDParams(Kc=1.58, Ti=9.5, Td=0.0),
            valve=ValveParams(), anomaly_type="MODEL_MISMATCH", seed=504,
        ),
        LoopConfig(
            loop_id="LOOP-027", tag_name="LIC-505", unit_name="加氢精制装置(Hydrotreater)",
            loop_type="Level", description="低压分离器液位(切换原料参数失配)", pv_unit="%",
            plant=PlantParams(K=1.85, tau=14.0, theta=4.5, pv_bias=50.0, op_bias=50.0),
            pid=PIDParams(Kc=1.52, Ti=8.5, Td=0.0),
            valve=ValveParams(), anomaly_type="MODEL_MISMATCH", seed=505,
        ),

        # --- 6. EXTERNAL_DISTURBANCE (3 loops) ---
        LoopConfig(
            loop_id="LOOP-028", tag_name="PIC-108", unit_name="常减压精馏塔(CDU)",
            loop_type="Pressure", description="燃料气压力回路(上游压缩机周期脉动)", pv_unit="kPa",
            plant=PlantParams(K=1.1, tau=12.0, theta=3.0, pv_bias=250.0, op_bias=50.0),
            pid=PIDParams(Kc=1.2, Ti=12.0, Td=0.0),
            valve=ValveParams(), anomaly_type="EXTERNAL_DISTURBANCE",
            disturbance_amp=1.8, disturbance_period=55.0, seed=601,
        ),
        LoopConfig(
            loop_id="LOOP-029", tag_name="TIC-206", unit_name="催化裂化装置(FCC)",
            loop_type="Temperature", description="分馏塔顶循环温控(上游进料周期波动)", pv_unit="°C",
            plant=PlantParams(K=1.2, tau=14.0, theta=3.0, pv_bias=135.0, op_bias=50.0),
            pid=PIDParams(Kc=1.25, Ti=14.0, Td=0.0),
            valve=ValveParams(), anomaly_type="EXTERNAL_DISTURBANCE",
            disturbance_amp=2.0, disturbance_period=65.0, seed=602,
        ),
        LoopConfig(
            loop_id="LOOP-030", tag_name="FIC-306", unit_name="乙烯裂解炉(Cracker)",
            loop_type="Flow", description="急冷油循环流量(泵组周期性脉动干扰)", pv_unit="t/h",
            plant=PlantParams(K=1.0, tau=10.0, theta=2.0, pv_bias=210.0, op_bias=50.0),
            pid=PIDParams(Kc=1.3, Ti=10.0, Td=0.0),
            valve=ValveParams(), anomaly_type="EXTERNAL_DISTURBANCE",
            disturbance_amp=1.9, disturbance_period=48.0, seed=603,
        ),
    ]
    return loops
