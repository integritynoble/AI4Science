"""Found by holding a conversation with the door, one turn at a time.

`tools/sarsi-examples/ten_conversations.py` walks ten turns through
`chat.handle` — the same entry the CLI, the REPL, and the web gateway call —
and counts what each turn spends. Everything here came out of that walk.
"""
import pytest

from ai4science.harness.agents.sarsi import (chat, registry as reg,
                                             session as ses, task as tsk,
                                             worker as wk)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


@pytest.fixture
def agent(config):
    return config.agents["sarsi-worker"]


# ── a name two callers still use, and nothing defines ───────────────────────

def test_session_exposes_the_runtime_resolver_its_callers_call():
    """`chat._guided` and `retry.hand_back` both call `ses.runtime_for`.

    It was renamed to the private `_rt` and neither call site followed, so both
    raise `AttributeError` the moment their `runtime` argument is None — which
    is every call that does not come from a test handing one in. Nothing in the
    suite noticed, because every test passes its own runtime."""
    assert callable(getattr(ses, "runtime_for", None)), (
        "session.runtime_for is called from chat.py and retry.py")


def test_a_plain_line_inside_a_task_does_not_crash_the_door(config, agent):
    """The web gateway calls `chat.handle` with no runtime at all
    (`gateway.py`), so a plain line typed while standing in a task went
    straight into `ses.runtime_for` and raised `AttributeError` — a traceback
    where a steer should have been.

    Reproduced live on 2026-08-24: turn 07 of the conversation walk filed a
    task from plain prose, the door stood in it, and turn 08 died.
    """
    t = tsk.create(config, agent, wk.Directive(agent_id=agent.id, goal="do it"))
    t.session = {"name": "sarsi-worker-x", "transport": "tmux"}
    tsk._save(agent, t)
    chat.handle(config, agent, f"/{t.id}", surface="cli")   # stand in it

    out = chat.handle(config, agent, "use the other solver", surface="cli")
    assert isinstance(out, str) and out.strip()


def test_the_resolver_still_answers_with_a_runtime_when_given_one(config, agent):
    """Restoring the name must not take the injection point away: a caller that
    hands in a runtime gets that one back, session or no session."""
    t = tsk.create(config, agent, wk.Directive(agent_id=agent.id, goal="do it"))
    mine = object()
    assert ses.runtime_for(t, mine) is mine
    assert ses.runtime_for(t) is not None


# ── a page about what it IS, answering a question about what HAPPENED ───────

@pytest.mark.parametrize("line", [
    "what did I ask you to do about the GAP-TV solver?",
    "what did you find in the benchmark last week?",
    "which solver did I tell you to use?",
])
def test_a_question_about_the_past_is_not_a_question_about_the_self(line):
    """`is_about_self` runs AHEAD of any generation, on purpose: a question
    about the worker is answered from measured state rather than narrated. The
    predicate was too wide — "you" is a self word and "what" is in `_ABOUT`, so
    every past-tense question containing both got the canned self-model page.

    Measured live on 2026-08-24: turn 07 of the conversation walk asked what
    the owner had asked for, and got "sarsi-worker — what I am, what I can do,
    and how I know". The self-model is a measurement of NOW; it has no answer
    about the past, and the docstring already named this exact failure."""
    from ai4science.harness.agents.sarsi import selfaware as sa
    assert not sa.is_about_self(line)


@pytest.mark.parametrize("line", [
    "what can you do", "who are you", "what are you", "what is your ceiling",
    "what tasks are you holding", "can you edit files",
    "are you able to run pytest",
])
def test_and_a_question_about_the_self_still_is(line):
    """The other half. Narrowing a predicate is only correct if what it existed
    for still passes — otherwise a measured answer is replaced by a narrated
    one, which is the failure in the opposite direction."""
    from ai4science.harness.agents.sarsi import selfaware as sa
    assert sa.is_about_self(line)


# ── `do that`: resolved, then thrown away ──────────────────────────────────

def test_an_elliptical_instruction_says_what_it_takes_the_line_to_mean(
        config, agent):
    """Plan §11.2: "`do that` resolves its referent from recent dialogue before
    routing". The router did — it read the referent off the recent window and
    routed the turn up to ACTION, exactly as failing-upward requires. The door
    then discarded both and replied "I could not tell whether that is a goal",
    which is not true of a turn it could place well enough to escalate."""
    from ai4science.harness.agents.sarsi import log as _log
    _log.append(agent.agent_dir, "cli", "write a script that deletes stale rows",
                "[sarsi-worker] noted", task_id="")

    out = chat.handle(config, agent, "do that", surface="cli")

    assert "could not tell" not in out
    assert "stale rows" in out, out
    assert "/new" in out, "the offer stays explicit — it must not file on its own"


def test_but_it_still_does_not_file_anything_by_itself(config, agent):
    """An elliptical instruction is the one place a referent can be resolved to
    the wrong turn, so naming it must not become acting on it. This door never
    files from plain prose."""
    from ai4science.harness.agents.sarsi import log as _log
    _log.append(agent.agent_dir, "cli", "delete the stale rows",
                "[sarsi-worker] noted", task_id="")
    before = len(tsk.all_of(config, agent))

    chat.handle(config, agent, "do that", surface="cli")

    assert len(tsk.all_of(config, agent)) == before


# ── the decisions with no record were the ones that mattered ────────────────

@pytest.mark.parametrize("line,why", [
    ("hello", "a greeting"),
    ("can you commit the fix?", "a request refused as something to DO"),
    ("that was wrong, use the other solver", "a correction"),
    ("build a loader for the raw scans", "a directive that gets filed"),
])
def test_a_turn_the_door_answers_itself_still_records_how_it_routed(
        config, agent, line, why):
    """§11.2: the router's decision is recorded in the context manifest.

    It was — but only when the gate ran, and the gate does not run for a turn
    the door answers and returns. Measured on the ten-turn walk: five of ten
    left no row, and every ACTION-handled turn was among them. The decisions
    with no record were the consequential ones."""
    from ai4science.harness.agents.sarsi import selfaware as sa
    before = len(sa.manifest(agent.agent_dir))

    chat.handle(config, agent, line, surface="cli")

    rows = sa.manifest(agent.agent_dir)
    assert len(rows) > before, f"{why} left no routing record"
    assert rows[-1].get("mode"), f"{why} recorded a row with no mode"
    assert rows[-1]["route"].get("why"), "and no reason for it"
    assert rows[-1].get("router_version"), (
        "a replay that cannot tell which router decided cannot separate a "
        "routing bug from a retrieval bug")


def test_a_route_only_row_does_not_claim_a_snapshot_it_never_took(
        config, agent):
    """The row carries no bytes because the turn assembled none — that zero IS
    the measurement. `replay` returns None for it, correctly: there is nothing
    to replay, and a row claiming otherwise would be worse than no row."""
    from ai4science.harness.agents.sarsi import selfaware as sa
    chat.handle(config, agent, "hello", surface="cli")

    row = sa.manifest(agent.agent_dir)[-1]
    assert row["byte_count"] == 0 and not row["gz_path"] and not row["sha256"]
    assert sa.replay(agent.agent_dir, row["context_id"]) is None
