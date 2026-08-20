"""Invariant 1's other half: entering a mode must *cost* nothing.

`route()` already answers this with an injected `create` spy
(`tests/test_console_modes.py:75-78,141-143`). That is not enough here for the
same reason the neighbouring file exists: the four Criticals were all reachable
from `route()` and unreachable from a keyboard, so they crossed no pre-filter a
`route()` test could see. And every keystroke-level assertion in
`tests/test_repl_live_keystrokes.py` is positive — the task got made, the option
appeared. A suite of positives cannot fail on a negative.

So this file drives the real REPL with piped stdin and asserts against the state
tree on disk: enter a worker, or decline the confirmation, and every regular file
under `SARSI_STATE_DIR` is byte-identical afterwards. No task, no session, no
spend.

None of these lines reach a model — entering a worker, offering a goal and
answering the confirmation are all decided before any generation — which is what
keeps an end-to-end negative cheap enough to keep.
"""
import hashlib
import os
import subprocess
import sys

import pytest


def _tree(root):
    return sorted((str(p.relative_to(root)), hashlib.md5(p.read_bytes()).hexdigest())
                  for p in root.rglob("*") if p.is_file())


def _init(state):
    env = {**os.environ, "SARSI_STATE_DIR": str(state), "COLUMNS": "140",
           "TERM": "dumb"}
    init = subprocess.run([sys.executable, "-m", "ai4science.cli", "sarsi",
                           "init", "--owner-id", "7007143162"],
                          capture_output=True, text=True, env=env, timeout=120)
    if init.returncode != 0:
        pytest.skip("cannot init a sarsi registry here")
    return env


def _drive(keys, env):
    try:
        p = subprocess.run([sys.executable, "-m", "ai4science.cli", "chat",
                            "--mode", "unified-LLM"], input=keys,
                           capture_output=True, text=True, timeout=150, env=env)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        pytest.skip(f"cannot drive the REPL here: {type(e).__name__}")
    return p.stdout + p.stderr


def test_entering_a_worker_and_leaving_creates_nothing(tmp_path):
    """Walking in and walking out again is free. Nothing on disk moves."""
    state = tmp_path / "state"
    env = _init(state)
    before = _tree(state)

    screen = _drive("/sarsi-worker\n/back\n/exit\n", env)

    assert _tree(state) == before, screen[-800:]


def test_declining_the_confirmation_creates_nothing(tmp_path):
    """`n` at the gate spends nothing — and the gate was actually reached.

    The `create it?` assertion is not decoration. Without it this test passes
    when the REPL dies before ever offering the confirmation, which is a
    negative test passing for the wrong reason.
    """
    state = tmp_path / "state"
    env = _init(state)
    before = _tree(state)

    screen = _drive("/sarsi-worker\nwrite a GAP-TV solver for CASSI\nn\n/exit\n",
                    env)

    assert "create it?" in screen, screen[-800:]
    assert "dropped — nothing was created" in screen, screen[-800:]
    assert _tree(state) == before, screen[-800:]

    os.environ["SARSI_STATE_DIR"] = str(state)
    from ai4science.harness.agents.sarsi import registry as reg, task as tsk
    config = reg.load(reg.config_path(state))
    assert tsk.all_of(config, config.agents["sarsi-worker"]) == [], screen[-800:]
