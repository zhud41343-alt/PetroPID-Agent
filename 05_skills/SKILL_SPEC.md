# PetroPID-Agent 标准化 Skill 规范与调用示例

## 1. 技能清单（注册表：`05_skills/skill_registry.json`）
| 序号 | Skill ID | 技能名称 | 归属智能体 | 核心功能 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | `skill.pid.diagnose` | `pid_loop_diagnosis` | DiagnosisAgent | 计算 Harris 指数、振荡指数 OI、粘滞指数 SI 与根因诊断 |
| 2 | `skill.pid.identify` | `fopdt_system_identification` | IdentificationAgent | FOPDT 过程辨识 + 35% 独立验证时段准确率评测 |
| 3 | `skill.pid.tune` | `adaptive_pid_tuning` | TuningAgent | SIMC + 多目标约束优化，生成 3 组候选 PID 参数 |
| 4 | `skill.pid.verify_safety` | `safety_constraint_verification` | SafetyVerificationAgent | 10 项硬约束 100% 校验 + 5 工况跨边界鲁棒性验证 |
| 5 | `skill.pid.query_knowledge` | `petro_knowledge_lookup` | OrchestratorAgent | 化工 PID 本体与知识三元组检索 |

## 2. 防重复调用机制
`SkillRunner` 对 `(skill_name, sorted_params)` 计算 SHA-256 幂等键，在单次多智能体协作会话中若发生重复工具调用，自动命中缓存并记录 `duplicate_calls_prevented`，彻底杜绝多智能体循环冗余调用与上下文膨胀。

## 3. 调用示例
```python
from skill_runner import SkillRunner

runner = SkillRunner()
diag = runner.invoke("pid_loop_diagnosis", {"loop_id": "LOOP-006"})
ident = runner.invoke("fopdt_system_identification", {"loop_id": "LOOP-006"})
tune = runner.invoke("adaptive_pid_tuning", {
    "loop_id": "LOOP-006",
    "plant_K": ident["K"],
    "plant_tau": ident["tau"],
    "plant_theta": ident["theta"],
    "current_Kc": 2.85,
    "current_Ti": 6.5,
    "anomaly_type": diag["anomaly_type"],
})
safety = runner.invoke("safety_constraint_verification", {
    "plant_K": ident["K"],
    "plant_tau": ident["tau"],
    "plant_theta": ident["theta"],
    **tune["recommended_pid"],
})
```

## 4. 单元测试
```bash
pytest 05_skills/tests/test_skills.py -v
```
