"""In-process MCP server exposing PWM-specific tools to the agent.

The Claude Agent SDK lets us define tools via the ``@tool`` decorator
and bundle them into an SDK-defined MCP server. That server is
registered in ``ClaudeAgentOptions.mcp_servers`` and the agent can call
the tools as ``mcp__pwm__<tool_name>``.

Tools we expose:

  pwm_validate        — run ai4science validate on the workspace
  pwm_judge_cassi     — run the CASSI Physics Judge (deterministic)
  pwm_status          — return workspace status (artifacts present, reports)
  pwm_lookup_artifact — read a specific artifact file by canonical name

All four are **deterministic** (no LLM under the hood). The PWM moat —
the Physics Judge as the source of verdict — is preserved: the agent
can call pwm_judge_cassi, but it cannot override the judge's output.

The implementations are kept as module-level async functions so they
can be unit-tested without spinning up a real MCP transport. The
``@tool``-decorated views are built inside :func:`build_pwm_mcp_server`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

try:
    from claude_agent_sdk import create_sdk_mcp_server, tool   # type: ignore
    _HAVE_SDK = True
except Exception:
    _HAVE_SDK = False
    create_sdk_mcp_server = None   # type: ignore
    tool = None                    # type: ignore


def _resolve_workspace(spec: str) -> Path:
    """Resolve the agent-supplied workspace arg under the current cwd."""
    p = Path(spec)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


# ─── Tool implementations (module-level — testable without transport) ─


async def pwm_validate(args: Dict[str, Any]) -> Dict[str, Any]:
    """Run the deterministic ai4science validator on the workspace."""
    from ai4science.commands.validate import _validate_one
    ws = _resolve_workspace(args.get("workspace", "."))
    per_file: List[Dict[str, str]] = []
    overall_ok = True
    for fname in ("principle.md", "spec.md", "benchmark.md", "solution.md"):
        path = ws / fname
        if not path.exists():
            per_file.append({"file": fname, "status": "absent"})
            continue
        status_md, atype, errs, warnings = _validate_one(path)
        status = "ok" if "ok" in status_md else "fail"
        if status != "ok":
            overall_ok = False
        per_file.append({
            "file": fname, "artifact_type": atype, "status": status,
            "errors": errs, "warnings": warnings,
        })
    return {
        "content": [{
            "type": "text",
            "text": json.dumps({"overall": "ok" if overall_ok else "fail",
                                 "files": per_file}, indent=2),
        }],
    }


async def pwm_judge_cassi(args: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke the CASSI Physics Judge (deterministic) on a workspace."""
    from ai4science.judge.cassi import judge_cassi
    ws = _resolve_workspace(args.get("workspace", "."))
    report = judge_cassi(ws)
    return {"content": [{"type": "text", "text": json.dumps(report, indent=2)}]}


async def pwm_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """Return workspace status: artifacts present, dirs, reports, config."""
    from ai4science.schemas import parse_front_matter
    import yaml

    ws = _resolve_workspace(args.get("workspace", "."))
    info: Dict[str, Any] = {"workspace": str(ws), "artifacts": {}, "dirs": {}, "reports": []}

    for fname in ("principle.md", "spec.md", "benchmark.md", "solution.md"):
        path = ws / fname
        if not path.exists():
            info["artifacts"][fname] = {"present": False}
            continue
        data, err = parse_front_matter(path)
        if err:
            info["artifacts"][fname] = {"present": True, "broken": err}
        else:
            info["artifacts"][fname] = {
                "present": True,
                "artifact_type": data.get("artifact_type"),
                "name": data.get("name"),
            }

    for d in ("data", "code", "results", "reports"):
        dpath = ws / d
        info["dirs"][d] = (
            {"present": True, "entries": len(list(dpath.iterdir()))}
            if dpath.exists() else {"present": False}
        )

    reports_dir = ws / "reports"
    if reports_dir.exists():
        info["reports"] = sorted(p.name for p in reports_dir.iterdir() if p.is_file())

    cfg_path = ws / ".ai4science" / "config.yaml"
    if cfg_path.exists():
        try:
            info["config"] = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            info["config_error"] = str(e)

    return {"content": [{"type": "text", "text": json.dumps(info, indent=2)}]}


async def pwm_lookup_artifact(args: Dict[str, Any]) -> Dict[str, Any]:
    """Read one PWM artifact file by canonical name; return raw + parsed."""
    from ai4science.schemas import parse_front_matter
    artifact = args.get("artifact", "").lower()
    if artifact not in ("principle", "spec", "benchmark", "solution"):
        return {"content": [{
            "type": "text",
            "text": f"error: unknown artifact {artifact!r}; expected one of "
                    f"principle/spec/benchmark/solution",
        }], "isError": True}

    ws = _resolve_workspace(args.get("workspace", "."))
    path = ws / f"{artifact}.md"
    if not path.exists():
        return {"content": [{
            "type": "text", "text": f"error: {path.name} not present in workspace",
        }], "isError": True}

    data, err = parse_front_matter(path)
    body = path.read_text(encoding="utf-8")
    payload: Dict[str, Any] = {
        "path": str(path),
        "front_matter": data if err is None else None,
        "parse_error": err,
        "raw_text": body if len(body) <= 16_000 else body[:16_000] + "\n[...truncated]",
    }
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}]}


# ─── SDK-decorated tool views + server build ─────────────────────────


def build_pwm_mcp_server():
    """Construct the PWM MCP server. Returns None if the SDK is unavailable."""
    if not _HAVE_SDK:
        return None

    # Wrap each implementation in the @tool decorator at construction time.
    _validate_tool = tool(
        "pwm_validate",
        "Run the deterministic ai4science validator on the workspace and "
        "return a structured report. No LLM involved — this is the canonical "
        "schema check. Use BEFORE proposing a submission is complete.",
        {
            "type": "object",
            "properties": {
                "workspace": {
                    "type": "string",
                    "description": "Workspace directory (relative to cwd). Default '.'.",
                    "default": ".",
                },
            },
            "required": [],
        },
    )(pwm_validate)

    _judge_tool = tool(
        "pwm_judge_cassi",
        "Run the deterministic CASSI Physics Judge (S1-S4 + silent-failure "
        "detector) on the workspace. Returns the same JSON as "
        "reports/judge_report.json. Use this whenever you've finished "
        "proposing edits — the judge is the SOURCE OF TRUTH, not you.",
        {
            "type": "object",
            "properties": {"workspace": {"type": "string", "default": "."}},
            "required": [],
        },
    )(pwm_judge_cassi)

    _status_tool = tool(
        "pwm_status",
        "Return workspace status: which artifact files are present, what "
        "reports have been generated, and what the .ai4science/config.yaml "
        "declares for judge_domain and agent_provider.",
        {
            "type": "object",
            "properties": {"workspace": {"type": "string", "default": "."}},
            "required": [],
        },
    )(pwm_status)

    _lookup_tool = tool(
        "pwm_lookup_artifact",
        "Read one PWM artifact file by canonical name (principle / spec / "
        "benchmark / solution) and return its full content. Cheaper than the "
        "agent calling Read+parse separately; also returns the YAML front "
        "matter as parsed JSON for convenience.",
        {
            "type": "object",
            "properties": {
                "artifact": {
                    "type": "string",
                    "enum": ["principle", "spec", "benchmark", "solution"],
                },
                "workspace": {"type": "string", "default": "."},
            },
            "required": ["artifact"],
        },
    )(pwm_lookup_artifact)

    return create_sdk_mcp_server(
        name="pwm",
        version="0.1.0",
        tools=[_validate_tool, _judge_tool, _status_tool, _lookup_tool],
    )


# Convenience: the tool names the agent will see (mcp__<server>__<tool>).
PWM_MCP_TOOL_NAMES: List[str] = [
    "mcp__pwm__pwm_validate",
    "mcp__pwm__pwm_judge_cassi",
    "mcp__pwm__pwm_status",
    "mcp__pwm__pwm_lookup_artifact",
]
