# 07 · 全记录审计证据链完整性报告（P1-1）

- **V4.3 新增全记录摘要**：`compute_full_record_digest(record)` 对完整记录（`audit_meta` + `final_decision` + `final_pid` + `diagnosis` + `identification` + `safety` + `trace`）计算规范化 SHA-256 摘要 `record_digest_sha256`。
- **合法格式原位篡改测试**（`test_p1_01_full_record_digest_detects_in_place_valid_format_mutations`）：修改 `trace[0].summary`、`identification.val_fit_pct`、`audit_meta.timestamp` 共 3 类合法格式字段，**3/3 检出 `AUDIT_FULL_RECORD_DIGEST_MISMATCH`**。
- **线上实测样本**：`LOOP-006` `record_digest_sha256 = 8418f4131f53fde1df91db7453503f5647c2438521ead6e467c1cfe827ff1b40`，`integrity_scope = canonical_sha256_hash_integrity_without_external_kms`。
- **安全边界诚实声明**：SHA-256 摘要提供**数据完整性与意外/原位修改检测**，在无外部 KMS/PKI 签名根的隔离仿真环境中，**不宣称密码学不可抵赖**。
