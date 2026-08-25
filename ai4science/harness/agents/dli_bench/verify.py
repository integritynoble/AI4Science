"""Verification, and the rule that makes it mean anything.

    The thing that decides whether a task succeeded is never the thing that
    performed it.

Enforced structurally rather than asked for. Every task is built into two
directories: a **work** directory, which is all the agent ever sees, and a
**keyed** directory, which holds the ground truth and is never staged. Scoring
runs in this process, against the keyed copy, using code the agent could not
have written. An agent that cannot read the answer cannot copy it into its own
output and pass a reference-free judge.

The second rule is that a verifier states what it misses. ``Verdict.note`` is
required and ``false_pass`` may be ``None`` only when the verifier genuinely has
no estimate -- which is common, and is the reason the field exists: to make the
absence visible rather than to pretend the number is one.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class Verdict:
    passed: bool
    metrics: Dict[str, float]
    reasons: Tuple[str, ...]
    #: What this check establishes, and what it cannot. Required.
    note: str
    #: Estimated probability the check passes a result that is actually wrong.
    #: None means unknown, which is honest and common.
    false_pass: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.note:
            raise ValueError("a verdict must say what its check does not cover")

    def report(self) -> str:
        L = ["verdict: %s" % ("PASS" if self.passed else "FAIL")]
        for k, v in sorted(self.metrics.items()):
            L.append("  %-24s %.6g" % (k, v))
        for r in self.reasons:
            L.append("  - %s" % r)
        fp = "unknown" if self.false_pass is None else "%.3g" % self.false_pass
        L.append("  false-pass rate: %s" % fp)
        L.append("  covers: %s" % self.note)
        return "\n".join(L)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def missing(work: Path, *names: str) -> Tuple[str, ...]:
    return tuple(n for n in names if not (work / n).exists())


def run_hidden_tests(work: Path, keyed: Path, test_file: str,
                     timeout: int = 120) -> Tuple[bool, str]:
    """Run a test file that lives in the keyed directory against the agent's work.

    The test is copied in at scoring time and deleted afterwards, so it is never
    present while the agent runs. An agent that can see the test can satisfy it
    without satisfying the task -- which is the difference between passing and
    being right.
    """
    src = keyed / test_file
    if not src.exists():
        return False, "hidden test %s is missing from the keyed directory" % test_file
    dst = work / ("_hidden_%s" % test_file)
    dst.write_bytes(src.read_bytes())
    try:
        import shutil as _sh
        py = sys.executable if not getattr(sys, "frozen", False) else (
            _sh.which("python3") or _sh.which("python") or sys.executable)
        r = subprocess.run(
            [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(dst)],
            cwd=str(work), capture_output=True, text=True, timeout=timeout)
        tail = (r.stdout or "")[-1500:] + (r.stderr or "")[-500:]
        return r.returncode == 0, tail
    except subprocess.TimeoutExpired:
        return False, "hidden tests timed out after %ds" % timeout
    finally:
        dst.unlink(missing_ok=True)
        for junk in work.glob("__pycache__"):
            pass
