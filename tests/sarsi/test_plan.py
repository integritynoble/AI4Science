"""`PLN` — the plan a task runs on.

The plan does four jobs and they are the same document: it tells the session
what to work next, tells the verifier what to judge, tells the owner what this
will need, and carries what the work revealed into the next generation.

Two rules are refusals: a phase without a `Verified when:` line has nothing for
the verifier to judge, and a **new generation** is the owner's act alone.
"""
import pytest

from ai4science.harness.agents.sarsi import plan as pl


def _phases():
    return [pl.Phase(title="drain the queue", body="stop new writes first",
                     verified_when="the queue length reads 0 in the console"),
            pl.Phase(title="re-run the export",
                     verified_when="export.csv exists and has 1,204 rows")]


def _plan(**kw):
    base = dict(goal="finish the export", phases=_phases())
    base.update(kw)
    return pl.Plan(**base)


# ── what a plan must contain ──────────────────────────────────────────

def test_a_phase_without_a_verified_when_line_is_refused():
    with pytest.raises(pl.BadPlan, match="Verified when"):
        pl.Phase(title="do the thing", verified_when="  ")


def test_a_plan_needs_at_least_one_phase():
    with pytest.raises(pl.BadPlan, match="phase"):
        _plan(phases=[])


def test_criteria_are_the_verified_when_lines_in_order():
    assert _plan().criteria() == [
        "the queue length reads 0 in the console",
        "export.csv exists and has 1,204 rows"]


# ── rendering and parsing round-trip ──────────────────────────────────

def test_rendered_plan_carries_every_phase_and_its_criterion():
    text = _plan().render()
    assert "## Phase 1 — drain the queue" in text
    assert "Verified when: export.csv exists and has 1,204 rows" in text


def test_a_rendered_plan_parses_back_to_the_same_criteria():
    parsed = pl.parse(_plan().render())
    assert parsed.criteria() == _plan().criteria()
    assert parsed.goal == "finish the export"


def test_permissions_needed_is_always_a_section_even_when_empty():
    """The owner reads this section to decide. It must not disappear when the
    plan happens to need nothing — an absent section reads as 'not considered'."""
    text = _plan(permissions=[]).render()
    assert "## Permissions needed" in text
    assert "none" in text.lower()


def test_a_resource_the_goal_never_named_is_written_unspecified():
    text = _plan(permissions=["write <unspecified>"]).render()
    assert "<unspecified>" in text
    assert list(pl.parse(text).permissions) == ["write <unspecified>"]


# ── generations and successors ────────────────────────────────────────

def test_the_first_plan_is_plan0():
    assert _plan().version == "plan0"


def test_a_successor_stays_inside_the_generation():
    assert _plan().successor_version() == "plan0_1"
    assert _plan(version="plan0_1").successor_version() == "plan0_2"


def test_the_agent_may_not_open_a_new_generation():
    """plan1.md is a new mission, and that is the owner's act alone."""
    with pytest.raises(pl.OwnerOnly, match="generation"):
        _plan().next_generation()


def test_the_owner_may_open_a_new_generation():
    nxt = _plan().next_generation(by_owner=True)
    assert nxt.version == "plan1"


# ── staleness ─────────────────────────────────────────────────────────

def test_a_stale_plans_criteria_are_withheld():
    """Judging this run against a superseded mission's standard is worse than
    judging against the goal alone."""
    assert _plan(stale=True).criteria() == []


def test_a_stale_plan_is_withheld_not_deleted():
    stale = _plan(stale=True)
    assert stale.phases and "drain the queue" in stale.render()


def test_an_owner_edit_makes_the_plan_fresh():
    """An owner edit is the mission being restated, not an abandonment of it."""
    edited = _plan(stale=True).owner_edit(phases=_phases())
    assert edited.stale is False and edited.owner_edited is True


# ── drafting from a directive ─────────────────────────────────────────

def test_draft_makes_one_phase_per_criterion_the_directive_carried():
    from ai4science.harness.agents.sarsi import worker
    d = worker.Directive(agent_id="work", goal="finish the export",
                         criteria=["export.csv exists", "it has 1,204 rows"])
    drafted = pl.draft(d)
    assert drafted.criteria() == ["export.csv exists", "it has 1,204 rows"]


def test_draft_without_criteria_still_produces_a_judgeable_phase():
    """A plan with nothing to verify is not a plan. When the directive supplies
    no criterion, the goal itself becomes one — and says it is provisional."""
    from ai4science.harness.agents.sarsi import worker
    drafted = pl.draft(worker.Directive(agent_id="work", goal="finish the export"))
    assert len(drafted.criteria()) == 1
    assert "finish the export" in drafted.criteria()[0]


def test_draft_declares_the_scope_and_secrets_as_permissions():
    from ai4science.harness.agents.sarsi import worker
    d = worker.Directive(agent_id="work", goal="finish the export",
                         scope=["/home/me/reports"], requires_secrets=["mail.read"])
    perms = list(pl.draft(d).permissions)
    assert any("/home/me/reports" in p for p in perms)
    assert any("mail.read" in p for p in perms)


def test_draft_never_invents_a_resource_the_goal_did_not_name():
    from ai4science.harness.agents.sarsi import worker
    drafted = pl.draft(worker.Directive(agent_id="work", goal="finish the export"))
    assert list(drafted.permissions) == []


# ── polish, and who wins ──────────────────────────────────────────────

def test_polish_writes_a_successor_when_the_owner_has_not_edited():
    out = _plan().polish(phases=_phases())
    assert out.adopted is True and out.plan.version == "plan0_1"


def test_polish_may_only_propose_over_an_owner_edited_plan():
    """The agent may improve its own plan; it may not adopt that improvement."""
    edited = _plan().owner_edit(phases=_phases())
    out = edited.polish(phases=_phases())
    assert out.adopted is False and out.proposal is not None


def test_a_proposal_leaves_the_owners_version_in_place():
    edited = _plan().owner_edit(phases=[pl.Phase(title="mine",
                                                 verified_when="I say so")])
    out = edited.polish(phases=_phases())
    assert out.plan.criteria() == ["I say so"]


# ── real model output, from a live planning run ───────────────────────

LIVE_PLAN = """\
# count the lines in every .txt file here and write counts.md

## Phase 1 — Fix the file set
Enumerate the `.txt` files at the top level of this folder.

Verified when: the run's transcript shows the output of `ls -1 *.txt` executed in
this folder, and that list is exactly the set of filenames appearing as rows in
the final `counts.md`.

## Phase 2 — Count lines
Verified when: the transcript shows raw `wc -l` output for every file, and each
number is reproducible by re-running `wc -l <file>`.

## Permissions needed
Nothing outside this folder. Concretely:
- Read `*.txt` in this folder.
- Create one new file, `counts.md`, in that same folder.
- No network, no credentials or secrets, no accounts.
"""


def test_a_wrapped_criterion_keeps_all_of_itself():
    """A `Verified when:` clause that wraps is one criterion, not its first
    line. Truncating it hands the verifier a weaker standard than the plan
    states — and the plan is the standard."""
    parsed = pl.parse(LIVE_PLAN)
    first = parsed.criteria()[0]
    assert first.endswith("`counts.md`.")
    assert "exactly the set of filenames" in first


def test_a_wrapped_criterion_stops_at_the_next_phase():
    parsed = pl.parse(LIVE_PLAN)
    assert "wc -l" not in parsed.criteria()[0]
    assert len(parsed.criteria()) == 2


def test_a_negative_line_is_a_constraint_not_a_permission_to_grant():
    """The model wrote "No network, no credentials" among the bullets. Asking
    the owner to GRANT that is nonsense; it is a limit the plan is accepting."""
    parsed = pl.parse(LIVE_PLAN)
    assert not any(p.lower().startswith("no ") for p in parsed.permissions)
    assert any("no network" in c.lower() for c in parsed.constraints)


def test_the_real_permissions_survive():
    parsed = pl.parse(LIVE_PLAN)
    assert any("Read" in p for p in parsed.permissions)
    assert any("counts.md" in p for p in parsed.permissions)
