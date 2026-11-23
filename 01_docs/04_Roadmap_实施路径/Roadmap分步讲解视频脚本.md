# Roadmap 分步实施讲解视频脚本（建议时长：1 分 30 秒 – 2 分钟）

| 时间段 | 画面操作 | 逐字口播稿 |
| :--- | :--- | :--- |
| **0:00–0:25** | 打开 `01_docs/04_Roadmap_实施路径/分步骤实施路径手册.md` 与 `02_系统蓝图设计文档.md` | “本段视频为您介绍 PetroPID-Agent 在石化装置落地的 6 阶段分步实施路径，整个试点周期仅需 4 到 6 周，低门槛、可复用。” |
| **0:25–0:55** | 依次展示 `02_datasets`、`03_models/ontology_model/petro_pid_ontology.owl` 与 `05_skills/skill_registry.json` | “第一至第三阶段，我们先通过标准清洗脚本对接 DCS 历史数据并完成脱敏；接着导入标准化 OWL 本体与知识三元组；再将诊断、辨识、整定和安全校验算子封装成带幂等防重缓存的 5 大标准 Skill。” |
| **0:55–1:30** | 展示 `06_mcp/integration_test_report.md`、`07_agents/integration_verify_report.md` 及 Web Demo 界面 | “第四至第六阶段，通过 MCP 协议接入华为 openJiuwen 多智能体与昇腾推理底座，先在看板上以‘只读影子模式’完成离线验证与 100% 安全审计，再经工程师审批灰度下发至 DCS，安全、可控地实现全厂控制回路智能化升级。” |
