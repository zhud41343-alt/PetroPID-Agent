# 08 · 独立安全决策与审计全量回归报告

- **本地全量测试**：`37/37 pytest PASS`（23.14s）｜`14/14 MCP PASS`｜OWL 116 三元组 / SQL 7 表 / KG 22 三元组 PASS；
- **核心覆盖**：9 状态 `FinalDecisionEngine`、强制 `record_digest_sha256`（12 项篡改 + B1/C 8 项等价篡改）、`409/404/410/422` 跨回路绑定、未知 CSV 零假真值、`deployment_authorized` 恒为 `False`；
- **安全边界**：SHA-256 摘要提供完整性检测，不含外部 KMS 签名根，不宣称密码学不可抵赖。
