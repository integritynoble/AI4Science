"""A finished-task document must not imply an outcome it cannot show.

`export.py` renders §12's document. Its verdict section was conditional --
`if task.verdict:` -- so a task archived with NO verdict produced a document
with no verdict section at all, which reads exactly like one that finished
well. A reader cannot tell "succeeded" from "nothing was recorded".

That is the same failure `spawn()` was fixed for: `unknown` exists there as a
REAL answer precisely so absence is never reported as a negative. A document is
read by a person months later, with less context than the code had, so the
asymmetry matters more here, not less.
"""
import json
import pytest

from ai4science.harness.agents.sarsi import (export, task as tsk,
                                             registry as reg, worker as wk)


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "s"
    root.mkdir(parents=True, exist_ok=True)
    p = reg.config_path(root)
    p.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(p)
    c.ensure_dirs()
    return c


def _task(config, *, verdict):
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="write the guide"),
                   backend="sarsi-ai4sci")
    t.verdict = verdict
    return a, t


def test_a_missing_verdict_says_so(config):
    """The whole point: absence is stated, not left blank."""
    a, t = _task(config, verdict=None)
    text = export.render(config, a, t).lower()
    assert "no verdict was recorded" in text


def test_a_recorded_verdict_is_still_rendered(config):
    """The honest-absence branch must not swallow a real verdict."""
    a, t = _task(config, verdict={"state": "passed", "reason": "criteria met"})
    text = export.render(config, a, t)
    assert "PASSED" in text
    assert "criteria met" in text
    assert "No verdict was recorded" not in text
