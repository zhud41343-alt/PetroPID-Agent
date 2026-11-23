# Toolkit 操作演示视频脚本（建议时长：2 分钟）

| 时间段 | 画面操作 | 逐字口播稿 |
| :--- | :--- | :--- |
| **0:00–0:25** | 打开文件夹 `D:\石油\PetroPID-Agent`，展示 01–08 规范目录结构 | “本段视频演示 PetroPID-Agent 工具套件的本地部署、自动化验证与 MCP 联调全过程。项目按中试基地交付规范划分为文档、数据集、四大模型、核心算子、Skill、MCP、多智能体与 Web Demo 八大模块。” |
| **0:25–0:55** | 打开终端运行 `python 03_models/validate_models.py` 和 `pytest 04_algorithms/tests/test_algorithms.py 05_skills/tests/test_skills.py -v` | “首先执行模型校验脚本，可以看到标准 OWL 本体 116 条三元组、6 张关系型 SQL 业务表和 22 条领域知识三元组全部校验通过。接着运行 pytest 单元测试，算子与 5 大标准化 Skill 测试用例全部绿色通过。” |
| **0:55–1:30** | 终端运行 `python 06_mcp/mcp_client.py` 和 `python 07_agents/benchmark_runner.py` | “接着验证 MCP 协议联调：客户端通过标准 JSON-RPC 2.0 协议拉起 MCP 服务端，完成 8 项端到端工具与资源联调测试。再运行 30 回路全量基准评测，几秒内输出全部 KPI 实测报告。” |
| **1:30–2:00** | 双击 `08_demo_web/start_demo.bat`，打开浏览器 `http://127.0.0.1:8000` 并点击切换回路 | “最后双击一键启动脚本，浏览器访问 8000 端口即可进入工业 DCS 多智能体交互看板，实现零门槛复现与演示。” |
