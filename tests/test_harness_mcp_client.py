from ai4science.harness.mcp_client import MCPClient, mcp_tools


class _FakeTransport:
    """In-process fake MCP server: answers initialize / tools/list / tools/call."""
    def __init__(self):
        self._tools = [{"name": "echo", "description": "echo text",
                        "inputSchema": {"type": "object",
                                        "properties": {"text": {"type": "string"}}}}]

    def request(self, method, params):
        if method == "initialize":
            return {"capabilities": {}}
        if method == "tools/list":
            return {"tools": self._tools}
        if method == "tools/call":
            return {"content": [{"type": "text", "text": "echo:" + params["arguments"]["text"]}]}
        raise AssertionError(method)


def test_client_lists_and_calls(tmp_path):
    c = MCPClient(transport=_FakeTransport(), server="demo")
    c.initialize()
    specs = c.list_tools()
    assert specs[0]["name"] == "echo"
    result = c.call_tool("echo", {"text": "hi"})
    assert result == "echo:hi"


def test_mcp_tools_wraps_with_namespace(tmp_path):
    c = MCPClient(transport=_FakeTransport(), server="demo")
    c.initialize()
    tools = mcp_tools(c)
    assert tools[0].name == "mcp__demo__echo"
    assert tools[0].parameters["properties"]["text"]["type"] == "string"
    out = tools[0].func(tmp_path, text="yo")
    assert out == "echo:yo"
