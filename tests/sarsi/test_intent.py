"""5-B1 — the worker tells what KIND of line it just received.

Every line became a task goal, verbatim. From the owner's own session:

    ❯ pleasa make a plan for me and create task
      goal:   pleasa make a plan for me and create task        ← a request to
                                                                 make a task
                                                                 became the task
    ❯ the goal is please write GAP-TV algorithm based on python for CASSI
      goal:   the goal is please write GAP-TV algorithm ...     ← the framing
                                                                 became part of
                                                                 the goal
    ❯ A2 is auto level
      goal:   A2 is auto level                                 ← an answer to a
                                                                 question became
                                                                 a task

The spec's table for this piece:

    | a greeting or chat                        | answer, create nothing      |
    | a question about itself, its ceiling      | answer from its own state   |
    | a directive                               | offer a task                |
    | ambiguous                                 | ask which, rather than
                                                  assume "directive"         |

Rows 1 and 2 landed with A3 and B4. This is rows 3 and 4 — and the distinction
they turn on: **a request to MAKE a task is not a goal.** Strip the request and
what is left is the goal, or nothing, and "nothing" is a question to ask rather
than a sentence to file.

The classifier is deliberately narrow. A router that guesses is worse than one
that is quiet, and the quiet answer here — `ambiguous`, ask — costs one round
trip, where guessing costs a task nobody wanted.
"""
import pytest

from ai4science.harness.agents.sarsi import intent


# ── the lines from the owner's session ────────────────────────────────

def test_a_request_to_make_a_task_is_not_a_goal():
    got = intent.classify("pleasa make a plan for me and create task")
    assert got.kind == "meta", got
    assert not got.goal


def test_even_when_it_points_at_a_goal_it_never_stated():
    """'according to this goal' refers to something the worker cannot see. The
    line is about task-making, and filing it as the goal produced a task whose
    goal was a request for a task."""
    got = intent.classify("please create the task for me according to this goal")
    assert got.kind == "meta", got


def test_but_a_request_that_NAMES_the_work_carries_it_through():
    """The useful half. Strip the request and the goal is what is left — so the
    natural phrasing works instead of being refused."""
    got = intent.classify("please make a task to write a GAP-TV solver for CASSI")
    assert got.kind == "directive", got
    assert got.goal == "write a GAP-TV solver for CASSI", got.goal


def test_the_framing_is_stripped_from_the_goal():
    got = intent.classify("the goal is please write GAP-TV algorithm based on python for CASSI")
    assert got.kind == "directive", got
    assert got.goal == "write GAP-TV algorithm based on python for CASSI", got.goal


def test_politeness_is_not_part_of_the_goal():
    got = intent.classify("please write GAP-TV algorithm based on python for CASSI")
    assert got.goal == "write GAP-TV algorithm based on python for CASSI", got.goal


def test_a_statement_is_not_a_directive():
    """`A2 is auto level` was the owner answering a question the worker had
    asked. It became a task. A line with nothing to do in it is ambiguous, and
    ambiguous means ask."""
    got = intent.classify("A2 is auto level")
    assert got.kind == "ambiguous", got


# ── the rows that already worked, kept honest ─────────────────────────

@pytest.mark.parametrize("line", ["hi", "thanks", "ok"])
def test_a_greeting_stays_a_greeting(line):
    assert intent.classify(line).kind == "greeting"


@pytest.mark.parametrize("line", [
    "write a GAP-TV solver for CASSI",
    "fix the failing test in operator.py",
    "add a --backend flag to sarsi do",
])
def test_a_plain_directive_is_still_a_directive(line):
    got = intent.classify(line)
    assert got.kind == "directive", got
    assert got.goal == line


def test_a_question_is_a_question():
    assert intent.classify("can you plan at A2?").kind == "question"


# ── what it refuses to decide ─────────────────────────────────────────

def test_ambiguous_says_what_it_could_not_tell():
    """An ask that does not say what was unclear is just a refusal."""
    got = intent.classify("A2 is auto level")
    assert got.why, "an ambiguous verdict must carry its reason"
    assert "goal" in got.why.lower() or "task" in got.why.lower(), got.why


def test_an_empty_line_decides_nothing():
    assert intent.classify("").kind == "empty"
    assert intent.classify("   ").kind == "empty"


def test_the_make_phrase_is_not_hunted_for_across_the_line():
    """The guard on tolerating a leading typo. An unanchored search would read
    this as a request to make a task and throw the real goal away."""
    got = intent.classify("write a script to create a task queue")
    assert got.kind == "directive", got
    assert got.goal == "write a script to create a task queue", got.goal
