"""ACP (Agent Client Protocol) stdio server for ai4science modes.

Spawned by ai4science.harness.agents.sarsi.acp.AcpRuntime when the session
spec is not 'opencode'. Speaks the same JSON-RPC 2.0 dialect as
`opencode acp --pure`, so the sarsi harness drives ai4science sessions
through the same transport and delivery path as opencode.

Usage (internal):  ai4science acp --pure [--mode general-purpose]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

app = typer.Typer(name="acp", hidden=True, invoke_without_command=True,
                  no_args_is_help=False)

_BACKEND = "qwen_local"
_DEFAULT_MODEL = "qwen3.8:27b"
_MAX_TOOL_TURNS = 20

_TOOLS = [
    {"type": "function", "function": {
        "name": "bash",
        "description": "Run a shell command in the session working directory.",
        "parameters": {"type": "object",
                       "properties": {"command": {"type": "string",
                                                  "description": "Shell command to run"}},
                       "required": ["command"]},
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a file's contents.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string",
                                               "description": "File path (relative or absolute)"}},
                       "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Write content to a file (creates or overwrites).",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"},
                                      "content": {"type": "string"}},
                       "required": ["path", "content"]},
    }},
]


def _write(obj: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _session_update(text: str) -> None:
    _write({"jsonrpc": "2.0", "method": "session/update", "params": {"update": {
        "sessionUpdate": "agent_message_chunk",
        "content": {"text": text},
    }}})


def _tool_update(name: str, args: str) -> None:
    _write({"jsonrpc": "2.0", "method": "session/update", "params": {"update": {
        "sessionUpdate": "tool_call",
        "content": {"tool": name, "input": args},
    }}})


def _run_bash(command: str, cwd: str) -> str:
    try:
        r = subprocess.run(["bash", "-c", command], cwd=cwd,
                           capture_output=True, text=True, timeout=120)
        out = r.stdout
        if r.stderr.strip():
            out += "\nstderr:\n" + r.stderr
        return (out or "(no output)")[:8000]
    except subprocess.TimeoutExpired:
        return "(command timed out after 120s)"
    except Exception as e:
        return f"(error: {e})"


def _run_read(path: str, cwd: str) -> str:
    try:
        p = Path(path) if os.path.isabs(path) else Path(cwd) / path
        return p.read_text(encoding="utf-8", errors="replace")[:8000]
    except Exception as e:
        return f"(error: {e})"


def _run_write(path: str, content: str, cwd: str) -> str:
    try:
        p = Path(path) if os.path.isabs(path) else Path(cwd) / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} bytes to {p}"
    except Exception as e:
        return f"(error: {e})"


def _execute_tool(name: str, args_json: str, cwd: str) -> str:
    try:
        args = json.loads(args_json)
    except Exception:
        return "(invalid tool arguments)"
    if name == "bash":
        return _run_bash(args.get("command", ""), cwd)
    if name == "read_file":
        return _run_read(args.get("path", ""), cwd)
    if name == "write_file":
        return _run_write(args.get("path", ""), args.get("content", ""), cwd)
    return f"(unknown tool: {name!r})"


def _chat_raw(messages: List[Dict], model: str,
              tools: Optional[List] = None) -> Dict:
    """Direct HTTP call to qwen_local, returning the raw response dict."""
    import urllib.error
    import urllib.request
    from ai4science.llm.openai_compat import resolve_key, resolve_base

    key = resolve_key(_BACKEND)
    if not key:
        raise RuntimeError("no API key for qwen_local")
    base = resolve_base(_BACKEND)
    if not base:
        raise RuntimeError("no base URL for qwen_local")

    body: Dict[str, Any] = {"model": model, "messages": messages}
    if tools:
        body["tools"] = tools

    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "User-Agent": "ai4science/acp"},
    )
    try:
        return json.load(urllib.request.urlopen(req, timeout=300))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}")


def _run_agentic(session: Dict, text: str, model: str) -> str:
    """Agentic loop: send prompt, execute any tool calls, repeat until text reply."""
    session["messages"].append({"role": "user", "content": text})

    for _ in range(_MAX_TOOL_TURNS):
        resp = _chat_raw(session["messages"], model, tools=_TOOLS)
        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []

        session["messages"].append(dict(msg))

        if not tool_calls:
            if content:
                _session_update(content)
            return content

        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            args_json = fn.get("arguments", "{}")
            tc_id = tc.get("id", "")
            _tool_update(name, args_json)
            result = _execute_tool(name, args_json, session["cwd"])
            session["messages"].append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": result,
            })

    # Hit the turn cap — ask for a summary
    session["messages"].append({"role": "user",
                                "content": "Summarize what you have done so far."})
    resp = _chat_raw(session["messages"], model)
    content = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if content:
        _session_update(content)
    return content


def _system_prompt(mode: str) -> str:
    return (
        f"You are a {mode} AI assistant with access to tools. "
        "Use bash to run shell commands, read_file to read files, and write_file to write files. "
        "Work step by step. When a task is complete, summarise what you did and what changed."
    )


_sessions: Dict[str, Dict] = {}


@app.callback()
def acp_main(
    ctx: typer.Context,
    pure: bool = typer.Option(False, "--pure",
                               help="Run as ACP JSON-RPC stdio server (internal)."),
    mode: str = typer.Option("general-purpose", "--mode",
                              help="Session mode passed by the harness."),
) -> None:
    """ACP stdio server — driven by the sarsi harness, not for direct use."""
    if not pure:
        if ctx.invoked_subcommand is None:
            typer.echo("Usage: ai4science acp --pure [--mode MODE]", err=True)
        return

    model = os.environ.get("AI4SCIENCE_MODEL", _DEFAULT_MODEL)

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method")
        rid = msg.get("id")
        params = msg.get("params") or {}

        try:
            if method == "initialize":
                _write({"jsonrpc": "2.0", "id": rid,
                        "result": {"serverCapabilities": {}}})

            elif method == "session/new":
                sid = str(uuid.uuid4())
                cwd = params.get("cwd") or os.getcwd()
                _sessions[sid] = {
                    "cwd": cwd,
                    "mode": mode,
                    "messages": [{"role": "system", "content": _system_prompt(mode)}],
                }
                _write({"jsonrpc": "2.0", "id": rid, "result": {"sessionId": sid}})

            elif method == "session/prompt":
                sid = params.get("sessionId")
                sess = _sessions.get(sid)
                if sess is None:
                    _write({"jsonrpc": "2.0", "id": rid, "error": {
                        "code": -32000,
                        "message": f"unknown session {sid!r}"}})
                    continue
                parts = params.get("prompt") or []
                text = "".join(
                    p.get("text", "") for p in parts if p.get("type") == "text")
                try:
                    _run_agentic(sess, text, model)
                    _write({"jsonrpc": "2.0", "id": rid,
                            "result": {"stopReason": "end_turn"}})
                except Exception as e:
                    _write({"jsonrpc": "2.0", "id": rid, "error": {
                        "code": -32000, "message": str(e)}})

            else:
                if rid is not None:
                    _write({"jsonrpc": "2.0", "id": rid, "result": {}})

        except Exception as e:
            if rid is not None:
                _write({"jsonrpc": "2.0", "id": rid, "error": {
                    "code": -32000, "message": str(e)}})
