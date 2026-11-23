# 09 · Render 正式公网真实浏览器与 HTTP 端到端验收报告（V4.2）

- **被测公网地址**：https://petropid-agent.onrender.com
- **主机验证源 (`BROWSER_HOST_FACTS`)**：`visited_origins: https://petropid-agent.onrender.com` | `blocked_origins: none`
- **浏览器实景截图**：`C:/Users/17048/.gemini/antigravity/brain/a5a1d051-1ae4-4411-b4a8-9b16d5a68426/browser_evidence/db89fd8e-586b-4bbf-8833-f2475cff4330/final_step_26.png`
- **HTTP 实测原始日志**：`competition_v4/render_live_http_verification.json`

## 一、全接口 HTTP 实测结果（9 / 9 PASS）
| 接口 | HTTP | 耗时 | 关键验证结果 |
| :--- | :---: | :---: | :--- |
| `GET /healthz?probe_llm=true` | 200 | 1713.8 ms | `version=4.2.0`, `connectivity_status=VERIFIED_LIVE`, `model=deepseek-flash`, `latency_ms=1301.5`, `request_id=90673ea4...` |
| `GET /api/loops` | 200 | 306.6 ms | 返回全部 30 个控制回路 |
| `GET /api/benchmark` | 200 | 289.0 ms | `version=V4.2-independent-audited`, `independent_full_task_success_rate_pct=80.0%`, `false_approval_rate_pct=0.0%` |
| `POST /api/run/LOOP-006` | 200 | 7069.1 ms | `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW`, `audit_verification=PASS`, `llm_mode=live_llm_api` |
| `POST /api/run/LOOP-012` | 200 | 4647.9 ms | `MODEL_VALIDATION_FAILED`, `audit_verification=PASS` |
| `POST /api/run/LOOP-021` | 200 | 4433.4 ms | `VALVE_MAINTENANCE_REQUIRED`, `audit_verification=PASS` |
| `POST /api/run/LOOP-029` | 200 | 8700.4 ms | `PERFORMANCE_NOT_IMPROVED`, `audit_verification=PASS` |
| `GET /api/approval/*` & `export_bundle` | 200/409/404 | <400 ms | 合法单 `200`（含 5 工况表）、跨回路 `409 Conflict`、不存在 `404 Not Found`、导出包 `run_id` 精确一致 |
| `POST /api/upload_csv` & `/api/sandbox` & `/api/copilot` | 200 | 1.7–6.0 s | 未知 CSV `has_known_plant_truth=false` → `MODEL_VALIDATION_FAILED`；Copilot 返回真实 DeepSeek 推理（`543 tokens`） |

## 二、真实浏览器 E2E 巡检结果
- **JS 控制台报错**：`0` 条
- **HTTP >= 400 错误**：`0` 条
- **30/30 回路加载、顶部 `Engine: live_llm_api`、4 个代表回路（`LOOP-006/012/021/029`）、Trace 真实 DeepSeek 遥测胶囊、4 张工程图表 Canvas 全部渲染正常**。
- **巡检发现的 2 处细节并在本轮立即修复**：
  1. AI 副驾驶跨回路点名解析（查看 `LOOP-029` 时提问 `LOOP-012` 已修复为优先解析提问中的 `LOOP-\d{3}`）；
  2. 窄屏下 Tab 2 验证段标签右边缘裁切（已改为右对齐防溢出）。
