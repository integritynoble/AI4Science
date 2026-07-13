"""Deterministic quiz-authoring gate for the personal-learning agent.

Runs inside the A1 sandbox as the registered verify command
(`python3 -I quiz_check.py --config <json>`); the control plane re-runs it, so
the agent cannot forge the verdict. Trusted config (source SHA-256s,
min_questions, coverage points) rides the CP-private argv the sandbox never
mounts. Stdlib only; NO ai4science import.

Gates delivery on:
  * integrity -- each source's on-disk SHA matches the config (anti-tamper);
  * structure -- quiz.json parses; >= min_questions; each question well-formed
                 (unique id, type mcq/short, prompt, answer, grounding; mcq has
                 >=2 options and a valid answer key);
  * grounding -- each question's grounding span appears VERBATIM in an
                 integrity-verified source (anti-hallucinated assessment item);
  * coverage  -- every coverage point is addressed in the study guide.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

_TYPES = {"mcq", "short"}


def _norm(text: str) -> str:
    return " ".join(text.split())


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _valid_question(q, sources_norm) -> str | None:
    """Return an error reason, or None if the question is valid + grounded."""
    if not isinstance(q, dict):
        return "question is not an object"
    qid = q.get("id")
    if not isinstance(qid, str) or not qid:
        return "question missing id"
    if q.get("type") not in _TYPES:
        return f"question {qid!r} has bad type"
    if not isinstance(q.get("prompt"), str) or not q["prompt"].strip():
        return f"question {qid!r} missing prompt"
    answer = q.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        return f"question {qid!r} missing answer"
    grounding = q.get("grounding")
    if not isinstance(grounding, str) or not grounding.strip():
        return f"question {qid!r} missing grounding"
    if q["type"] == "mcq":
        options = q.get("options")
        if not isinstance(options, dict) or len(options) < 2:
            return f"question {qid!r} needs >=2 options"
        if answer not in options:
            return f"question {qid!r} answer is not an option key"
    # grounding must be verbatim in some integrity-verified source
    span = _norm(grounding)
    if not any(span in body for body in sources_norm.values()):
        return f"question {qid!r} grounding not found verbatim in any source"
    # grounding must actually support the answer (not just be a real-but-irrelevant span)
    if q["type"] == "mcq":
        options = q.get("options", {})
        option_text = _norm(str(options.get(answer, "")))
        if not option_text or option_text not in span:
            return f"question {qid!r} answer not supported by grounding"
    else:  # short
        answer_text = _norm(answer)
        if not answer_text or answer_text not in span:
            return f"question {qid!r} answer not supported by grounding"
    return None


def check_quiz(workspace, config: dict) -> dict:
    ws = Path(workspace)
    sources = dict(config.get("sources", {}))
    min_q = int(config.get("min_questions", 1))
    coverage = list(config.get("coverage_points", []))
    guide_name = config.get("study_guide", "study_guide.md")
    quiz_name = config.get("quiz", "quiz.json")

    # integrity
    sources_norm = {}
    for rel, expected in sources.items():
        try:
            if sha256_file(ws / rel) != expected:
                return {"ok": False, "reason": f"integrity: source {rel!r} was tampered with"}
            sources_norm[rel] = _norm((ws / rel).read_text())
        except (OSError, UnicodeDecodeError):
            return {"ok": False, "reason": f"integrity: source {rel!r} unreadable"}

    # study guide
    guide_path = ws / guide_name
    if not guide_path.is_file():
        return {"ok": False, "reason": f"missing or empty {guide_name!r}"}
    try:
        guide = guide_path.read_text()
    except (OSError, UnicodeDecodeError):
        return {"ok": False, "reason": f"{guide_name!r} unreadable"}
    if not guide.strip():
        return {"ok": False, "reason": f"missing or empty {guide_name!r}"}

    # quiz structure
    quiz_path = ws / quiz_name
    if not quiz_path.is_file():
        return {"ok": False, "reason": f"missing {quiz_name!r}"}
    try:
        quiz = json.loads(quiz_path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"ok": False, "reason": "quiz.json is not valid JSON"}
    questions = quiz.get("questions") if isinstance(quiz, dict) else None
    if not isinstance(questions, list) or len(questions) < min_q:
        return {"ok": False, "reason": f"structure: fewer than {min_q} questions"}
    seen = set()
    for q in questions:
        reason = _valid_question(q, sources_norm)
        if reason:
            key = "grounding" if "grounding" in reason else "structure"
            return {"ok": False, "reason": f"{key}: {reason}"}
        if q["id"] in seen:
            return {"ok": False, "reason": f"structure: duplicate question id {q['id']!r}"}
        seen.add(q["id"])

    # coverage (in the study guide)
    guide_lines = [_norm(l).lower() for l in guide.splitlines() if l.strip()]
    for point in coverage:
        toks = [t for t in re.findall(r"[a-z0-9]+", point.lower()) if len(t) > 3]
        if toks and not any(all(t in line for t in toks) for line in guide_lines):
            return {"ok": False, "reason": f"coverage: point not addressed: {point!r}"}

    return {"ok": True, "reason": "grounded"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--workspace", default=".")
    args = ap.parse_args()
    try:
        config = json.loads(args.config)
    except json.JSONDecodeError:
        sys.stderr.write("invalid --config json\n")
        return 1
    result = check_quiz(Path(args.workspace), config)
    if not result["ok"]:
        sys.stderr.write(result["reason"] + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
