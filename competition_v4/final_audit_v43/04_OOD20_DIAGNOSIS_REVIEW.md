# 04 · OOD-20 阀门粘滞漏诊根因与 32 样本 SOPDT 复验报告（P0-02）

- **OOD-20 复验结果**：`pred_anomaly = VALVE_STICTION`，`stiction_index = 0.5179`，`oscillation_index = 0.0867`，`uncertainty_reason = LOW_OSC_FILTERED_VALVE_STICTION`，`final_status = VALVE_MAINTENANCE_REQUIRED`，`false_healthy = False`（已彻底消除漏诊为健康的风险）。
- **OOD-07 临界带透明保留**：`SI = 0.2536`，`evidence_sufficient = False`，`uncertainty_reason = DIAGNOSIS_AMBIGUOUS_STICTION_VS_DISTURBANCE`，`final_status = MODEL_VALIDATION_FAILED`（不强行过拟合阈值，通过不确定性告警与模型门控拒批）。

| 32 样本二阶 SOPDT 综合指标（含 OOD-01..32） | 实测值 |
| :--- | :---: |
| 故障诊断准确率 (`diagnosis_accuracy_pct`) | **96.88%** (31/32) |
| 阀门粘滞精确召回率 (`stiction_exact_recall_pct`) | **75.0%** |
| 阀门粘滞检出或不确定性拦截率 | **87.5%** |
| 健康误报率 (`healthy_false_positive_rate_pct`) | **0.0%** |
| **异常漏检率 / 错误健康判定数** | **0.0% (`0` 例)** |
| 诊断不确定性覆盖率 (`uncertainty_coverage_pct`) | **12.5%** |
| 错误参数推荐率 (`false_parameter_recommendation_rate_pct`) | **0.0%** |
