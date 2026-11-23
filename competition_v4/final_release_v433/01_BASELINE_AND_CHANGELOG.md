# 01 · V4.3.3 Final Freeze 基线与变更日志

- **生成时间**：2026-11-23 14:22:24 UTC
- **V4.3.2 回滚 Tag**：`v4.3.2-baseline`（上一轮审计 `main` SHA：`340ecff21d44db0330de05cf5768eb381ad50d37`）
- **V4.3.3 应用部署 SHA (`application_commit_full`)**：`d8efc92c3ec78a207919a307b23f15b82e01dba6`（GitHub Actions CI 全绿 + Render 实测 40 位一致）
- **核心变更**：
  1. **P0-01**：彻底移除 B1 假等价审计（`len(digest)==64`），B1/B2/C 共享同一 `verify_audit_record()`，新增 8 项相同篡改单测 `test_v433_b1_c_audit_equivalence.py`；
  2. **P0-02**：保存全部 144 次原始消融试验 JSON + CSV + 独立复算脚本 `07_agents/recompute_ablation.py`，新增同等信息边界对照组 `B2_single_agent_compact_real_audit`，修正所有 P50 延迟差值；
  3. **P0-03 & P1-05**：新增真实 GitHub Actions CI（[Run #45192957510](https://github.com/zhud41343-alt/PetroPID-Agent/actions/runs/45192957510) 56s 全绿），Render 实测 40 位 SHA `d8efc92c3ec78a207919a307b23f15b82e01dba6` 完全一致。
