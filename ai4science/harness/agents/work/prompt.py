from __future__ import annotations
import json

JOURNAL_TAIL = 10

_PROTOCOL = """You are the PWM general work agent. You complete verifiable tasks
(coding, data analysis, file transformations) inside an isolated A1 sandbox:
no network, no credentials, workspace-relative paths only. Files you write and
commands you run all happen in the run workspace.

Reply with EXACTLY ONE fenced json block choosing your next action:

```json
{"action": "step", "summary": "<one line>", "stage_files": {"<rel_path>": "<full file content>"}, "command": ["<argv0>", "<arg1>"]}
```
- "stage_files" writes files into the workspace (optional); "command" runs one
  argv-style command in the sandbox (optional); include at least one of them.
- Work in small steps. Inspect files by running commands (e.g. ["ls", "-la"],
  ["cat", "calc.py"]) and reading the output in the journal next turn.

```json
{"action": "verify"}
```
- Request this when you believe the success criteria below now pass. The
  control plane re-runs the verify commands itself; you cannot skip this gate.

```json
{"action": "blocked", "reason": "<why you cannot proceed>"}
```
- Use this honestly when the task cannot be completed. Never fake success.
"""


def _criteria_text(criteria: dict) -> str:
    return ("SUCCESS CRITERIA (delivery gate, verified by the control plane):\n"
            f"verify_commands: {json.dumps(criteria.get('verify_commands', []))}\n"
            f"required_artifacts: {json.dumps(criteria.get('required_artifacts', []))}\n")


def build_work_messages(state, criteria: dict, last_feedback=None):
    """-> (system, messages) for an Anthropic Messages request via /llm_egress."""
    system = _PROTOCOL + "\n" + _criteria_text(criteria)
    lines = [f"OBJECTIVE: {state.contract.objective}"]
    if state.contract.constraints:
        lines.append("CONSTRAINTS: " + "; ".join(state.contract.constraints))
    tail = state.journal[-JOURNAL_TAIL:]
    if tail:
        lines.append(f"JOURNAL (last {len(tail)} steps, oldest first):")
        for e in tail:
            lines.append(json.dumps({
                "plan": e.get("plan"), "failed": e.get("failed"),
                "exit_code": e.get("exit_code"),
                "stdout_tail": e.get("stdout_tail"), "stderr_tail": e.get("stderr_tail"),
            }))
    else:
        lines.append("JOURNAL: empty (this is your first step).")
    if last_feedback is not None:
        lines.append("LAST VERIFY FEEDBACK (fix these, then verify again):")
        lines.append(json.dumps(last_feedback))
    lines.append("Reply with your next action now.")
    return system, [{"role": "user", "content": "\n".join(lines)}]


_CRITERIA_PROTOCOL = """You are the PWM general work agent preparing a task's
success criteria. Propose objective, machine-checkable criteria for the task:
shell commands that must exit 0 in the sandbox (no network available) and/or
workspace-relative artifact paths that must exist. Reply with EXACTLY ONE
fenced json block:

```json
{"action": "propose_criteria", "verify_commands": [["<argv0>", "<arg1>"]], "required_artifacts": ["<rel_path>"]}
```
"""


def build_criteria_messages(objective: str, input_files: list):
    user = (f"OBJECTIVE: {objective}\n"
            f"INPUT FILES STAGED IN THE WORKSPACE: {json.dumps(list(input_files))}\n"
            "Propose the success criteria now.")
    return _CRITERIA_PROTOCOL, [{"role": "user", "content": user}]
