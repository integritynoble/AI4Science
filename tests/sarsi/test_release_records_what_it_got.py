"""`release` must not record a ceiling the session did not get.

    try:
        rt.set_ceiling(name, raised)
    except Exception:
        pass
    if task.session:
        task.session["ceiling"] = raised          # recorded regardless

The raise is what turns A0 into working authority, and the hook reads the LIVE
supervisor record rather than this one. So when it failed the session kept
running at A0 while the board, `attention` and `agents` all showed the raised
ceiling — the owner told a thing that was not true about the one field the
whole ladder rests on.

Same rule as the governance wiring, and as the pane check before it: honoured
or refused, never dropped.
"""
import time

import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             session as ses, task as tsk,
                                             worker as wk)

BODY = "# g\n\n## Phase 1 — do it\nVerified when: out.md exists\n"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


class RT:
    engine = "claude"

    def __init__(self, *, raises=None):
        self.raises = raises
        self.raised_to = None

    def start(self, name, cwd, **kw):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text, **kw):
        return {"ok": True}

    def stop(self, name):
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        if self.raises:
            raise self.raises
        self.raised_to = ceiling
        return {"name": name, "ceiling": ceiling}


def _ready(config, agent):
    d = wk.Directive(agent_id=agent.id, goal="write the report")
    t = tsk.create(config, agent, d)
    (tsk.dir_of(agent, t.id) / "plan0.md").write_text(BODY)
    t = tsk.attach_plan(config, agent, t, pl.parse(BODY))
    t.awaiting = []
    t = ses.assign(config, agent, t, runtime=RT(), installed=lambda: set())
    t.state = tsk.RUNNING
    return tsk._touch(agent, t, time.time)


def test_a_ceiling_that_would_not_raise_is_reported(config):
    agent = config.agents["sarsi-worker"]
    t = _ready(config, agent)
    with pytest.raises(ses.CouldNotRelease, match="ceiling"):
        ses.release(config, agent, t, runtime=RT(raises=OSError("no record")))


def test_and_the_record_still_says_what_the_session_actually_has(config):
    """The dangerous half: recorded regardless, so the board showed the raised
    ceiling while the session went on running at A0."""
    agent = config.agents["sarsi-worker"]
    t = _ready(config, agent)
    before = t.session["ceiling"]
    try:
        ses.release(config, agent, t, runtime=RT(raises=OSError("no record")))
    except ses.CouldNotRelease:
        pass
    assert tsk.get(config, agent, t.id).session["ceiling"] == before


def test_a_caller_error_is_reported_the_same_way(config):
    agent = config.agents["sarsi-worker"]
    t = _ready(config, agent)
    with pytest.raises(ses.CouldNotRelease):
        ses.release(config, agent, t,
                    runtime=RT(raises=AttributeError("no set_ceiling")))


def test_a_release_that_takes_is_unchanged(config):
    agent = config.agents["sarsi-worker"]
    t = _ready(config, agent)
    rt = RT()
    t = ses.release(config, agent, t, runtime=rt)
    assert rt.raised_to == t.session["ceiling"] != "A0"
    assert t.released_at is not None
