# 10 · Render V4.3.3 正式发布清单与线上 HTTP 实测

| 字段 | 实测值 |
| :--- | :--- |
| `backend_frozen_commit_full` | `d8efc92c3ec78a207919a307b23f15b82e01dba6`（V4.3.3 算法、安全约束、审计引擎冻结基线，零改动） |
| `latest_hmi_playwright_ci_commit_full` | `a5867d22ecac6f808d9322cd0a3dee6f9341a5a8`（P1-A/B 双校验闭环 + Sandbox 一键 CSV + Playwright 真浏览器 CI 回归） |
| `github_actions_ci_run` | `45359152526`（`completed / success`，Linux CI `40 passed, 1 skipped` + `node --check` + Playwright Chromium E2E + 14 MCP + OWL/SQL/KG + 基准 + 消融） |
| `app_version` / `algorithm_version` | `4.3.3` / `petropid-alg-v4.3.3` |
| `dataset_version` | `petropid-sim-30loops-v2.0` |
| `deepseek_live_probe` | `VERIFIED_LIVE`（`deepseek-flash`，实测延迟 `1009.8 ms`，`req: 420bddd8-3709-4505-8b34-b5b346290546`） |
| `deployment_authorized` | `false` |
| `browser_and_http_verification` | 后端 9/9 HTTP PASS + Render 公网 E2E 0 JS 报错 / 0/18 HTTP 失败 + GitHub CI 无头 Chromium Playwright 8 项回归全通过 |
