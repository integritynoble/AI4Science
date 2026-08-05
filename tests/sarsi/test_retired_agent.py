"""One worker to start with, without deleting what the other one did.

The roster shipped two general workers with the same engine and the same
authority — `sarsi-worker` (catch-all: shell, editor, browser) and `work` (the
job: qupath, matlab, **mail**). The owner wants one to begin with.

Deleting the roster entry would have been the obvious move and is the wrong one:
a roster entry owns its task folder, and `work` holds 32 archived tasks on the
live machine. Removing it makes that history unreachable from every command that
reads it — `tasks --archived`, `plan`, `blast`, `spend` — which is a real loss to
avoid a hypothetical one.

So an agent can be **retired**: out of routing, still readable.

  * **nothing new is routed to it.** `who` does not suggest it, and `do` refuses
    it by name rather than accepting work nobody will supervise.
  * **its history stands.** Its folder, its plans, its verdicts and its spend are
    read exactly as before, because they are the record of what it actually did.
  * **it is visible as retired**, not missing. An agent that vanished from
    `agents` would leave the owner wondering whether the machine lost it.
  * **`mail` does not move.** The surviving worker keeps shell, editor and
    browser. A single do-everything agent that also reads the mailbox is the
    concentration the seven-agent split exists to prevent, and mail is the tool
    most likely to carry someone else's instructions into a session.
"""
import pytest

from ai4science.harness.agents.sarsi import registry as reg


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


# ── the roster now has one general worker ─────────────────────────────

def test_work_is_retired(config):
    assert config.agents["work"].retired is True


def test_the_surviving_worker_is_the_catch_all(config):
    assert config.agents["sarsi-worker"].retired is False


def test_it_did_not_inherit_mail(config):
    """The one capability whose absence is doing real work."""
    assert "mail" not in config.agents["sarsi-worker"].tools
    assert set(config.agents["sarsi-worker"].tools) == {"shell", "editor",
                                                        "browser"}


def test_the_specific_agents_are_untouched(config):
    """This is about the two GENERAL workers. `social`, `funding`, `jobs` and
    `abraham` exist so that different kinds of data do not mix, which is a
    different question from having two catch-alls."""
    for name in ("social", "funding", "jobs", "abraham"):
        assert config.agents[name].retired is False


# ── nothing new is routed to it ───────────────────────────────────────

def test_workers_does_not_offer_a_retired_agent(config):
    assert "work" not in [a.id for a in config.workers()]


def test_who_does_not_suggest_it(config):
    from ai4science.harness.agents.sarsi import triage
    picked = triage.suggest(config, "fix the failing test in the repo")
    assert "work" not in [c.agent_id for c in picked.candidates]
    assert picked.best is None or picked.best.agent_id != "work"


def test_and_it_still_picks_the_surviving_worker(config):
    """Retiring one must not leave a demand with nobody to take it.

    `work` carried the general-work vocabulary and `sarsi-worker` shipped with
    none, so retiring it silently would strand every "fix the repo" demand on
    "I cannot tell" — a worse answer than the one it replaced.
    """
    from ai4science.harness.agents.sarsi import triage
    picked = triage.suggest(config, "fix the failing test in the repo")
    assert picked.best is not None
    assert picked.best.agent_id == "sarsi-worker"


def test_but_the_mail_words_did_not_come_across(config):
    """The vocabulary follows the capability. Routing a mailbox demand to an
    agent with no mailbox would be a confident wrong answer, and this module
    exists to prefer "I cannot tell" to one of those."""
    from ai4science.harness.agents.sarsi import triage
    for word in ("email", "mailbox"):
        assert word not in (config.agents["sarsi-worker"].about or [])
    picked = triage.suggest(config, "clear out the mailbox")
    assert picked.best is None or picked.best.agent_id != "sarsi-worker"


# ── but its history stands ────────────────────────────────────────────

def test_the_agent_is_still_loadable(config):
    """Every command that reads history needs the Agent to resolve its folder."""
    assert config.agents["work"].id == "work"
    assert config.agents["work"].tasks.parent.name == "work"


def test_its_tasks_are_still_readable(config):
    from ai4science.harness.agents.sarsi import plan as pl, task as tsk, worker
    agent = config.agents["work"]
    d = worker.Directive(agent_id=agent.id, goal="something it did before")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    tsk.archive(config, agent, t)
    assert [x.id for x in tsk.all_of(config, agent, archived=True)] == [t.id]


def test_its_spend_is_still_counted(config):
    """It is the record of real cost. A total that fell when an agent retired
    would be the one thing a spend figure must never do."""
    from ai4science.harness.agents.sarsi import spend as sp
    assert sp.for_agent(config, config.agents["work"]) is not None


# ── and it says so rather than vanishing ──────────────────────────────

def test_the_listing_shows_it_as_retired(config):
    from ai4science.harness.agents.sarsi import admin
    rows = {r["id"]: r for r in admin.agent_rows(config)}
    assert rows["work"].get("retired") is True
    assert rows["sarsi-worker"].get("retired") is False


def test_handing_it_work_is_refused_by_name(config):
    """Accepting it would file a task nobody is going to supervise."""
    from ai4science.harness.agents.sarsi import worker
    agent = config.agents["work"]
    d = worker.Directive(agent_id=agent.id, goal="do a new thing")
    with pytest.raises(worker.NotAWorker, match="retired"):
        worker.admit(config, agent, d)


# ── and the LISTING says so, not just the record behind it ────────────

def test_the_rendered_listing_marks_it(isolated):
    """Live on grace this was the gap: `agent_rows` carried `retired` and the
    table the owner actually reads showed `work` as an ordinary worker that
    drives sessions. Asserting on the record and not on the output tested my
    own abstraction rather than the thing anybody looks at."""
    from typer.testing import CliRunner
    from ai4science.cli import app as cli
    runner = CliRunner()
    runner.invoke(cli, ["sarsi", "init", "--owner-id", "7007143162"])
    out = runner.invoke(cli, ["sarsi", "agents"]).output
    line = [l for l in out.splitlines() if "work " in l and "sarsi-worker" not in l]
    assert line, out
    assert "retired" in line[0].lower()


def test_a_retired_agent_is_not_shown_as_driving_sessions(isolated):
    """It can no longer be given anything to drive one WITH."""
    from typer.testing import CliRunner
    from ai4science.cli import app as cli
    runner = CliRunner()
    runner.invoke(cli, ["sarsi", "init", "--owner-id", "7007143162"])
    out = runner.invoke(cli, ["sarsi", "agents"]).output
    line = [l for l in out.splitlines() if "work " in l and "sarsi-worker" not in l][0]
    assert "yes" not in line
