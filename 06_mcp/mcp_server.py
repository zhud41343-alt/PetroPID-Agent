"""Standards-Compliant JSON-RPC 2.0 MCP Server for PetroPID-Agent.

Supports Model Context Protocol (MCP 2024-11-05) methods:
- initialize
- tools/list
- tools/call
- resources/list
- resources/read

Can run in stdio mode (`python mcp_server.py`) or be invoked programmatically by
MCP clients and the FastAPI Web Demo (`/mcp/rpc`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05_skills"))

from skill_runner import SkillRunner


class PetroPIDMCPServer:
    """JSON-RPC 2.0 MCP Server wrapping PetroPID Skills and domain resources."""

    SERVER_INFO = {
        "name": "petropid-mcp-server",
        "version": "1.0.0",
        "protocolVersion": "2024-11-05",
    }

    def __init__(self) -> None:
        self.runner = SkillRunner()
        with open(ROOT / "05_skills" / "skill_registry.json", "r", encoding="utf-8") as f:
            self.registry = json.load(f)

    def handle_request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": self.SERVER_INFO["protocolVersion"],
                    "serverInfo": {
                        "name": self.SERVER_INFO["name"],
                        "version": self.SERVER_INFO["version"],
                    },
                    "capabilities": {"tools": {}, "resources": {}},
                }
            elif method == "tools/list":
                tools = [
                    {
                        "name": s["name"],
                        "description": s["description"],
                        "inputSchema": s["input_schema"],
                    }
                    for s in self.registry["skills"]
                ]
                result = {"tools": tools}
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments") or {}
                output = self.runner.invoke(tool_name, arguments)
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(output, ensure_ascii=False),
                        }
                    ],
                    "structuredContent": output,
                    "isError": False,
                }
            elif method == "resources/list":
                result = {
                    "resources": [
                        {
                            "uri": "petropid://datasets/catalog",
                            "name": "PetroPID 30-Loop Benchmark Catalog",
                            "mimeType": "application/json",
                        },
                        {
                            "uri": "petropid://ontology/owl",
                            "name": "Petrochemical PID Control OWL Ontology",
                            "mimeType": "application/rdf+xml",
                        },
                        {
                            "uri": "petropid://knowledge/triples",
                            "name": "Petrochemical PID Knowledge Triples",
                            "mimeType": "application/json",
                        },
                    ]
                }
            elif method == "resources/read":
                uri = params.get("uri", "")
                text, mime = self._read_resource(uri)
                result = {"contents": [{"uri": uri, "mimeType": mime, "text": text}]}
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }

            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(exc)},
            }

    def _read_resource(self, uri: str) -> tuple[str, str]:
        if uri == "petropid://datasets/catalog":
            p = ROOT / "02_datasets" / "labels" / "loop_labels.json"
            return p.read_text(encoding="utf-8"), "application/json"
        if uri == "petropid://ontology/owl":
            p = ROOT / "03_models" / "ontology_model" / "petro_pid_ontology.owl"
            return (p.read_text(encoding="utf-8") if p.exists() else "<rdf:RDF/>"), "application/rdf+xml"
        if uri == "petropid://knowledge/triples":
            p = ROOT / "03_models" / "knowledge_model" / "knowledge_triples.json"
            return (p.read_text(encoding="utf-8") if p.exists() else "[]"), "application/json"
        raise ValueError(f"Unknown resource URI: {uri}")


def serve_stdio() -> None:
    """Run MCP server over stdin/stdout line-delimited JSON-RPC 2.0."""
    server = PetroPIDMCPServer()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        resp = server.handle_request(req)
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    serve_stdio()
