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
#: "output contains X", and the phrasing people actually use — "the output of
#: `cmd` contains X", "prints X", "reports X". The narrow original matched only
#: the first, so the rest fell through to a bare exit-code check and passed on
#: output that demonstrably lacked the string.
_OUTPUT_CONTAINS = re.compile(
    r"(?:output|stdout)\s*(?:of\s+`[^`]*`\s*)?(?:contains?|includes?|shows?|"
    r"has|says)\s+(.{1,120})"
    r"|(?:prints?|reports?|outputs?)\s+(.{1,120})", re.I)

#: An expected exit code that is not zero. "exits with code 3" was checked
#: against 0, so a satisfied criterion was reported as a failure.
_EXPECTED_EXIT = re.compile(
    r"exit(?:s)?(?:\s+with)?(?:\s+(?:code|status))?\s+([1-9]\d{0,2})\b", re.I)


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
          timeout: int = DEFAULT_TIMEOUT, *, trusted: bool = False,
          _depth: int = 0) -> Dict[str, Any]:
    """Evaluate one `Verified when:` criterion deterministically.

    Returns PASS, FAIL, or UNVERIFIED.  UNVERIFIED means the criterion could
    not be evaluated without an LLM — the caller should fall through to the
    model verifier.

    `trusted` says the criterion came from a plan the OWNER agreed. Only a
    trusted criterion may name a command to run: on the automatic path the
    executor writes `plan0.md` and its `Verified when:` lines become the
    criteria verbatim, so an untrusted command criterion would let the thing
    being judged choose the code that judges it. [§M4.2 runtime independence]
    """
    crit = (criterion or "").strip()
    if not crit:
        return _verdict(UNVERIFIED, "criterion is empty")

    cwd = _safe_cwd(work_dir)
    if cwd is not None and _depth == 0:
        # "report.md exists and `/bin/false` exits 0" used to return on the
        # first classifier that matched and close the phase on one of the two
        # conditions it declared. Each clause is judged; the phase passes only
        # if every judgeable clause passes, and an unjudgeable clause makes the
        # whole thing unverified rather than quietly optional.
        parts = _clauses(crit)
        if len(parts) > 1:
            results = [check(c, work_dir, timeout=timeout, trusted=trusted,
                             _depth=1) for c in parts]
            if any(r["state"] == FAIL for r in results):
                bad = next(r for r in results if r["state"] == FAIL)
                return _verdict(FAIL, f"one clause failed: {bad['why']}",
                                check=bad.get("check", ""))
            if all(r["state"] == PASS for r in results):
                return _verdict(PASS,
                                "; ".join(r["why"] for r in results),
                                check=" AND ".join(r.get("check", "") for r in results))
            unk = next(r for r in results if r["state"] == UNVERIFIED)
            return _verdict(UNVERIFIED,
                            f"part of this criterion cannot be checked "
                            f"deterministically: {unk['why']}")
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
        if not trusted and not _is_safe_command(cmd):
            # The criterion came from a plan the EXECUTOR wrote. On the
            # automatic path the session writes `plan0.md`, `adopt_plan` takes
            # its `Verified when:` lines verbatim, and this function used to
            # `subprocess.run` whatever sat between the backticks — so the
            # thing being judged chose the code its judge would execute, as
            # the judge, outside the work dir. Measured: a criterion reading
            # "`/bin/bash -c touch /tmp/x` exits 0" ran and passed.
            #
            # §M4.2's runtime independence is exactly this: the session whose
            # artifact is being judged must not control the verifier. An
            # unagreed command is not run — it is handed back as unverified,
            # which routes it to the owner instead of to a shell.
            return _verdict(UNVERIFIED,
                            f"the criterion asks to run `{cmd[:60]}`, which is "
                            f"not a recognised check, and this plan was not "
                            f"agreed by the owner — a session does not choose "
                            f"the command that judges it",
                            check="")
        # An expected exit code, when one is named. Checking `exits with code 3`
        # against 0 reported a satisfied criterion as a failure.
        want = _EXPECTED_EXIT.search(crit)
        if want:
            return _check_exit_code(cmd, int(want.group(1)), cwd, timeout)
        oc = _OUTPUT_CONTAINS.search(crit)
        if oc:
            want_text = (oc.group(1) or oc.group(2) or "").strip()
            if want_text:
                return _check_output_contains(cmd, want_text, cwd, timeout)
        if _EXIT_ZERO.search(crit) or _NO_ERRORS.search(crit):
            return _check_exit_zero(cmd, cwd, timeout)
        # A command with no stated expectation is NOT "exit 0 means done".
        # "output of `cat out.txt` contains ZZZ" fell through to here and
        # passed on exit 0 while the output plainly lacked ZZZ — a false PASS
        # on a criterion the artifact demonstrably failed.
        return _verdict(UNVERIFIED,
                        f"`{cmd[:60]}` is named but the criterion does not say "
                        f"what would count as passing — state an exit code or "
                        f"the output expected",
                        check="")

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


#: The only executables an UNAGREED criterion may run. Test runners and
#: read-only inspectors — the commands a `Verified when:` line legitimately
#: names. Not `bash`, `sh`, `env`, `cat` or anything that takes another program
#: or an arbitrary path as its argument, because the whole point is that the
#: session being judged wrote this string.
_SAFE_CMDS = frozenset("""
pytest tox nox unittest make npm yarn pnpm cargo go gradle mvn
ruff flake8 mypy pyright black isort eslint tsc
git ls diff stat wc grep find du
""".split())

#: Shell punctuation that turns one command into several. `shlex.split` does not
#: interpret these, but a criterion carrying them is not a plain command and is
#: not the shape this allowlist was reasoned about.
_SHELLY = re.compile(r"[;&|><$`\n]|\.\.")


def _is_safe_command(cmd: str) -> bool:
    """May this command run from a plan the owner never agreed?

    Name on the allowlist, no shell punctuation, no absolute path, no `..`.
    An unsafe command is not refused outright — it is returned UNVERIFIED, so
    it reaches the owner instead of a shell.
    """
    text = (cmd or "").strip()
    if not text or _SHELLY.search(text) or text.startswith("/"):
        return False
    try:
        import shlex
        argv = shlex.split(text)
    except ValueError:
        return False
    if not argv or any(a.startswith("/") for a in argv):
        return False
    head = argv[0].rsplit("/", 1)[-1].lower()
    if head in ("python", "python3") and len(argv) >= 3 and argv[1] == "-m":
        return argv[2].split(".")[0].lower() in _SAFE_CMDS
    return head in _SAFE_CMDS


#: Splits a conjunctive criterion. Only on `and`/`;`/`&&` OUTSIDE backticks —
#: `\`a && b\`` is one command, not two clauses.
def _clauses(crit: str) -> list:
    parts, buf, in_tick = [], [], False
    i = 0
    while i < len(crit):
        ch = crit[i]
        if ch == "`":
            in_tick = not in_tick
            buf.append(ch)
            i += 1
            continue
        if not in_tick:
            low = crit[i:i + 5].lower()
            if low.startswith(" and "):
                parts.append("".join(buf)); buf = []; i += 5; continue
            if crit[i:i + 2] == "&&":
                parts.append("".join(buf)); buf = []; i += 2; continue
            if ch == ";":
                parts.append("".join(buf)); buf = []; i += 1; continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _check_exit_code(cmd: str, want: int, cwd: Path,
                     timeout: int) -> Dict[str, Any]:
    """A command that must exit with a SPECIFIC code."""
    try:
        r = _run(cmd, cwd, timeout=timeout)
    except Exception as e:
        return _verdict(FAIL, f"could not run `{cmd}`: {e}", check=cmd)
    if r.returncode == want:
        return _verdict(PASS, f"`{cmd}` exited {want} as required", check=cmd)
    return _verdict(FAIL,
                    f"`{cmd}` exited {r.returncode}, expected {want}: "
                    f"{(r.stdout or r.stderr or '').strip()[:200]}", check=cmd)


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
        root = cwd.resolve()
        # NOT `startswith`: `/tmp/base/work-evil/loot.txt` string-starts-with
        # `/tmp/base/work` and is a different directory. `permissions.py:284`
        # already had this right, with a comment naming this exact bug.
        if root != target and root not in target.parents:
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
