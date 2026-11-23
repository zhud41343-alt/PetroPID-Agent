# 12 · 剩余风险与边界透明声明（V4.2）

1. **真实工业现场未验证（仿真边界）**：全部数据来自机理仿真与隔离沙盒，`deployment_authorized` 恒为 `False`，无真实 DCS/PLC 投运授权。
2. **Render Free 持久化与冷启动限制**：Free 层容器重启/重新部署会清空本地临时 SQLite 缓存（已通过 `404` 明确报错禁止伪造历史审批单）；闲置 15 分钟休眠，首次唤醒需 40–50s。
3. **Render 容器未装重型 `openjiuwen`（含 `pymilvus`）**：为保证 512MB Free 内存稳定零 OOM，原生 `openjiuwen==0.1.21` 工具层在本地实测通过，云端运行轻量适配层；`openjiuwen.core.workflow` + Milvus 向量库编排保持 `UNVERIFIED`。
4. **30 回路中 6 个低激励迟缓回路未自动辨识成功**：独立全任务精确匹配率为 `24/30 (80.0%)`，这真实反映了无足够激励时 FOPDT 辨识的物理极限（0 危险误放行）。
5. **二阶强滤波粘滞边界 (`OOD-07`)**：已在 V4.2 加入 `DIAGNOSIS_AMBIGUOUS_STICTION_VS_DISTURBANCE` 不确定性告警并拒批，后续引入阀位回讯 (MV/Valve Position) 可进一步根除歧义。
6. **3 段配套视频尚未录制**：当前总分不含 10 分视频项，需在 2026-12-08 18:00 前完成录屏。
