# 08 · SIMC Pareto 与 32 样本 SOPDT 联合复验摘要

- 原始复现实验脚本：`07_agents/v43_studies.py`
- 原始结果文件：`competition_v4/final_audit_v43/v43_sopdt32_and_pareto.json`
- SIMC 对照核心结论：`PetroPID-Balanced` 是唯一在低 IAE (`0.458`) 下实现 **100% 安全门控与 100% 5 工况通过** 的候选（`SIMC` 仅 `45.45%` 多工况、`0%` 安全通过；`Performance` 仅 `20%` 多工况、`0%` 安全通过）。
- 32 样本 SOPDT 核心结论：诊断准确率 `96.88%`（31/32）、异常漏检率 `0.0%`（0 例误判健康）、危险误放行率 `0.0%`。
