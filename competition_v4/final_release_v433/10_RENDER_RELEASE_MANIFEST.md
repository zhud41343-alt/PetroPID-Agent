# 10 · Render V4.3.3 正式发布清单与线上 HTTP 实测

| 字段 | 实测值 |
| :--- | :--- |
| `backend_frozen_commit_full` | `d8efc92c3ec78a207919a307b23f15b82e01dba6`（V4.3.3 算法、安全约束、审计引擎冻结基线，零改动） |
| `code_freeze_commit_full` | `a3e37b83b4f06b05e10aa4af3bbc924e6c5825e3`（P2 未验禁用复核单 + ISDB 三方法对照 & 76/76 独立 `verify_audit_record()`） |
| `render_observed_commit_full` | `a3e37b83b4f06b05e10aa4af3bbc924e6c5825e3`（**40 位完全一致**，`source = render_runtime_env`，`build_time_utc = 2026-11-24T13:48:21Z`） |
| `github_actions_ci_run` | `45407211036`（`completed / success`，40 passed / 1 skipped + `node --check` + Playwright 8/8 PASS + 14 MCP + OWL/SQL/KG + 基准 + 消融） |
| `app_version` / `algorithm_version` | `4.3.3` / `petropid-alg-v4.3.3` |
| `dataset_version` | `petropid-sim-30loops-v2.0` |
| `deepseek_live_probe` | `VERIFIED_LIVE`（`deepseek-flash`，实测延迟 `1115.0 ms`，`request_id: 29d32d42-9fce-4aa3-864a-517d4e842ba6`） |
| `deployment_authorized` | `false` |
| `browser_and_http_verification` | 后端 9/9 HTTP PASS + Render 公网 E2E 0 JS 报错 / 0/18 HTTP 失败 + GitHub CI 无头 Chromium Playwright 8 项回归全通过 |
