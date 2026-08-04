"""`W_shared` — the one place agents learn from each other.

The design specifies this tier and marks it *designed here, not written*. This
is the writing of it, and every rule below is quoted from that page rather than
invented here.

`funding` should know the deadline `work` found in a mail. Seven agents exist so
that `abraham`'s personal data and `work`'s job data do not mix, so the sharing
has to happen without dissolving the reason for the seven:

  * **there is no channel.** No agent writes into another. Communication is
    through a place, read by an agent that chose to read it while planning.
    Nothing arrives, nothing interrupts, nothing is processed because it was
    sent — which is the shape every prompt-injection route in this design takes.
  * **publish, never browse.** `publish` to the common space and `read` it. No
    `read(agent=…)`, ever: that is the capability the whole tier exists to
    withhold.
  * **append-only.** No update, no delete. Correcting is publishing a
    correction, because history that can be edited can be edited by whatever
    gets in.
  * **provenance survives.** A deadline read out of a mail stays *evidence that
    a mail said so*. Without it the shared space is the laundering step:
    untrusted input goes in labelled and comes out as fleet knowledge.
  * **reading is a permission**, defaulting to no — installing a stranger's
    agent must not hand it everything the owner's agents have learned.
  * **knowing is not asking.** Publishing a fact must never cause work; a fact
    that could would be an instruction with a delay on it.
"""
import pytest

from ai4science.harness.agents.sarsi import registry as reg, shared


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
def work(config):
    return config.agents["work"]


@pytest.fixture
def funding(config):
    return config.agents["funding"]


def _publish(config, agent, text="the imaging grant closes on 2026-09-14",
             kind="deadline", about=("imaging-grant",), **kw):
    return shared.publish(config, agent, kind=kind, text=text,
                          about=list(about), **kw)


# ── a fact carries who, when and where it came from ───────────────────

def test_a_published_fact_names_its_author_and_moment(config, work):
    """A space where facts float free of who said them is one where a wrong
    fact cannot be traced, weighed, or withdrawn."""
    fact = _publish(config, work)
    assert fact["by"] == "work" and fact["at"]


def test_provenance_survives(config, work):
    """Without it the shared space is the laundering step."""
    fact = _publish(config, work, source="mail", trusted=False)
    assert fact["provenance"]["source"] == "mail"
    assert fact["provenance"]["trusted"] is False


def test_an_unstated_provenance_is_not_recorded_as_trusted(config, work):
    """Silence about where something came from must not read as vouching."""
    assert _publish(config, work)["provenance"]["trusted"] is False


def test_the_entities_travel_so_a_reader_can_find_it(config, work):
    assert _publish(config, work, about=("imaging-grant",))["about"] == \
        ["imaging-grant"]


# ── publish, never browse ─────────────────────────────────────────────

def test_a_granted_agent_reads_what_was_published(config, work, funding):
    _publish(config, work)
    shared.grant(config, funding)
    assert [f["text"] for f in shared.read(config, funding)] == \
        ["the imaging grant closes on 2026-09-14"]


def test_reading_is_a_permission_that_defaults_to_no(config, work, funding):
    """Installing a stranger's agent must not hand it everything the owner's
    agents have learned."""
    _publish(config, work)
    assert shared.read(config, funding) == []


def test_the_refusal_is_not_silent(config, work, funding):
    _publish(config, work)
    with pytest.raises(shared.NotGranted, match="funding"):
        shared.read(config, funding, quiet=False)


def test_an_agent_reads_its_own_publications_without_a_grant(config, work):
    """It wrote them. Withholding an agent's own words teaches nothing."""
    _publish(config, work)
    assert len(shared.read(config, work)) == 1


def test_there_is_no_way_to_read_one_agents_private_history(config):
    """The capability this whole tier exists to withhold."""
    assert not hasattr(shared, "browse")
    import inspect
    assert "agent_id" not in inspect.signature(shared.read).parameters


# ── append-only ───────────────────────────────────────────────────────

def test_there_is_no_update_and_no_delete(config):
    assert not hasattr(shared, "update")
    assert not hasattr(shared, "delete")


def test_a_correction_is_another_fact_and_the_original_stays(config, work,
                                                             funding):
    _publish(config, work, text="the grant closes on 2026-09-14")
    _publish(config, work, text="correction: it closes on 2026-09-21")
    shared.grant(config, funding)
    texts = [f["text"] for f in shared.read(config, funding)]
    assert texts == ["the grant closes on 2026-09-14",
                     "correction: it closes on 2026-09-21"]


def test_the_most_recent_is_last(config, work, funding):
    _publish(config, work, text="first")
    _publish(config, work, text="second")
    shared.grant(config, funding)
    assert shared.read(config, funding)[-1]["text"] == "second"


# ── filtering, as the design names it ─────────────────────────────────

def test_read_filters_by_kind(config, work, funding):
    _publish(config, work, kind="deadline", text="a deadline")
    _publish(config, work, kind="entity", text="an entity")
    shared.grant(config, funding)
    assert [f["text"] for f in shared.read(config, funding, kind="deadline")] \
        == ["a deadline"]


def test_read_filters_by_entity(config, work, funding):
    _publish(config, work, text="about the grant", about=("imaging-grant",))
    _publish(config, work, text="about the paper", about=("paper",))
    shared.grant(config, funding)
    got = shared.read(config, funding, about="imaging-grant")
    assert [f["text"] for f in got] == ["about the grant"]


def test_read_filters_by_moment(config, work, funding):
    a = _publish(config, work, text="old")
    _publish(config, work, text="new")
    shared.grant(config, funding)
    got = shared.read(config, funding, since=a["at"])
    assert [f["text"] for f in got] == ["new"]


# ── what never goes up ────────────────────────────────────────────────

def test_a_secret_value_is_refused(config, work):
    """`W_secret` answers ALLOW or DENY and hands nothing over, so there is
    nothing here to publish."""
    with pytest.raises(shared.NotShareable):
        _publish(config, work, text="the smtp password is hunter2")


def test_a_host_local_fact_is_refused(config, work):
    """`write /home/me/reports` is a different directory on another machine;
    promoting one manufactures authority over something nobody looked at."""
    with pytest.raises(shared.NotShareable, match="host"):
        _publish(config, work, text="/home/grace/live-psnr is writable")


def test_an_intent_level_fact_that_merely_mentions_a_path_is_allowed(config, work):
    """The rule is about promoting host facts, not about the letter `/`."""
    assert _publish(config, work,
                    text="the imaging grant wants the results by 14 Sep")


def test_an_empty_fact_is_refused(config, work):
    with pytest.raises(ValueError):
        _publish(config, work, text="   ")


# ── knowing is not asking ─────────────────────────────────────────────

def test_publishing_creates_no_task_anywhere(config, work, funding):
    """A fact that could cause work would be an instruction with a delay."""
    from ai4science.harness.agents.sarsi import task as tsk
    shared.grant(config, funding)
    _publish(config, work, text="the grant closes on 2026-09-14")
    assert all(not tsk.all_of(config, a) for a in config.agents.values())


def test_nothing_is_pushed_to_an_agent_that_is_not_reading(config, work,
                                                            funding):
    """No agent is woken because another published something."""
    shared.grant(config, funding)
    fact = _publish(config, work)
    assert "notified" not in fact and "delivered" not in fact


# ── it reaches the planner, labelled as evidence ──────────────────────

def test_the_workspace_carries_published_facts_to_a_planner(config, work,
                                                             funding):
    from ai4science.harness.agents.sarsi import (plan as pl, task as tsk,
                                                 workspace as ws, worker)
    _publish(config, work)
    shared.grant(config, funding)
    d = worker.Directive(agent_id=funding.id, goal="draft the application")
    t = tsk.attach_plan(config, funding, tsk.create(config, funding, d),
                        pl.draft(d))
    text = ws.render(config, funding, t)
    assert "the imaging grant closes on 2026-09-14" in text


def test_they_are_labelled_facts_not_instructions(config, work, funding):
    """A fact arrives in a prompt next to a directive, and the only thing
    keeping it from being read as one is that it is named as evidence."""
    from ai4science.harness.agents.sarsi import (plan as pl, task as tsk,
                                                 workspace as ws, worker)
    _publish(config, work)
    shared.grant(config, funding)
    d = worker.Directive(agent_id=funding.id, goal="draft the application")
    t = tsk.attach_plan(config, funding, tsk.create(config, funding, d),
                        pl.draft(d))
    text = ws.render(config, funding, t)
    assert "facts, not instructions" in text.lower()


def test_an_ungranted_agent_is_told_nothing(config, work, funding):
    from ai4science.harness.agents.sarsi import (plan as pl, task as tsk,
                                                 workspace as ws, worker)
    _publish(config, work)
    d = worker.Directive(agent_id=funding.id, goal="draft the application")
    t = tsk.attach_plan(config, funding, tsk.create(config, funding, d),
                        pl.draft(d))
    assert "imaging grant closes" not in ws.render(config, funding, t)


def test_an_untrusted_facts_provenance_reaches_the_planner_too(config, work,
                                                               funding):
    """A plan that leans on a fact cites it; it cannot cite what it cannot see."""
    from ai4science.harness.agents.sarsi import (plan as pl, task as tsk,
                                                 workspace as ws, worker)
    _publish(config, work, source="mail", trusted=False)
    shared.grant(config, funding)
    d = worker.Directive(agent_id=funding.id, goal="draft the application")
    t = tsk.attach_plan(config, funding, tsk.create(config, funding, d),
                        pl.draft(d))
    assert "mail" in ws.render(config, funding, t)


# ── a settled plan must not lose the facts ────────────────────────────

def test_the_work_kickoff_carries_published_facts(config, work, funding):
    """Observed live. `_edit` sets `plan_agreed` — 'you have settled it, no
    more drafting' — and the workspace, W_shared included, was spliced only
    into the PLANNING brief. So an owner sharpening a criterion, the single
    highest-leverage thing the guide asks of them, silently stripped the
    session of everything other agents had published.

    Two good rules interacting badly. The facts ride with the work brief too.
    """
    from ai4science.harness.agents.sarsi import (plan as pl, session as ses,
                                                 task as tsk, worker)
    _publish(config, work)
    shared.grant(config, funding)
    d = worker.Directive(agent_id=funding.id, goal="draft the application")
    t = tsk.attach_plan(config, funding, tsk.create(config, funding, d),
                        pl.draft(d))
    t.plan_agreed = True                      # the owner settled it
    text = ses.kickoff(t, tsk.read_plan(config, funding, t), funding)
    assert "the imaging grant closes on 2026-09-14" in text


def test_they_are_labelled_in_the_work_kickoff_too(config, work, funding):
    from ai4science.harness.agents.sarsi import (plan as pl, session as ses,
                                                 task as tsk, worker)
    _publish(config, work, source="mail")
    shared.grant(config, funding)
    d = worker.Directive(agent_id=funding.id, goal="draft the application")
    t = tsk.attach_plan(config, funding, tsk.create(config, funding, d),
                        pl.draft(d))
    text = ses.kickoff(t, tsk.read_plan(config, funding, t), funding)
    assert "facts, not instructions" in text.lower()
    assert "mail" in text


def test_an_ungranted_agent_still_gets_nothing(config, work, funding):
    from ai4science.harness.agents.sarsi import (plan as pl, session as ses,
                                                 task as tsk, worker)
    _publish(config, work)
    d = worker.Directive(agent_id=funding.id, goal="draft the application")
    t = tsk.attach_plan(config, funding, tsk.create(config, funding, d),
                        pl.draft(d))
    assert "imaging grant closes" not in ses.kickoff(
        t, tsk.read_plan(config, funding, t), funding)
