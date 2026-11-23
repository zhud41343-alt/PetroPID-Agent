# PetroPID 核心工业控制算子与算法接口说明

所有算子源码位于 `04_algorithms/petro_pid/`，单元测试位于 `04_algorithms/tests/test_algorithms.py`。

## 1. 算子清单
| 算子模块 | 核心函数 | 输入 | 输出 | 功能说明 |
| :--- | :--- | :--- | :--- | :--- |
| `simulator.py` | `simulate_loop(plant, pid, valve, dt, n_steps, ...)` | `PlantParams`, `PIDParams`, `ValveParams` | `Dict[str, np.ndarray]` (`t, sp, pv, op, mv, err, dist`) | FOPDT + Choudhury 粘滞 + ISA PID 闭环仿真 |
| `diagnosis.py` | `diagnose_loop(sp, pv, op, dt, estimated_delay_s, pid_kc, pid_ti)` | 时序数组 `sp, pv, op` | `DiagnosisResult` | Harris 指数、振荡指数 OI、粘滞指数 SI、超调/IAE 与根因分类 |
| `identification.py` | `identify_fopdt(pv, op, dt, train_ratio=0.65)` | 时序数组 `pv, op` | `IdentificationResult` | FOPDT 非线性最小二乘辨识 + 35% 独立验证时段 R² 与预测准确率 |
| `tuning.py` | `tune_pid(plant, current_pid, anomaly_type, dt)` | 辨识后的 `PlantParams`, 当前 `PIDParams` | `TuningResult` | SIMC 解析基线 + Nelder-Mead 多目标约束优化，输出保守/均衡/高性能 3 组方案 |
| `safety_verifier.py` | `verify_pid_safety(plant, candidate_pid, dt, ...)` | `PlantParams`, 候选 `PIDParams` | `SafetyVerificationResult` | 10 项硬约束 100% 校验（参数边界、GM/PM/Ms、超调、阀门饱和与速率、5 工况鲁棒性）及 100% 违规标记 |

## 2. 单元测试运行方式
```bash
pytest 04_algorithms/tests/test_algorithms.py -v
```
