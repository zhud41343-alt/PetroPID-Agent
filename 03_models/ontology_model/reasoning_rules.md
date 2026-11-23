# PetroPID 领域本体推理规则与版本复用说明

## 1. 核心推理规则（SWRL 风格）
- **R-01（阀门粘滞拦截规则）**：`ControlLoop(?l) ^ hasStictionIndex(?l, ?si) ^ greaterThanOrEqual(?si, 0.42) ^ hasOscillationIndex(?l, ?oi) ^ greaterThanOrEqual(?oi, 0.35) -> hasAnomaly(?l, VALVE_STICTION) ^ recommendsStrategy(?l, ConservativeStrategy)`
- **R-02（激进整定规则）**：`ControlLoop(?l) ^ hasOscillationIndex(?l, ?oi) ^ greaterThanOrEqual(?oi, 0.35) ^ hasStictionIndex(?l, ?si) ^ lessThan(?si, 0.42) -> hasAnomaly(?l, AGGRESSIVE_TUNING) ^ recommendsStrategy(?l, BalancedSIMCStrategy)`
- **R-03（安全下发一票否决规则）**：`PIDController(?c) ^ verifiedAgainst(?c, ?s) ^ (GM < 1.8 OR PM < 35° OR Ms > 2.2 OR MultiRegimePassRate < 80%) -> BlockDCSDeployment(?c)`

## 2. 版本与复用说明
- 当前版本：`v1.0.0`（命名空间 `http://petropid.ai/ontology/pid#`）
- 同时提供 Turtle (`.ttl`) 与标准 RDF/XML (`.owl`) 两种序列化文件，已通过 `rdflib` 语法与三元组完整性校验，可直接导入 Protégé 或中试基地知识图谱平台复用。
