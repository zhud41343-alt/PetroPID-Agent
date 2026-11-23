# 10 · Render 正式公网 V4.3 精确版本与全接口验收报告

- **公网地址**：https://petropid-agent.onrender.com
- **版本一致性**：`version = 4.3.0`，`code_commit_full = cd5848ea9125fc8d34df91df0179abbb5fb9f23a`（与 GitHub `main` `cd5848ea9125fc8d34df91df0179abbb5fb9f23a` **40 位 SHA 完全一致**，`code_commit_source = render_runtime_env`）。
- **原始日志**：`competition_v4/final_audit_v43/render_v43_live_verification.json`
- **9 项全接口实测**：`/healthz?probe_llm=true` (`200 VERIFIED_LIVE`)、`/api/loops` (`200 30`)、`/api/benchmark` (`200`)、`/api/openjiuwen` (`200`)、`LOOP-006/012/021/029` (`200` 全带 `record_digest_sha256` & `audit_status=PASS`)、跨回路审批单 (`200/409/404`)、`/api/sandbox` (`200`)、`/api/upload_csv` (`200 has_known_plant_truth=false -> MODEL_VALIDATION_FAILED`)、`/api/copilot` (`200 DeepSeek 528 tok`)。
- **浏览器 E2E**：已在 V4.2 同源前端实测 0 JS 报错 / 0 HTTP 错误，且 2 处 UI 细节修复已随 `cd5848e` 部署上线。
