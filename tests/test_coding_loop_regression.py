"""U02–U06 of TERMINAL_UX.md, driven through the real harness loop.

A scripted adapter plays the model; everything else — tools, gate, shell,
persistence, verification — is the production code. Each test is one row of
the acceptance table: a real bug fix that preserves the user's unrelated
edits, a failed test that cannot become a false completion, an interrupt and
a kill-and-relaunch that lose nothing, a missing tool, a provider failure, a
denied path, an empty and a dirty repository.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ai4science.harness import interrupt, persistence
from ai4science.harness.adapters.stub import StubAdapter
from ai4science.harness.events import Done, TextDelta, ToolCall, Usage
from ai4science.harness.session import AgentSession
from ai4science.harness.tools import default_registry

PY = sys.executable

ANALYSIS = '''def mean(samples):
    return sum(samples) / len(samples)
'''
TEST = '''from analysis import mean

def test_mean():
    assert mean([2, 4]) == 3

def test_empty():
    assert mean([]) == 0
'''
FIX_OLD = "    return sum(samples) / len(samples)\n"
FIX_NEW = "    if not samples:\n        return 0\n    return sum(samples) / len(samples)\n"


def _project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "analysis.py").write_text(ANALYSIS)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_analysis.py").write_text(TEST)
    (tmp_path / "tests" / "__init__.py").write_text("")
    return tmp_path


def _session(ws: Path, script, **kw) -> AgentSession:
    return AgentSession(adapter=StubAdapter(script), model="stub", backend="anthropic",
                        workspace=ws, registry=default_registry(), read_only=False,
                        auto_yes=True, on_text=lambda t: None, **kw)


def _pytest_cmd() -> str:
    return f"{PY} -m pytest -q -p no:cacheprovider tests/test_analysis.py"


# ── U02: a real bug fix, with the user's unrelated edits preserved ───────

def test_real_bug_fix_preserves_unrelated_user_edits(tmp_path):
    ws = _project(tmp_path)
    # The user has an uncommitted, unrelated edit in the same file.
    (ws / "analysis.py").write_text("# user's WIP note\n" + ANALYSIS)
    script = [
        [ToolCall("c1", "read", {"path": "analysis.py"}), Done("tool_use")],
        [ToolCall("c2", "edit", {"path": "analysis.py", "old": FIX_OLD, "new": FIX_NEW}), Done("tool_use")],
        [ToolCall("c3", "bash", {"cmd": _pytest_cmd()}), Done("tool_use")],
        [TextDelta("Fixed: empty input returns 0. Tests pass."), Done("end")],
    ]
    s = _session(ws, script)
    final = s.run_turn("fix the empty-input crash")
    assert "Tests pass" in final
    text = (ws / "analysis.py").read_text()
    assert text.startswith("# user's WIP note\n")          # untouched
    assert "if not samples" in text
    assert [c.status for c in s.turn_checks] == ["passed"]
    assert s.verification_note(final) is None              # the claim has a run behind it


def test_tool_failure_and_stderr_reach_the_model(tmp_path):
    ws = _project(tmp_path)
    script = [
        [ToolCall("c1", "edit", {"path": "analysis.py", "old": "nonexistent", "new": "x"}), Done("tool_use")],
        [ToolCall("c2", "bash", {"cmd": f"{PY} -c 'import sys; print(\"boom\", file=sys.stderr); sys.exit(3)'"}), Done("tool_use")],
        [TextDelta("done"), Done("end")],
    ]
    s = _session(ws, script)
    s.run_turn("edit and run")
    tool_msgs = [m.content for m in s.history if m.role == "tool"]
    assert tool_msgs[0].startswith("[error]") and "not found" in tool_msgs[0]
    assert "boom" in tool_msgs[1] and "(exit code 3)" in tool_msgs[1]


# ── U05: no false completion after a failed or skipped test ─────────────

def test_failed_test_is_stated_by_the_harness_not_the_model(tmp_path):
    ws = _project(tmp_path)
    script = [
        [ToolCall("c1", "bash", {"cmd": _pytest_cmd()}), Done("tool_use")],   # fails: no fix
        [TextDelta("All done, the tests pass now."), Done("end")],
    ]
    s = _session(ws, script)
    final = s.run_turn("fix it")
    assert [c.status for c in s.turn_checks] == ["failed"]
    note = s.verification_note(final)
    assert note and "did not all pass" in note and "exit 1" in note


def test_claimed_pass_with_no_test_run_is_flagged(tmp_path):
    ws = _project(tmp_path)
    script = [
        [ToolCall("c1", "edit", {"path": "analysis.py", "old": FIX_OLD, "new": FIX_NEW}), Done("tool_use")],
        [TextDelta("Fixed; all tests pass."), Done("end")],
    ]
    s = _session(ws, script)
    final = s.run_turn("fix it")
    assert s.turn_checks == []
    note = s.verification_note(final)
    assert note and "no test command ran" in note


def test_honest_summary_without_claim_gets_no_note(tmp_path):
    ws = _project(tmp_path)
    s = _session(ws, [[TextDelta("I changed analysis.py; I did not run the tests."), Done("end")]])
    final = s.run_turn("fix it")
    assert s.verification_note(final) is None


# ── U04: interruption and kill-and-relaunch ──────────────────────────────

def test_interrupt_mid_turn_keeps_transcript_and_finished_work(tmp_path):
    ws = _project(tmp_path)

    class Interrupting(StubAdapter):
        def stream(self, *a, **k):
            for ev in super().stream(*a, **k):
                yield ev
                if isinstance(ev, ToolCall) and ev.id == "c2":
                    interrupt.request()

    script = [
        [ToolCall("c1", "edit", {"path": "analysis.py", "old": FIX_OLD, "new": FIX_NEW}), Done("tool_use")],
        [TextDelta("now testing "), ToolCall("c2", "bash", {"cmd": _pytest_cmd()}), Done("tool_use")],
        [TextDelta("never reached"), Done("end")],
    ]
    shown = []
    s = AgentSession(adapter=Interrupting(script), model="stub", backend="anthropic",
                     workspace=ws, registry=default_registry(), auto_yes=True,
                     on_text=shown.append)
    final = s.run_turn("fix it")
    assert "interrupted" in "".join(shown) and "never reached" not in final
    assert "if not samples" in (ws / "analysis.py").read_text()   # the applied edit stays
    assert not interrupt.requested()                               # flag consumed
    # Every tool call in the transcript has an answer: the next request is valid.
    tool_ids = {m.tool_call_id for m in s.history if m.role == "tool"}
    for m in s.history:
        if m.role == "assistant":
            assert all(tc.id in tool_ids for tc in m.tool_calls)


def test_kill_mid_turn_resumes_at_last_tool_call(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr(persistence, "sessions_dir", lambda: sessions)
    ws = _project(tmp_path / "ws")

    class Dies(StubAdapter):
        """The process is killed while the model is producing its third reply."""
        def stream(self, history, *a, **k):
            if len([m for m in history if m.role == "tool"]) >= 2:
                raise SystemExit("SIGKILL stand-in")
            yield from super().stream(history, *a, **k)

    script = [
        [ToolCall("c1", "read", {"path": "analysis.py"}), Done("tool_use")],
        [ToolCall("c2", "edit", {"path": "analysis.py", "old": FIX_OLD, "new": FIX_NEW}), Done("tool_use")],
    ]
    s = AgentSession(adapter=Dies(script), model="stub", backend="anthropic",
                     workspace=ws, registry=default_registry(), auto_yes=True,
                     on_text=lambda t: None,
                     on_checkpoint=lambda: persistence.save("sid1", ws, s.history))
    with pytest.raises(SystemExit):
        s.run_turn("fix it")
    # A fresh process resumes: both tool results are there, nothing dangles.
    hist = persistence.load("sid1")
    assert [m.role for m in hist] == ["user", "assistant", "tool", "assistant", "tool"]
    assert hist[-1].content == "edited analysis.py"
    assert persistence.most_recent(ws) == "sid1"
    resumed = _session(ws, [[TextDelta("continuing"), Done("end")]])
    resumed.history.extend(hist)
    assert "continuing" in resumed.run_turn("go on")


# ── U06: missing tool, provider failure, denied path, empty and dirty repos ──

def test_unknown_tool_names_the_available_ones(tmp_path):
    ws = _project(tmp_path)
    s = _session(ws, [[ToolCall("c1", "run_tests", {}), Done("tool_use")],
                      [TextDelta("ok"), Done("end")]])
    s.run_turn("go")
    msg = [m.content for m in s.history if m.role == "tool"][0]
    assert msg.startswith("[error] unknown tool 'run_tests'")
    assert "bash" in msg and "edit" in msg


def test_provider_failure_mid_turn_leaves_a_valid_transcript(tmp_path):
    ws = _project(tmp_path)

    class Flaky(StubAdapter):
        def stream(self, history, *a, **k):
            if any(m.role == "tool" for m in history):
                raise RuntimeError("HTTP 529: overloaded")
            yield from super().stream(history, *a, **k)

    s = AgentSession(adapter=Flaky([[ToolCall("c1", "read", {"path": "analysis.py"}), Done("tool_use")]]),
                     model="stub", backend="anthropic", workspace=ws,
                     registry=default_registry(), auto_yes=True, on_text=lambda t: None)
    with pytest.raises(RuntimeError, match="529"):
        s.run_turn("go")
    tool_ids = {m.tool_call_id for m in s.history if m.role == "tool"}
    assert all(tc.id in tool_ids for m in s.history if m.role == "assistant" for tc in m.tool_calls)


def test_denied_paths_stay_denied_while_routine_work_proceeds(tmp_path):
    ws = _project(tmp_path)
    (ws / "hidden_tests").mkdir()
    (ws / "hidden_tests" / "answer.py").write_text("SECRET = 1\n")
    outside = tmp_path.parent / "outside.txt"
    script = [
        [ToolCall("c1", "write", {"path": "hidden_tests/answer.py", "content": "SECRET = 2\n"}), Done("tool_use")],
        [ToolCall("c2", "write", {"path": str(outside), "content": "escaped"}), Done("tool_use")],
        [ToolCall("c3", "write", {"path": "notes.md", "content": "routine\n"}), Done("tool_use")],
        [TextDelta("done"), Done("end")],
    ]
    s = _session(ws, script)
    s.run_turn("go")
    msgs = [m.content for m in s.history if m.role == "tool"]
    assert msgs[0].startswith("[blocked]") and (ws / "hidden_tests" / "answer.py").read_text() == "SECRET = 1\n"
    assert msgs[1].startswith("[blocked]") and not outside.exists()
    assert (ws / "notes.md").read_text() == "routine\n"


def test_empty_repository_and_dirty_repository(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=empty, check=True)
    s = _session(empty, [[ToolCall("c1", "glob", {"pattern": "*"}), Done("tool_use")],
                         [ToolCall("c2", "write", {"path": "README.md", "content": "# new\n"}), Done("tool_use")],
                         [TextDelta("created"), Done("end")]])
    assert "created" in s.run_turn("start")
    assert (empty / "README.md").exists()

    dirty = _project(tmp_path / "dirty")
    subprocess.run(["git", "init", "-q"], cwd=dirty, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], cwd=dirty, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"], cwd=dirty, check=True)
    (dirty / "scratch.txt").write_text("user's untracked scratch\n")           # dirty state
    s = _session(dirty, [[ToolCall("c1", "edit", {"path": "analysis.py", "old": FIX_OLD, "new": FIX_NEW}), Done("tool_use")],
                         [TextDelta("edited"), Done("end")]])
    s.run_turn("fix")
    status = subprocess.run(["git", "status", "--short"], cwd=dirty, capture_output=True, text=True).stdout
    assert " M analysis.py" in status and "?? scratch.txt" in status
    assert (dirty / "scratch.txt").read_text() == "user's untracked scratch\n"


# ── U06: long context — many large tool outputs, bounded history, valid transcript ──

def test_long_context_stays_bounded_and_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_TOOL_RESULT_CHARS", "5000")
    ws = _project(tmp_path)
    (ws / "big.txt").write_text("line\n" * 20_000)             # ~100k chars
    script = []
    for i in range(8):
        script.append([ToolCall(f"c{i}", "read", {"path": "big.txt"}), Done("tool_use")])
        script.append([TextDelta(f"turn {i} done"), Done("end")])
    summaries = []

    def summarize(t):
        summaries.append(len(t))
        return "SUMMARY of earlier work"

    s = _session(ws, script, compact_limit_chars=12_000, summarize=summarize)
    for i in range(8):
        assert f"turn {i} done" in s.run_turn(f"read big {i}")
        answered = {m.tool_call_id for m in s.history if m.role == "tool"}
        for m in s.history:
            if m.role == "assistant":
                assert all(tc.id in answered for tc in m.tool_calls)
    total = sum(len(m.content) for m in s.history)
    assert total < 40_000, total
    assert summaries, "compaction never ran"
    tool_msgs = [m for m in s.history if m.role == "tool"]
    assert all("truncated" in m.content and len(m.content) < 5_500 for m in tool_msgs)
