# 08 · DeepSeek 在线大模型端到端实测与降级透明度报告

- **安全边界**：DeepSeek 仅承担工程推理与副驾驶解释，**绝不参与或覆盖 `decision_engine.py` 的确定性安全门控与 `deployment_authorized=false`**。
- **健康探针诚实化**：`GET /healthz` 区分 `CONFIGURED_UNPROBED` 与 `?probe_llm=true` 真实连通性探针，绝不仅凭配置了 API Key 宣称在线可用。
- **线上 Render 实测证据（`https://petropid-agent.onrender.com`）**：
  - `GET /healthz?probe_llm=true`：`connectivity_status = VERIFIED_LIVE`，`model = deepseek-flash`，`latency_ms = 1301.5 ms`，`request_id = 90673ea4-3265-4da5-970a-026461e90739`
  - `POST /api/copilot`（自由提问 `LOOP-012` 拒批原因）：`HTTP 200`，`model = deepseek-flash`，`latency_ms = 1429.2 ms`，`total_tokens = 543`，`request_id = 9bfb3e46-9db2-48ba-afc2-92fdecfcfa3f`
  - 降级机制：当 API 超时或异常时，自动回退 `deterministic_local_engine` 并如实返回 `fallback_reason`，保留原安全状态。
