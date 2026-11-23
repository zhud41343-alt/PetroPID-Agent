# 03 · Render 正式公网真实浏览器「评委 5 步导览」端到端实测报告

- **实测地址**：https://petropid-agent.onrender.com （`BROWSER_HOST_FACTS`: `visited_origins: https://petropid-agent.onrender.com`, `blocked_origins: none`）
- **实测版本**：`5808b9d474e6`（首次点击巡检发现按钮 ①–④ `runCurrentLoop is not defined` 缺陷，当场修复为 `runWorkflow()` 并重新部署复测）
- **复测结果（全部 5 个按钮实点通过）**：
  - **① 安全放行复核 (LOOP-006)**：`POST /api/run/LOOP-006` `200` → `RUN-20261123135319415-b083cdae5a` → `SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW`（时域图激活）
  - **② 模型失配拒批 (LOOP-012)**：`POST /api/run/LOOP-012` `200` → `RUN-20261123135336220-a8f22821f1` → `MODEL_VALIDATION_FAILED`（FOPDT 验证图激活，右对齐标签无裁切）
  - **③ 阀门粘滞拦截 (LOOP-021)**：`POST /api/run/LOOP-021` `200` → `RUN-20261123135353618-f029feb551` → `VALVE_MAINTENANCE_REQUIRED`（PV-OP 相图激活）
  - **④ 外扰性能拒批 (LOOP-029)**：`POST /api/run/LOOP-029` `200` → `RUN-20261123135410152-63715bc9f0` → `PERFORMANCE_NOT_IMPROVED`
  - **⑤ 压力沙盒 / CSV**：切换至沙盒视图并实跑 `POST /api/sandbox` `200` → `RUN-20261123134654470-fe82c4d3ce`
  - **AI 副驾驶跨回路点名**：在 `LOOP-029` 页面提问“为什么 LOOP-012 被拒批了？”正确解析并回答 `LOOP-012 (LIC-103)`
- **复测报错计数**：**JS 控制台报错 `0`**｜**HTTP >= 400 错误 `0`（0/22 失败）**
- **实景截图**：`browser_evidence/b4291eda-6b1e-438d-baee-4baad5012efb/final_step_47.png`
