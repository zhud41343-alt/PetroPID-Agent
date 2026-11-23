# 03 · 独立分布外泛化验证报告（SOPDT 二阶机理模型）

- **实验脚本**：`07_agents/v4_studies.py` · 原始结果：`competition_v4/v4_experiments.json`
- **防同源泄漏设计**：采用完全独立的**二阶加纯滞后 (SOPDT) 机理仿真器**与独立随机种子 `9001–9012`（12 个未见回路，非 FOPDT 开发集），测试系统对模型结构失配与 6 类异常的真实泛化与安全拒绝能力。

## 12 个独立 SOPDT 泛化回路实测结果
| 案例编号 | 真实二阶工况 | 预测异常 | 独立验证 Fit% / R² | 最终审批状态 | 安全性评价 |
| :--- | :--- | :--- | :---: | :--- | :--- |
| `OOD-01` | 激进振荡 SOPDT | `AGGRESSIVE_TUNING` | 有效 | `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW` | 正确整定并安全放行 |
| `OOD-02` | 激进振荡 SOPDT | `AGGRESSIVE_TUNING` | 有效 | `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW` | 正确整定并安全放行 |
| `OOD-03` | 增益漂移 SOPDT | `MODEL_MISMATCH` | 有效 | `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW` | 正确重辨识并放行 |
| `OOD-04` | 增益漂移 SOPDT | `MODEL_MISMATCH` | 有效 | `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW` | 正确重辨识并放行 |
| `OOD-05` | 保守迟缓 SOPDT (无未测负载阶跃) | `SLUGGISH_TUNING` | 有效 | `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW` | 证明系统在激励充分时可正确整定迟缓回路 |
| `OOD-06` | 保守迟缓 SOPDT (无未测负载阶跃) | `SLUGGISH_TUNING` | 有效 | `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW` | 正确整定并安全放行 |
| `OOD-07` | 阀门粘滞 SOPDT | 拦截 | 未通过 | `MODEL_VALIDATION_FAILED` | **零危险误放行**（门控拦截） |
| `OOD-08` | 阀门粘滞 SOPDT | `VALVE_STICTION` | 有效 | `VALVE_MAINTENANCE_REQUIRED` | 精准识别机械粘滞并派发检修 |
| `OOD-09` | 外部周期扰动 SOPDT | `EXTERNAL_DISTURBANCE` | 有效 | `PERFORMANCE_NOT_IMPROVED` | 正确拒绝无效调参 |
| `OOD-10` | 外部周期扰动 SOPDT | `EXTERNAL_DISTURBANCE` | 有效 | `PERFORMANCE_NOT_IMPROVED` | 正确拒绝无效调参 |
| `OOD-11` | 健康运行 SOPDT | `NORMAL` | 跳过 | `HEALTHY_NO_CHANGE` | 保持原参数 |
| `OOD-12` | 低激励稳态 SOPDT | `NORMAL` | 跳过 | `HEALTHY_NO_CHANGE` | 避免非必要侵入扰动 |

**结论**：12/12 独立二阶 SOPDT 泛化案例中，**危险误放行率为 0% (0/12)**，同时验证了无未测负载阶跃时迟缓回路可正常辨识整定。
