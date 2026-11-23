# 01 · P0 阻断缺陷整改与验证报告（V4.2）

- **生成时间**：2026-11-23 12:30:51 UTC
- **分支 / Commit**：`v4.2-final` (`fea2d75`) / 公网 `main` (`a18cc9d`)
- **自动化验证**：`32/32 pytest` 通过（含 `test_v42_p0_audit.py` 专项 P0 回归）、`14/14 MCP` 通过、Render 线上 HTTP 实测通过

| 编号 | 问题摘要 | 修复位置 | 核心修复措施 | 自动化/线上验证证据 | 状态 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **P0-01** | `run_id` 秒级碰撞风险 | `07_agents/orchestrator.py` | 改为 UTC 毫秒 + `uuid4` 唯一 `run_id`，独立区分 `request_id`、`input_hash`、`output_hash`、`cache_key`、`cache_hit` | `test_p0_01_run_id_uniqueness_under_high_concurrency_and_same_second`（16 并发同秒运行 0 碰撞） | **FIXED & VERIFIED** |
| **P0-02** | 审批单/审计包跨回路绑定与静默重跑 | `08_demo_web/app.py` | 实现 `_resolve_run_strict`：跨回路返回 `409 Conflict`、缺失返回 `404`、淘汰返回 `410`、篡改返回 `422`，严禁静默替代或自动重跑 | `test_p0_02_strict_cross_loop_and_missing_run_id_binding` + Render 线上实测 `409/404/200` | **FIXED & VERIFIED** |
| **P0-03** | 输入哈希未覆盖完整时序与配置 | `07_agents/decision_engine.py` | 新增 `compute_canonical_input_hash`（覆盖全量 `t/sp/pv/op`、NaN/Inf 规范化、6 位浮点精度、PID、4 项安全阈值、策略、数据源与版本） | `test_p0_03_complete_canonical_input_hash_sensitivity`（8 类单点/参数微扰 100% 触发哈希变化） | **FIXED & VERIFIED** |
| **P0-04** | 审计门控默认 `PASS` | `07_agents/decision_engine.py` | `audit_status` 默认改为 `NOT_EVALUATED`（直接 fail-closed 为 `AUDIT_INCOMPLETE`）；实现两阶段独立验证 `verify_pre_decision_audit_evidence` + `verify_audit_record` | `test_p0_04_audit_gate_never_defaults_pass_and_detects_tampering`（9 类字段篡改 100% 检出） | **FIXED & VERIFIED** |
| **P0-05** | 正确决策率依赖被测 `model_valid` | `07_agents/benchmark_runner.py` | 重建纯独立场景真值评估协议 `_independent_expected_decision(true_anomaly)`，拆分 6 项独立指标，如实披露 `24/30=80.0%` 与 `0%` 危险误放行 | `07_agents/benchmark_results.json` (`V4.2-independent-audited`) | **FIXED & VERIFIED** |
| **P0-06** | 未知 CSV 使用硬编码假设对象真值 | `08_demo_web/app.py`、`07_agents/orchestrator.py` | 移除假 `true_K=1.2`，标记 `has_known_plant_truth=False` / `UPLOADED_HISTORICAL_CSV`，禁止输出 `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW` | `test_p0_06_unknown_uploaded_csv_never_claims_validated_plant_improvement` + Render 线上实测 | **FIXED & VERIFIED** |
