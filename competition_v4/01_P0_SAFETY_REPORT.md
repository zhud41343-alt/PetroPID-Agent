# 01 · P0 独立最终安全决策层报告

## 一、核心安全不变量（代码级强制）
源码位于 `07_agents/decision_engine.py`（`final_decision_aggregation`）：
1. **决策与文本彻底解耦**：大模型与 Agent 文本绝不直接决定最终放行状态，所有状态由结构化 `DecisionEvidence` 确定性推导。
2. **三权严格分离**：
   - `candidate_eligible_for_review`：仅在全部门控 `PASS` 时为 `True`；
   - `engineering_approval_status`：`PENDING_MANUAL_REVIEW` / `NOT_APPLICABLE` / `REJECTED_BY_GATE`（永不自动填为已批准）；
   - `deployment_authorized`：**在本隔离仿真项目中硬编码永远为 `False`**。
3. **9 态固定优先级**：`INPUT_DATA_INVALID` > `SIMULATION_TIMEOUT` > `AUDIT_INCOMPLETE` > `HEALTHY_NO_CHANGE` > `VALVE_MAINTENANCE_REQUIRED` > `MODEL_VALIDATION_FAILED` > `SAFETY_REJECTED` > `PERFORMANCE_NOT_IMPROVED` > `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW`。
4. **严禁“未知即通过”**：任一必需门控为 `NOT_EVALUATED` 时自动 fail-closed 拦截，并保留所有并发失败原因码于 `reason_codes`。

## 二、P0 安全回归测试结果（全部实测通过）
- `04_algorithms/tests/test_v4_safety_and_faults.py`：**5/5 模块全覆盖通过**（覆盖全 9 态 `deployment_authorized=False`、缺失证据 fail-closed、多故障并存全因保留、空/NaN/乱序/过短输入注入、`run_id` 与规范化 SHA-256 防篡改重算、CSV 400/413/NaN 安全防护）。
- `04_algorithms/tests/test_v3_regressions.py`：**14/14 回归全通过**（`LOOP-006`, `LOOP-012`–`017`, `LOOP-020`, `LOOP-028`–`030`）。
