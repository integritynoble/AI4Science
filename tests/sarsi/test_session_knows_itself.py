"""What the SESSION is told about its own standing.

From `guide-sarsi-claude-overview.md`, capability 5: "for each node — what is its
object, and how does it use the workspace?" A session that does not know what it
may do bumps into gates instead of planning around them, and the loop has to
nurse it through each one.

The planning brief already carried both: `ws.render(...)` and an explicit "while
planning you are at ceiling A0". The KICKOFF — the brief that starts the actual
work, after release — carried the goal, the plan reference, the phases, the
shared facts and the house rules, but **never said what ceiling the session was
now at or what that permits**. So the session was told what to do and not what
it was allowed to do, at exactly the moment the ceiling had just changed.

`session.py` already records this same lesson about the shared facts:

    Two good rules interacting badly: the single highest-leverage thing an
    owner can do was stripping the session of everything the fleet had learned.
    So the facts ride here too.

Bounded on purpose. The kickoff does not carry the conversation — that is what
keeps a session's context independent of the chat's — so this is the ceiling and
what it permits, not the self-model.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import (registry as reg, session as ses,
                                             task as tsk, worker as wk)


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "s"; root.mkdir(parents=True, exist_ok=True)
    p = reg.config_path(root)
    p.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(p); c.ensure_dirs()
    return c


def _task(config, ceiling="A2"):
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="write a file"))
    t.session = {"name": "sarsi-worker-abcd", "ceiling": ceiling}
    return a, t


def test_the_kickoff_says_what_ceiling_the_session_is_at(config):
    a, t = _task(config, "A2")
    text = ses.kickoff(t, None, a)
    assert "A2" in text, text


def test_and_what_that_ceiling_actually_permits(config):
    """The letter alone answers nothing — that is the whole reason the field
    exists. A session told "A2" and not what A2 means still has to find out by
    being refused."""
    a, t = _task(config, "A2")
    text = ses.kickoff(t, None, a).lower()
    assert "git push" in text or "consequential" in text, text


def test_a0_says_the_restrictive_thing_not_a_permissive_one(config):
    """The dangerous direction. A session that believes it may write when it
    may not will produce a gate at every step and blame the plan."""
    a, t = _task(config, "A0")
    text = ses.kickoff(t, None, a).lower()
    assert "read" in text
    assert "git push" not in text


def test_it_stays_bounded(config):
    """The kickoff does not carry the conversation. This adds the standing, not
    the self-model — a kickoff that grows without limit is the context problem
    the design exists to avoid."""
    a, t = _task(config, "A2")
    text = ses.kickoff(t, None, a)
    standing = [l for l in text.splitlines() if "A2" in l]
    assert len(standing) <= 2, standing


def test_a_session_with_no_recorded_ceiling_says_nothing_about_it(config):
    """Silence rather than a guess: an invented ceiling is worse than none,
    because the session would plan against it."""
    a, t = _task(config)
    t.session = {"name": "sarsi-worker-abcd"}      # no ceiling recorded
    text = ses.kickoff(t, None, a)
    assert "A0" not in text and "A1" not in text and "A2" not in text
