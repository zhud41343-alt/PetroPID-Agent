# PetroPID-Agent · 评委一键评审入口（Judge Portal）

> **参赛项目**：第二届石油和化工行业人工智能创新大赛 · 智能体赛道 · 赛题 5  
> **安全边界声明**：本项目全部代码、仿真、沙盒与评测均限于隔离离线环境，未连接或修改任何真实 DCS/PLC，**`deployment_authorized` 恒为 `false`**；审计机制采用全记录规范化 **SHA-256 摘要完整性校验**。

---

## 一、快速入口（评委 5 分钟直达核心证据）

| 评审关注点 | 直接打开入口 | 实测状态 |
| :--- | :--- | :--- |
| **公网可交互 Demo** | https://petropid-agent.onrender.com | 匿名直连已测：`/healthz` HTTP 200，当前线上版本为 **V4.3.3 / commit `cfd568a02eab`**；V4.3.4 候选暂以本地离线证据包为准 |
| **本地离线备演入口** | `python 08_demo_web/app.py` → `http://127.0.0.1:8000` | 零外网依赖，离线规则无缝运行 |
| **主视频脚本（2 分 30 秒）** | [05_DEMO_VIDEO_SCRIPT.md](competition_v4/submission_v433/05_DEMO_VIDEO_SCRIPT.md) | 覆盖 `LOOP-006` 放行导出 → `LOOP-012` 模型拒批 → `LOOP-021` 阀检建议（待人工录屏配音） |
| **全口径主成绩单** | [00_MASTER_SCORECARD.md](competition_v4/submission_v433/00_MASTER_SCORECARD.md) | V4.3.3 冻结基线（`24/30`, `11/17`, `0/19`）与 V4.3.4 正式编排候选（`30/30`, `17/17`, `0/13`, `30/30` 审计 PASS）并列可溯源 |
| **正式 V4.3.4 编排 30 回路评测** | [09_V434_FORMAL_BENCHMARK.md](competition_v4/submission_v433/09_V434_FORMAL_BENCHMARK.md) · [v434_formal_benchmark.json](competition_v4/submission_v433/v434_formal_benchmark.json) | 经 `PetroPIDOrchestrator(..., validation_profile="v4.3.4")` 全链路实测 `30/30`、`0` 误放行；24 回路预隔离合成留出检验 `23/24 (95.83%)` |
| **强单体（B3）vs 五阶段（C）公平对照** | [07_B3_VS_C_FAIR_AGENT_BENCHMARK.md](competition_v4/submission_v433/07_B3_VS_C_FAIR_AGENT_BENCHMARK.md) | 同等回退决策打平（`24/24 vs 24/24`），多智能体增量归因为阶段职责隔离、独立审批与失败阶段定位（`100% vs 0%`） |
| **Critic-Refiner 严格安全压力测试** | [10_V434_CRITIC_REFINER_BENCHMARK.md](competition_v4/submission_v433/10_V434_CRITIC_REFINER_BENCHMARK.md) · [v434_critic_refiner_benchmark.json](competition_v4/submission_v433/v434_critic_refiner_benchmark.json) | 12 组手工构造可整定难例 `0/12 → 12/12`；6 条预置诊断阻断路径两侧均 `0/6` 放行，明确标注为组件级回归 |
| **正式技术方案 & 矢量架构图** | [01_TECHNICAL_SPECIFICATION.md](competition_v4/submission_v433/01_TECHNICAL_SPECIFICATION.md) · [02_ARCHITECTURE_DIAGRAM.svg](competition_v4/submission_v433/02_ARCHITECTURE_DIAGRAM.svg) | 含 12 项证据溯源总表 [03_EVIDENCE_TRACEABILITY_MATRIX.md](competition_v4/submission_v433/03_EVIDENCE_TRACEABILITY_MATRIX.md) |
| **ISDB 76 回路真实工业数据外部评估** | [04_ISDB_EXTERNAL_INDUSTRIAL_EVAL.md](competition_v4/submission_v433/04_ISDB_EXTERNAL_INDUSTRIAL_EVAL.md) | 未知真值门禁 `0/76` 放行、`76/76` 二次完整性核验；冻结基线与 V4.3.4 探索扩展分栏，严格子集 F1 `52.63%` vs `80.00%` |
| **openJiuwen 原生 Workflow 实测记录** | [openjiuwen_native_workflow_run.json](competition_v4/submission_v433/openjiuwen_native_workflow_run.json) | 本地 `openjiuwen==0.1.21` Pregel `Workflow` 在 `LOOP-006/012/021` 全部 `COMPLETED` |
| **终审答辩成品 PPT（12 页）与 10 问应答** | [Image2.5视觉版.pptx](competition_v4/submission_v433/PetroPID-Agent_V4.3.4_终审答辩_Image2.5版.pptx) · [Image2.5视觉版.pdf](competition_v4/submission_v433/PetroPID-Agent_V4.3.4_终审答辩_Image2.5版.pdf) · [可编辑矢量版.pptx](competition_v4/submission_v433/PetroPID-Agent_V4.3.4_终审答辩.pptx) · [06_DEFENSE_PPT_OUTLINE.md](competition_v4/submission_v433/06_DEFENSE_PPT_OUTLINE.md) | 12 页 16:9 ISA-101 工业视觉成品（含逐页演讲备注与定稿提示词 [12_PPT_IMAGE_PROMPTS_FINAL.md](competition_v4/submission_v433/12_PPT_IMAGE_PROMPTS_FINAL.md)） |
| **GitHub Actions 全绿 CI** | https://github.com/zhud41343-alt/PetroPID-Agent/actions/runs/45407805806 | Linux CI `40 passed, 1 skipped` + Playwright 无头 Chromium `8/8 PASS` + `14/14 MCP` |

---

## 二、14 项竞赛交付物完整索引（每项均可直接打开）

| # | 交付资产类别 | 评委可打开入口 |
| :---: | :--- | :--- |
| 1 | Story 业务场景与 2 分 30 秒视频脚本 | [业务场景说明](01_docs/01_Story_业务场景/业务场景说明与典型案例.md) · [Story视频脚本](01_docs/01_Story_业务场景/Story演示视频脚本与分镜.md) |
| 2 | Toolkit 工具套件与复现教程 | [工具套件部署教程](01_docs/02_Toolkit_工具套件/工具套件介绍与部署使用教程.md) · [Toolkit视频脚本](01_docs/02_Toolkit_工具套件/Toolkit操作演示视频脚本.md) |
| 3 | Reference 技术参考文档（4 篇） | [需求调研](01_docs/03_Reference_参考文档/01_场景需求调研文档.md) · [系统蓝图](01_docs/03_Reference_参考文档/02_系统蓝图设计文档.md) · [实施规范](01_docs/03_Reference_参考文档/03_场景实施规范文档.md) · [公式推导](01_docs/03_Reference_参考文档/04_技术参考资料与公式推导.md) |
| 4 | Roadmap 6 阶段实施路径 | [实施路径手册](01_docs/04_Roadmap_实施路径/分步骤实施路径手册.md) · [Roadmap脚本](01_docs/04_Roadmap_实施路径/Roadmap分步讲解视频脚本.md) |
| 5 | 石化 30 回路离线基准数据集 | [02_datasets/](02_datasets/)（5 大装置 × 6 类工况 + 脱敏声明） |
| 6 | SQL 数据模型（7 表） | [03_models/data_model/](03_models/data_model/) · [validate_models.py](03_models/validate_models.py) |
| 7 | ISA-5.1 信息模型 & 22 条知识三元组 | [03_models/info_model/](03_models/info_model/) · [03_models/knowledge_model/](03_models/knowledge_model/) |
| 8 | OWL/RDF 石化控制本体（116 三元组） | [petro_pid_ontology.owl](03_models/ontology_model/petro_pid_ontology.owl) |
| 9 | 核心工业控制算法与安全检验算子 | [04_algorithms/petro_pid/](04_algorithms/petro_pid/)（FOPDT/SOPDT 仿真、诊断、65/35 辨识、SIMC、11 项硬约束） |
| 10 | 5 大标准化 Skill 与幂等缓存单测 | [05_skills/](05_skills/) · [test_skills.py](05_skills/tests/test_skills.py) |
| 11 | MCP JSON-RPC 2.0 服务端/客户端（14/14） | [mcp_server.py](06_mcp/mcp_server.py) · [mcp_client.py](06_mcp/mcp_client.py) · [联调报告](06_mcp/integration_test_report.md) |
| 12 | 多智能体编排、独立 9 态决策与 openJiuwen | [orchestrator.py](07_agents/orchestrator.py) · [decision_engine.py](07_agents/decision_engine.py) · [openjiuwen_native_workflow.py](07_agents/openjiuwen_native_workflow.py) |
| 13 | 工业 HMI 工作站与 Playwright 回归 | [08_demo_web/](08_demo_web/) · [test_playwright_e2e.py](08_demo_web/tests/test_playwright_e2e.py) |
| 14 | 消融/泛化/外部实测与 CI 完整证据包 | [competition_v4/submission_v433/](competition_v4/submission_v433/) · [competition_v4/final_release_v433/](competition_v4/final_release_v433/) |

---

## 三、一键全量离线复现命令

```bash
cd D:\石油\PetroPID-Agent
pip install -r requirements.txt
python 03_models/validate_models.py
pytest 04_algorithms/tests/ 05_skills/tests/ -v
python 06_mcp/mcp_client.py
python 07_agents/benchmark_runner.py
python 07_agents/v434_formal_benchmark.py
python 07_agents/recompute_ablation.py
python 07_agents/v434_fair_comparison.py
python 07_agents/v434_changepoint_validation_study.py
python 07_agents/openjiuwen_native_workflow.py
python 08_demo_web/app.py
```

V4.3.4 候选 profile 的本地复现：

```bash
python -c "import sys; sys.path.insert(0, '07_agents'); from orchestrator import PetroPIDOrchestrator; r=PetroPIDOrchestrator().run_loop_workflow('LOOP-012', validation_profile='v4.3.4'); print(r['final_status'], r['audit_meta']['audit_verification']['audit_status'], r['deployment_authorized'])"
```
