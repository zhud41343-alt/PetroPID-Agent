# 09 · openJiuwen 与 DeepSeek 真实运行边界报告

- **DeepSeek 在线推理（本地 + Render 双端 VERIFIED）**：线上 `/healthz?probe_llm=true` 实测 `connectivity_status = VERIFIED_LIVE`，`model = deepseek-flash`，`latency_ms = 1071.2 ms`，`request_id = 04011aec-bf1d-47a5-88e5-8e837ec4144a`；Copilot 自由问答实测 `528 tokens`、`1331.5 ms`。
- **openJiuwen 分层声明**：
  - 本地环境：`openjiuwen==0.1.21` 原生 `LocalFunction` / `ToolCard` / `McpServerConfig` 注册与调用实测 PASS；
  - Render 512MB Free 容器：轻量兼容适配层运行（避免 `pymilvus` OOM）；
  - `openjiuwen.core.workflow` + 外部 Milvus 向量库编排：**`UNVERIFIED`**。
