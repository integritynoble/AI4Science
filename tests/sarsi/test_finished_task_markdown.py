"""§12: a finished task is written down as a document, not only as a record.

    > sarsi-worker should take down history and finished task. The finished
    > task can be put into md file or others in computer.

C10 records the gap this closes: `archive()` kept a structured record and there
was **no markdown export**, so the half of §12 a person can actually read did
not exist.

Two things the spec leaves to the owner are decided here and stated, because an
implementation cannot avoid choosing:

  Q23 WHERE  the task's own directory, beside the record — a task's history
             should travel with the task rather than living in a second place
             that can drift from it.
  Q24 WHEN   automatically on archive. §12 makes recording the WORKER's job
             ("sarsi-worker should take down history"), not a step a person has
             to remember; a history that depends on someone remembering is the
             one that is missing when it matters.

And per C10 it ACCOMPANIES the record rather than replacing it: the structured
record is what code reads, the document is what a person reads, and losing
either to gain the other would be a bad trade.
"""
import json
import pytest

from ai4science.harness.agents.sarsi import (task as tsk, registry as reg,
                                             worker as wk)


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


def _archive(config, *, verdict):
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="write the guide"),
                   backend="sarsi-ai4sci")
    if verdict is not None:
        t.verdict = verdict
    t = tsk.archive(config, a, t)
    return config, a, t


@pytest.fixture
def archived(config):
    return _archive(config, verdict={"ok": True, "summary": "did the thing"})


@pytest.fixture
def archived_no_verdict(config):
    return _archive(config, verdict=None)


def test_archiving_writes_a_readable_document(archived):
    config, agent, task = archived
    p = tsk.dir_of(agent, task.id) / tsk.FINISHED_NAME
    assert p.exists(), "archive() must write the §12 document"
    text = p.read_text()
    assert task.id in text
    assert task.goal in text


def test_the_structured_record_still_exists(archived):
    """C10: the document accompanies the record. Code reads one, a person the
    other; replacing the record with prose would break every caller."""
    config, agent, task = archived
    rec = tsk.dir_of(agent, task.id) / tsk.RECORD_NAME
    assert rec.exists()
    assert json.loads(rec.read_text())["id"] == task.id


def test_it_names_the_executor_that_ran_it(archived):
    """Which engine ran a task is a fact about the task (backends.py's own
    rule). A history that omits it cannot answer 'what ran this?' later."""
    config, agent, task = archived
    text = (tsk.dir_of(agent, task.id) / tsk.FINISHED_NAME).read_text()
    assert task.backend in text


def test_a_task_with_no_verdict_says_so_rather_than_implying_success(archived_no_verdict):
    """The failure this guards: an archived task with no recorded verdict must
    not read as a completed one. Silence is not success -- the same rule the
    spawn reporting follows."""
    config, agent, task = archived_no_verdict
    text = (tsk.dir_of(agent, task.id) / tsk.FINISHED_NAME).read_text().lower()
    assert "no verdict" in text or "not recorded" in text


def test_export_is_idempotent(archived):
    """Archiving twice must not append a second copy underneath the first."""
    config, agent, task = archived
    p = tsk.dir_of(agent, task.id) / tsk.FINISHED_NAME
    first = p.read_text()
    tsk.archive(config, agent, task)
    assert p.read_text().count("# Finished task") == 1
    assert len(p.read_text()) >= len(first) - 200
