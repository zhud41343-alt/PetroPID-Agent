# 03 · 全量技术主张与可复现证据溯源总表（Evidence Traceability Matrix）

> **目的**：确保参赛材料、技术方案说明书与答辩 PPT 中的每一项量化数据与安全承诺，均可一一追溯至具体源码、独立复算脚本、原始数据文件、GitHub Actions CI 运行记录与 Git SHA。  
> **版本绑定**：后端冻结基线 `d8efc92c3ec78a207919a307b23f15b82e01dba6` ｜ 代码冻结基线 `a3e37b83b4f06b05e10aa4af3bbc924e6c5825e3`（与 Render 公网 40 位一致） ｜ 最新全绿 CI Run `45407211036`

| 序号 | 技术主张 / 核心指标 | 源码 / 脚本位置 | 原始证据 / 报告文件 | 自动化验证方式与实测记录 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | **后端冻结基线零改动**（`d8efc92c`） | `04_algorithms/`, `07_agents/decision_engine.py`, `07_agents/orchestrator.py` | `competition_v4/final_release_v433/01_BASELINE_AND_CHANGELOG.md` | `git diff d8efc92..07534e3 -- 04_algorithms/petro_pid 07_agents/decision_engine.py 07_agents/orchestrator.py` 零改动 |
| 2 | **30 回路基准**：诊断 `30/30`、保守安全 `30/30`、独立精确匹配 `24/30 (80.0%)`、危险误放行 `0/19` | `07_agents/benchmark_runner.py` | `competition_v4/final_release_v433/07_TASK_SUCCESS_FINAL.md` | GitHub Actions CI Run `45362645906` Step 10 自动复算 PASS |
| 3 | **40 样本 SOPDT 泛化**：全量 `38/40 (95%)`、严格留出集 `OOD-33..40` `7/8 (87.5%)`、错误推荐 `0/24`（95% 上界 `≤11.73%`） | `07_agents/v432_studies.py` | `competition_v4/final_release_v433/06_SOPDT_40_FINAL_REVIEW.md` | 严格分层记录 + `OOD-36` 失败案例透明保留 |
| 4 | **B1 与 C 等价审计与 8 类篡改故障注入** | `07_agents/decision_engine.py`, `04_algorithms/tests/test_v433_b1_c_audit_equivalence.py` | `competition_v4/final_release_v433/02_B1_AUDIT_EQUIVALENCE_FIX.md` | `pytest` 自动执行 8 类篡改故障注入 PASS |
| 5 | **144 次模块消融原始记录与独立复算** | `07_agents/v433_ablation.py`, `07_agents/recompute_ablation.py` | `competition_v4/final_release_v433/03_ABLATION_120_RAW_TRIALS.json`, `ablation_summary.csv`, `05_B1_C_FAIRNESS_REPORT.md` | GitHub Actions CI Run `45362645906` Step 11 独立复算 PASS |
| 6 | **11 项安全硬约束、9 态状态机与 `deployment_authorized=false`** | `04_algorithms/petro_pid/safety_verifier.py`, `07_agents/decision_engine.py` | `competition_v4/final_release_v433/08_SAFETY_AND_AUDIT_REGRESSION.md` | `pytest` 全量安全测试（Linux CI `40 passed, 1 skipped`；本地 `41 passed`） |
| 7 | **跨回路 `run_id` 越权返回 `HTTP 409` 与畸形 CSV 返回 `HTTP 400`** | `08_demo_web/app.py`, `04_algorithms/tests/test_v433_web_and_frontend_e2e.py` | CI Run `45362645906` Step 5 | FastAPI `TestClient` 自动化负向测试 PASS |
| 8 | **前端 Fail-Closed 双重保护（HTTP 500 清空旧态禁导出 + 篡改审计拦截）** | `08_demo_web/static/app.js`, `08_demo_web/tests/test_playwright_e2e.py` | CI Run `45362645906` Step 6–7 (`node --check` + Playwright Chromium) | GitHub Actions Ubuntu 无头 Chromium 实测 `PLAYWRIGHT_E2E_ALL_8_CHECKS_PASSED`（`1440×900` + `1366×768`，0 JS 报错） |
| 9 | **MCP JSON-RPC 2.0 协议与 OWL/SQL/KG 知识模型** | `06_mcp/mcp_client.py`, `03_models/validate_models.py` | `06_mcp/integration_test_report.md` | CI Run `45362645906` Step 8–9（`14/14 MCP` + `116 OWL / 7 SQL / 22 KG`）PASS |
| 10 | **公网在线部署与 DeepSeek 实时探针** | `Dockerfile`, `08_demo_web/app.py` (`/healthz?probe_llm=true`) | `competition_v4/final_release_v433/10_RENDER_RELEASE_MANIFEST.md`, `11_BROWSER_E2E_FINAL.md` | https://petropid-agent.onrender.com 在线 `VERIFIED_LIVE`、`deployment_authorized=false` |
| 11 | **正式参赛技术方案与矢量架构图** | `competition_v4/submission_v433/01_TECHNICAL_SPECIFICATION.md` | `competition_v4/submission_v433/02_ARCHITECTURE_DIAGRAM.svg` | 面向赛题 5 评委与答辩 PPT 直接复用 |
| 12 | **ISDB 外部工业数据三方法对照与 76/76 独立二次审计**（冻结 V4.3.3 F1 `52.63%` vs Horch 1999 F1 `58.82%` / Prec `71.43%` vs 归一化滞环 Prec `100%`；未知真值门禁 `0/76` 放行；独立 `verify_audit_record()` `76/76 PASS`） | `07_agents/isdb_external_eval.py` | `competition_v4/submission_v433/04_ISDB_EXTERNAL_INDUSTRIAL_EVAL.md`, `isdb_external_raw_results.json` | 源 `isdb10.mat` SHA-256 `4dd329b5...e7df`（非再分发），JSON 原生 5 组标签与三方法指标对齐 |
