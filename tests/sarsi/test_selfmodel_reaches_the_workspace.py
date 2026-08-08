"""The self-model must change the CONTEXT, not deliver a pep talk.

From `Response_as_Action_A_Plain_Explanation.pdf`:

    The workspace **is** the context window. It is the text in the context
    window, item for item. Whatever is in it exists; whatever is not, does not
    — however true, however recently learned, however clearly written in a file
    the agent did not open.

    A lesson can be correct, written down, stored, indexed, and completely
    inert, because nothing put it in front of the model at the moment it
    mattered.

    The self-model enters here, and **only** here. It does not tell the agent to
    be careful — that would be a pep talk, and pep talks are bottom-rung
    evidence.

That is exactly what was missing. `selfaware`, `competence` and `forecast` all
answered questions *to the owner* and reached the session not at all: the worker
could say "I am overconfident" to a human and never to the model about to write
the next plan.

The same document reports nine measured experiments on what form the material
must take:

    lesson present vs absent                 0/6 → 6/6   large
    retrieved by key vs just listed          no difference
    buried among 99 other lessons            no difference
    a one-line title instead of the episode  no difference

**Putting it in the context at all is the whole effect.** So this is a few
lines, not a digest, and no retrieval machinery is built — the paper withdrew
that mechanism for costing an extra draft per turn and paying nothing.

And the qualifier, which decides what belongs: expect it to matter "only where
the lesson is a fact about your repository that the model cannot work out — on
general good practice it is already right without help." An L3/L4 record is
exactly such a fact. "Be careful" is not.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import (forecast as fc, registry as reg,
                                             task as tsk, worker as wk,
                                             workspace as ws)


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "s"; root.mkdir(parents=True, exist_ok=True)
    p = reg.config_path(root)
    p.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(p); c.ensure_dirs()
    return c


def _judged(config, agent, p, state, n=1):
    for _ in range(n):
        t = tsk.create(config, agent, wk.Directive(agent_id=agent.id, goal="g"))
        fc.record(config, agent, t, p)
        t.verdict = {"state": state, "independent": True}
        tsk._save(agent, t)
    return t


def test_a_measured_record_reaches_the_session(config):
    """The whole point. It was answerable to a human and invisible to the model
    that writes the next plan."""
    a = config.agents["sarsi-worker"]
    _judged(config, a, 0.9, "FAIL", n=4)
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="new work"))
    text = ws.render(config, a, t)
    assert "Brier" in text or "overconfident" in text.lower(), text


def test_what_it_has_proven_reaches_it_too(config):
    a = config.agents["sarsi-worker"]
    _judged(config, a, 0.5, "FAIL", n=3)
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="new work"))
    text = ws.render(config, a, t)
    assert "verified outcome" in text, text


def test_a_worker_with_no_record_says_nothing_rather_than_reassuring_itself(config):
    """An unmeasured worker must not put "no verified outcomes yet" in front of
    the model as though it were a finding. Absence of evidence is not a lesson,
    and filling the slot with it is the wallpaper the paper warns about."""
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    text = ws.render(config, a, t)
    assert "no verified outcomes" not in text.lower(), text
    assert "no forecasts scored" not in text.lower(), text


def test_it_is_a_few_lines_and_not_a_digest(config):
    """Nine experiments found a one-line title works as well as the full
    episode, and that burying it among 99 others costs nothing. So the budget
    is spent on PRESENCE, not on length."""
    a = config.agents["sarsi-worker"]
    _judged(config, a, 0.9, "FAIL", n=6)
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    text = ws.render(config, a, t)
    block = [l for l in text.splitlines()
             if "brier" in l.lower() or "verified outcome" in l.lower()]
    assert 0 < len(block) <= 3, block


def test_it_is_not_a_pep_talk(config):
    """"Be careful" is bottom-rung evidence and the model is already right about
    general good practice without help. Only the measured facts go in."""
    a = config.agents["sarsi-worker"]
    _judged(config, a, 0.9, "FAIL", n=4)
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    text = ws.render(config, a, t).lower()
    for pep in ("be careful", "take your time", "double-check", "try your best"):
        assert pep not in text, pep
