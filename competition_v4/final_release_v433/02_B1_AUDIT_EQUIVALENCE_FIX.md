# 02 · P0-01 B1/B2/C 审计验证等价性修复报告

- **旧缺陷**：V4.3.2 中 B1 仅判断 `len(digest) == 64`，未调用 `verify_audit_record()`。
- **V4.3.3 修复**（`07_agents/v433_ablation.py`）：实现 `build_equivalent_audit_record()`，为 B1/B2 构建与 C 完全同构的 V4.3.3 审计记录（含 `run_id`、`request_id`、`input_hash`、`output_hash`、`diagnosis`、`identification`、`safety`、`final_decision`、`trace`、`waveforms`、`record_digest_sha256`），并经同一 `verify_audit_record()` 校验。
- **等价篡改单测**：`04_algorithms/tests/test_v433_b1_c_audit_equivalence.py` 对 B1 与 C 施加相同 8 项篡改（删摘要、改诊断、改模型精度、改安全结论、改终态、改 Trace、改输入哈希、改版本号），**B1 检出 8/8、C 检出 8/8**。
