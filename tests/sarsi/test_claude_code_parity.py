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


# ── busy vs finished, which the loop keys its whole cadence on ────────

def test_a_working_session_reads_as_busy():
    """Captured mid-turn from the real thing. Claude Code swaps one footer item
    while it works:

        ⏸ manual mode on · ? for shortcuts · ← for agents      idle
        ⏸ manual mode on · esc to interrupt · ← for agents     working

    `_BUSY` is that one phrase. It is worth a fixture because it has already
    drifted once — the ai4science TUI said `esc to stop` while its own sibling
    renderer said `esc to interrupt`, and a session under the full-screen
    renderer looked permanently idle to the loop.
    """
    assert operator._busy(_fixture("claude_code_busy.txt")) is True


def test_a_finished_session_does_not():
    """The other direction, and the more dangerous one: a loop that believes a
    finished session is busy waits for ever and reports nothing wrong."""
    assert operator._busy(_fixture("claude_code_idle_after_turn.txt")) is False


def test_a_glyph_is_not_a_state():
    """`✻ Churned for 4s` sits on the FINISHED screen — the same glyph that
    heads a working one. abraham's run sat at `✻ Brewed for 35s` and the loop
    reported busy for ever at a session that had already stopped."""
    finished = _fixture("claude_code_idle_after_turn.txt")
    assert "✻" in finished
    assert operator._busy(finished) is False


def test_an_ACTIONABLE_suggestion_is_still_not_an_instruction():
    """The strongest case, and the reason the styling rule is not fussiness.

    After a turn, Claude Code offered `create hello.txt with hello in it` in the
    input box. That is not a generic placeholder — it is a complete, actionable
    instruction, indistinguishable in text from something the owner typed. The
    loop would have pressed Enter and had the session act on a request nobody
    made.

    It is ignored for one reason: SGR 2. Read the pane without escapes and this
    test's second assertion shows exactly what would happen instead.
    """
    styled = _fixture("claude_code_actionable_suggestion.txt", styled=True)
    plain = _SGR.sub("", styled)
    assert operator._dim_at_prompt(styled) is True
    assert operator._stranded(plain, styled=styled) is None
    assert operator._stranded(plain) == "create hello.txt with hello in it"


def test_the_pane_reader_captures_the_styling_it_depends_on():
    """The whole rule rests on `capture-pane -e`. A reader that drops `-e`
    would leave every test above passing and the live loop blind — the styling
    is not decoration here, it is the discriminator."""
    import inspect
    src = inspect.getsource(operator.TmuxPane.capture_styled)
    assert '"-e"' in src, src
    # …and that the styled capture actually REACHES the decision. A pane that
    # can produce styling, feeding a caller that never asks for it, is the same
    # blindness with an extra method.
    tick = inspect.getsource(operator.tick)
    assert "capture_styled" in tick, "tick never asks for the styled pane"
    assert "styled" in tick, tick[:200]
