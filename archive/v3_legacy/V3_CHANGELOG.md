# PetroPID-Agent V3.0 工程整改变更日志 (`V3_CHANGELOG.md`)

- **基线标签**：`v2.0-baseline` (`40f24bf`)
- **整改分支**：`v3.0-rectification`

## 核心源码修改清单
1. **`04_algorithms/petro_pid/identification.py`**
   - 新增 `allow_next_stage` 模型门控开关、`val_nrmse`、`val_fit_pct`、`val_bias_offset`、`resid_lag1_autocorr`、`failure_reason`、`closed_loop_bias_note`。
   - 严格区分 `R²` 与 `Fit%=(1-NRMSE)*100`，不再混用；设置独立验证门控 `val_r2 >= 0.80` 且 `val_fit_pct >= 85%`。
2. **`04_algorithms/petro_pid/safety_verifier.py`**
   - 新增硬约束 **`C-000` 模型可信度门控**（任何未通过独立验证的模型必返回 `VIOLATION_MODEL_VALIDATION_FAILED`）。
   - 在 `OperatingPointCheck` 和 `SafetyVerificationResult` 中显式区分并暴露 **标称超调红线 (`<=18%`)** 与 **扰动工况专用红线 (`<=25%`, `OI<=0.42`, `全稳定`)**，彻底消除 `LOOP-006` 阈值不一致问题。
3. **`07_agents/orchestrator.py`**
   - 彻底移除 V2.0 中 `ident["success"]==False` 时静默回退 `meta["true_K"]` 的真值泄漏逻辑。
   - 新增确定性 **性能净改善门控**，解决 `LOOP-028`–`030` 外部周期扰动 IAE 恶化却获批的 P0 缺陷。
   - 统一实现 7 态机器可读审批状态，杜绝“已批准下发真实 DCS”等不安全表述，新增公平算法对照（原 PID vs 传统 SIMC vs 优化安全门控）。
4. **`07_agents/benchmark_runner.py`**
   - 统一 30 回路 KPI 计算口径，同时透明披露有效模型 (`n=19`) 与全量非健康回路 (`n=25`)、6 类故障分组、状态分布、P50/P95/P99 耗时与公平基线对照。
5. **`04_algorithms/tests/test_v3_regressions.py`**（新增）
   - 新增 14 项针对 `LOOP-006`, `LOOP-012`–`017`, `LOOP-020`, `LOOP-028`–`030`、激励不足、无效模型门控的自动化回归测试，全部 `PASS`。
6. **`06_mcp/mcp_client.py`**
   - 扩充至 14 项协议级正向+负向+异常恢复测试（含 `-32601` 未知方法、非法 `loop_id`、越权 URI 拦截与异常恢复），全部 `PASS`。
7. **`08_demo_web/{app.py, static/index.html, static/style.css, static/app.js}`**
   - 新增 **5 阶段评委演示条**、**非纯色高显眼度风险/拒绝横幅**、**5 工况表显式展示专用红线**、**公平对照 IAE 展示**，升级审批单为带仿真声明与红绿拦截横幅的《DCS PID 参数变更安全复核单》。
