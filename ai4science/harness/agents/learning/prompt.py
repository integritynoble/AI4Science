from __future__ import annotations
import json

_PROTOCOL = """You are the PWM personal-learning agent (tutor). You teach a topic
from the source material staged in your A1 sandbox workspace (no network) by
producing two deliverables: study_guide.md and quiz.json.

Reply with EXACTLY ONE fenced json block choosing your next action:

```json
{"action": "step", "summary": "<one line>", "stage_files": {"study_guide.md": "<content>", "quiz.json": "<json content>"}, "command": ["cat", "material/m.txt"]}
```
- Use "command" to read the staged material (e.g. ["cat","material/m.txt"]).
- Use "stage_files" to write study_guide.md and quiz.json.

```json
{"action": "verify"}
```
- Request when both deliverables are complete and grounded.

```json
{"action": "blocked", "reason": "<why>"}
```
- Use honestly if the material cannot support a quiz on the topic.

REQUIREMENTS (the gate re-checks these):
- study_guide.md: a concise study guide addressing every coverage point below.
- quiz.json: {"topic": "...", "questions": [ ... ]} with >= the required number of
  questions. Each question is an object:
    {"id": "q1", "type": "mcq", "prompt": "...", "options": {"A":"...","B":"..."},
     "answer": "B", "grounding": "<a verbatim quote from the material that supports the answer>"}
  or  {"id": "q2", "type": "short", "prompt": "...", "answer": "...",
     "grounding": "<verbatim quote>"}
  The "grounding" span MUST appear verbatim in the staged material (no paraphrase,
  no fabrication) — a fabricated grounding fails the check. MCQ "answer" must be
  one of the option keys.
- Do not invent facts; ground every answer in the material.
"""

_CHECKLIST = ("\nBefore you verify, check: (1) >= the required number of questions? "
              "(2) does every question's grounding quote appear verbatim in the material? "
              "(3) is each MCQ answer a valid option key? (4) is every coverage point in "
              "the study guide? Fix gaps first.\n")


def _context(topic, coverage_points, sources_index):
    return "\n".join([f"TOPIC: {topic}",
                      "COVERAGE POINTS (each must be in the study guide): " + json.dumps(list(coverage_points)),
                      "STAGED MATERIAL FILES: " + json.dumps(list(sources_index))])


def build_learning_messages(state, topic, coverage_points, sources_index,
                            last_feedback=None, prompt_profile="terse"):
    system = _PROTOCOL + (_CHECKLIST if prompt_profile == "checklist" else "")
    lines = [_context(topic, coverage_points, sources_index)]
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


_COVERAGE_PROTOCOL = """You are the PWM personal-learning agent planning a topic's
coverage. Propose the key points a study guide + quiz must cover, given the topic
and the staged material. Reply with EXACTLY ONE fenced json block:

```json
{"action": "propose_coverage", "coverage_points": ["<point 1>", "<point 2>"]}
```
"""


def build_coverage_proposal_messages(topic, sources_index):
    user = (f"TOPIC: {topic}\nSTAGED MATERIAL FILES: {json.dumps(list(sources_index))}\n"
            "Propose the coverage points now.")
    return _COVERAGE_PROTOCOL, [{"role": "user", "content": user}]
