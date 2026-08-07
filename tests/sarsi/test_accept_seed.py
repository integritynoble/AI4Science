"""The owner can accept a seed plan the session never improved.

`collect_plan` refuses a plan identical to the worker's seed — rightly: a
session that ignored the seed has not engaged with it, and collecting it
anyway would launder the worker's own draft as the session's work.

It offers `accept_seed` as the deliberate owner override, and the docstring
says so. But no CLI flag reached it, so a task whose session described a
better plan in its transcript instead of writing one was stuck at `planning`
permanently, with the refusal naming a step the owner could not take.

Found by driving a live sarsi-pwm run to a verdict and being unable to.
"""
import json
import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             session as ses, task as tsk,
                                             worker as wk)


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "s"; root.mkdir(parents=True, exist_ok=True)
    p = reg.config_path(root); p.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(p); c.ensure_dirs(); return c


def _seeded(config):
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="do the thing"))
    t.session = {"name": "sarsi-worker-test"}
    d = wk.Directive(agent_id=a.id, goal="do the thing")
    (tsk.dir_of(a, t.id) / "plan0.md").write_text(pl.draft(d).render())
    return a, t


def test_accept_seed_is_off_by_default(config):
    """The guard's default stands. (Reproducing the seed-identity refusal in a
    fixture needs the real attach/collect round trip; the live evidence is a
    sarsi-pwm task that sat at `planning` with an unimproved plan0.md while the
    loop reported `planning` nine times — which is the condition this flag
    exists to release.)"""
    import inspect
    assert inspect.signature(ses.collect_plan).parameters["accept_seed"].default is False


def test_but_the_owner_can_accept_it_deliberately(config):
    a, t = _seeded(config)
    after = ses.collect_plan(config, a, t, session_idle=True, accept_seed=True)
    assert after.state != tsk.PLANNING


def test_the_cli_exposes_it(config):
    """The gap this closes: the refusal named `accept_seed`, and no command
    could pass it. An escape hatch the owner cannot reach is not a hatch."""
    from typer.testing import CliRunner
    from ai4science.cli import app
    out = CliRunner().invoke(app, ["sarsi", "supervise", "--help"]).output
    assert "--accept-seed" in out
