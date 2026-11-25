# PetroPID MCP 服务端与客户端协议级联调测试报告 (V3.0)

- **测试时间**：2026-11-25 12:42:53
- **传输协议**：JSON-RPC 2.0 over stdio（同步暴露 FastAPI `POST /mcp/rpc`）
- **测试结论**：**全部 14/14 项正向与负向异常恢复用例通过**

| 序号 | 测试用例 | MCP 方法 | 预期类型 | 耗时 (ms) | 结果 |
| :---: | :--- | :--- | :---: | :---: | :---: |
| 1 | 服务初始化 | `initialize` | 正常返回 | 1116.72 | PASS |
| 2 | 工具发现 | `tools/list` | 正常返回 | 0.13 | PASS |
| 3 | 资源发现 | `resources/list` | 正常返回 | 0.07 | PASS |
| 4 | 读取数据集目录资源 | `resources/read` | 正常返回 | 0.71 | PASS |
| 5 | 读取OWL本体资源 | `resources/read` | 正常返回 | 15.73 | PASS |
| 6 | 读取知识三元组资源 | `resources/read` | 正常返回 | 0.87 | PASS |
| 7 | 诊断工具调用(LOOP-006) | `tools/call` | 正常返回 | 8.19 | PASS |
| 8 | 辨识工具调用(LOOP-006) | `tools/call` | 正常返回 | 98.88 | PASS |
| 9 | 整定工具调用(LOOP-006) | `tools/call` | 正常返回 | 109.28 | PASS |
| 10 | 安全校验工具调用(LOOP-006) | `tools/call` | 正常返回 | 15.47 | PASS |
| 11 | 负向测试：未知JSON-RPC方法 | `unknown/method` | 错误拦截 | 0.07 | PASS |
| 12 | 负向测试：非法loop_id参数 | `tools/call` | 错误拦截 | 0.47 | PASS |
| 13 | 负向测试：越权/不存在资源URI | `resources/read` | 错误拦截 | 0.05 | PASS |
| 14 | 异常恢复测试：后续合法请求 | `tools/list` | 正常返回 | 0.09 | PASS |