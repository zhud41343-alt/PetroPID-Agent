# V3.0 自动化测试与验证报告 (`V3_TEST_REPORT.md`)

- **测试时间**：2026-11-23
- **测试环境**：Windows 11 / Python 3.11.6 / pytest 9.2.0 / 隔离本地仿真环境（未连接任何真实 DCS/PLC）

## 一、单元测试、回归测试与协议测试实测记录
| 测试套件 | 命令 | 用例数 | 结果 | 耗时 | 覆盖重点 |
| :--- | :--- | :---: | :---: | :---: | :--- |
| 核心控制算子单测 | `pytest 04_algorithms/tests/test_algorithms.py` | 5 | **5/5 PASS** | ~0.9s | 仿真器、30 回路诊断、FOPDT 辨识、SIMC/优化整定、安全拦截 |
| **V3.0 回归测试套件** | `pytest 04_algorithms/tests/test_v3_regressions.py` | 14 | **14/14 PASS** | ~7.4s | `LOOP-006` 显式双阈值、`LOOP-012`–`017` `MODEL_VALIDATION_FAILED`、`LOOP-020` `VALVE_MAINTENANCE_REQUIRED`、`LOOP-028`–`030` `PERFORMANCE_NOT_IMPROVED`、激励不足、无效模型拦截、全 30 回路合法枚举 |
| 标准化 Skill 单测 | `pytest 05_skills/tests/test_skills.py` | 2 | **2/2 PASS** | ~0.4s | 5 大 Skill 注册表校验、SHA-256 防重缓存命中验证 |
| **MCP 协议级联调测试** | `python 06_mcp/mcp_client.py` | 14 | **14/14 PASS** | ~1.2s | `initialize`、`tools/list`、`resources/list`、3 项 `resources/read`、4 阶段 `tools/call`、3 项负向错误拦截、异常恢复 |
| 模型与本体校验 | `python 03_models/validate_models.py` | 3 | **3/3 PASS** | ~0.4s | OWL 116 三元组 (`rdflib`)、SQL 7 表 (`sqlite3`)、知识模型 22 三元组 CSV |
| **30 回路全量基准复算** | `python 07_agents/benchmark_runner.py` | 30 | **30/30 PASS** | ~4.4s | 无缓存独立会话复算全部 30 回路状态、KPI、P50/P95/P99 与公平基线对照 |

## 二、Web API 与浏览器交互验证状态
- **API 集成验证**：`/`, `/api/loops`, `/api/benchmark`, `/api/openjiuwen`, `/api/run/LOOP-006`, `/api/run/LOOP-012`, `/api/run/LOOP-020`, `/api/run/LOOP-028`, `/api/sandbox`, `/api/copilot`, `/api/approval/LOOP-006`, `/mcp/rpc` 全部验证通过。
- **真实浏览器目视交互验收**：已通过内置浏览器对 V2.0 完成全量目视与交互验收并修复全部 5 项 UI 瑕疵（P&ID 截断、Copilot Markdown、OP `[0,100]` 物理量程、FOPDT 刻度/Nyquist 标签、窄屏响应式）；V3.0 新增的 5 阶段评委演示条、非纯色风险横幅、显式扰动红线与审批单升级已部署至 `http://127.0.0.1:8000` 并同步映射公网隧道，将在最终回归中执行 API 端到端校验。
