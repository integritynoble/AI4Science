"""The turn is priced before it is answered. [plan v3 §7.0, §11.2]

`hello` and `implement M2` used to cost the same thing, because there was
nothing in the worker that could tell them apart before assembling context.
These are the tests for the thing that now can — and the ones that matter most
are the negative ones: an instruction must never be answered as conversation
because a classifier was unsure.
"""
import pytest

from ai4science.harness.agents.sarsi import (chat, discourse, mode,
                                             registry as reg, selfaware as sa)


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


def _buf(*pairs):
    return discourse.Buffer(
        exchanges=[{"exchange_id": f"x{i}", "at": "2026-08-22T00:00:00+00:00",
                    "in": a, "out": b} for i, (a, b) in enumerate(pairs)],
        total=len(pairs))


# ── the fast path ─────────────────────────────────────────────────────────────

def test_a_greeting_is_chat():
    assert mode.route("hello").mode == mode.CHAT


def test_an_ordinary_question_is_chat():
    assert mode.route("what is a Kalman filter?").mode == mode.CHAT


def test_a_local_follow_up_is_chat_and_resolves_from_recent_dialogue():
    """`why?` must not search long-term memory for the word `why`. [§6.6]"""
    buf = _buf(("how does hybrid retrieval work?",
                "it unions lexical and semantic candidates, then reranks."))
    r = mode.route("why?", buf=buf)
    assert r.mode == mode.CHAT
    assert r.referent == "how does hybrid retrieval work?"
    assert "hybrid retrieval" in r.query
    assert not r.asks_older


def test_continue_is_a_follow_up_not_an_instruction():
    buf = _buf(("what does the gate do?", "it assembles W_t once per turn."))
    assert mode.route("continue", buf=buf).mode == mode.CHAT


def test_but_continue_after_an_instruction_is_still_that_instruction():
    """`continue` following `write the solver` means keep going with the WORK.
    A discourse follow-up is cheap only while what it follows was cheap."""
    buf = _buf(("write the GAP-TV solver", "opened tsk_ab12 and started it"))
    assert mode.route("continue", buf=buf).mode == mode.ACTION


def test_a_deliberative_question_is_reason():
    r = mode.route("how does the semantic arm compare to lexical retrieval?")
    assert r.mode == mode.REASON


def test_an_explicit_old_memory_question_is_reason():
    r = mode.route("what did we decide yesterday about embeddings?")
    assert r.mode == mode.REASON
    assert r.asks_older


# ── the one-way valve ─────────────────────────────────────────────────────────

def test_a_directive_is_action():
    assert mode.route("implement the M2 gate").mode == mode.ACTION


def test_a_polite_request_wearing_a_question_mark_is_still_action():
    """`can you create a task for X?` ends in `?`. It is an instruction."""
    r = mode.route("can you create a task for GAP-TV?")
    assert r.mode == mode.ACTION


def test_an_unplaceable_line_routes_up_never_down():
    r = mode.route("GAP-TV solver for CASSI")
    assert r.mode == mode.ACTION
    assert r.escalated


def test_do_that_inherits_the_weight_of_what_it_points_at():
    """The referent is the instruction; the pronoun is just shorter."""
    buf = _buf(("create a task to port the solver", "opened tsk_ab12"))
    r = mode.route("do that", buf=buf)
    assert r.mode == mode.ACTION
    assert r.referent == "create a task to port the solver"


def test_a_plain_line_inside_a_task_is_action_because_it_is_keystrokes():
    r = mode.route("looks good", cursor=True)
    assert r.mode == mode.ACTION


def test_asking_about_a_past_act_is_not_asking_for_one():
    """`why did you commit that?` names a side-effect verb and is a question."""
    r = mode.route("why did you commit that?")
    assert r.mode != mode.ACTION


def test_mutating_and_read_only_slashes_are_told_apart():
    assert mode.route("/new write a solver").mode == mode.ACTION
    assert mode.route("/tasks").mode == mode.CHAT
    assert mode.route("/archive tsk_ab12").mode == mode.ACTION


def test_the_router_never_downgrades_an_action_when_it_is_unsure():
    """Every line here carries side-effecting language in request position.
    Whatever the classifier made of them, none may land on the fast path."""
    for line in ("please delete the stale rows",
                 "could you deploy the exporter",
                 "go ahead and commit it",
                 "let's archive tsk_ab12",
                 "i want you to run the benchmark"):
        assert mode.route(line).mode == mode.ACTION, line


# ── the gate charges the routed price ─────────────────────────────────────────

def test_chat_mode_does_not_measure_the_self_model(config, agent, monkeypatch):
    """A greeting must not pay for a live probe. [§7.2]"""
    called = []
    from ai4science.harness.agents.sarsi import selfmodel as sm
    monkeypatch.setattr(sm, "sync", lambda *a, **k: called.append(1) or [])
    sa.workspace_context(config, agent, observation="hello",
                         route=mode.route("hello"))
    assert called == []


def test_action_mode_still_measures_the_self_model(config, agent, monkeypatch):
    called = []
    from ai4science.harness.agents.sarsi import selfmodel as sm
    monkeypatch.setattr(sm, "sync", lambda *a, **k: called.append(1) or [])
    sa.workspace_context(config, agent, observation="implement M2",
                         route=mode.route("implement the M2 gate"))
    assert called == [1]


def test_chat_context_is_smaller_than_action_context(config, agent):
    from ai4science.harness.agents.sarsi import log
    for i in range(12):
        log.append(agent.agent_dir, "cli", f"question {i}", f"answer {i}")
    chat_ctx = sa.workspace_context(config, agent, observation="hello",
                                    route=mode.route("hello"))
    action_ctx = sa.workspace_context(config, agent, observation="implement M2",
                                      route=mode.route("implement the M2 gate"))
    assert len(chat_ctx) < len(action_ctx)


def test_chat_mode_keeps_a_bounded_window_not_the_whole_transcript(config, agent):
    """Many turns later, CHAT still carries a window — and says what it left."""
    from ai4science.harness.agents.sarsi import log
    for i in range(400):
        log.append(agent.agent_dir, "cli", f"turn {i} " + "x" * 200,
                   f"reply {i} " + "y" * 200)
    ctx = sa.workspace_context(config, agent, observation="why?",
                               route=mode.route("why?"))
    assert "turn 399" in ctx
    assert "turn 0 " not in ctx
    assert "older not in this window" in ctx


# ── the decision is recorded, so a routing bug replays apart from retrieval ───

def test_the_mode_and_router_version_are_in_the_manifest(config, agent):
    import json
    r = mode.route("hello")
    sa.workspace_context(config, agent, observation="hello", route=r)
    rows = [json.loads(l) for l in
            (agent.agent_dir / "context_manifest.jsonl").read_text().splitlines()]
    last = rows[-1]
    assert last["mode"] == "CHAT"
    assert last["router_version"] == mode.ROUTER_VERSION
    assert last["gate_version"] == sa.GATE_VERSION
    assert last["route"]["why"]
    assert "sections" in last and last["sections"]


# ── the door: answering is not acting ────────────────────────────────────────

def test_a_question_answered_by_the_model_still_files_nothing(config, agent,
                                                              monkeypatch):
    from ai4science.harness.agents.sarsi import reply, task as tsk
    monkeypatch.setattr(reply, "engine",
                        lambda: (lambda prompt: "A Kalman filter is a recursive estimator."))
    out = chat.handle(config, agent, "what is a Kalman filter?", surface="cli")
    assert "recursive estimator" in out
    assert "/new" in out                      # the offer is stated, not taken
    assert tsk.all_of(config, agent) == []    # and nothing was filed


def test_a_question_about_the_worker_never_reaches_the_model(config, agent,
                                                            monkeypatch):
    """`is_about_self` stays ahead of generation: the self-model is measured,
    and a model asked to describe itself narrates."""
    from ai4science.harness.agents.sarsi import reply
    called = []
    monkeypatch.setattr(reply, "engine",
                        lambda: (lambda p: called.append(p) or "I am wonderful."))
    out = chat.handle(config, agent, "what can you do?", surface="cli")
    assert called == []
    assert "wonderful" not in out


def test_with_no_engine_the_door_says_so_rather_than_answering_nothing(config, agent):
    out = chat.handle(config, agent, "how are the exports going?", surface="cli")
    assert "no model engine is reachable" in out
    assert "/new" in out
