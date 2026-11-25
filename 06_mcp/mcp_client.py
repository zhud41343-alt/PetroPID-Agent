"""MCP Client & Protocol-Level Integration Test Suite (V3.0).

Tests:
1. initialize
2. tools/list (schema & count verification)
3. resources/list & resources/read (catalog, OWL ontology, knowledge triples)
4. Full 4-stage tools/call chain on LOOP-006
5. Negative protocol tests: unknown method (-32601), invalid loop_id (-32000),
   unknown resource URI (-32000), and recovery on subsequent valid request!
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]


class StdioMCPClient:
    def __init__(self, server_script: Path) -> None:
        child_env = os.environ.copy()
        # Keep JSON-RPC stdout and diagnostic stderr UTF-8 on Windows hosts
        # whose default console code page is GBK. This makes the documented
        # local reproduction command behave like Linux CI.
        child_env.setdefault("PYTHONIOENCODING", "utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, str(server_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=child_env,
        )
        self._id = 0

    def request(self, method: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            err = self.proc.stderr.read() if self.proc.stderr else ""
            raise RuntimeError(f"MCP server closed unexpectedly: {err}")
        return json.loads(line)

    def close(self) -> None:
        self.proc.terminate()
        self.proc.wait(timeout=5)


def run_integration_test() -> None:
    server_script = ROOT / "06_mcp" / "mcp_server.py"
    client = StdioMCPClient(server_script)
    logs = []

    def record(name: str, method: str, params: Dict[str, Any], expect_error: bool = False) -> Dict[str, Any]:
        t0 = time.perf_counter()
        resp = client.request(method, params)
        ms = round((time.perf_counter() - t0) * 1000.0, 2)
        has_err = "error" in resp
        ok = (has_err == expect_error)
        assert ok, f"Case {name} failed: {resp}"
        logs.append({"case": name, "method": method, "expect_error": expect_error, "latency_ms": ms, "ok": ok})
        return resp

    try:
        record("服务初始化", "initialize", {})
        tools_r = record("工具发现", "tools/list", {})
        assert len(tools_r["result"]["tools"]) == 5
        res_r = record("资源发现", "resources/list", {})
        assert len(res_r["result"]["resources"]) == 3
        record("读取数据集目录资源", "resources/read", {"uri": "petropid://datasets/catalog"})
        record("读取OWL本体资源", "resources/read", {"uri": "petropid://ontology/owl"})
        record("读取知识三元组资源", "resources/read", {"uri": "petropid://knowledge/triples"})

        diag_r = record("诊断工具调用(LOOP-006)", "tools/call", {"name": "pid_loop_diagnosis", "arguments": {"loop_id": "LOOP-006"}})
        diag_out = diag_r["result"]["structuredContent"]

        id_r = record("辨识工具调用(LOOP-006)", "tools/call", {"name": "fopdt_system_identification", "arguments": {"loop_id": "LOOP-006"}})
        id_out = id_r["result"]["structuredContent"]

        tune_r = record("整定工具调用(LOOP-006)", "tools/call", {
            "name": "adaptive_pid_tuning",
            "arguments": {
                "loop_id": "LOOP-006", "plant_K": id_out["K"], "plant_tau": id_out["tau"],
                "plant_theta": id_out["theta"], "current_Kc": 2.15, "current_Ti": 8.5,
                "anomaly_type": diag_out["anomaly_type"],
            },
        })
        tune_out = tune_r["result"]["structuredContent"]
        rec = tune_out["recommended_pid"]

        safe_r = record("安全校验工具调用(LOOP-006)", "tools/call", {
            "name": "safety_constraint_verification",
            "arguments": {
                "plant_K": id_out["K"], "plant_tau": id_out["tau"], "plant_theta": id_out["theta"],
                "Kc": rec["Kc"], "Ti": rec["Ti"], "Td": rec["Td"],
            },
        })
        safe_out = safe_r["result"]["structuredContent"]
        assert safe_out["approved"] is True

        # Negative protocol & error recovery tests
        err1 = record("负向测试：未知JSON-RPC方法", "unknown/method", {}, expect_error=True)
        assert err1["error"]["code"] == -32601
        record("负向测试：非法loop_id参数", "tools/call", {"name": "pid_loop_diagnosis", "arguments": {"loop_id": "LOOP-999"}}, expect_error=True)
        record("负向测试：越权/不存在资源URI", "resources/read", {"uri": "file:///etc/passwd"}, expect_error=True)
        # Verify server recovers cleanly after errors
        record("异常恢复测试：后续合法请求", "tools/list", {}, expect_error=False)

        lines = [
            "# PetroPID MCP 服务端与客户端协议级联调测试报告 (V3.0)",
            "",
            f"- **测试时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "- **传输协议**：JSON-RPC 2.0 over stdio（同步暴露 FastAPI `POST /mcp/rpc`）",
            f"- **测试结论**：**全部 {len(logs)}/{len(logs)} 项正向与负向异常恢复用例通过**",
            "",
            "| 序号 | 测试用例 | MCP 方法 | 预期类型 | 耗时 (ms) | 结果 |",
            "| :---: | :--- | :--- | :---: | :---: | :---: |",
        ]
        for i, item in enumerate(logs, 1):
            lines.append(
                f"| {i} | {item['case']} | `{item['method']}` | {'错误拦截' if item['expect_error'] else '正常返回'} | {item['latency_ms']} | PASS |"
            )

        (ROOT / "06_mcp" / "integration_test_report.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"MCP V3.0 protocol test PASSED ({len(logs)}/{len(logs)}).")
    finally:
        client.close()


if __name__ == "__main__":
    run_integration_test()
