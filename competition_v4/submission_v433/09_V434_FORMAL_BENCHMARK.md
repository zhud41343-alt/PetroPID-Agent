# 09 · V4.3.4 正式编排 30 回路全链路评测报告

> **评测脚本**：[07_agents/v434_formal_benchmark.py](../../07_agents/v434_formal_benchmark.py)  
> **逐例原始 JSON**：[v434_formal_benchmark.json](./v434_formal_benchmark.json)  
> **执行入口**：`PetroPIDOrchestrator.run_loop_workflow(loop_id, validation_profile="v4.3.4")`（离线确定性模式，`deployment_authorized=false`）

## 一、核心汇总指标（对比 V4.3.3 冻结基线）

| 指标 | V4.3.3 冻结基线 (`benchmark_runner.py`) | V4.3.4 正式编排 (`v434_formal_benchmark.py`) |
| :--- | :---: | :---: |
| 故障诊断准确率 | `30/30 (100.0%)` | **`30/30 (100.0%)`** |
| 独立全任务精确匹配率 | `24/30 (80.0%)` | **`30/30 (100.0%)`** |
| 可整定回路仿真通过率 (`n=17`) | `11/17 (64.71%)` | **`17/17 (100.0%)`** |
| 危险误放行次数 | `0/19 (0.0%)` | **`0/13 (0.0%)`** |
| 5 工况通过率（放行组 / 全部已检） | `100.0% (n=11)` / `78.4% (n=25)` | **`100.0% (n=17)` / `78.4% (n=25)`** |
| 审计通过率 / 二次核验通过 | `30/30` | **`30/30` / `30/30`** |
| `deployment_authorized=true` | `0` | **`0`** |
| 纯直流负载阶跃二次校验触发回路 | `0` | **`6`（`LOOP-012..017`）** |
| 单回路耗时（Mean / P50 / P95 / Max） | `0.231s / 0.205s / 0.513s / 0.553s` | **`0.1738s / 0.2034s / 0.2559s / 0.2615s`** |

## 二、`LOOP-012..017` 增强 C-000 验证证据明细

| 回路 | 扣偏移后 R² | 扣偏移后 Fit | 标准差比 (`va/tr`) | 直流偏移 (`σ`) | 5工况通过 | 最终状态 | 审计 |
| :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: |
| `LOOP-012` | `0.9854` | `96.08%` | `0.558` | `2.88σ` | `100.0%` | `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW` | `PASS` |
| `LOOP-013` | `0.9782` | `95.37%` | `0.649` | `3.01σ` | `100.0%` | `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW` | `PASS` |
| `LOOP-014` | `0.9839` | `95.99%` | `0.585` | `3.08σ` | `100.0%` | `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW` | `PASS` |
| `LOOP-015` | `0.9847` | `96.29%` | `0.594` | `3.06σ` | `100.0%` | `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW` | `PASS` |
| `LOOP-016` | `0.9755` | `95.01%` | `0.717` | `3.09σ` | `100.0%` | `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW` | `PASS` |
| `LOOP-017` | `0.9798` | `95.8%` | `0.664` | `3.01σ` | `100.0%` | `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW` | `PASS` |

## 三、复现命令
```bash
python 07_agents/v434_formal_benchmark.py
```
