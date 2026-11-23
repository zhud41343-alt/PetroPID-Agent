# PetroPID 化工自控领域知识模型规范

## 1. 知识表示方案
采用标准 **(Subject, Predicate, Object, Confidence, RuleID)** 结构化知识三元组（JSON 与 CSV 双格式存储于 `03_models/knowledge_model/`），并与 `03_models/ontology_model/` 中的 OWL 本体类通过 `subject_code` 精确对齐。

## 2. 知识抽取与更新流程
1. **抽取来源**：结合石化行业自控工程规范（SH/T 3005）、ISA-5.1、Skogestad SIMC 整定理论及 Choudhury 阀门粘滞诊断文献，提炼 22 条核心高置信度三元组。
2. **更新闭环**：多智能体在现场执行后，经工艺专家审核的新增异常案例通过结构化模板写入三元组库，并触发版本递增。
3. **质量校验规则**：
   - `confidence` 必须位于 `[0.80, 1.00]`；
   - `subject_code` 必须映射到 OWL 本体中已定义的合法类；
   - 禁止存在冲突的“推荐处置”与“禁止操作”三元组。
