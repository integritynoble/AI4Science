"""Delegating from the chat REPL to the sarsi worker of the same name.

Switching to `work` with `/agent work` gives you the *chat* agent — it answers
in-process, so asking it for a GAP-TV implementation makes it write one right
there. That is the original ai4science agent doing what it has always done.

The seven sarsi agents are the other door: the agent you talk to does not
execute, it opens a task, agrees a plan with `sarsi-claude`, and that session
drives Claude Code.

`/do` is the bridge between the two, and it is deliberately explicit:

  * **it delegates, it never executes.** `/do` creates the task and returns —
    the goal text is handed to the worker, never run in the REPL process;
  * **it refuses to guess which worker you meant.** From an agent with no sarsi
    counterpart (`general-purpose`, `imaging`) it names the ones that exist
    rather than picking one;
  * **an unconfigured registry says how to configure it** instead of raising
    into the REPL loop, which would drop the session.
"""
from __future__ import annotations

import pytest

from ai4science.harness.repl import _dispatch_slash


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def registry(tmp_path):
    """A real registry on disk — what `ai4science sarsi init` would write."""
    import json

    from ai4science.harness.agents.sarsi import registry as reg
    raw = reg.default_config(owner_id="7007143162")
    (tmp_path / reg.CONFIG_NAME).write_text(json.dumps(raw))
    reg.load().ensure_dirs()
    return tmp_path


def _state(agent: str = "sarsi-worker") -> dict:
    return {"read_only": False, "auto_yes": False, "exit": False, "agent": agent}


# ── /do opens a task on the worker of the same name ───────────────────

def test_do_creates_a_task_on_the_matching_worker(registry):
    from ai4science.harness.agents.sarsi import registry as reg, task as tsk
    handled, msg = _dispatch_slash("/do write a gap-tv algorithm for cassi",
                                   _state("sarsi-worker"))
    assert handled
    config = reg.load()
    goals = [t.goal for t in tsk.all_of(config, config.agents["sarsi-worker"])]
    assert goals == ["write a gap-tv algorithm for cassi"]


def test_do_reports_the_task_id_so_it_can_be_opened(registry):
    from ai4science.harness.agents.sarsi import registry as reg, task as tsk
    _, msg = _dispatch_slash("/do drain the export queue", _state("sarsi-worker"))
    config = reg.load()
    task = tsk.all_of(config, config.agents["sarsi-worker"])[0]
    assert task.id in msg


def test_do_says_the_plan_comes_next_rather_than_claiming_it_is_done(registry):
    """The worker drafts, `sarsi-claude` agrees it, the owner releases it."""
    _, msg = _dispatch_slash("/do ship the thing", _state("sarsi-worker"))
    assert "plan" in msg.lower()


def test_do_does_not_execute_the_goal_itself(registry):
    """The whole point of the bridge: delegation, not another executor."""
    from ai4science.harness.agents.sarsi import registry as reg, task as tsk
    _dispatch_slash("/do rm -rf /tmp/nothing-here", _state("sarsi-worker"))
    config = reg.load()
    task = tsk.all_of(config, config.agents["sarsi-worker"])[0]
    assert task.session is None          # nothing started from the REPL process


def test_a_different_agent_opens_the_task_on_its_own_worker(registry):
    from ai4science.harness.agents.sarsi import registry as reg, task as tsk
    _dispatch_slash("/do draft the thread", _state("social"))
    config = reg.load()
    assert tsk.all_of(config, config.agents["social"])
    assert tsk.all_of(config, config.agents["sarsi-worker"]) == []


# ── /tasks reads the board through the same door ──────────────────────

def test_tasks_lists_the_workers_board(registry):
    _dispatch_slash("/do finish the export", _state("sarsi-worker"))
    handled, msg = _dispatch_slash("/tasks", _state("sarsi-worker"))
    assert handled and "finish the export" in msg


# ── the refusals ──────────────────────────────────────────────────────

def test_do_from_an_agent_with_no_worker_names_the_ones_that_exist(registry):
    """Guessing a worker would file the task under the wrong owner."""
    handled, msg = _dispatch_slash("/do something", _state("general-purpose"))
    assert handled
    assert "sarsi-worker" in msg and "abraham" in msg
    from ai4science.harness.agents.sarsi import registry as reg, task as tsk
    config = reg.load()
    assert all(not tsk.all_of(config, a) for a in config.agents.values())


def test_do_with_no_registry_says_how_to_make_one(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "empty"))
    handled, msg = _dispatch_slash("/do something", _state("sarsi-worker"))
    assert handled and "sarsi init" in msg


def test_do_with_no_goal_asks_for_one_rather_than_filing_an_empty_task(registry):
    from ai4science.harness.agents.sarsi import registry as reg, task as tsk
    handled, msg = _dispatch_slash("/do", _state("sarsi-worker"))
    assert handled and "usage" in msg.lower()
    config = reg.load()
    assert tsk.all_of(config, config.agents["sarsi-worker"]) == []


def test_help_mentions_the_bridge(registry):
    _, msg = _dispatch_slash("/help", _state("sarsi-worker"))
    assert "/do" in msg


# ── the wiring: the live loop knows which agent is active ─────────────

def test_the_running_repl_files_the_task_under_the_agent_in_use(registry, tmp_path,
                                                                monkeypatch):
    """`_dispatch_slash` reads `state["agent"]`, so the loop has to put it
    there — and keep it current when `/agent` switches."""
    import ai4science.harness.repl as repl_mod
    from ai4science.harness.adapters.stub import StubAdapter
    from ai4science.harness.events import Done, TextDelta
    from ai4science.harness.agents.sarsi import registry as reg, task as tsk
    from ai4science.llm import routing

    monkeypatch.setattr(repl_mod, "adapter_for",
                        lambda b: StubAdapter([[TextDelta("hi"), Done("end")]]))
    monkeypatch.setattr(repl_mod, "make_meter", lambda **kw: lambda u: None)
    monkeypatch.setattr(routing, "backend_available", lambda b: True)
    monkeypatch.setattr("ai4science.harness.persistence.save", lambda *a, **k: None)

    inputs = iter(["/do write a gap-tv algorithm for cassi", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))

    repl_mod.run_common_repl(tmp_path, backend="anthropic", model="stub",
                             mode_label="social")

    config = reg.load()
    goals = [t.goal for t in tsk.all_of(config, config.agents["social"])]
    assert goals == ["write a gap-tv algorithm for cassi"]
