"""Esc-to-interrupt — Claude Code parity.

A runaway tool (`find /`…) used to lock the whole TUI until the 300s bash
timeout: the worker thread was stuck in proc.wait, queued input never ran,
and Esc did nothing. Now `harness/interrupt.py` carries a global request:
the TUI's Esc sets it, shell.bash polls it and kills the process tree, and
run_loop ends the turn cleanly (remaining tool calls answered as skipped so
the history stays valid for the next API call).
"""
from __future__ import annotations

import threading
import time

import pytest

from ai4science.harness import interrupt
from ai4science.harness import loop as loop_mod
from ai4science.harness.events import Message, ToolCall, Done
from ai4science.harness.permissions import PermissionGate
from ai4science.harness.tools import shell
from ai4science.harness.tools.base import Registry, Tool


@pytest.fixture(autouse=True)
def _clean_event():
    interrupt.clear()
    yield
    interrupt.clear()


# ── the event ────────────────────────────────────────────────────────────────

def test_interrupt_request_and_clear():
    assert not interrupt.requested()
    interrupt.request()
    assert interrupt.requested()
    interrupt.clear()
    assert not interrupt.requested()


# ── bash honors it promptly ──────────────────────────────────────────────────

def test_bash_killed_on_interrupt(tmp_path):
    threading.Timer(0.4, interrupt.request).start()
    start = time.monotonic()
    out = shell.bash(tmp_path, cmd="sleep 30")
    assert time.monotonic() - start < 4
    assert "interrupted" in out.lower()


def test_bash_interrupt_kills_children(tmp_path):
    marker = tmp_path / "alive.txt"
    threading.Timer(0.4, interrupt.request).start()
    shell.bash(tmp_path, cmd=f"sleep 2 && echo done > {marker}")
    time.sleep(2.5)
    assert not marker.exists()


def test_bash_unaffected_when_not_interrupted(tmp_path):
    out = shell.bash(tmp_path, cmd="printf 'ok\\n'")
    assert "ok" in out and "interrupted" not in out.lower()


# ── the loop ends the turn cleanly ───────────────────────────────────────────

def _interrupting_registry():
    """Tool 'slow' sets the interrupt mid-execution (as Esc would);
    tool 'after' records whether it ever ran."""
    ran = {"after": False}

    def _slow(workspace, **kw):
        interrupt.request()
        return "(interrupted by user)"

    def _after(workspace, **kw):
        ran["after"] = True
        return "should never run"

    reg = Registry()
    reg.add(Tool(name="slow", description="d", parameters={}, func=_slow))
    reg.add(Tool(name="after", description="d", parameters={}, func=_after))
    return reg, ran


def test_loop_stops_turn_on_interrupt(tmp_path):
    class _TwoCallAdapter:
        def __init__(self):
            self.streams = 0
        def stream(self, history, tools, *, model, reasoning):
            self.streams += 1
            yield ToolCall("c1", "slow", {})
            yield ToolCall("c2", "after", {})
            yield Done("tool_use")

    reg, ran = _interrupting_registry()
    adapter = _TwoCallAdapter()
    history = [Message(role="user", content="go")]
    gate = PermissionGate(workspace=tmp_path, read_only=False, auto_yes=True)
    out = loop_mod.run_loop(
        adapter=adapter, model="stub", reasoning="low",
        history=history, workspace=tmp_path, registry=reg,
        gate=gate, on_text=lambda t: None, meter=lambda u: None)

    assert adapter.streams == 1                  # no second LLM round-trip
    assert ran["after"] is False                 # remaining call skipped
    tool_msgs = [m for m in history if m.role == "tool"]
    assert len(tool_msgs) == 2                   # every tool_call id answered
    assert "skipped" in tool_msgs[1].content.lower()
    assert "interrupted" in out.lower()          # user sees the note
    assert not interrupt.requested()             # consumed, not leaked
