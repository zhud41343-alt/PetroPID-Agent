# 01 · P0-01 强制全记录审计摘要修复报告（V4.3.2）

- **漏洞根因**：V4.3 中 `if rec_digest is not None:` 允许删除或置空 `record_digest_sha256` 跳过完整摘要校验。
- **V4.3.2 修复**（`07_agents/decision_engine.py`）：
  - `record_digest_sha256` 现为**强制必填项**，缺失/`None`/空串返回 `AUDIT_MISSING_RECORD_DIGEST_LEGACY_OR_UNVERIFIED`（`FAIL` + HTTP `422`）；
  - 校验 64 位小写 hex 格式并用 `hmac.compare_digest` 恒定时间比对重算值；
  - `compute_full_record_digest` 现覆盖 `audit_meta`、`final_decision`、`final_pid`、`diagnosis`、`identification`、`tuning`、`safety`、`baseline_comparison`、`trace` 及导出 `waveforms`；明确标注非受保护显示投影字段（`identification_plot`/`phase_portrait`/`nyquist_plot`）。
- **12 项负向测试全通过**：`04_algorithms/tests/test_v432_p0_audit_digest.py`（全量 `36/36 pytest PASS`）。
