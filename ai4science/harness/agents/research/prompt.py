from __future__ import annotations
import json

_PROTOCOL = """You are the PWM research agent. You answer a research question
using ONLY the source documents staged in your A1 sandbox workspace (no
network). Work in the workspace: read the sources under sources/ with shell
commands, then write report.md.

Reply with EXACTLY ONE fenced json block choosing your next action:

```json
{"action": "step", "summary": "<one line>", "stage_files": {"report.md": "<full content>"}, "command": ["cat", "sources/a.txt"]}
```
- Use "command" to read sources (e.g. ["cat","sources/a.txt"], ["ls","sources"]).
- Use "stage_files" to write report.md.

```json
{"action": "verify"}
```
- Request when report.md is complete and grounded.

```json
{"action": "blocked", "reason": "<why>"}
```
- Use honestly if the sources cannot answer the question.

REQUIREMENTS for report.md (the grounding gate re-checks these):
- Cite EVERY substantial claim with an inline marker like [S1], [S2].
- End with a `## References` section, one line per source used:
  `S1: sources/a.txt — "<a verbatim quote copied exactly from that source>"`
  The quoted span MUST appear verbatim in the named source (no paraphrase, no
  fabrication) — a fabricated quote fails the check.
- Address every coverage point listed below.
- State uncertainty honestly instead of inventing support.
"""

_CHECKLIST = ("\nBefore you verify, walk a checklist: (1) does every claim "
              "paragraph carry a [S<n>] marker? (2) does each References quote appear "
              "verbatim in its source? (3) is every coverage point addressed? Fix gaps first.\n")


def _context(question, coverage_points, sources_index):
    lines = [f"QUESTION: {question}",
             "COVERAGE POINTS (each must be addressed): " + json.dumps(list(coverage_points)),
             "STAGED SOURCE FILES: " + json.dumps(list(sources_index))]
    return "\n".join(lines)


def build_research_messages(state, question, coverage_points, sources_index,
                            last_feedback=None, prompt_profile="terse"):
    system = _PROTOCOL + (_CHECKLIST if prompt_profile == "checklist" else "")
    lines = [_context(question, coverage_points, sources_index)]
    tail = state.journal[-10:]
    if tail:
        lines.append("JOURNAL (recent steps):")
        for e in tail:
            lines.append(json.dumps({"plan": e.get("plan"), "exit_code": e.get("exit_code"),
                                     "stdout_tail": e.get("stdout_tail"),
                                     "stderr_tail": e.get("stderr_tail")}))
    else:
        lines.append("JOURNAL: empty (first step).")
    if last_feedback is not None:
        lines.append("LAST VERIFY FEEDBACK (fix, then verify again):")
        lines.append(json.dumps(last_feedback))
    lines.append("Reply with your next action now.")
    return system, [{"role": "user", "content": "\n".join(lines)}]


_COVERAGE_PROTOCOL = """You are the PWM research agent planning a research
question's coverage. Propose the key sub-questions/points the report must
address, given the question and the staged sources. Reply with EXACTLY ONE
fenced json block:

```json
{"action": "propose_coverage", "coverage_points": ["<point 1>", "<point 2>"]}
```
"""


def build_coverage_proposal_messages(question, sources_index):
    user = (f"QUESTION: {question}\nSTAGED SOURCE FILES: {json.dumps(list(sources_index))}\n"
            "Propose the coverage points now.")
    return _COVERAGE_PROTOCOL, [{"role": "user", "content": user}]
