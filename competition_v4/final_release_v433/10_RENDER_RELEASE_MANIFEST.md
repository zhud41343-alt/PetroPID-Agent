# 10 · Render V4.3.3 正式发布清单与线上 HTTP 实测

| 字段 | 实测值 |
| :--- | :--- |
| `backend_frozen_commit_full` | `d8efc92c3ec78a207919a307b23f15b82e01dba6`（V4.3.3 算法、安全约束、审计引擎冻结基线，零改动） |
| `latest_hmi_ci_commit_full` | `a560c2bad2206ce92413a48d2060552e67490fc9`（ISA-101 前端重构 + Sandbox 一键 CSV + 41 项 Web/CI 回归） |
| `render_observed_commit_full` | `a560c2bad2206ce92413a48d2060552e67490fc9`（**40 位完全一致**，`source = render_runtime_env`） |
| `github_actions_ci_run` | `45222790201`（`completed / success`，41 pytest + `node --check` + 14 MCP + OWL/SQL/KG + 基准 + 消融） |
| `app_version` / `algorithm_version` | `4.3.3` / `petropid-alg-v4.3.3` |
| `dataset_version` | `petropid-sim-30loops-v2.0` |
| `deepseek_live_probe` | `VERIFIED_LIVE`（`deepseek-flash`，实测延迟 `1009.8 ms`，`req: 420bddd8-3709-4505-8b34-b5b346290546`） |
| `deployment_authorized` | `false` |
| `http_and_browser_checks` | **后端 9/9 HTTP PASS + 新版前端公网 E2E 0 JS 报错 / 0/18 HTTP 失败**（见 `11_BROWSER_E2E_FINAL.md` 与 `render_v433_live_verification.json`） |
