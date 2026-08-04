"""`sarsi-machine` answering "who should do this?" — and doing nothing else.

The manager is the agent you talk to when you do not know which worker a demand
belongs to. It has exactly one power here: **it suggests.** It may not create
the task, and that is not a policy but the invariant the whole design rests on —
*the agent you talk to does not execute*.

What it suggests from is evidence, in this order:

  * **precedent** — a worker that has already *verified* similar work is the
    strongest signal there is, because it is a result rather than a claim;
  * **declared tools** — what the roster says it has;
  * **its name**, last and weakest.

Two refusals matter more than the ranking:

  * **it never picks when nothing distinguishes them.** Routing personal work to
    `work` or professional work to `abraham` is a scope mistake with real
    consequences, and a confident wrong answer is worse than "I cannot tell".
  * **every suggestion says why.** A ranking with no reason is a guess wearing a
    number, and the owner cannot check a number.
"""
import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             task as tsk, triage, verifier as vf,
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


def _verified(config, agent_id, goal):
    agent = config.agents[agent_id]
    d = worker.Directive(agent_id=agent_id, goal=goal)
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    return tsk.finish(config, agent, t, verdict=vf.parse("PASS: done"))


# ── it suggests, and says why ─────────────────────────────────────────

def test_a_tool_the_roster_declares_is_a_reason(config):
    got = triage.suggest(config, "run the qupath segmentation")
    assert got.best and got.best.agent_id == "work"
    assert "qupath" in got.best.why


def test_every_suggestion_carries_its_reason(config):
    """A ranking with no reason is a guess wearing a number."""
    got = triage.suggest(config, "post the thread to the timeline")
    assert all(c.why for c in got.candidates)


def test_precedent_outranks_a_matching_tool(config):
    """A worker that has already VERIFIED similar work is a result, not a
    claim — the strongest signal available."""
    _verified(config, "jobs", "draft the qupath segmentation writeup")
    got = triage.suggest(config, "draft the qupath segmentation writeup")
    assert got.best.agent_id == "jobs"
    assert "verified" in got.best.why.lower() or "before" in got.best.why.lower()


def test_precedent_names_the_task_it_is_citing(config):
    """So the owner can go and read the thing being cited."""
    done = _verified(config, "funding", "draft the fellowship application")
    got = triage.suggest(config, "draft the fellowship application")
    assert done.id in got.best.why


def test_unverified_work_is_not_precedent(config):
    """Holding a similar task proves nothing about being able to finish one."""
    agent = config.agents["jobs"]
    d = worker.Directive(agent_id="jobs", goal="run the qupath segmentation")
    tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    got = triage.suggest(config, "run the qupath segmentation")
    assert got.best.agent_id == "work"


# ── the manager routes and never executes ─────────────────────────────

def test_the_manager_is_never_a_candidate(config):
    """It drives no sessions. Suggesting itself would be suggesting nothing
    gets done."""
    got = triage.suggest(config, "who should look at the manager console?")
    assert all(c.agent_id != "sarsi-machine" for c in got.candidates)


def test_suggesting_creates_nothing(config):
    triage.suggest(config, "run the qupath segmentation")
    assert all(not tsk.all_of(config, a) for a in config.agents.values())


def test_the_manager_cannot_be_made_to_hold_the_task(config):
    """The invariant, tried directly: routing must not become a back door."""
    from ai4science.harness.agents.sarsi import worker as wk
    manager = config.agents["sarsi-machine"]
    with pytest.raises(wk.NotAWorker):
        wk.admit(config, manager, wk.Directive(agent_id=manager.id, goal="x"))


# ── it declines to guess ──────────────────────────────────────────────

def test_nothing_distinguishing_produces_no_best(config):
    """Personal work routed to `work`, or professional work to `abraham`, is a
    scope mistake with real consequences."""
    got = triage.suggest(config, "handle the thing")
    assert got.best is None
    assert "cannot tell" in got.summary.lower() or "nothing" in got.summary.lower()


def test_a_tie_is_reported_as_a_tie(config):
    _verified(config, "jobs", "write the report")
    _verified(config, "funding", "write the report")
    got = triage.suggest(config, "write the report")
    assert got.best is None
    assert "jobs" in got.summary and "funding" in got.summary


def test_an_empty_demand_is_refused(config):
    with pytest.raises(ValueError):
        triage.suggest(config, "   ")


# ── what the owner is told ────────────────────────────────────────────

def test_the_summary_names_the_worker_and_the_command_to_use(config):
    got = triage.suggest(config, "run the qupath segmentation")
    assert "work" in got.summary
    assert "sarsi do work" in got.summary


def test_the_summary_of_a_tie_asks_rather_than_assumes(config):
    _verified(config, "jobs", "write the report")
    _verified(config, "funding", "write the report")
    assert "?" in triage.suggest(config, "write the report").summary


# ── asking the manager in chat ────────────────────────────────────────

def test_asking_the_manager_who_should_do_it(config):
    from ai4science.harness.agents.sarsi import chat
    out = chat.handle(config, config.agents["sarsi-machine"],
                      "/who run the qupath segmentation", surface="cli")
    assert "work" in out


def test_a_worker_asked_the_same_thing_still_answers(config):
    """The question is about the fleet, not about who was asked."""
    from ai4science.harness.agents.sarsi import chat
    out = chat.handle(config, config.agents["work"],
                      "/who post the thread", surface="cli")
    assert "social" in out


def test_what_an_agent_is_for_is_evidence(config):
    """The guide said what each agent is for and the registry did not, so
    routing had only tool names — and `social` scored zero on "post the
    thread"."""
    got = triage.suggest(config, "post the thread to the timeline")
    assert got.best and got.best.agent_id == "social"
    assert "what it is for" in got.best.why


def test_purpose_outranks_a_tool_it_merely_holds(config):
    """A tool is a capability; a purpose is what it is there to do."""
    got = triage.suggest(config, "book the dentist appointment")
    assert got.best.agent_id == "abraham"


def test_one_shared_word_is_not_precedent(config):
    """Live: "post the thread about the CASSI results" routed to `work`,
    because an old verified task shared the single word "cassi". One noun in
    common is a coincidence, and it outranked what `social` is actually for."""
    _verified(config, "work", "reconstruct the CASSI cube with GAP-TV")
    got = triage.suggest(config, "post the thread about the CASSI results")
    assert got.best and got.best.agent_id == "social"


def test_two_shared_words_still_count_as_precedent(config):
    _verified(config, "jobs", "draft the qupath segmentation writeup")
    got = triage.suggest(config, "draft the qupath segmentation writeup")
    assert got.best.agent_id == "jobs"


def test_a_registry_written_before_about_existed_still_routes(tmp_path):
    """Live on grace: an older `sarsi.json` has no `about`, so every purpose
    match was lost and 'book the dentist appointment' routed nowhere. The
    `spec` field had this exact gap, and this is the same fix."""
    raw = reg.default_config(owner_id="1")
    for entry in raw["agents"]["list"]:
        entry.pop("about", None)
    c = reg.parse(raw, root=tmp_path)
    assert triage.suggest(c, "book the dentist appointment").best.agent_id == \
        "abraham"
