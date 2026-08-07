"""What a worker can truthfully say about itself.

`Agent.self_aware` has been a `bool` that `admin` reports and `playbook` lists
as an authority field, and that **nothing reads**. So the worker could not
answer "what am I, what may I do at this ceiling, what am I holding" — which is
why `can you plan at A2?` became a task goal instead of an answer. It had
nothing to answer *from*.

Modelled on the console's `selfmodel.py`, whose discipline is the point:

    Claims are DERIVED AT READ TIME from stores that already exist … Nothing
    here fabricates: an empty store yields an honest "no verified outcomes
    recorded yet" claim.

So every claim here names the store it came from and its authority level, and a
worker with no history says so rather than inventing one. A self-model that
narrates is worse than none: it reads like evidence.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import (registry as reg, selfaware,
                                             task as tsk, worker as wk)


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "s"; root.mkdir(parents=True, exist_ok=True)
    p = reg.config_path(root)
    p.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(p); c.ensure_dirs()
    return c


# ── the claims, each linked to a store ────────────────────────────────

def test_every_claim_names_its_store_and_authority(config):
    """The whole discipline in one assertion. A claim with no provenance is a
    sentence, and a sentence that looks like evidence is the failure mode this
    is built to avoid."""
    a = config.agents["sarsi-worker"]
    for c in selfaware.claims(config, a):
        assert c["field"] and c["store"], c
        assert 1 <= c["authority_level"] <= 7, c
        assert c["authority"], c


def test_it_knows_who_it_is_from_the_registry(config):
    a = config.agents["sarsi-worker"]
    got = {c["field"]: c for c in selfaware.claims(config, a)}
    assert got["id"]["value"] == "sarsi-worker"
    assert got["id"]["authority_level"] == 1, "identity is governance metadata"


def test_it_knows_its_ceiling_and_what_that_permits(config):
    """Not the letter alone. 'A2' answers nothing without what A2 lets it do —
    and the owner asking `can you plan at A2?` wanted the second half."""
    a = config.agents["sarsi-worker"]
    got = {c["field"]: c for c in selfaware.claims(config, a)}
    assert got["ceiling"]["value"] == a.ceiling
    permits = got["permits"]["value"].lower()
    assert "write" in permits


def test_a_ceiling_it_asked_for_but_did_not_get_is_reported_as_such(config):
    """A3 is earned, not set. A worker that reports the registry's A3 while
    running at A2 is describing a permission it does not have."""
    a = config.agents["sarsi-worker"]
    a.ceiling = "A3"
    got = {c["field"]: c for c in selfaware.claims(config, a)}
    assert got["ceiling"]["value"] == "A3"
    assert got["effective_ceiling"]["value"] in ("A2", "A3")
    if got["effective_ceiling"]["value"] == "A2":
        assert "earn" in got["effective_ceiling"]["provenance"].lower()


def test_it_knows_what_it_is_holding(config):
    a = config.agents["sarsi-worker"]
    tsk.create(config, a, wk.Directive(agent_id=a.id, goal="one"))
    got = {c["field"]: c for c in selfaware.claims(config, a)}
    assert got["tasks"]["value"] >= 1
    assert got["tasks"]["authority_level"] == 2, "runtime instrumentation"


def test_an_empty_worker_says_so_rather_than_inventing(config):
    """The honest-empty rule, borrowed verbatim in spirit from selfmodel.py."""
    a = config.agents["sarsi-worker"]
    got = {c["field"]: c for c in selfaware.claims(config, a)}
    assert got["tasks"]["value"] == 0
    text = selfaware.describe(config, a)
    assert "no task" in text.lower() or "0 task" in text.lower(), text


def test_it_does_not_claim_to_execute(config):
    """The invariant the whole system rests on: the agent you talk to does not
    execute. A self-model that forgets this is the one that matters."""
    text = selfaware.describe(config, a_worker(config)).lower()
    assert "does not execute" in text or "not execute" in text


def a_worker(config):
    return config.agents["sarsi-worker"]


# ── the flag finally means something ──────────────────────────────────

def test_the_self_aware_flag_is_honoured(config):
    """It existed, was reported by `admin`, listed by `playbook` as an authority
    field, and read by nothing. A flag nobody reads is a claim nobody keeps."""
    a = config.agents["sarsi-worker"]
    a.self_aware = False
    assert selfaware.describe(config, a) == ""


# ── answering a question about itself ─────────────────────────────────

@pytest.mark.parametrize("question", [
    "can you plan at A2?",
    "what are you?",
    "what can you do?",
    "which tasks are you holding?",
    "what is your ceiling?",
])
def test_a_question_about_itself_is_recognised(question):
    assert selfaware.is_about_self(question), question


@pytest.mark.parametrize("question", [
    "what is the capital of France?",
    "how does GAP-TV work?",
    "why is the sky blue?",
])
def test_and_a_question_about_the_world_is_not(question):
    """A router that guesses is worse than one that is quiet: a question this
    cannot answer from its own state must reach the model, not a canned page."""
    assert not selfaware.is_about_self(question), question
