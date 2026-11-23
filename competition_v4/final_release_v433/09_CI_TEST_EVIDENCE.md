# 09 · GitHub Actions 离线 CI 真实运行证据

- **工作流文件**：`.github/workflows/ci.yml`（严格离线 `PETROPID_LLM_DISABLE_DOTENV=1`，零密钥暴露）
- **真实 CI 运行链接**：https://github.com/zhud41343-alt/PetroPID-Agent/actions/runs/45192957510
- **Run ID**：`45192957510`（Job ID `137755841059`）
- **绑定 Git SHA**：`d8efc92c3ec78a207919a307b23f15b82e01dba6`
- **运行状态 / 耗时**：**`completed / success`（56s 全绿）**
- **通过步骤**：`pytest`（36 passed, 1 skipped native openJiuwen on lightweight Ubuntu CI）→ `MCP 14/14` → `OWL/SQL/KG` → `30-loop Benchmark` → `144-trial Ablation Recompute`。
