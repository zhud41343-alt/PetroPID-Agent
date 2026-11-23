# 07 · 华为 openJiuwen 能力分层核验报告

| 能力层级 | 本地环境（Windows Python 3.11） | 公网 Render（512MB Free Docker） | 客观证据 |
| :--- | :---: | :---: | :--- |
| 1. 原生 SDK 安装 (`openjiuwen==0.1.21`) | **VERIFIED** | NOT_INSTALLED（受 512MB 内存限制，避免 OOM） | `pip show openjiuwen` + `test_skills.py` |
| 2. 原生 `LocalFunction` / `ToolCard` / `McpServerConfig` 注册 | **VERIFIED** | 兼容适配层导出 Manifest | `07_agents/openjiuwen_adapter.py` |
| 3. 原生 `LocalFunction.invoke()` 工具执行 | **VERIFIED** | 标准 MCP + SkillRunner | `test_openjiuwen_native_sdk_tool_registration` PASS |
| 4. 真实在线大模型推理协作 (DeepSeek) | **VERIFIED** | **VERIFIED** | `live_llm_verification.json` + `render_live_http_verification.json` |
| 5. `openjiuwen.core.workflow` + Milvus 向量库编排 | **UNVERIFIED** | **UNVERIFIED** | 未部署外部 Milvus 实例，如实保留 `UNVERIFIED` |
