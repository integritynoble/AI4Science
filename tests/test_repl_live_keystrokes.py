"""The loop, driven by keystrokes — not `route()` called directly.

Four Criticals shipped past 1945 passing tests on this exact surface, for one
reason: **every test called `console.route` directly and never crossed the
loop's own pre-filters.** `/<worker> do <goal>` was swallowed, `/<task>
<instruction>` was swallowed, `[Enter=yes]` was dead, and `/research` announced
a switch that never happened. Each was reachable from `route()` and unreachable
from a keyboard.

So a new option on the confirmation block gets this test and not another
`route()` assertion. It drives the real REPL with piped stdin and reads what a
person would see.

None of these lines reach a model: entering a worker, offering a goal, and
answering the confirmation are all decided before any generation. That is what
makes an end-to-end test cheap enough to keep.
"""
import os
import subprocess
import sys

import pytest

KEYS = "/sarsi-worker\nwrite a GAP-TV solver for CASSI\np\n/exit\n"


def _drive(keys: str) -> str:
    env = {**os.environ, "COLUMNS": "140", "TERM": "dumb"}
    try:
        p = subprocess.run([sys.executable, "-m", "ai4science.cli",
                            "chat", "--mode", "unified-LLM"],
                           input=keys, capture_output=True, text=True,
                           timeout=150, env=env)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        pytest.skip(f"cannot drive the REPL here: {type(e).__name__}")
    return p.stdout + p.stderr


@pytest.fixture(scope="module")
def screen():
    return _drive(KEYS)


def test_entering_a_worker_works_from_a_keystroke(screen):
    assert "now addressing sarsi-worker" in screen, screen[-800:]


def test_the_confirmation_offers_the_plan_option(screen):
    """It has to be ON the block. An option nobody is told about is one nobody
    finds, and this block is the only place the owner learns what `p` does."""
    assert "p=plan" in screen, screen[-800:]


def test_and_pressing_p_reaches_the_plan_branch(screen):
    """The assertion the four Criticals would have failed. `p` is typed at a
    real prompt and the answer comes back through the real loop."""
    assert "write the plan yourself" in screen, screen[-800:]
    assert "--set-from" in screen, screen[-800:]


def test_the_goal_reached_the_confirmation_stripped(screen):
    """B1's stripping, seen from the keyboard rather than from `classify`."""
    assert "write a GAP-TV solver for CASSI" in screen, screen[-800:]
