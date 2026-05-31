from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai4science.harness.tools.base import Tool


class StdioTransport:
    """JSON-RPC over a server subprocess's stdin/stdout (newline-delimited)."""
    def __init__(self, cmd: List[str], cwd: Optional[Path] = None) -> None:
        self.proc = subprocess.Popen(
            cmd, cwd=str(cwd) if cwd else None,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self._id = 0

    def request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        resp = json.loads(line)
        if "error" in resp:
            raise RuntimeError(resp["error"])
        return resp.get("result", {})

    def close(self) -> None:
        try:
            self.proc.terminate()
        except Exception:
            pass


class MCPClient:
    def __init__(self, *, transport, server: str) -> None:
        self.transport = transport
        self.server = server
        self._tools: List[Dict] = []

    def initialize(self) -> None:
        self.transport.request("initialize", {"protocolVersion": "2024-11-05",
                                              "capabilities": {},
                                              "clientInfo": {"name": "ai4science"}})

    def list_tools(self) -> List[Dict]:
        self._tools = self.transport.request("tools/list", {}).get("tools", [])
        return self._tools

    def call_tool(self, name: str, args: Dict[str, Any]) -> str:
        res = self.transport.request("tools/call", {"name": name, "arguments": args})
        parts = [b.get("text", "") for b in res.get("content", [])
                 if isinstance(b, dict) and b.get("type") == "text"]
        return "".join(parts)


def mcp_tools(client: MCPClient) -> List[Tool]:
    out = []
    for spec in (client._tools or client.list_tools()):
        name = spec["name"]
        qualified = f"mcp__{client.server}__{name}"

        def _make(tool_name: str):
            def _call(workspace: Path, **args) -> str:
                return client.call_tool(tool_name, args)
            return _call

        out.append(Tool(qualified, spec.get("description", ""),
                        spec.get("inputSchema", {"type": "object"}),
                        _make(name), mutating=True))
    return out
