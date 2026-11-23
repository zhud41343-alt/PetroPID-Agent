# 03 · 真实独立 A/B/C 多智能体对照实验报告（P0-01）

- **实验协议**：P0-01 genuinely independent A/B/C execution (72 real trials, zero hardcoded percentages)
- **编排模式声明**：`deterministic_local_state_machine_with_skillrunner_and_decision_engine (not native openjiuwen.core.workflow)`（明确区分于原生 `openjiuwen.core.workflow`）
- **原始数据**：`competition_v4/final_audit_v43/real_agent_abc_results.json`（含全部 72 次试验明细）

| 架构系统 | 试验数 | 任务成功率 | 注入超时故障恢复率 | 重复工具调用拦截 | 平均交接字节 (估算Token) | 耗时 P50 / P95 | 全记录审计验证率 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| A_fixed_python_pipeline | 24 | 75.0% | 0.0% | 0 | 15023 B (~3756 tok) | 32.61 / 195.18 ms | 0.0% |
| B_single_agent_coordinator | 24 | 100.0% | 100.0% | 0 | 10699 B (~2675 tok) | 73.33 / 200.74 ms | 0.0% |
| C_petropid_5agent_swarm | 24 | 100.0% | 100.0% | 6 | 2632 B (~658 tok) | 168.97 / 240.89 ms | 100.0% |

- **客观结论（含诚实代价）**：
  1. **System A** 延迟最低（P50 `32.61ms`），但在 6 次注入超时故障中全部崩溃（`0.0%` 恢复，总成功率 `75.0%`），无防重与审计验证；
  2. **System B** 具备真实单步重试能力（`100.0%` 故障恢复），但单体上下文膨胀至 `10,699 B`、无 SHA-256 防重缓存（`0` 拦截）且无两阶段审计；
  3. **System C (PetroPID V4.3)** 在保持 `100%` 任务成功与故障恢复的同时，交接体积压缩至 **`2,632 B`**（比 B 降 **75.4%**、比 A 降 **82.5%**），SHA-256 幂等缓存拦截 **6/6** 重复调用，全记录审计校验率 **100%**；**诚实代价**是 P50 延迟增加约 `95ms`（`168.97ms` vs B `73.33ms`），用于全记录哈希与频域/基线校验。
