"""Problem lists for the rest of the research agents — and what grounds them.

Computational imaging's list is grounded in what **this machine has actually
done**: the CASSI forward-model bug that cost 35.5→28 dB is in this repository's
own history, so its first problem is a fact rather than a reading.

The others are not, and writing them as though they were would be the failure
this system spends its whole design avoiding — an assertion in the shape of a
measurement. For cancer, drug design and low-dose CT I am reading the field, not
reporting evidence held here, and a problem list that did not say so would be
exactly the thing the ordering rule refuses: something nobody on this machine can
check, ranked as though they could.

So a problem carries **where it came from**:

  * `grounded` — this machine has evidence for it: a repository, a benchmark it
    has run, a failure it recorded.
  * otherwise — a reading of the field, useful for aiming and **not** a
    substitute for someone who works in it.

The list still orders, because the rule is about dependencies rather than about
who wrote them down. What changes is what a reader is told they are looking at.
"""
import pytest

from ai4science.harness.agents.sarsi import problems


ALL = ("computational-imaging", "cancer", "drug-design", "low-dose-ct")


def _list(field):
    return problems.for_field(field)


# ── every field this machine has an agent for has a list ──────────────

@pytest.mark.parametrize("field", ALL)
def test_the_field_has_a_list(field):
    assert _list(field), field


@pytest.mark.parametrize("field", ALL)
def test_and_it_orders_without_a_cycle_or_a_ghost(field):
    got = problems.order(_list(field))
    assert [p.id for p in got]


@pytest.mark.parametrize("field", ALL)
def test_every_problem_says_what_would_settle_it(field):
    """A problem with no `verified_when` is a topic, not a problem."""
    for p in _list(field):
        assert p.verified_when, f"{field}/{p.id}"


@pytest.mark.parametrize("field", ALL)
def test_and_why_it_is_where_it_is(field):
    for p in _list(field):
        assert p.because, f"{field}/{p.id}"


@pytest.mark.parametrize("field", ALL)
def test_each_list_reaches_a_solution_tier(field):
    """A field whose list stops at benchmarks has nothing anyone can win."""
    assert any(p.tier == "L4" for p in _list(field)), field


# ── and says where it came from ───────────────────────────────────────

def test_computational_imaging_is_grounded_in_this_machines_own_work():
    """Its first problem is a failure recorded in this repository, not a
    reading of the literature."""
    first = problems.order(_list("computational-imaging"))[0]
    assert first.grounded is True
    assert "CASSI" in first.because


@pytest.mark.parametrize("field", ("cancer", "drug-design", "low-dose-ct"))
def test_a_field_i_only_read_about_says_so(field):
    """Not one problem in these is claimed as evidence held here. Writing them
    as though they were would be an assertion in the shape of a measurement."""
    assert any(p.grounded is False for p in _list(field)), field


def test_the_reading_is_marked_per_problem_not_per_field():
    """A field can have some of both — low-dose CT has a repository behind part
    of it and a reading behind the rest."""
    got = _list("low-dose-ct")
    assert {p.grounded for p in got} == {True, False}


def test_an_ungrounded_problem_is_still_ordered():
    """The rule is about dependencies, not about who wrote them down. What
    changes is what the reader is told they are looking at."""
    got = problems.order(_list("drug-design"))
    assert len(got) == len(_list("drug-design"))


# ── the reader is told, in the listing ────────────────────────────────

def _cli():
    from typer.testing import CliRunner
    from ai4science.cli import app
    return CliRunner(), app


@pytest.mark.parametrize("field", ALL)
def test_the_cli_lists_every_field(field, tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    runner, app = _cli()
    res = runner.invoke(app, ["sarsi", "problems", field])
    assert res.exit_code == 0, res.output


def test_and_marks_which_problems_are_a_reading(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    runner, app = _cli()
    out = runner.invoke(app, ["sarsi", "problems", "cancer"]).output.lower()
    assert "reading" in out or "not grounded" in out


def test_computational_imaging_does_not_carry_that_mark_on_its_first(
        tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    runner, app = _cli()
    out = runner.invoke(app, ["sarsi", "problems",
                              "computational-imaging"]).output
    first = out.split("2. [")[0]
    assert "reading" not in first.lower()


def test_listing_the_fields_themselves(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    runner, app = _cli()
    out = runner.invoke(app, ["sarsi", "problems"]).output
    for field in ALL:
        assert field in out


# ── computational imaging is co-design, not algorithm-only ────────────

def test_the_optic_is_a_design_variable_not_a_constant():
    """The list treated the hardware as given, which is the algorithm half of a
    field that is co-design: the coding optic and the reconstruction are
    designed together, and a solution scored on an arbitrary mask is a solution
    to an arbitrary problem."""
    ids = {p.id for p in _list("computational-imaging")}
    assert "hardware-model" in ids


def test_the_mask_finding_on_this_machine_grounds_it():
    """binary vs continuous mask: HDNet 35→28 dB. That is a HARDWARE-model
    result held here, not a reading — the mask IS the coding optic."""
    hw = [p for p in _list("computational-imaging")
          if p.id == "hardware-model"][0]
    assert hw.grounded is True
    assert "mask" in hw.because.lower()


def test_and_the_built_optic_is_its_own_problem():
    """A mask optimised in simulation and then fabricated does not match. That
    gap is the field's, and it is the one problem here that needs a body."""
    ids = {p.id for p in _list("computational-imaging")}
    assert "built-vs-simulated" in ids


def test_co_design_cannot_come_before_the_thing_it_optimises_against():
    """Joint optimisation needs a forward model to optimise through and a
    benchmark to score against. The rule should place it after both without
    being told."""
    got = [p.id for p in problems.order(_list("computational-imaging"))]
    assert got.index("co-design") > got.index("forward-model")
    assert got.index("co-design") > got.index("benchmark")


def test_and_the_principle_still_lands_last():
    """Adding a whole hardware branch must not disturb the claim §11b makes."""
    got = problems.order(_list("computational-imaging"))
    assert got[-1].id == "principle"
