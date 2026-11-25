# V3.0 多智能体架构、openJiuwen 现状与 MCP 协议验证报告 (`V3_AGENT_MCP_REPORT.md`)

## 一、诚实架构分层（严格区分规则/状态机/LLM/openJiuwen）
| 组件层级 | 实际实现方式 | 当前验证状态 | 边界说明 |
| :--- | :--- | :---: | :--- |
| **控制核心算子** (`04_algorithms/`) | 确定性科学计算 Python/SciPy | **真实验证通过** | 绝不依赖大模型生成数值，消除数值幻觉 |
| **5-Agent 协同编排** (`07_agents/orchestrator.py`) | 结构化多阶段状态机 + 紧凑状态黑板 + 幂等缓存 | **真实验证通过** | 每个 Agent 独立记录耗时、输入摘要、输出与拦截状态；大模型无法绕过 `SafetyVerificationAgent` |
| **LLM 推理网关** (`07_agents/llm_gateway.py`) | OpenAI / 昇腾 MindIE 兼容接口 + 离线确定性引擎 | **离线引擎已验证；在线 API 待配置 Key** | 当前演示环境未配置外部 API Key，默认运行 `deterministic_local_engine`，已如实显示于页面顶栏 |
| **openJiuwen 适配层** (`07_agents/openjiuwen_adapter.py`) | 符合 `openjiuwen.swarm.v1` 规范的清单与接口适配层 | **兼容层已验证；原生 SDK 未安装** | 当前本地 Python 环境未安装 `openjiuwen` 原生包，已如实在 `/api/openjiuwen` 返回 `native_sdk_detected: false`，**绝不伪造原生 SDK 运行日志** |
| **本体与知识模型** (`03_models/`) | `rdflib` 116 三元组 OWL + 22 条 JSON/CSV 知识三元组 | **已接入业务判断** | `DiagnosisAgent` 与 `OrchestratorAgent` 通过 `petro_knowledge_lookup` Skill 检索规则 `R-01`–`R-06`，直接参与阀门粘滞拦截与工程建议生成 |

## 二、MCP 协议级实测结果（`06_mcp/mcp_client.py`）
通过真实子进程 `stdio` JSON-RPC 2.0 客户端执行 **14/14 项协议级正向与负向测试全部通过**（详单见 `06_mcp/integration_test_report.md`）：
- 正向用例（10 项）：`initialize`、`tools/list` (5 工具)、`resources/list` (3 资源)、3 项 `resources/read`（数据集目录/OWL 本体/知识三元组）、4 阶段 `tools/call` 闭环链。
- 负向与异常恢复用例（4 项）：未知方法返回 `-32601`、非法 `loop_id` 返回 `-32000`、越权 URI (`file:///etc/passwd`) 拦截返回 `-32000`、异常后服务端状态无污染并正常响应后续 `tools/list`。
