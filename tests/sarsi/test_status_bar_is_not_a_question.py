"""Claude Code's status bar is furniture, not a question.

Live on grace, in the middle of a released run, `supervise` reported:

    the session asked: ⏸ manual mode on · ?
    asks-owner — sarsi-worker needs you: nothing in the plan, the scope or what
    you have said settles this

Nobody asked anything. That is the bottom line of every Claude Code pane —

    ⏸ manual mode on · ? for shortcuts · ← for agents

— and `_QUESTION` matches any run of 8–200 non-newline characters ending in a
`?`, so `⏸ manual mode on · ?` qualified. The session had just said what it was
about to do and was waiting; the loop woke the owner over a keyboard hint, and
the task stalled at `asks-owner` for the rest of the run.

This is the third time today the loop has read the TUI's chrome as content: a
dimmed placeholder submitted as an instruction, `Try "…"` submitted as a prompt,
and now the shortcut bar escalated as a question. The shape is always the same —
a matcher written against what a session *says* is pointed at a pane that also
contains what the *tool* says. So the fix is the same shape too: name the
furniture and take it out before reading, rather than making the question
pattern cleverer about which `?` it likes.
"""
from ai4science.harness.agents.sarsi import answering as anq

#: The real bottom line, verbatim from a live pane.
STATUS = "  ⏸ manual mode on · ? for shortcuts · ← for agents"

PANE = (
    "  Next unit is Phase 2: create top.md naming b and 11. That's one Write\n"
    "  call, no shell.\n"
    "\n"
    "✻ Cogitated for 21s\n"
    "\n"
    "────────────────────────────────────────\n"
    "❯ \n"
    "────────────────────────────────────────\n"
    + STATUS + "\n"
)


def test_the_status_bar_alone_is_not_a_question():
    assert anq.question_on(STATUS) is None


def test_nor_at_the_foot_of_a_working_pane():
    """The live one. The pane says plenty; none of it is a question."""
    assert anq.question_on(PANE) is None


def test_the_other_chrome_line_too():
    """`? for shortcuts` appears in more than one bar."""
    assert anq.question_on("  ⏵⏵ accept edits on · ? for shortcuts") is None


def test_but_a_real_question_is_still_read():
    """The guard must not swallow what this node exists for."""
    pane = PANE.replace("❯ \n",
                        "Which directory should I write the summary into?\n")
    assert anq.question_on(pane) == \
        "Which directory should I write the summary into?"


def test_a_real_question_below_the_bar_survives_it():
    """Order must not matter: the bar is removed, not used as a terminator."""
    pane = "Should I overwrite the existing file?\n" + STATUS + "\n"
    assert anq.question_on(pane) == "Should I overwrite the existing file?"


def test_an_option_menu_is_still_the_gate_s_business():
    """Unchanged — answering a permission gate here would route around the one
    place authority is decided."""
    assert anq.question_on("Do you want to proceed?\n ❯ 1. Yes\n   2. No\n") is None
