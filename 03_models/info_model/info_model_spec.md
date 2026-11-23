# PetroPID 行业信息模型规范

## 1. 业务实体与 ISA-5.1 编码映射规则
本信息模型对齐 **ISA-5.1** 仪表位号规范与 **ISA-95** 制造运行架构，完整 JSON 定义见 `03_models/info_model/info_model.json`。

| 编码类型 | 正则规范 | 示例 | 业务语义 |
| :--- | :--- | :--- | :--- |
| 回路编号 | `^LOOP-[0-9]{3}$` | `LOOP-006` | 平台内部脱敏唯一标识 |
| 仪表位号 | `^(TIC\|FIC\|PIC\|LIC)-[0-9]{3}$` | `TIC-201` | 温度/流量/压力/液位指示控制位号 |
| 安全约束编号 | `^C-[0-9]{3}$` | `C-004` | 频域/时域/多工况安全校验规则唯一标识 |

## 2. 信息流转与接口约束
1. **数据脱敏边界**：原始工厂 IP 与涉密配方在边缘采集层剥离，进入智能体层仅流转标准化位号与相对时间戳。
2. **上下文防膨胀约束**：智能体间仅传递 `LoopDiagnosticSnapshot` 与 `ProcessDynamicsModel` 压缩 JSON（单次交互负载 < 4 KB），原始时序数组保留在 MCP 服务端内存中计算。
3. **DCS 下发强约束**：任何 `PIDParameterRecommendation` 未获得 `approved=true` 与 `constraint_coverage_pct=100%` 签章前，严禁进入下发队列。
