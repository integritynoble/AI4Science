"""A verdict is not unmade by a message that could not be delivered.

Found while wiring plan v3: `guide()` raised `UnboundLocalError` on every call
— a local `import router as _rt` shadowed the module-level `_rt()` that
resolves the runtime — and the deterministic FAIL path of `_verify_phase` ends
in `guide()`. The whole branch sat inside `except Exception: pass`, so a
recorded FAIL was unwound and the turn fell through to the LLM verifier, which
said PASS.

Two failures, and only together did they hurt: a steering bug turned every
deterministic FAIL into a model's opinion. Both halves are pinned here — the
guide call itself, and the verdict surviving a steer that cannot land.
"""
import pathlib
import time

import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
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


class Runtime:
    def __init__(self):
        self.sent, self.stopped = [], []

    def start(self, name, cwd, **kw):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        self.sent.append((name, text))
        return {"ok": True}

    def stop(self, name):
        self.stopped.append(name)
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {"name": name, "ceiling": ceiling}


PLAN = ("# write the report\n\n## Phase 1 — write it\nDo the thing.\n"
        "Verified when: out.txt exists\n\n## Permissions needed\n- none\n")


def _task(config, agent, rt=None):
    d = wk.Directive(agent_id=agent.id, goal="write the report")
    t = tsk.create(config, agent, d)
    (tsk.dir_of(agent, t.id) / "plan0.md").write_text(PLAN)
    t = tsk.attach_plan(config, agent, t, pl.parse(PLAN))
    t.plan_agreed = True
    if rt is not None:
        t = ses.assign(config, agent, t, runtime=rt, installed=lambda: set())
        t.work_started_at = time.time()
    return tsk._touch(agent, t, time.time)


def test_the_owner_can_steer_a_session_at_all(config, agent):
    """The shadowing bug: every `guide()` raised before a keystroke was sent."""
    rt = Runtime()
    t = _task(config, agent, rt)
    ses.guide(config, agent, t, "try the other approach", by_owner=True,
              runtime=rt)
    assert rt.sent and rt.sent[-1][1] == "try the other approach"


def test_a_deterministic_fail_is_recorded_when_the_steer_cannot_land(config, agent):
    """No session to steer. The check still ran, and what it found stands."""
    t = _task(config, agent)                    # never assigned: no session
    out = ses._verify_phase(config, agent, t, verifier=_never_called,
                            evidence="I say it is done", engine="claude",
                            index=0, now=time.time)
    assert out.phase_verdicts["0"]["state"] == "FAIL"
    assert out.phase_verdicts["0"]["engine"] == "deterministic"


def test_and_the_model_verifier_is_never_consulted_about_it(config, agent):
    """A criterion a check can settle is not a matter of opinion."""
    t = _task(config, agent)
    ses._verify_phase(config, agent, t, verifier=_never_called,
                      evidence="I say it is done", engine="claude", index=0,
                      now=time.time)
    assert _never_called.calls == 0


def test_a_satisfied_criterion_passes_through_the_same_path(config, agent):
    t = _task(config, agent)
    (ses.work_dir_for(agent, t) / "out.txt").write_text("done\n")
    out = ses._verify_phase(config, agent, t, verifier=_never_called,
                            evidence="", engine="claude", index=0,
                            now=time.time)
    assert out.phase_verdicts["0"]["state"] == "PASS"
    assert out.phase_verdicts["0"]["independent"] is True


def test_the_work_dir_has_exactly_one_answer(config, agent):
    """The check looks in one place; a caller that guesses another is asking
    about a different directory than the verifier reads.

    A task carries `work_root` from creation, so the declared root — not the
    task folder — is where artifacts land, and it was guessing THAT wrong
    which made three fixtures write `out.txt` somewhere nothing reads."""
    t = _task(config, agent)
    assert t.work_root                                   # set at creation
    assert ses.work_dir_for(agent, t) == pathlib.Path(t.work_root).resolve()
    t.work_root = ""
    assert ses.work_dir_for(agent, t) == tsk.dir_of(agent, t.id)


class _NeverCalled:
    calls = 0

    def __call__(self, **kw):
        type(self).calls += 1
        return {"state": "PASS", "why": "looks fine to me"}


_never_called = _NeverCalled()
