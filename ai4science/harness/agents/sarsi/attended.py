"""The record an *attended* session leaves, for the two readers that need one.

`blast` and `spend` were both written against Claude Code's transcript, because
the first spec that ran was `claude-code`. Four of the seven agents — `social`,
`funding`, `jobs`, `abraham` — run the ai4science TUI instead, which writes no
such transcript, so three live runs in a row ended on the same two lines:

    blast: no record of what it touched — the transcript could not be read
    spend: tokens: not recorded

Honest, and useless: more than half the fleet was unmeasurable. Nothing was
missing, only unjoined. The harness already persists a session per workspace
with its tool calls, and the meter already writes every metered call to the LLM
ledger. This module reads those two and hands each reader the shape it expects.

Two rules it inherits rather than invents:

  * **unknown is not zero.** No session for this directory *raises*. A reader
    that cannot find a record must keep saying so; a fallback that returned `[]`
    would turn "we have no idea" into "it touched nothing, and it cost nothing",
    which is the confident wrong these two modules exist to avoid.
  * **a relative path is resolved where it was written.** The harness records
    `path: outline.md` and opens it as `workspace / path`. Left relative it
    would resolve against whatever directory the *reader* happens to be in, and
    a file written safely inside the task folder could be reported as an escape.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

#: harness tool name → the name `blast` classifies by. Its `_WRITERS` and
#: `_OPAQUE` are spelled in Claude Code's vocabulary; this is the same set of
#: acts under different names, so the mapping lives here and neither reader
#: learns a second vocabulary.
_AS = {"write": "Write", "edit": "Edit", "read": "Read",
       "bash": "Bash", "glob": "Glob", "grep": "Grep"}


def sessions_dir() -> Path:
    """Where the harness keeps them. Resolved per call, never cached — the path
    hangs off `HOME`, and a worker reads another account's records."""
    from ai4science import user
    return user.config_path().parent / "sessions"


def session_id(cwd: str) -> Optional[str]:
    """The harness session that ran in this directory, or `None`.

    `index.json` maps a resolved workspace to its session id — the same lookup
    the harness itself does when it resumes.
    """
    index = sessions_dir() / "index.json"
    try:
        table = json.loads(index.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    try:
        key = str(Path(cwd).expanduser().resolve())
    except OSError:
        key = str(cwd)
    found = table.get(key) or table.get(str(cwd))
    return str(found) if found else None


def _records(session: str) -> List[Dict[str, Any]]:
    path = sessions_dir() / f"{session}.jsonl"
    out: List[Dict[str, Any]] = []
    try:
        handle = open(path, errors="replace")
    except OSError:
        return out
    with handle:
        for line in handle:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue          # a damaged line loses itself, never the rest
    return out


# ── for `blast` ───────────────────────────────────────────────────────

def acts(cwd: str) -> List[Dict[str, Any]]:
    """Every tool call the attended session made, in `blast`'s shape.

    Raises when there is no session to read, so "touched nothing" stays
    distinguishable from "we have no idea what it touched".
    """
    session = session_id(cwd)
    if not session:
        raise FileNotFoundError(f"no ai4science session recorded for {cwd}")
    root = Path(cwd).expanduser()
    out: List[Dict[str, Any]] = []
    for record in _records(session):
        for call in (record.get("tool_calls") or []):
            if not isinstance(call, dict):
                continue
            args = call.get("arguments")
            args = args if isinstance(args, dict) else {}
            entry: Dict[str, Any] = {
                "name": _AS.get(str(call.get("name") or ""),
                                str(call.get("name") or "")),
                "input": dict(args),
            }
            path = args.get("path")
            if path:
                # `workspace / path` — exactly how the tool opened it
                entry["input"]["file_path"] = str(
                    Path(path) if Path(path).is_absolute() else root / path)
            out.append(entry)
    return out


# ── for `spend` ───────────────────────────────────────────────────────

def metered(cwd: str) -> List[Dict[str, Any]]:
    """Every metered call attributed to this session, in `spend`'s shape.

    The ledger records tokens and PWM but no cache figures — the harness does
    not report them — so those keys are absent rather than zero, and `spend`
    prints a cache line only for the sessions that have one.
    """
    session = session_id(cwd)
    if not session:
        raise FileNotFoundError(f"no ai4science session recorded for {cwd}")
    from ai4science.llm import ledger

    out: List[Dict[str, Any]] = []
    for entry in ledger.load():
        if str(entry.get("session") or "") != session:
            continue
        out.append({"input_tokens": int(entry.get("input_tokens") or 0),
                    "output_tokens": int(entry.get("output_tokens") or 0),
                    "pwm": float(entry.get("pwm") or 0.0)})
    return out
