# V4.3.4 Critic-Refiner 组件级安全压力测试

## 1. 评测定位

本实验回答一个局部工程问题：在严格安全裕度下，独立的 `SafetyVerifierAgent` 反馈能否帮助 `TunerAgent` 修正候选 PID 参数。它是可复现的组件级压力测试，不能替代完整生产链路评测、独立诊断准确率或真实工业泛化验证。

脚本与原始结果：

- `07_agents/v434_critic_refiner_study.py`
- `competition_v4/submission_v433/v434_critic_refiner_benchmark.json`

## 2. 实验设计

- 严格规格：`GM ≥ 3.5`、`PM ≥ 60°`、`Ms ≤ 1.25`、超调 `≤ 5%`。
- 12 组手工构造的高时滞、紧裕度、可整定 FOPDT 回路。
- B3-SinglePass 使用固定候选顺序，一次整定后结束。
- C-CriticRefiner 由安全校验器返回结构化违约项和裕度缺口，最多进行 3 轮有界修正，每轮独立复核。
- 另设 6 条预置诊断阻断路径，检查任何候选是否越过已知阻断状态。

## 3. 实测结果

| 组别 | B3-SinglePass | C-CriticRefiner | 解释 |
| :--- | :---: | :---: | :--- |
| 12 组高时滞可整定难例 | `0/12` | `12/12` | 组件级安全裕度反馈带来可复现的整定恢复 |
| 6 条预置诊断阻断路径 | `0/6` 放行 | `0/6` 放行 | 两侧均保持拒绝，不越过诊断阻断 |

12 组难例的提升来自反馈修正机制。6 条阻断路径由实验配置预先标记为不可整定，属于“拒绝覆盖”回归测试，不能当作独立诊断准确率样本。

## 4. 复现与边界

```bash
cd D:\石油\PetroPID-Agent
python 07_agents/v434_critic_refiner_study.py
```

该实验没有连接真实 DCS/PLC，没有执行参数下发，`deployment_authorized` 不参与放行。正式主成绩单仍以 `v434_formal_benchmark.json` 和 V4.3.3 冻结基线为准。
