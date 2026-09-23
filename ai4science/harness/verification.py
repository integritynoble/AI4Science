"""What the harness itself can say about a turn's verification (ticket U05).

The model reports; the harness records. Every `bash` call that looks like a
test or check runner is logged with the exit code the shell tool appended,
and after the turn the harness prints its own line from that log — never
from the model's prose. Two cases are called out:

  * a check ran and failed, timed out or was interrupted → shown with its
    exit status, so a summary that says "done" sits under a line that says
    "✗ pytest … exit 1";
  * the final text claims tests pass/are green and NO check ran this turn →
    a warning that nothing was run.

This is deterministic and cheap. It does not judge whether the right tests
ran, only whether what the text claims has a run behind it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

_RUNNER = re.compile(
    r"(?:^|[\s;&|(])(?:python[0-9.]*\s+-m\s+)?"
    r"(?:pytest|unittest|tox|nox|npm\s+test|yarn\s+test|pnpm\s+test|make\s+(?:test|check)|"
    r"cargo\s+test|go\s+test|mvn\s+test|gradle\s+test|ctest|rspec|jest|vitest|mocha)"
    r"(?=\s|$|[;&|)])")
_EXIT = re.compile(r"\(exit code (-?\d+)\)\s*$")
_TIMED_OUT = "(timed out after"
_INTERRUPTED = "(interrupted by user)"
_CLAIM = re.compile(
    r"\b(?:all\s+)?(?:tests?|test\s+suite|suite|checks?|specs?)\b[^.\n]{0,60}?"
    r"\b(?:pass(?:es|ed|ing)?|green|succeed(?:s|ed)?|ok)\b", re.I)


@dataclass(frozen=True)
class Check:
    cmd: str
    status: str          # "passed" | "failed" | "timed out" | "interrupted"
    exit_code: Optional[int]

    @property
    def ok(self) -> bool:
        return self.status == "passed"


def is_check_command(cmd: str) -> bool:
    return bool(_RUNNER.search(cmd or ""))


def classify(cmd: str, result: str) -> Optional[Check]:
    """A Check for a bash call that ran a test runner, else None."""
    if not is_check_command(cmd):
        return None
    tail = (result or "").rstrip()
    if _INTERRUPTED in tail:
        return Check(cmd, "interrupted", None)
    if _TIMED_OUT in tail:
        return Check(cmd, "timed out", None)
    m = _EXIT.search(tail)
    if m:
        code = int(m.group(1))
        return Check(cmd, "failed" if code != 0 else "passed", code)
    if tail.startswith("[blocked]") or tail.startswith("[error]") \
            or tail.startswith("(failed to start"):
        return Check(cmd, "failed", None)
    return Check(cmd, "passed", 0)


def claims_passing(text: str) -> bool:
    return bool(_CLAIM.search(text or ""))


def _short(cmd: str, width: int = 70) -> str:
    cmd = " ".join(cmd.split())
    return cmd if len(cmd) <= width else cmd[: width - 1] + "…"


def summarize(checks: List[Check], final_text: str) -> Optional[str]:
    """The harness's own line about this turn, or None when there is nothing
    worth saying (checks all passed and the text made no claim beyond them, or
    no checks and no claim)."""
    if checks:
        bad = [c for c in checks if not c.ok]
        if bad:
            lines = []
            for c in bad:
                status = c.status if c.exit_code is None else f"exit {c.exit_code}"
                lines.append(f"✗ {_short(c.cmd)} ({status})")
            head = "checks this turn did not all pass — do not treat the work as verified:"
            return head + "\n  " + "\n  ".join(lines)
        return None
    if claims_passing(final_text):
        return ("⚠ the answer says tests/checks pass, but no test command ran this "
                "turn — nothing was verified")
    return None
