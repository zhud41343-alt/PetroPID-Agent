# 02 · run_id 唯一性、跨回路绑定与两阶段审计核验报告

- **验证时间**：2026-11-23 12:30:51 UTC
- **本地并发测试**：`test_p0_01_run_id_uniqueness_under_high_concurrency_and_same_second`（6 线程并发 16 次运行：8×LOOP-006 + 4×LOOP-012 + 4×LOOP-021）→ **16/16 `run_id` 唯一、16/16 `request_id` 唯一、同输入共享 `input_hash` 与 `cache_key` 且 `cache_hit=False`**。
- **两阶段审计防篡改测试**：`test_p0_04_audit_gate_never_defaults_pass_and_detects_tampering` → 篡改 `dataset_version` / `input_hash` / `output_hash` / `run_id` / `timestamp` / `trace` / `identification` / `safety` / `deployment_authorized` 共 9 项，**9/9 检出 `FAIL`**。
- **线上 Render 实测证据（`https://petropid-agent.onrender.com`）**：
  - `LOOP-006 run_id`: `RUN-20261123124124007-60f3a4b344` | `request_id`: `REQ-783876f288c1`
  - `input_hash`: `c0f4b9e6d5e39b59bce063cae4ba79b5364db49cba41e609411e6ec76e9c72a4`
  - `output_hash`: `e40a1172c68d66f3be962a1138c9f94da650ed9481d163c263229d2e78465085`
  - `audit_verification`: `{'audit_status': 'PASS', 'errors': []}`
  - 合法审批单 `GET /api/approval/LOOP-006?run_id=...` → **`HTTP 200`**（含 5 工况表：`True`）
  - 跨回路绑定 `GET /api/approval/LOOP-012?run_id=<LOOP-006 run_id>` → **`HTTP 409` (Conflict)**
  - 不存在 `run_id` → **`HTTP 404` (Not Found)**
  - 审计包导出 `GET /api/export_bundle/LOOP-006?run_id=...` → **`HTTP 200`**（`run_id` 一致：`True`）
