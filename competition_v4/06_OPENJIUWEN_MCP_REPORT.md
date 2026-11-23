# 06 · openJiuwen 0.1.21 原生 SDK、MCP 与 OWL 本体工程验证报告

## 一、openJiuwen 0.1.21 原生 SDK 实测验证结果
- **已安装原生版本**：`openjiuwen==0.1.21`（通过 PyPI 正式安装）
- **已实测通过的原生模块**（`07_agents/openjiuwen_adapter.py` + `pytest 05_skills/tests/test_skills.py::test_openjiuwen_native_sdk_tool_registration`）：
  - `openjiuwen.core.foundation.tool.LocalFunction`（已将 5 大 PetroPID Skill 注册为原生 `LocalFunction` 并实测调用 `pid_loop_diagnosis(loop_id="LOOP-006")` 返回 `AGGRESSIVE_TUNING`）
  - `openjiuwen.core.foundation.tool.base.ToolCard`（承载 5 大技能标准 JSON Schema 契约）
  - `openjiuwen.core.foundation.tool.McpServerConfig`（原生注册 `petropid-control-server` MCP stdio 服务）
- **诚实未验证边界（`UNVERIFIED`）**：
  - `openjiuwen.core.workflow` 依赖可选向量库 `pymilvus`，当前离线环境未启用向量库，因此编排层仍运行轻量化确定性多智能体状态机 + 独立 `FinalDecisionEngine`；
  - 在线大模型 API 推理未配置外部 API Key，当前运行 `deterministic_local_engine`。

## 二、MCP 协议验证（14/14 PASS）
- `python 06_mcp/mcp_client.py` 真实子进程 JSON-RPC 2.0 联调 **14/14 PASS**（含未知方法 `-32601`、非法 `loop_id`、越权 URI 拦截及异常恢复）。

## 三、OWL/RDF 与知识三元组业务溯源
- `petro_pid_ontology.owl`（`rdflib` 116 三元组）与 `knowledge_triples.json`（22 条三元组）均通过 `petro_knowledge_lookup` Skill 直接参与诊断规则匹配（`R-01`–`R-06`）。
