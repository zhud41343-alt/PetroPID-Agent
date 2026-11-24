# 11 · Render 正式公网真实浏览器端到端验收记录（V4.3.3 Final CLPM 升级版）

- **浏览器实测源**：`https://petropid-agent.onrender.com`（`1440×900` 桌面视口，`BROWSER_HOST_FACTS`: `visited_origins: https://petropid-agent.onrender.com`, `blocked_origins: none`）
- **线上部署版本与探针核验**（`GET /healthz?probe_llm=true`, HTTP 200）：
  - `code_commit_full`: `3b3a683b5e542dad1ae3fddbcc2d36f7041be85c`（对应历史公网部署实测版本；正式功能代码冻结基线为 `a3e37b83b4f06b05e10aa4af3bbc924e6c5825e3`，已在 GitHub Actions CI Run `45407805806` 通过无头 Chromium Playwright 8 项自动化回归，并在 Render 公网 `/healthz?probe_llm=true` 核实 `VERIFIED_LIVE`）
  - `version`: `4.3.3` | `algorithm_version`: `petropid-alg-v4.3.3` | `dataset_version`: `petropid-sim-30loops-v2.0`
  - `deployment_authorized`: `false`
  - `llm_health`: `configured_mode=live_llm_api`, `connectivity_status=VERIFIED_LIVE`, `model=deepseek-flash`, `latency_ms=1009.8`, `request_id=420bddd8-3709-4505-8b34-b5b346290546`
- **全流程实测结果**：
  1. **主页与 `LOOP-006 · TIC-201`**：顶部副标题显示「参考 ISA-101 高性能 HMI 设计原则 · 离线机理仿真与安全校验」、遥测条显示「离线仿真基准: 30 回路」；单行绿色 DCS 审批横幅与 `.fp-delta` `-98%` 单行徽章渲染完整无裁切；底部审计条显示 `RUN-20261123163736867-36e19ac2dc`、`5aebd325b9df…` 与 `审计: PASS`；
  2. **`LOOP-012 · LIC-103`**：正确展示红色拦截横幅与 `模型未过 · 拒绝变更`（`MODEL_VALIDATION_FAILED`）；
  3. **`LOOP-021 · FIC-404`**：正确展示 `阀门粘滞 · 建议检修`（`VALVE_MAINTENANCE_REQUIRED`），切换「阀门相图」清晰呈现带滞环方向箭头的 PV-OP 相图（`SI = 0.46`）；
  4. **`LOOP-029 · TIC-206`**：正确展示 `外扰未改善 · 保持原参`（`PERFORMANCE_NOT_IMPROVED`）；
  5. **压力沙盒 (`view-sandbox`)**：`POST /api/sandbox` 返回 HTTP 200（`RUN-20261123164130948-adcc9ea576`），双图波形与 `C-000..C-010` 11 项约束表完整渲染；
  6. **全厂 30 回路总览 (`view-plant`)**：5 大石化装置离线仿真基准热图单行 5 列对齐（`y=282`），5 个健康回路均显示 `运行健康 · 无需变更`。
- **报错统计**：**JS 控制台报错 `0`**｜**HTTP >= 400 错误 `0`（0/18 失败）**。
- **后端冻结声明**：自 V4.3.3 后端基线 `d8efc92c3ec78a207919a307b23f15b82e01dba6` 以来仅更新前端静态文件（`08_demo_web/static/`）与验收文档，后端算法、安全判定与审计代码零改动。
