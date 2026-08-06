"""The ordered problem list — Point 23, as an algorithm rather than an opinion.

    Solve what unblocks the most tiers below it, among the things that can be
    verified now.

Two clauses, and the order they are applied in is the whole design:

  * **"can be verified now"** is a *filter*, not a tiebreak. A problem whose
    dependencies are unsolved cannot be checked, so it is not a candidate however
    much it would unblock. Ranking by unblocking first and readiness second would
    put the most valuable unverifiable thing at the top of the list, which is
    where a field goes to argue instead of measure.
  * **"unblocks the most"** ranks what is left, counted *transitively* — a
    problem that unblocks one problem which unblocks four has unblocked five.

The list is **computed, not sorted by hand.** A hand-ordered list is one
person's judgement wearing an algorithm's clothes, and nobody can tell whether
it changed because the field moved or because somebody edited it.

The test that matters most is the last one: the rule is applied to the real
computational-imaging problems and checked against the order §11b claims. If
those disagree, either the rule is wrong or the document is, and finding out
which is worth more than the code.
"""
import pytest

from ai4science.harness.agents.sarsi import problems


def _p(pid, tier, deps=(), solved=False, verifiable=True):
    return problems.Problem(id=pid, tier=tier, title=pid, depends_on=list(deps),
                            solved=solved, verifiable=verifiable)


# ── ready comes first, and it is a filter ─────────────────────────────

def test_a_problem_whose_dependency_is_open_is_not_next():
    got = problems.order([_p("a", "L2"), _p("b", "L3", deps=["a"])])
    assert [p.id for p in got] == ["a", "b"]


def test_even_when_the_blocked_one_would_unblock_more():
    """The clause order. Ranking by unblocking first would put the most
    valuable unverifiable thing at the top, which is where a field goes to
    argue instead of measure."""
    got = problems.order([
        _p("small", "L3"),                       # ready, unblocks nothing
        _p("huge", "L1", deps=["small"]),        # unblocks four, NOT ready
        _p("x", "L4", deps=["huge"]),
        _p("y", "L4", deps=["huge"]),
        _p("z", "L4", deps=["huge"]),
        _p("w", "L4", deps=["huge"]),
    ])
    assert got[0].id == "small"


def test_and_a_problem_nobody_can_check_yet_is_not_ready():
    """`verifiable` is the field's own honest answer about itself — a
    principle that cannot be tested with what exists unblocks nothing, because
    every tier under it inherits the doubt."""
    got = problems.order([_p("untestable", "L1", verifiable=False),
                          _p("plain", "L3")])
    assert got[0].id == "plain"


def test_solving_one_makes_its_dependents_ready():
    listing = [_p("a", "L2", solved=True), _p("b", "L3", deps=["a"])]
    assert problems.next_of(listing).id == "b"


def test_a_solved_problem_is_not_offered(  ):
    assert problems.next_of([_p("a", "L2", solved=True)]) is None


# ── unblocking is counted transitively ────────────────────────────────

def test_a_problem_that_unblocks_a_chain_counts_the_whole_chain():
    """One that unblocks one problem which unblocks four has unblocked five."""
    listing = [_p("root", "L2"), _p("mid", "L3", deps=["root"]),
               _p("leaf1", "L4", deps=["mid"]), _p("leaf2", "L4", deps=["mid"]),
               _p("other", "L3")]
    # root → mid → {leaf1, leaf2}: three downstream, not four. My first count
    # was wrong and the code was right, which is the direction worth having.
    assert problems.unblocks(listing, "root") == 3
    assert problems.unblocks(listing, "other") == 0


def test_and_the_bigger_unblocker_comes_first_when_both_are_ready():
    listing = [_p("big", "L2"), _p("small", "L2"),
               _p("x", "L3", deps=["big"]), _p("y", "L3", deps=["big"])]
    got = [p.id for p in problems.order(listing)]
    assert got.index("big") < got.index("small")


# ── a list that cannot be ordered is refused ──────────────────────────

def test_a_cycle_is_refused_rather_than_silently_ordered():
    """An order produced from a cycle is an arbitrary one wearing an
    algorithm's clothes."""
    with pytest.raises(problems.Unorderable, match="cycle"):
        problems.order([_p("a", "L2", deps=["b"]), _p("b", "L2", deps=["a"])])


def test_a_dependency_that_is_not_in_the_list_is_refused():
    with pytest.raises(problems.Unorderable, match="ghost"):
        problems.order([_p("a", "L3", deps=["ghost"])])


def test_a_duplicate_id_is_refused():
    """Ids key the dependency graph. Two problems with one id is two answers to
    "is it solved"."""
    with pytest.raises(problems.Unorderable, match="twice"):
        problems.order([_p("a", "L2"), _p("a", "L3")])


# ── it is computed, and it is a read ──────────────────────────────────

def test_ordering_does_not_mutate_the_list():
    listing = [_p("b", "L3", deps=["a"]), _p("a", "L2")]
    problems.order(listing)
    assert [p.id for p in listing] == ["b", "a"]


def test_the_order_says_why_each_one_is_where_it_is():
    """A list a reader cannot argue with is one they have to take on faith."""
    got = problems.order([_p("a", "L2"), _p("b", "L3", deps=["a"])])
    assert "unblocks" in got[0].why.lower()
    assert "a" in got[1].why or "waiting" in got[1].why.lower()


# ── the real field ────────────────────────────────────────────────────

def test_computational_imaging_orders_the_way_the_design_says_it_does():
    """§11b claims this order, from the rule. Applying the rule to the real
    problems has to produce it — or the rule is wrong, or the document is."""
    got = [p.id for p in problems.order(problems.COMPUTATIONAL_IMAGING)]
    assert got == ["forward-model", "benchmark", "baselines", "solution",
                   "principle"], got


def test_and_the_principle_is_last_not_first():
    """The claim in the doc worth checking hardest: a field's principle is
    often the LAST thing verifiable, which is why "start from first principles"
    is bad advice for an agent that has to show its work."""
    got = problems.order(problems.COMPUTATIONAL_IMAGING)
    assert got[-1].tier == "L1"
    assert got[0].tier == "L2"


def test_every_problem_in_it_says_what_solving_it_would_mean():
    for p in problems.COMPUTATIONAL_IMAGING:
        assert p.verified_when, p.id


def test_the_first_one_is_the_forward_model_and_says_why():
    first = problems.order(problems.COMPUTATIONAL_IMAGING)[0]
    assert "forward model" in first.title.lower()
    assert "uncomparable" in first.because or "compar" in first.because


# ── and the owner can read it ─────────────────────────────────────────

def _cli():
    from typer.testing import CliRunner
    from ai4science.cli import app
    return CliRunner(), app


def test_the_cli_lists_the_field_in_order(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    runner, app = _cli()
    out = runner.invoke(app, ["sarsi", "problems", "computational-imaging"]).output
    assert out.index("forward-model") < out.index("benchmark")
    assert out.index("solution") < out.index("principle")


def test_and_says_what_solving_each_would_mean(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    runner, app = _cli()
    out = runner.invoke(app, ["sarsi", "problems", "computational-imaging"]).output
    assert "0.1 dB" in out          # the forward model's verified-when
    assert "verified when" in out.lower()


def test_and_why_each_sits_where_it_does(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    runner, app = _cli()
    out = runner.invoke(app, ["sarsi", "problems", "computational-imaging"]).output
    assert "unblocks" in out.lower()


def test_a_field_with_no_list_says_so_rather_than_printing_nothing(
        tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    runner, app = _cli()
    res = runner.invoke(app, ["sarsi", "problems", "astrology"])
    assert res.exit_code != 0
    assert "astrology" in res.output
