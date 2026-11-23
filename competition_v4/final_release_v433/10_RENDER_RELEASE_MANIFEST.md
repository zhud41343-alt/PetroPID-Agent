# 10 · Render V4.3.3 正式发布清单与线上 HTTP 实测

| 字段 | 实测值 |
| :--- | :--- |
| `application_commit_full` | `d8efc92c3ec78a207919a307b23f15b82e01dba6` |
| `render_observed_commit_full` | `d8efc92c3ec78a207919a307b23f15b82e01dba6`（**40 位完全一致**，`source = render_runtime_env`） |
| `app_version` / `algorithm_version` | `4.3.3` / `petropid-alg-v4.3.3` |
| `dataset_version` | `petropid-sim-30loops-v2.0` |
| `build_time_utc` | `2026-11-23T14:19:29Z` |
| `deepseek_live_probe` | `VERIFIED_LIVE` (`deepseek-flash`, `1097.2 ms`, `req: 3071cb03-afce-4044-9ea4-4c08fb767fd3`) |
| `deployment_authorized` | `false` |
| `http_checks` | **9 / 9 PASS**（见 `render_v433_live_verification.json`） |
