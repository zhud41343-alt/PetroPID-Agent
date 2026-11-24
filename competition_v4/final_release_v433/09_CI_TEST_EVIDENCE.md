# 09 · GitHub Actions 离线 CI 真实运行证据

- **工作流文件**：`.github/workflows/ci.yml`（严格离线 `PETROPID_LLM_DISABLE_DOTENV=1`，零密钥暴露）
- **最新代码冻结全绿 CI 链接**：https://github.com/zhud41343-alt/PetroPID-Agent/actions/runs/45407211036
- **Run ID**：`45407211036`（绑定代码冻结基线 `a3e37b83b4f06b05e10aa4af3bbc924e6c5825e3`；后端算法冻结基线 `d8efc92c` 对应 Run `45192957510`）
- **运行状态**：**`completed / success`（全部 11 步 100% PASS）**
- **通过步骤**：
  1. `pytest`（**Linux CI：`40 passed, 1 skipped`**；本地 `41 passed`）
  2. `node --check 08_demo_web/static/app.js`
  3. **真实无头 Chromium Playwright E2E 回归**（含未验审计禁用「导出复核单」断言、HTTP 500 清旧态禁导出、沙盒一键 CSV、`1440×900` & `1366×768` 双视口 0 JS 报错）
  4. `MCP 14/14` → `OWL/SQL/KG` → `30-loop Benchmark` → `144-trial Ablation Recompute`
