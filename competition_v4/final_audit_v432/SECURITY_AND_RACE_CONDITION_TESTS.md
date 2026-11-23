# 08 · 安全审计、并发竞态与负向测试汇总

- **全量自动化测试**：**`36/36 pytest PASS`**（含 `test_v42_p0_audit.py` 16 并发同秒 `run_id`、`409/404/410/422` 跨回路绑定、8 类输入哈希微扰、未知 CSV 真值隔离；`test_v43_p0_and_p1.py` OOD-20/Performance 负向；`test_v432_p0_audit_digest.py` 12 项强制全记录摘要篡改与旧版记录拒绝）。
- **前端防乱序**：`latestRequestSeq` 单调递增序号丢弃过期异步返回；Render Free 重启清空临时 SQLite 时返回 `404` 拒绝伪造历史审批单。
