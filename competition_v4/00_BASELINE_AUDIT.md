# 00 · V3.3 → V4.0 全仓工程审计报告

- **基线标签**：`v3.3-baseline` (`43cccc0`) → 整改分支：`v4.0-final`
- **审计范围**：后端 (`08_demo_web/app.py`)、多智能体与安全层 (`07_agents/`)、核心算法 (`04_algorithms/`)、MCP (`06_mcp/`)、数据集与四大模型 (`02_datasets/`, `03_models/`)、前端 HMI (`08_demo_web/static/`)

| 问题编号 | 严重程度 | 源码位置 | 复现条件 | 根因 | V4.0 修复措施 | 验证方法 | 状态 |
| :--- | :---: | :--- | :--- | :--- | :--- | :--- | :---: |
| **A-01** | P0 | `07_agents/orchestrator.py` | 多故障同时出现或证据缺失 | 最终状态分散在多个 `if/else` 分支，无独立权威决策层 | 独立抽取 `07_agents/decision_engine.py` (`final_decision_aggregation`)，强制 9 态固定优先级 + `PASS/FAIL/NOT_EVALUATED` + `deployment_authorized=False` | `test_v4_safety_and_faults.py` | **已修复** |
| **A-02** | P0 | `08_demo_web/app.py` | 导出审批单或 JSON 审计包 | `/api/approval` 与 `/api/export_bundle` 每次重新运行而非复用当前 `run_id` | 建立 `RUN_STORE[run_id]` 单一事实源，审批单与审计 JSON 均按 `?run_id=` 读取同一不可变结果对象 | `test_run_id_single_source_of_truth_and_csv_security` | **已修复** |
| **A-03** | P0 | `08_demo_web/static/app.js` | 快速切换回路或慢网络旧响应晚归 | 前端无请求序号保护，旧响应可能覆盖新回路画面 | 新增单调递增 `latestRequestSeq` 竞态保护，过期响应自动丢弃 | 代码审查 + 交互测试 | **已修复** |
| **A-04** | P0 | `08_demo_web/app.py` | 上传超大/含 NaN/乱序时间戳 CSV | V3.3 对 CSV 执行静默插值，未限制文件大小与非有限值 | 强制 512 KB 大小限制、5000 行上限、禁用静默插值，非法输入进入 `FinalDecisionEngine` 返回 `INPUT_DATA_INVALID` | `test_input_fault_injection_*` & `test_run_id_*` | **已修复** |
| **A-05** | P1 | `07_agents/openjiuwen_adapter.py` | 检查 `openJiuwen` 原生运行状态 | 本地未安装 `openjiuwen==0.1.21` 原生包 | 如实标注 `native_sdk_detected=false` 与 `petropid_compatible_runtime`，并在报告中标记原生 SDK 集成 `UNVERIFIED` | `/api/openjiuwen` 实测 | **如实披露** |
