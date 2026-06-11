"""Read-only bash auto-allow — Claude Code parity.

Claude Code does not ask permission for read-only shell commands (find, ls,
grep, cat, git log, ...). The native harness should classify those and skip
the [y/N] confirmation — and allow them even in /readonly mode, like Claude
Code's plan mode. Anything not provably read-only falls through to the
existing confirm gate (conservative: false-negatives prompt, never the
reverse).
"""
from ai4science.harness.permissions import PermissionGate, is_read_only_bash


# ── classifier: provably read-only commands ─────────────────────────────────

def test_classifier_accepts_plain_readers():
    for cmd in [
        "ls -la",
        "cat a.txt",
        "head -20 notes.md",
        "tail -f run.log",
        "grep -rn 'foo' src",
        "rg --files",
        "wc -l file.py",
        "pwd",
        "du -sh .",
        "df -h",
        "stat a.txt",
        "file a.bin",
        "which python3",
        "uname -a",
        "whoami",
        "date",
        "tree -L 2",
        "realpath .",
        "printenv HOME",
        "nproc",
    ]:
        assert is_read_only_bash(cmd), cmd


def test_classifier_accepts_heyang_find_pipeline():
    # The exact command from the agent-prod transcript: stderr→/dev/null is
    # fine, pipe into an allowlisted reader is fine.
    cmd = 'find / -iname "*low*dose*" -o -iname "*ldct*" 2>/dev/null | head -50'
    assert is_read_only_bash(cmd)


def test_classifier_accepts_chains_of_readers():
    assert is_read_only_bash("pwd && ls -la")
    assert is_read_only_bash("grep -c def a.py; wc -l a.py")
    assert is_read_only_bash("sort names.txt | uniq | head")


def test_classifier_accepts_readonly_git():
    for cmd in [
        "git status",
        "git log --oneline -5",
        "git diff HEAD~1",
        "git show abc123",
        "git ls-files",
        "git rev-parse HEAD",
        "git blame a.py",
    ]:
        assert is_read_only_bash(cmd), cmd


def test_classifier_accepts_dev_null_redirects_only():
    assert is_read_only_bash("ls missing_dir 2>/dev/null")
    assert is_read_only_bash("grep -r foo . 2>&1 | head")
    assert not is_read_only_bash("ls > files.txt")
    assert not is_read_only_bash("cat a >> b")
    assert not is_read_only_bash("echo hi 2>err.log")


# ── classifier: anything mutating / executing / unknown ─────────────────────

def test_classifier_rejects_mutators_and_unknowns():
    for cmd in [
        "rm -rf /",
        "mv a b",
        "cp a b",
        "touch x",
        "mkdir d",
        "chmod +x s.sh",
        "pip install requests",
        "python3 -c 'open(\"x\",\"w\")'",
        "curl http://evil.example",
        "sed -i s/a/b/ file",
        "tee out.txt",
        "xargs rm",
        "env rm -rf x",
        "",
    ]:
        assert not is_read_only_bash(cmd), cmd


def test_classifier_rejects_substitution_and_backticks():
    assert not is_read_only_bash("ls $(rm -rf x)")
    assert not is_read_only_bash("cat `rm x`")
    assert not is_read_only_bash("diff <(rm x) a")


def test_classifier_rejects_any_nonreadonly_segment():
    assert not is_read_only_bash("ls && rm x")
    assert not is_read_only_bash("cat a | sh")
    assert not is_read_only_bash("pwd; curl http://x")


def test_classifier_rejects_dangerous_find_flags():
    assert not is_read_only_bash("find . -name '*.tmp' -delete")
    assert not is_read_only_bash("find . -exec rm {} \\;")
    assert not is_read_only_bash("find . -execdir rm {} \\;")
    assert not is_read_only_bash("find . -ok rm {} \\;")
    assert is_read_only_bash("find . -name '*.py' -type f")


def test_classifier_rejects_mutating_git():
    for cmd in ["git push", "git commit -m x", "git checkout .",
                "git reset --hard", "git branch newb", "git remote add o u"]:
        assert not is_read_only_bash(cmd), cmd


def test_classifier_rejects_sort_output_flag():
    assert not is_read_only_bash("sort -o out.txt in.txt")
    assert is_read_only_bash("sort in.txt")


# ── gate behavior ────────────────────────────────────────────────────────────

def test_gate_auto_allows_readonly_bash_without_confirm(tmp_path):
    gate = PermissionGate(workspace=tmp_path, read_only=False, auto_yes=False,
                          confirm=lambda n, a, p: False)   # would deny if asked
    ok, _ = gate.allow("bash", {"cmd": "ls -la"})
    assert ok is True


def test_gate_allows_readonly_bash_in_readonly_mode(tmp_path):
    gate = PermissionGate(workspace=tmp_path, read_only=True, auto_yes=False)
    ok, _ = gate.allow("bash", {"cmd": "grep -rn foo ."})
    assert ok is True


def test_gate_still_confirms_mutating_bash(tmp_path):
    gate = PermissionGate(workspace=tmp_path, read_only=False, auto_yes=False,
                          confirm=lambda n, a, p: False)
    ok, _ = gate.allow("bash", {"cmd": "rm -rf build"})
    assert ok is False


def test_gate_still_blocks_mutating_bash_in_readonly_mode(tmp_path):
    gate = PermissionGate(workspace=tmp_path, read_only=True, auto_yes=False)
    ok, reason = gate.allow("bash", {"cmd": "rm -rf build"})
    assert ok is False and "read-only" in reason.lower()


def test_gate_sandbox_beats_readonly_classification(tmp_path):
    # Protected dirs stay blocked even for a read-only command.
    gate = PermissionGate(workspace=tmp_path, read_only=False, auto_yes=True)
    ok, reason = gate.allow("bash", {"cmd": "cat judge/answers.txt"})
    assert ok is False and "sandbox" in reason.lower()


# ── SDK paths honor the same classification ──────────────────────────────────

def test_sdk_callback_auto_allows_readonly_bash(tmp_path):
    import pytest
    pytest.importorskip("claude_agent_sdk")
    import asyncio
    from claude_agent_sdk import PermissionResultAllow
    from ai4science.agents.permissions import make_workspace_permission_callback

    cb = make_workspace_permission_callback(tmp_path, auto_yes=False)
    res = asyncio.run(cb("Bash", {"command": "find . -name '*.py' | head -20"}, None))
    assert isinstance(res, PermissionResultAllow)


def test_sdk_repl_bash_auto_allow_helper():
    from ai4science.harness.sdk_repl import _bash_auto_allow
    assert _bash_auto_allow("Bash", {"command": "ls -la"})
    assert not _bash_auto_allow("Bash", {"command": "rm -rf build"})
    assert not _bash_auto_allow("Write", {"file_path": "a.py"})
