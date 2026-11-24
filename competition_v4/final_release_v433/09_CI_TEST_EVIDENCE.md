# 09 · GitHub Actions 离线 CI 真实运行证据

- **工作流文件**：`.github/workflows/ci.yml`（严格离线 `PETROPID_LLM_DISABLE_DOTENV=1`，零密钥暴露）
- **最新全绿 CI 运行链接**：https://github.com/zhud41343-alt/PetroPID-Agent/actions/runs/45359152526
- **Run ID**：`45359152526`
- **绑定 Git SHA**：`a5867d22ecac6f808d9322cd0a3dee6f9341a5a8`（后端算法冻结基线仍为 `d8efc92c`，历史上对应 Run `45192957510`）
- **运行状态**：**`completed / success`（全部 11 步 100% PASS）**
- **通过步骤**：
  1. `pytest` 安全、审计、算法与 Web/HMI 契约测试（**Linux CI：`40 passed, 1 skipped`**，跳过项为轻量化 Ubuntu 环境未安装原生 openJiuwen SDK 的可选测试；本地全量 `41 passed`）
  2. `node --check 08_demo_web/static/app.js` 前端语法门禁
  3. **真实无头 Chromium Playwright E2E 回归**（`08_demo_web/tests/test_playwright_e2e.py`，覆盖 4 类典型回路、HTTP 500 清除旧工单与禁导出、篡改缺失审计/约束响应拦截、沙盒一键 CSV 正常 200 / 缺列 400、`1440×900` & `1366×768` 双视口 0 JS 报错）
  4. `MCP 14/14` → `OWL/SQL/KG` → `30-loop Benchmark` → `144-trial Ablation Recompute`
