# 06 · 40 样本二阶 SOPDT 严格分层验证与混淆矩阵（P1-02）

- **数据集严格分层**（不再将回归集称为盲测）：`{'original_12': 12, 'v42_regression_12': 12, 'v43_regression_8': 8, 'v432_strict_holdout_8': 8}`
- **全新严格留出集 8 样本 (`OOD-33..40`, seeds `9301..9308`，阈值零调整)**：
  - 诊断准确率：**`87.5%`**（7/8）｜错误健康判定：**`0`**｜错误参数推荐：**`0`**
- **全量 40 样本统计**：
  - 总诊断准确率：**`95.0%`**（38/40）｜错误健康判定：**`0`**｜错误参数推荐：**`0 / 24`**
  - **Clopper-Pearson 95% 单侧置信上界（0/24 错误推荐）**：**`<= 11.73%`**

```json
{
  "AGGRESSIVE_SOPDT": {
    "AGGRESSIVE_TUNING": 5
  },
  "DRIFT_SOPDT": {
    "MODEL_MISMATCH": 5
  },
  "SLUGGISH_SOPDT": {
    "SLUGGISH_TUNING": 6
  },
  "STICTION_SOPDT": {
    "EXTERNAL_DISTURBANCE": 1,
    "VALVE_STICTION": 7,
    "SLUGGISH_TUNING": 1
  },
  "EXT_DIST_SOPDT": {
    "EXTERNAL_DISTURBANCE": 6
  },
  "NORMAL_SOPDT": {
    "NORMAL": 4
  },
  "LOW_EXCIT_SOPDT": {
    "UNCERTAIN_LOW_EXCIT": 4
  },
  "HYBRID_STICT_DIST": {
    "EXTERNAL_DISTURBANCE": 1
  }
}
```
