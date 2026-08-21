"""Deterministic phase verifier — criterion text → shell check → PASS/FAIL.

Parses `Verified when:` text and runs the corresponding deterministic check
without an LLM call. Falls through to `UNVERIFIED` when no deterministic check
can be inferred from the criterion — the caller should then invoke the LLM
verifier.

The worker runs checks but **never writes** to the task workspace. Every check
here is read-only: exit-code tests, file existence, git status, grep. The
working directory for all checks is `work_dir` (the task's declared `work_root`
or its own folder).

Independence note: `deterministic=True` in the returned verdict means the
result is a code check, not a model call. It is independent of the executor's
self-report in a stronger sense than the LLM verifier — the executor cannot
talk its way into a deterministic PASS.

Return shape: {"state": "PASS"|"FAIL"|"UNVERIFIED", "why": str,
               "deterministic": bool, "check": str}
"""
from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

PASS = "PASS"
FAIL = "FAIL"
UNVERIFIED = "UNVERIFIED"

#: Maximum time for any one shell check. A hanging test suite must not
#: block the worker's supervise loop indefinitely.
DEFAULT_TIMEOUT = 60

#: Tools recognised as test runners by name alone.
_TEST_RUNNERS = frozenset(("pytest", "python", "python3", "make", "cargo",
                           "go", "npm", "yarn", "jest", "mocha", "rspec",
                           "mvn", "gradle", "tox", "nox"))


# ── criterion classifiers ─────────────────────────────────────────────────────

#: Backtick-quoted command: `pytest` or `python run.py`
_BACKTICK_CMD = re.compile(r"`([^`]{1,200})`")

#: "exit(s) with (code) 0" or "returns 0"
_EXIT_ZERO = re.compile(r"exit(?:s)?(?: with(?: code)?)?\s*0", re.I)

#: "tests? pass(es?)"
_TESTS_PASS = re.compile(r"\btests?\s+pass", re.I)

#: pytest invocation anywhere in the criterion
_PYTEST = re.compile(r"\bpytest\b", re.I)

#: "file X exists" / "X is created" / "X.ext exists"
_FILE_EXISTS = re.compile(
    r"(?:file\s+)?([\w./\\-]+\.[A-Za-z0-9]{1,10})\s+"
    r"(?:exists?|is\s+created?|is\s+present|was\s+created?)",
    re.I,
)

#: "git(?: status)? is clean" / "no uncommitted changes" / "working tree.*clean"
_GIT_CLEAN = re.compile(
    r"(?:git(?:\s+status)?\s+is\s+clean|"
    r"no\s+uncommitted\s+changes|"
    r"working\s+tree\s+(?:is\s+)?clean)",
    re.I,
)

#: "no errors?" / "runs without errors?" / "no (stderr|error output)"
_NO_ERRORS = re.compile(
    r"(?:runs?\s+without\s+errors?|no\s+(?:stderr|error\s+output|errors?))",
    re.I,
)

#: "output contains X" — capture what follows "contains"
_OUTPUT_CONTAINS = re.compile(r"output\s+contains?\s+(.{1,120})", re.I)


# ── verdict helpers ───────────────────────────────────────────────────────────

def _verdict(state: str, why: str, check: str = "") -> Dict[str, Any]:
    return {"state": state, "why": why, "deterministic": state != UNVERIFIED,
            "check": check}


def _run(cmd: str, cwd: Path, timeout: int = DEFAULT_TIMEOUT,
         _run=subprocess.run) -> subprocess.CompletedProcess:
    try:
        return _run(
            shlex.split(cmd), cwd=str(cwd),
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        raise
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"command timed out after {timeout}s: {cmd}") from e


def _safe_cwd(work_dir: Optional[Path]) -> Optional[Path]:
    if work_dir is None:
        return None
    try:
        p = work_dir.expanduser().resolve()
        return p if p.is_dir() else None
    except Exception:
        return None


# ── public API ────────────────────────────────────────────────────────────────

def check(criterion: str, work_dir: Optional[Path],
          timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Evaluate one `Verified when:` criterion deterministically.

    Returns PASS, FAIL, or UNVERIFIED.  UNVERIFIED means the criterion could
    not be evaluated without an LLM — the caller should fall through to the
    model verifier.
    """
    crit = (criterion or "").strip()
    if not crit:
        return _verdict(UNVERIFIED, "criterion is empty")

    cwd = _safe_cwd(work_dir)
    if cwd is None:
        return _verdict(UNVERIFIED,
                        f"work_dir {work_dir!r} is not a directory — "
                        "cannot run deterministic checks")

    # 1. Git clean check (no commands to run, just git status)
    if _GIT_CLEAN.search(crit):
        return _check_git_clean(cwd)

    # 2. File existence check
    m = _FILE_EXISTS.search(crit)
    if m:
        return _check_file_exists(m.group(1), cwd)

    # 3. Backtick-quoted command
    bt = _BACKTICK_CMD.search(crit)
    if bt:
        cmd = bt.group(1).strip()
        if _EXIT_ZERO.search(crit) or _NO_ERRORS.search(crit):
            return _check_exit_zero(cmd, cwd, timeout)
        # Output contains check
        oc = _OUTPUT_CONTAINS.search(crit)
        if oc:
            return _check_output_contains(cmd, oc.group(1).strip(), cwd, timeout)
        # Default: just check exit code for any command in backticks
        return _check_exit_zero(cmd, cwd, timeout)

    # 4. "tests pass" or "pytest" without backtick → infer pytest
    if _PYTEST.search(crit) or _TESTS_PASS.search(crit):
        # Prefer `pytest -x` (stop on first failure) for speed
        return _check_exit_zero("pytest -x", cwd, timeout)

    # 5. Exit-zero with a named executable (first word of a recognisable tool)
    if _EXIT_ZERO.search(crit):
        words = crit.split()
        for w in words:
            clean = re.sub(r"[^a-z0-9_.-]", "", w.lower())
            if clean in _TEST_RUNNERS:
                return _check_exit_zero(clean, cwd, timeout)

    return _verdict(UNVERIFIED,
                    "criterion does not match any deterministic check pattern — "
                    "falling through to LLM verifier")


# ── check implementations ─────────────────────────────────────────────────────

def _check_git_clean(cwd: Path) -> Dict[str, Any]:
    try:
        r = _run("git status --porcelain", cwd)
        if r.returncode != 0:
            return _verdict(UNVERIFIED,
                            f"git status failed (exit {r.returncode}): "
                            f"{r.stderr.strip()[:200]}",
                            check="git status --porcelain")
        dirty = r.stdout.strip()
        if not dirty:
            return _verdict(PASS, "git status is clean — working tree has no uncommitted changes",
                            check="git status --porcelain")
        lines = dirty.splitlines()
        sample = "; ".join(lines[:5])
        extra = f" (and {len(lines)-5} more)" if len(lines) > 5 else ""
        return _verdict(FAIL,
                        f"working tree is not clean: {sample}{extra}",
                        check="git status --porcelain")
    except Exception as e:
        return _verdict(UNVERIFIED, f"git status check failed: {e}",
                        check="git status --porcelain")


def _check_file_exists(name: str, cwd: Path) -> Dict[str, Any]:
    # Only paths that stay inside the evidence root are allowed.
    try:
        target = (cwd / name).resolve()
        if not str(target).startswith(str(cwd.resolve())):
            return _verdict(UNVERIFIED,
                            f"file path {name!r} escapes the work directory — "
                            "refusing to check it",
                            check=f"exists({name})")
        if target.exists():
            size = target.stat().st_size
            return _verdict(PASS,
                            f"{name} exists ({size} bytes)",
                            check=f"exists({name})")
        return _verdict(FAIL,
                        f"{name} does not exist in {cwd}",
                        check=f"exists({name})")
    except Exception as e:
        return _verdict(UNVERIFIED, f"file-existence check failed: {e}",
                        check=f"exists({name})")


def _check_exit_zero(cmd: str, cwd: Path, timeout: int) -> Dict[str, Any]:
    try:
        r = _run(cmd, cwd, timeout)
        if r.returncode == 0:
            out_snip = r.stdout.strip()[:300] or "(no stdout)"
            return _verdict(PASS,
                            f"exit 0: {out_snip}",
                            check=cmd)
        err_snip = (r.stderr or r.stdout).strip()[:400]
        return _verdict(FAIL,
                        f"exit {r.returncode}: {err_snip}",
                        check=cmd)
    except FileNotFoundError:
        return _verdict(UNVERIFIED,
                        f"command not found: {cmd.split()[0]!r}",
                        check=cmd)
    except RuntimeError as e:
        return _verdict(FAIL, str(e), check=cmd)
    except Exception as e:
        return _verdict(UNVERIFIED, f"check failed: {e}", check=cmd)


def _check_output_contains(cmd: str, expected: str, cwd: Path,
                            timeout: int) -> Dict[str, Any]:
    try:
        r = _run(cmd, cwd, timeout)
        combined = r.stdout + r.stderr
        # Strip the quoted wrapper if the expected text is quoted
        needle = expected.strip().strip("\"'`")
        if needle.lower() in combined.lower():
            return _verdict(PASS,
                            f"output of `{cmd}` contains {needle!r}",
                            check=f"{cmd} | contains({needle!r})")
        sample = combined.strip()[:300] or "(no output)"
        return _verdict(FAIL,
                        f"output of `{cmd}` does not contain {needle!r}. "
                        f"Output: {sample}",
                        check=f"{cmd} | contains({needle!r})")
    except FileNotFoundError:
        return _verdict(UNVERIFIED,
                        f"command not found: {cmd.split()[0]!r}",
                        check=cmd)
    except Exception as e:
        return _verdict(UNVERIFIED, f"check failed: {e}", check=cmd)
