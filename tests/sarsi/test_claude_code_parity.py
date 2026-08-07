"""Piece 4 — the loop read against REAL Claude Code screens.

Four of the six defects that blocked `sarsi-pwm` were the same shape: **a
pattern written against assumed wording, meeting the real one.** Finding those
one per driven run is the expensive way; this file is the cheap way.

The fixtures beside this file are `tmux capture-pane` output from an actual
`claude` session on 2026-08-07 (Claude Code v2.1.224), captured WITH escape
sequences where the styling carries meaning. They are ground truth, not
paraphrase — the failure mode this whole exercise exists to avoid is a test that
restates what someone believed the screen said.

Refresh them by running `claude` in a scratch folder and re-capturing; do not
hand-edit them, because an edited fixture is an assumption again.
"""
import pathlib
import re

import pytest

from ai4science.harness.agents.sarsi import operator

HERE = pathlib.Path(__file__).parent / "fixtures"
_SGR = re.compile(r"\x1b\[[0-9;]*m")


def _fixture(name: str, *, styled: bool = False) -> str:
    raw = (HERE / name).read_text()
    return raw if styled else _SGR.sub("", raw)


# ── the four things the loop reads, on real screens ───────────────────

def test_the_trust_gate_is_recognised_and_answered():
    """Claude Code renders it as an ARROW picker — `❯ 1. Yes, I trust this
    folder` with `Enter to confirm` — where ai4science renders a typed number.
    Both must satisfy `_GATE_SHAPE`, whose `❯?` is optional for exactly this
    reason."""
    screen = _fixture("claude_code_trust_gate.txt")
    assert operator._GATE_SHAPE.search(screen)
    got = operator._gate(screen)
    assert got and got[0] == "1", got


def test_a_dim_suggestion_is_not_a_stranded_prompt():
    """The live case this caught: after a turn, Claude Code left `git init` in
    the input box as a SUGGESTION. Stripped of styling it is indistinguishable
    from something the owner typed, and the loop would have pressed Enter and
    run it — an action nobody asked for.

    The styling is the discriminator, and the loop already reads it: a
    suggestion carries SGR 2 (dim), typed text does not. This asserts it against
    a real suggestion rather than a constructed one.
    """
    styled = _fixture("claude_code_suggestion.txt", styled=True)
    assert operator._dim_at_prompt(styled) is True
    assert operator._stranded(_SGR.sub("", styled), styled=styled) is None


def test_and_the_stripped_capture_alone_would_have_been_fooled():
    """Kept as a warning, and because it is how this was nearly mis-reported:
    read WITHOUT escapes, the suggestion looks exactly like a stranded prompt.
    Any future check that strips styling before deciding is wrong."""
    plain = _fixture("claude_code_suggestion.txt")
    assert operator._stranded(plain) == "git init"


# ── the two gaps this sweep found ─────────────────────────────────────

def test_the_wider_option_is_recognised_in_claude_codes_own_words():
    """`_STANDING_OPTION` exists to make sure the loop NEVER presses the
    "and stop asking" option — a standing permission is the owner's to give.

    It matched `don't ask again` and `and stop asking`. Claude Code says:

        2. Yes, allow all edits during this session (shift+tab)

    so the guard was blind to the real wording, and the one option it exists to
    recognise was the one it could not see.
    """
    screen = _fixture("claude_code_write_gate.txt")
    wider = [l for l in screen.splitlines() if l.strip().startswith("2.")]
    assert wider, "the fixture no longer has a second option"
    assert operator._STANDING_OPTION.search(wider[0]), wider[0]


def test_the_write_gate_names_its_file_even_without_a_full_path():
    """Defect 6 answers a gate the ceiling has since allowed, and finds the
    target with `_gate_write_path`. That looked for a verb plus an ABSOLUTE
    path, which is what the ai4science TUI prints:

        Write /home/grace/pwmv2/DONE.md  (1 line)

    Claude Code prints a bare name instead:

        Do you want to create hello.txt?

    so the fix could never fire on `sarsi-claude` — the backend the loop was
    built for.
    """
    screen = _fixture("claude_code_write_gate.txt")
    assert operator._gate_write_path(screen) != "", screen[-400:]


def test_a_bare_filename_is_resolved_inside_the_declared_paths():
    """A bare name has no directory, so it is resolved against the roots the
    task declared — and only those.

    **What that can and cannot check, stated plainly.** A bare name carries no
    location, so "is this outside the declared paths?" is not answerable from
    the gate: it lands in the session's cwd, and the cwd is always one of the
    declared roots. Resolving it against the roots is therefore right, and the
    containment test is vacuous for this shape — it is doing real work only for
    the absolute-path shape below.

    The safety does not rest on containment here. It rests on the ceiling: the
    hook is still asked, with the resolved path, and answers for A0 exactly as
    it would have.
    """
    screen = _fixture("claude_code_write_gate.txt")
    assert operator._ceiling_would_allow(screen, "A1", ["/home/grace/paritycheck"])
    # the ceiling still decides, which is what actually protects this path
    assert not operator._ceiling_would_allow(screen, "A0", ["/home/grace/paritycheck"])
    # and with nothing declared there is nowhere to resolve it to
    assert not operator._ceiling_would_allow(screen, "A1", [])


def test_an_absolute_path_outside_the_declared_roots_is_still_refused():
    """Where containment does real work: a gate naming a path of its own must
    not be answered because some other directory was declared. Widening is not
    something a gate gets to arrange."""
    screen = ("⏺ write\n  Write /etc/passwd  (1 line)\n\n"
              "Do you want to proceed?\n\n  1. Yes\n  2. No\n"
              "Type a number (1-2) and press Enter ❯ ")
    assert not operator._ceiling_would_allow(screen, "A2", ["/home/grace/paritycheck"])
