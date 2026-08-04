"""`HANDOFF.md` — what the next session needs, written before this one ends.

The spec's task layout names it and nothing wrote it, so a stopped and resumed
task started from the plan alone: the next session could not tell which phases
were already verified, what the verifier had objected to, or what the owner had
been asked.

The rule that shapes every line of it: **it records what the RECORD knows, not
what the session believed.** A handoff that says *"I was about to run the
export"* is a guess about a process that has ended — and a confident guess is
exactly what makes the next session redo the wrong half. Where the record is
silent, so is the file.

Three consequences:

  * **verified phases are named, so they are not redone.** This is the whole
    point, and it is only possible because a phase now carries its own verdict.
  * **it holds no secret and no body.** Same rule as the ledger and the
    workspace: a handoff sits in the task folder, and a task folder is not a
    place for a second copy of a credential.
  * **an empty record produces an honest, short file** rather than a padded one.
"""
import pytest

from ai4science.harness.agents.sarsi import (handoff as ho, plan as pl,
                                             registry as reg, session as ses,
                                             task as tsk, verifier as vf,
                                             worker)


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
    return config.agents["work"]


class FakeRuntime:
    engine = "claude"

    def __init__(self):
        self.stopped = []

    def start(self, name, cwd, *, govern, ceiling, env=None, spec=None):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        return {"ok": True}

    def stop(self, name):
        self.stopped.append(name)
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {"ok": True}


TWO = pl.Plan(goal="finish the export",
              phases=[pl.Phase(title="drain the queue",
                               verified_when="the queue length reads 0"),
                      pl.Phase(title="re-run the export",
                               verified_when="export.csv has 1,204 rows")])


def _task(config, agent):
    d = worker.Directive(agent_id=agent.id, goal="finish the export")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), TWO)
    return tsk.start(config, agent, t)


def _running(config, agent, rt):
    return ses.assign(config, agent, _task(config, agent), runtime=rt)


# ── what it carries ───────────────────────────────────────────────────

def test_it_states_the_goal(config, agent):
    assert "finish the export" in ho.render(config, agent, _task(config, agent))


def test_it_names_the_phases_already_verified(config, agent):
    """The whole point: the next session must not redo them."""
    t = _task(config, agent)
    t = tsk.record_phase(config, agent, t, 0,
                         vf.parse("PASS: the console shows 0"))
    text = ho.render(config, agent, tsk.get(config, agent, t.id))
    assert "drain the queue" in text
    assert "do not redo" in text.lower() or "already verified" in text.lower()


def test_it_names_where_the_work_actually_is(config, agent):
    t = _task(config, agent)
    t = tsk.record_phase(config, agent, t, 0, vf.parse("PASS: done"))
    text = ho.render(config, agent, tsk.get(config, agent, t.id))
    assert "re-run the export" in text


def test_it_carries_the_last_verdicts_objection(config, agent):
    t = _task(config, agent)
    t.verdict = vf.parse("FAIL: export.csv has 0 rows, not 1204")
    tsk._touch(agent, t, __import__("time").time)
    text = ho.render(config, agent, tsk.get(config, agent, t.id))
    assert "0 rows" in text


def test_it_carries_the_open_questions(config, agent):
    from ai4science.harness.agents.sarsi import ledger
    t = _task(config, agent)
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": t.id, "state": "question",
                   "evidence": ["Q: which directory should I index?",
                                "escalated: the plan does not settle it"]})
    assert "which directory should I index?" in ho.render(config, agent, t)


def test_it_carries_the_grants_the_task_holds(config, agent):
    t = _task(config, agent)
    t.grants = ["read secret mail.read"]
    tsk._touch(agent, t, __import__("time").time)
    assert "mail.read" in ho.render(config, agent, tsk.get(config, agent, t.id))


# ── what it must not carry ────────────────────────────────────────────

def test_it_does_not_guess_what_the_session_was_doing(config, agent):
    """A confident guess about a process that has ended is what makes the next
    session redo the wrong half."""
    text = ho.render(config, agent, _task(config, agent)).lower()
    assert "i was about to" not in text
    assert "in progress" not in text


def test_an_unjudged_phase_is_not_described_as_done(config, agent):
    text = ho.render(config, agent, _task(config, agent))
    assert "do not redo" not in text.lower()


def test_it_holds_no_secret_value(config, agent):
    from ai4science.harness.agents.sarsi import vault
    vault.put(config, "mail.smtp", "hunter2")
    t = _task(config, agent)
    t.grants = ["read secret mail.smtp"]
    tsk._touch(agent, t, __import__("time").time)
    assert "hunter2" not in ho.render(config, agent, tsk.get(config, agent, t.id))


# ── writing it ────────────────────────────────────────────────────────

def test_it_is_written_into_the_task_folder(config, agent):
    t = _task(config, agent)
    path = ho.write(config, agent, t)
    assert path.name == "HANDOFF.md"
    assert path.parent == tsk.dir_of(agent, t.id)
    assert "finish the export" in path.read_text()


def test_stopping_a_task_writes_one(config, agent):
    """The moment the context is about to be lost is the moment it is worth
    having."""
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    ses.stop(config, agent, t, runtime=rt)
    assert (tsk.dir_of(agent, t.id) / "HANDOFF.md").exists()


def test_rewriting_it_replaces_rather_than_appends(config, agent):
    t = _task(config, agent)
    ho.write(config, agent, t)
    ho.write(config, agent, t)
    assert path_count(ho.write(config, agent, t).read_text()) == 1


def path_count(text: str) -> int:
    return text.count("# Handoff")


# ── the next session is told it exists ────────────────────────────────

def test_the_kickoff_points_at_it_when_there_is_one(config, agent):
    t = _task(config, agent)
    ho.write(config, agent, t)
    text = ses.kickoff(tsk.get(config, agent, t.id),
                       tsk.read_plan(config, agent, t), agent)
    assert "HANDOFF.md" in text


def test_the_kickoff_does_not_mention_one_that_does_not_exist(config, agent):
    t = _task(config, agent)
    text = ses.kickoff(t, tsk.read_plan(config, agent, t), agent)
    assert "HANDOFF.md" not in text
