"""`out.txt exists and contains 42` — both halves checkable, and it was not.

`verify.check` splits a conjunctive criterion on `and` and judges each clause,
which is right: `report.md exists and `/bin/false` exits 0` must not close on
the first half alone. But the second clause of an ordinary compound names no
file, because the file was named in the first one — and a clause with no
subject matches no pattern, so the whole criterion fell through to a model.

Found by the memory-loop walk (2026-08-24), where it was the shape three of the
tree's own tests were written around.

The elision is resolved ONLY when it cannot mean anything else:

  * the clause matched nothing on its own;
  * it names no file of its own;
  * the clauses BEFORE it name exactly one distinct file;
  * and the reading is stated on the verdict, never silently assumed.

A clause that inherited the wrong file would be a check confidently judging
something nobody asked about — worse than a model that knows it is guessing.
So every one of those conditions is a test here.
"""
import pytest

from ai4science.harness.agents.sarsi import verify


@pytest.fixture
def work(tmp_path):
    return tmp_path


def test_the_second_clause_inherits_the_file_the_first_one_named(work):
    (work / "out.txt").write_text("42\n")
    r = verify.check("out.txt exists and contains 42", work)
    assert r["state"] == "PASS", r
    assert r["deterministic"] is True


def test_and_it_fails_when_the_inherited_clause_fails(work):
    (work / "out.txt").write_text("7\n")
    r = verify.check("out.txt exists and contains 42", work)
    assert r["state"] == "FAIL", r
    assert r["deterministic"] is True
    assert "42" in r["why"]


def test_the_verdict_says_which_file_it_read_the_clause_against(work):
    (work / "out.txt").write_text("42\n")
    r = verify.check("out.txt exists and contains 42", work)
    assert "out.txt" in r["check"], r
    assert "contains" in r["check"]


# ── and every way it must NOT guess ─────────────────────────────────────────

def test_two_files_named_before_it_is_ambiguous_and_stays_unverified(work):
    """Which one does `contains 42` mean? Nobody said, so nothing decides."""
    (work / "a.txt").write_text("42\n")
    (work / "b.txt").write_text("42\n")
    r = verify.check("a.txt exists and b.txt exists and contains 42", work)
    assert r["state"] == "UNVERIFIED", r


def test_an_elided_clause_with_nothing_before_it_stays_unverified(work):
    """The subject has to have been established. A clause that comes first
    establishes nothing."""
    (work / "out.txt").write_text("42\n")
    r = verify.check("contains 42 and out.txt exists", work)
    assert r["state"] == "UNVERIFIED", r


def test_a_clause_that_names_its_own_file_is_left_alone(work):
    """It means what it says, and what it says is not the earlier file."""
    (work / "a.txt").write_text("42\n")
    (work / "b.txt").write_text("nothing\n")
    r = verify.check("a.txt exists and b.txt contains 42", work)
    assert r["state"] == "FAIL", r
    assert "b.txt" in r["why"]


def test_a_command_clause_is_not_given_a_filename(work):
    """A backtick command is a command. Prefixing a filename onto it would be
    inventing a different check entirely."""
    (work / "out.txt").write_text("42\n")
    r = verify.check("out.txt exists and `true` exits 0", work, trusted=True)
    assert r["state"] == "PASS", r


def test_an_unjudgeable_clause_still_makes_the_whole_thing_unverified(work):
    """The rule that must not move: an unjudgeable clause is not quietly
    optional. Inheritance resolves an ELISION, never an unknown."""
    (work / "out.txt").write_text("42\n")
    r = verify.check("out.txt exists and it reads well", work)
    assert r["state"] == "UNVERIFIED", r


def test_a_single_clause_criterion_is_untouched(work):
    """Nothing to inherit from, and no splitting happened."""
    r = verify.check("contains 42", work)
    assert r["state"] == "UNVERIFIED", r


@pytest.mark.parametrize("crit", [
    "out.txt exists and contains 42",
    "out.txt exists and it contains 42",
    "out.txt exists and which contains 42",
    "out.txt exists and that contains 42",
    "out.txt exists and includes 42",
    "out.txt exists and mentions 42",
])
def test_the_ways_a_session_actually_writes_it(crit, work):
    """The pronoun is captured out rather than merely tolerated: the retry is
    built as `"<file> <predicate>"`, and `"out.txt it contains 42"` matches
    nothing. A session writes both forms as readily."""
    (work / "out.txt").write_text("42\n")
    assert verify.check(crit, work)["state"] == "PASS", crit


@pytest.mark.parametrize("crit", [
    "out.txt exists and it contains 43",
    "out.txt exists and contains 43",
])
def test_and_each_of_them_can_still_fail(crit, work):
    (work / "out.txt").write_text("42\n")
    r = verify.check(crit, work)
    assert r["state"] == "FAIL" and r["deterministic"] is True, r


def test_a_diff_scope_criterion_is_still_never_split(work):
    """`the diff touches only src/ and tests/` is ONE condition over two
    directories. Splitting it judged the second half as a criterion of its own,
    and that rule predates this one."""
    r = verify.check("the diff touches only src/ and tests/", work)
    assert "subject from an earlier clause" not in (r.get("check") or "")


def test_expected_text_containing_and_is_not_silently_truncated(work):
    """The load-bearing interaction with the splitter.

    `_clauses` splits on ` and ` wherever it appears, including inside the text
    a file is meant to contain. `out.txt contains Alice and Bob` becomes
    `["out.txt contains Alice", "Bob"]` — and if the inherited check simply
    judged the first half, it would deterministically answer a question the
    criterion did not ask.

    It cannot, and the reason is the rule that predates all of this: an
    unjudgeable clause makes the WHOLE criterion unverified rather than quietly
    optional. `Bob` matches no pattern and opens with no predicate verb, so it
    is unjudgeable, so nothing is settled. Truncation always leaves such a
    remnant behind."""
    (work / "out.txt").write_text("Alice and Bob\n")
    r = verify.check("out.txt contains Alice and Bob", work)
    assert r["state"] == "UNVERIFIED", r


def test_a_trailing_fragment_after_an_inherited_clause_also_stops_it(work):
    (work / "out.txt").write_text("42 43\n")
    r = verify.check("out.txt exists and contains 42 and 43", work)
    assert r["state"] == "UNVERIFIED", r
