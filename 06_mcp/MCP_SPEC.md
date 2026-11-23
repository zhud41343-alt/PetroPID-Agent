# PetroPID MCP 服务规范与工具资源清单

## 1. 协议与接入方式
- **协议标准**：Model Context Protocol (MCP `2024-11-05`) / JSON-RPC 2.0
- **传输方式**：
  1. `stdio` 模式：`python 06_mcp/mcp_server.py`（配置文件见 `06_mcp/mcp_config.json`）
  2. `HTTP JSON-RPC` 模式：随 Web Demo 暴露于 `POST http://127.0.0.1:8000/mcp/rpc`

## 2. MCP Tools 清单
| Tool 名称 | 功能描述 | 必选入参 | 核心出参 |
| :--- | :--- | :--- | :--- |
| `pid_loop_diagnosis` | 回路性能评估与异常根因诊断 | `loop_id` | `anomaly_type, harris_index, oscillation_index, stiction_index, needs_retuning` |
| `fopdt_system_identification` | FOPDT 过程辨识与独立验证 | `loop_id` | `success, K, tau, theta, val_r2, val_accuracy_pct` |
| `adaptive_pid_tuning` | SIMC + 多目标约束自适应整定 | `loop_id, plant_K, plant_tau, plant_theta, current_Kc, current_Ti` | `recommended_strategy, recommended_pid, candidates, improved_metrics` |
| `safety_constraint_verification` | 10 项安全约束与 5 工况鲁棒性校验 | `plant_K, plant_tau, plant_theta, Kc, Ti` | `approved, constraint_coverage_pct, violation_tags, multi_regime_pass_rate_pct` |
| `petro_knowledge_lookup` | 化工自控本体与故障知识三元组检索 | `anomaly_type` | `ontology_class, matched_triples, engineering_guidance` |

## 3. MCP Resources 清单
| Resource URI | MIME 类型 | 说明 |
| :--- | :--- | :--- |
| `petropid://datasets/catalog` | `application/json` | 30 个化工控制回路脱敏元数据目录 |
| `petropid://ontology/owl` | `application/rdf+xml` | 化工 PID 控制领域标准 OWL/RDF 本体文件 |
| `petropid://knowledge/triples` | `application/json` | 化工 PID 故障诊断与整定知识三元组清单 |

## 4. 联调验证命令
```bash
python 06_mcp/mcp_client.py
```
