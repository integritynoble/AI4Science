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
from typing import Any, Dict, List, Optional

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

#: `out.txt contains "42"` — a content predicate over a file, not a command.
#: NOT `has`: "export.csv has 1,204 rows" is a claim about the file's SHAPE,
#: and reading it as a substring test turns a criterion the model verifier
#: judged correctly into a deterministic FAIL. Only verbs that actually mean
#: "this text appears in that file".
_FILE_CONTAINS = re.compile(
    r"([\w./-]+\.[A-Za-z0-9]{1,8})\s+(?:contains?|includes?|mentions?)\s+"
    r"['\"]?(.{1,120}?)['\"]?\s*$", re.I)

#: `sha256 of out.txt is a948…` — an exact content hash.
_FILE_HASH = re.compile(
    r"(?:sha256|hash|checksum)\s+of\s+([\w./-]+)\s+(?:is|equals?|matches)\s+"
    r"([0-9a-f]{8,64})", re.I)

#: `the field accuracy in metrics.json is at least 0.9`, and the dotted form.
_JSON_FIELD = re.compile(
    r"(?:the\s+)?(?:json\s+)?field\s+\.?([\w.\[\]]+)\s+(?:in|of)\s+"
    r"([\w./-]+\.json)\s+(?:is|equals?|reads?)\s+"
    r"(?:(?P<op>at least|at most|greater than|less than|exactly)\s+)?"
    r"['\"]?(?P<val>[^'\"]{1,60}?)['\"]?\s*$", re.I)

#: `the diff touches only src/ and tests/` — or, with no paths named, the
#: task's own declared `may_touch`.
_DIFF_SCOPED = re.compile(
    r"(?:the\s+)?(?:diff|changes?|edits?)\s+(?:touch(?:es)?|are|is|stay(?:s)?|"
    r"remain(?:s)?)\s+(?:only\s+|within\s+|inside\s+|restricted to\s+|"
    r"confined to\s+)?(?P<paths>.*)$", re.I)
_NO_FILES_OUTSIDE = re.compile(
    r"no\s+files?\s+outside\s+(?:the\s+)?declared\s+paths?", re.I)

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
          may_touch: Optional[List[str]] = None,
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
        # A diff-scope criterion names its paths with `and` — "the diff touches
        # only src/ and tests/" is ONE condition over two directories, not two
        # conditions, and splitting it judged the second half as a criterion of
        # its own.
        parts = [] if (_DIFF_SCOPED.search(crit) or _NO_FILES_OUTSIDE.search(crit)) \
            else _clauses(crit)
        if len(parts) > 1:
            results = [check(c, work_dir, timeout=timeout, trusted=trusted,
                             may_touch=may_touch, _depth=1) for c in parts]
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

    # 2b. Content predicate over a file — §M4.1's "file content/hash matches
    # predicate", which was listed and never implemented.
    mh = _FILE_HASH.search(crit)
    if mh:
        return _check_file_hash(mh.group(1), mh.group(2), cwd)
    mj = _JSON_FIELD.search(crit)
    if mj:
        return _check_json_field(mj.group(2), mj.group(1), mj.group("op") or "is",
                                 mj.group("val"), cwd)
    mc = _FILE_CONTAINS.search(crit)
    if mc and not _BACKTICK_CMD.search(crit):
        return _check_file_contains(mc.group(1), mc.group(2), cwd)

    # 2c. The diff stays inside the declared paths. `may_touch` is parsed onto
    # the task and, until now, no check ever consulted it — the data existed
    # and the check did not.
    if _NO_FILES_OUTSIDE.search(crit) and may_touch:
        return _check_diff_scope(list(may_touch), cwd)
    md = _DIFF_SCOPED.search(crit)
    if md:
        named = [w.strip(" .,`'\"") for w in
                 re.split(r"\s+and\s+|,\s*", md.group("paths") or "") if w.strip()]
        allowed = [n for n in named if n and "/" in n or n.endswith("/")] or list(may_touch or [])
        if allowed:
            return _check_diff_scope(allowed, cwd)

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


def _check_file_contains(name: str, want: str, cwd: Path) -> Dict[str, Any]:
    """A file whose CONTENT has to say something. §M4.1 type 3."""
    target = _inside(name, cwd)
    if target is None:
        return _verdict(UNVERIFIED,
                        f"file path {name!r} escapes the work directory",
                        check=f"contains({name})")
    if not target.exists():
        return _verdict(FAIL, f"{name} does not exist in {cwd}",
                        check=f"contains({name})")
    try:
        body = target.read_text(errors="replace")
    except Exception as e:
        return _verdict(UNVERIFIED, f"could not read {name}: {e}",
                        check=f"contains({name})")
    if want in body:
        return _verdict(PASS, f"{name} contains {want!r}",
                        check=f"contains({name})")
    return _verdict(FAIL,
                    f"{name} does not contain {want!r} "
                    f"({len(body)} bytes read)", check=f"contains({name})")


def _check_file_hash(name: str, want: str, cwd: Path) -> Dict[str, Any]:
    """An exact content hash — the strongest file predicate there is."""
    import hashlib
    target = _inside(name, cwd)
    if target is None:
        return _verdict(UNVERIFIED,
                        f"file path {name!r} escapes the work directory",
                        check=f"sha256({name})")
    if not target.exists():
        return _verdict(FAIL, f"{name} does not exist in {cwd}",
                        check=f"sha256({name})")
    got = hashlib.sha256(target.read_bytes()).hexdigest()
    if got.startswith(want.lower()):
        return _verdict(PASS, f"sha256({name}) = {got[:16]}… as required",
                        check=f"sha256({name})")
    return _verdict(FAIL,
                    f"sha256({name}) is {got[:16]}…, expected {want[:16]}…",
                    check=f"sha256({name})")


def _check_json_field(name: str, field: str, op: str, want: str,
                      cwd: Path) -> Dict[str, Any]:
    """A predicate over one field of a JSON artifact. §M4.1 type 4."""
    import json as _json
    target = _inside(name, cwd)
    if target is None:
        return _verdict(UNVERIFIED,
                        f"file path {name!r} escapes the work directory",
                        check=f"json({name}.{field})")
    if not target.exists():
        return _verdict(FAIL, f"{name} does not exist in {cwd}",
                        check=f"json({name}.{field})")
    try:
        doc = _json.loads(target.read_text())
    except Exception as e:
        return _verdict(FAIL, f"{name} is not readable JSON: {e}",
                        check=f"json({name}.{field})")
    cur: Any = doc
    for part in field.replace("[", ".").replace("]", "").split("."):
        if not part:
            continue
        try:
            cur = cur[int(part)] if part.isdigit() else cur[part]
        except Exception:
            return _verdict(FAIL, f"{name} has no field {field!r}",
                            check=f"json({name}.{field})")
    check = f"json({name}.{field})"
    lo = str(op).lower()
    try:
        if lo in ("at least", "greater than", "at most", "less than"):
            a, b = float(cur), float(want)
            ok = {"at least": a >= b, "greater than": a > b,
                  "at most": a <= b, "less than": a < b}[lo]
            return _verdict(PASS if ok else FAIL,
                            f"{field} is {cur}, {lo} {want} is "
                            f"{'satisfied' if ok else 'not satisfied'}", check=check)
    except (TypeError, ValueError):
        return _verdict(FAIL,
                        f"{field} is {cur!r}, which cannot be compared numerically "
                        f"with {want!r}", check=check)
    want_norm = want.strip().strip("'\"")
    ok = str(cur).strip().lower() == want_norm.lower()
    if not ok and want_norm.lower() in ("true", "false"):
        ok = bool(cur) is (want_norm.lower() == "true")
    return _verdict(PASS if ok else FAIL,
                    f"{field} is {cur!r}" + ("" if ok else f", expected {want_norm!r}"),
                    check=check)


def _check_diff_scope(allowed: List[str], cwd: Path) -> Dict[str, Any]:
    """Every changed file sits under a declared path. §M4.1 type 5."""
    try:
        r = _run("git status --porcelain", cwd)
    except Exception as e:
        return _verdict(UNVERIFIED, f"could not read the diff: {e}",
                        check="diff-scope")
    if r.returncode != 0:
        return _verdict(UNVERIFIED,
                        f"git status failed (exit {r.returncode}) — no diff to scope",
                        check="diff-scope")
    changed = [ln[3:].strip() for ln in r.stdout.splitlines() if ln.strip()]
    norm = [a.rstrip("/") for a in allowed if a]
    stray = [f for f in changed
             if not any(f == a or f.startswith(a + "/") for a in norm)]
    if not changed:
        return _verdict(PASS, "nothing was changed, so nothing left the "
                              "declared paths", check="diff-scope")
    if stray:
        return _verdict(FAIL,
                        f"{len(stray)} file(s) changed outside "
                        f"{', '.join(norm)}: {', '.join(stray[:5])}",
                        check="diff-scope")
    return _verdict(PASS,
                    f"all {len(changed)} changed file(s) are within "
                    f"{', '.join(norm)}", check="diff-scope")


def _inside(name: str, cwd: Path) -> Optional[Path]:
    """The path, if it stays inside the work dir. None if it escapes."""
    try:
        target = (cwd / name).resolve()
        root = cwd.resolve()
        if root != target and root not in target.parents:
            return None
        return target
    except Exception:
        return None


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
