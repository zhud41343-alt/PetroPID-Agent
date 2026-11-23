# 07 · V4.0 端到端自动化测试报告

- **执行时间**：2026-11-23（隔离仿真测试环境，未接入真实 DCS/PLC）

| 测试套件 | 执行命令 | 用例数 | 结果 | 耗时 | 核心验证内容 |
| :--- | :--- | :---: | :---: | :---: | :--- |
| 核心算子单测 | `pytest 04_algorithms/tests/test_algorithms.py` | 5 | **5/5 PASS** | ~0.9s | 仿真器、30 回路诊断、FOPDT 辨识、整定、安全拦截 |
| V3.0 问题回路回归 | `pytest 04_algorithms/tests/test_v3_regressions.py` | 14 | **14/14 PASS** | ~7.4s | `LOOP-006`, `LOOP-012`–`017`, `LOOP-020`, `LOOP-028`–`030`, 激励不足, 无效模型 |
| **V4.0 P0 安全负例/故障注入/审计一致性** | `pytest 04_algorithms/tests/test_v4_safety_and_faults.py` | 5 模块 (20+断言) | **5/5 PASS** | ~1.4s | 全 9 态 `deployment_authorized=False`、缺失证据 fail-closed、多故障保留全因、空/NaN/乱序/过短输入、`run_id` 与审批单/JSON 哈希一致、CSV 400/413/NaN 安全防护 |
| Skill 幂等单测 | `pytest 05_skills/tests/test_skills.py` | 2 | **2/2 PASS** | ~0.4s | 5 Skill 注册表与 SHA-256 防重缓存 |
| MCP 协议级测试 | `python 06_mcp/mcp_client.py` | 14 | **14/14 PASS** | ~1.2s | 正向全链路 + 4 项负向与异常恢复 |
| 30 回路 Benchmark & SIMC/消融/SOPDT 研究 | `python 07_agents/benchmark_runner.py` & `v4_studies.py` | 42 回路 | **PASS** | ~11s | 30 标准回路 + 12 独立二阶 SOPDT 泛化回路 |

- **合计自动化 pytest**：**`26/26 PASSED (10.08s)`**，零失败用例。
- **浏览器交互测试**：V2.0/V3.3 已完成真实 Edge/内置浏览器全 30 回路与沙盒/副驾驶交互验证；V4.0 后端新增 `RUN_STORE[run_id]` 与 `FinalDecisionEngine` 已通过 `TestClient` API 集成测试，V4.0 完整 Playwright 浏览器重放标为待跑（`PENDING_BROWSER_REPLAY`）。
