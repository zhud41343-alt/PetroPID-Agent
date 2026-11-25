# PetroPID-Agent V2.0 → V3.0 深度工程审计报告 (`V3_AUDIT_REPORT.md`)

- **审计基准**：Git 基线标签 `v2.0-baseline` (`40f24bf`) → 整改分支 `v3.0-rectification`
- **审计范围**：全仓 `01_docs/`–`08_demo_web/`、30 回路实测数据、安全放行逻辑、KPI 口径与多智能体架构

## 一、V2.0 发现的 5 项核心缺陷与代码级根因

| 编号 | 问题摘要 | 代码位置与函数 | 真实根因 | V3.0 整改措施 |
| :--- | :--- | :--- | :--- | :--- |
| **DEF-01 (P0)** | `LOOP-012`–`017` 辨识验证精度仅 51%–60%，却仍显示 `APPROVED_FOR_DCS_DEPLOYMENT` | `07_agents/orchestrator.py` (`_execute_pipeline`) | V2.0 在 `ident["success"]==False` 时静默回退到 `meta["true_K"]`（真值泄漏），且 `SafetyVerificationAgent` 未检查模型有效性 | 彻底删除 `true_K` 回退；新增硬约束 `C-000` 模型可信度门控；验证未达标直接返回 `MODEL_VALIDATION_FAILED` 并保持原参数 |
| **DEF-02 (P0)** | `LOOP-028`–`030`（外部周期扰动）整定后 IAE 反而恶化（如 1.51→1.55），却被标为获批 | `07_agents/orchestrator.py` (`_execute_pipeline`) | 缺少确定性性能净改善门控，未区分“外部周期扰动反馈调参无效”场景 | 新增性能改善门控：若候选参数未改善或恶化 IAE/OI，或属 `EXTERNAL_DISTURBANCE`，统一返回 `PERFORMANCE_NOT_IMPROVED` 并建议排查扰动源与前馈补偿 |
| **DEF-03 (P0)** | `LOOP-006` 标称超调红线 `<=18%`，高增益/大滞后工况超调 `20.36%` 却显示 `PASS` | `04_algorithms/petro_pid/safety_verifier.py` (`verify_pid_safety`) | 扰动工况内部使用 `os_r <= 25.0`，但 API、UI 表格与审批单均未显式展示该专用阈值 | 在 `OperatingPointCheck`、API、前端表格与审批单中显式分离并展示 **标称超调红线 (`<=18%`)** 与 **扰动工况专用红线 (`<=25%`, `OI<=0.42`, `全稳定`)** |
| **DEF-04 (P0)** | 30 回路 KPI 统计口径不透明（如 FOPDT 96.06% vs 25 非健康回路 86.35%） | `07_agents/benchmark_runner.py` (`main`) | V2.0 仅对 `ident["success"]==True` 和 3 类整定异常求平均，未同时披露全量分母与被拒样本 | 统一 KPI 计算服务：同时透明披露**有效辨识模型 (`n=19`: Fit 95.35%, R² 0.9539)** 与 **全部 25 非健康回路 (`n=25`: Fit 91.50%, R² 0.8584)**，以及 6 类故障分组与 P50/P95/P99 耗时 |
| **DEF-05 (P1)** | 审批文案易被误解为“已批准下发真实 DCS”，且 `openJiuwen` 仅运行兼容适配层 | `08_demo_web/app.py`, `07_agents/openjiuwen_adapter.py` | 缺少仿真边界声明与原生 SDK 运行状态诚实披露 | 统一采用 `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW` 等 7 态机器可读枚举，显式声明未连接真实 DCS，并如实标注 `openJiuwen` 运行模式 |
