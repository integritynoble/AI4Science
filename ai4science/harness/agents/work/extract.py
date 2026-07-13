from __future__ import annotations
import json
import re
from dataclasses import dataclass, field

_FENCED = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


@dataclass
class WorkAction:
    action: str                      # "step" | "propose_criteria" | "verify" | "blocked"
    summary: str = ""
    stage_files: dict = field(default_factory=dict)
    command: list = field(default_factory=list)
    verify_commands: list = field(default_factory=list)
    required_artifacts: list = field(default_factory=list)
    reason: str = ""


def _valid_step(data: dict) -> WorkAction | None:
    summary = data.get("summary")
    stage_files = data.get("stage_files") or {}
    command = data.get("command") or []
    if not isinstance(summary, str) or not summary:
        return None
    if not isinstance(stage_files, dict) or not all(
            isinstance(k, str) and k and isinstance(v, str)
            for k, v in stage_files.items()):
        return None
    if not isinstance(command, list) or not all(
            isinstance(a, str) and a for a in command):
        return None
    if not stage_files and not command:
        return None
    return WorkAction("step", summary=summary, stage_files=stage_files, command=command)


def _valid_propose(data: dict) -> WorkAction | None:
    vcs = data.get("verify_commands") or []
    arts = data.get("required_artifacts") or []
    if not isinstance(vcs, list) or not all(
            isinstance(c, list) and c and all(isinstance(a, str) and a for a in c)
            for c in vcs):
        return None
    if not isinstance(arts, list) or not all(isinstance(a, str) and a for a in arts):
        return None
    if not vcs and not arts:
        return None
    return WorkAction("propose_criteria", verify_commands=vcs, required_artifacts=arts)


def parse_work_action(text) -> WorkAction | None:
    """Parse the first schema-valid fenced ```json action block; None if none."""
    for m in _FENCED.finditer(text or ""):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        action = data.get("action")
        if action == "step":
            parsed = _valid_step(data)
        elif action == "propose_criteria":
            parsed = _valid_propose(data)
        elif action == "verify":
            parsed = WorkAction("verify")
        elif action == "blocked":
            parsed = WorkAction("blocked", reason=str(data.get("reason", "")))
        else:
            parsed = None
        if parsed is not None:
            return parsed
    return None
