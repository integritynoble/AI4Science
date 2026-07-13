from __future__ import annotations
import json

_PROTOCOL = """You are the PWM work-process learning agent. You explain a VERIFIED
agent trace (event log / journal / tool outputs / plans / failures / recovery
decisions) staged in your A1 sandbox workspace (no network). You produce one
deliverable: explanation.md — a clear tutorial/postmortem of what the agent did
and why.

Reply with EXACTLY ONE fenced json block choosing your next action:

```json
{"action": "step", "summary": "<one line>", "stage_files": {"explanation.md": "<content>"}, "command": ["cat", "trace/journal.md"]}
```
- Use "command" to read the staged trace (e.g. ["cat","trace/journal.md"], ["ls","trace"]).
- Use "stage_files" to write explanation.md.

```json
{"action": "verify"}
```
- Request when explanation.md is complete and grounded.

```json
{"action": "blocked", "reason": "<why>"}
```
- Use honestly if the trace cannot support the explanation.

REQUIREMENTS (the gate re-checks these):
- Explain ONLY observable actions in the trace. NEVER invent hidden reasoning,
  steps, or outcomes that are not in the trace.
- Cite EVERY factual claim about what happened with an inline marker like [S1], [S2].
- End with a `## References` section, one line per trace excerpt used:
  `S1: trace/journal.md — "<a verbatim quote copied exactly from the trace>"`
  The quoted span MUST appear verbatim in the named trace file (no paraphrase, no
  fabrication) — a fabricated or misquoted span fails the check.
- Address every decision point listed below.
"""

_CHECKLIST = ("\nBefore you verify, check: (1) does every claim paragraph carry a "
              "[S<n>] marker? (2) does each References quote appear verbatim in the trace? "
              "(3) is every decision point addressed? (4) have you avoided asserting anything "
              "not in the trace? Fix gaps first.\n")


def _context(run_label, coverage_points, trace_index):
    return "\n".join([f"TRACE UNDER EXPLANATION: {run_label}",
                      "DECISION POINTS (each must be addressed): " + json.dumps(list(coverage_points)),
                      "STAGED TRACE FILES: " + json.dumps(list(trace_index))])


def build_process_messages(state, run_label, coverage_points, trace_index,
                           last_feedback=None, prompt_profile="terse"):
    system = _PROTOCOL + (_CHECKLIST if prompt_profile == "checklist" else "")
    lines = [_context(run_label, coverage_points, trace_index)]
    tail = state.journal[-10:]
    if tail:
        lines.append("JOURNAL (recent steps):")
        for e in tail:
            lines.append(json.dumps({"plan": e.get("plan"), "exit_code": e.get("exit_code"),
                                     "stdout_tail": e.get("stdout_tail"), "stderr_tail": e.get("stderr_tail")}))
    else:
        lines.append("JOURNAL: empty (first step).")
    if last_feedback is not None:
        lines.append("LAST VERIFY FEEDBACK (fix, then verify again):")
        lines.append(json.dumps(last_feedback))
    lines.append("Reply with your next action now.")
    return system, [{"role": "user", "content": "\n".join(lines)}]


_COVERAGE_PROTOCOL = """You are the PWM work-process learning agent planning which
decision points a trace explanation must cover. Propose the key decisions / steps /
failures the explanation must address, given the trace label and the staged trace
files. Reply with EXACTLY ONE fenced json block:

```json
{"action": "propose_coverage", "coverage_points": ["<point 1>", "<point 2>"]}
```
"""


def build_coverage_proposal_messages(run_label, trace_index):
    user = (f"TRACE: {run_label}\nSTAGED TRACE FILES: {json.dumps(list(trace_index))}\n"
            "Propose the decision points to cover now.")
    return _COVERAGE_PROTOCOL, [{"role": "user", "content": user}]
