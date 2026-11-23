# 07 · 端到端集成与自动化测试报告（V4.2 统一版本化证据）

- **统一版本**：`v4.2-final` / 公网 `main` (`version = 4.2.0`)
- **公网地址**：https://petropid-agent.onrender.com
- **代码仓库**：https://github.com/zhud41343-alt/PetroPID-Agent

| 测试套件 | 执行命令 / 目标 | 实测结果 | 证据文件 |
| :--- | :--- | :---: | :--- |
| **Pytest 全量单元/安全/P0审计/Skill** | `pytest 04_algorithms/tests/ 05_skills/tests/ -q` | **32 / 32 PASS** | `04_algorithms/tests/test_v42_p0_audit.py` 等 |
| **MCP 协议全链路测试** | `python 06_mcp/mcp_client.py` | **14 / 14 PASS** | `06_mcp/mcp_client.py` |
| **OWL / SQL / 知识图谱校验** | `python 03_models/validate_models.py` | **PASS** (116 三元组 / 7 表 / 22 知识) | `03_models/` |
| **原生 openJiuwen 0.1.21 工具调用** | `test_openjiuwen_native_sdk_tool_registration` | **PASS (本地)** | `05_skills/tests/test_skills.py` |
| **Render 正式公网全接口 HTTP 实测** | `python 07_agents/verify_render_live.py` | **9 / 9 PASS** (`200/409/404/live_llm_api`) | `competition_v4/render_live_http_verification.json` |
| **P1 Pareto / 24-SOPDT / Agent 价值实验** | `python 07_agents/v42_p1_studies.py` | **PASS** (`0/24` 危险误放行) | `competition_v4/v42_p1_experiments.json` |
| **Render 正式公网浏览器 E2E QA** | 见 `competition_v4/final_audit/RENDER_BROWSER_E2E_REPORT.md` | 同步实时验收记录 | `final_audit/RENDER_BROWSER_E2E_REPORT.md` |
