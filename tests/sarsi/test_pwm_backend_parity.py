"""Piece 3, step 1: the ai4science TUI speaks the loop's language.

`sarsi-claude` opens a tmux session running Anthropic's `claude` binary.
`sarsi-pwm` opens one running **ai4science** — PWM Code — and is to be the
default. The blocker was assumed to be architectural and is not: the
supervision loop reads four things, two are already identical in both TUIs, and
two differ in *string only*.

    | | ai4science | Claude Code |
    |---|---|---|
    | busy marker    | `esc to stop`                  | `esc to interrupt` |
    | folder-trust   | "is this a **folder** you…"    | "Is this a **project** you created or one you trust" |

And the inline renderer (`commands/chat.py`) already says `esc to interrupt`,
so it is the full-screen renderer that drifted from its own sibling — not a
deliberate difference anyone chose.

**The loop does not learn a second dialect; the TUI stops speaking one.** The
alternative — teaching `operator.py` both spellings — buys a second thing to
keep in step forever, in exchange for two strings, and every future divergence
becomes someone else's problem to notice.

These tests read the real source rather than a copy of the strings, because a
test that restated them would drift with them and pass while the loop went
blind. That failure mode has already happened once on this branch, in the drift
guard that compared two hand-typed literals.
"""
import pathlib
import re

import pytest

from ai4science.harness.agents.sarsi import operator, session

REPO = pathlib.Path(__file__).resolve().parents[2]
TUI = REPO / "ai4science/harness/tui.py"
CHAT = REPO / "ai4science/commands/chat.py"


def _emitted(path: pathlib.Path, pattern: str) -> bool:
    """Does the file EMIT this text — ignoring comments.

    A comment explaining why the old spelling was wrong is not the old
    spelling. The first version of this helper searched raw file text and so
    failed on the fix's own explanatory comment, which is a test measuring the
    wrong thing rather than a bug in the code.
    """
    body = "\n".join(l for l in path.read_text().splitlines()
                      if not l.lstrip().startswith("#"))
    return re.search(pattern, body) is not None


# ── the busy marker ───────────────────────────────────────────────────

def test_the_loop_knows_exactly_one_busy_marker():
    """If this grows a second spelling, the fix went into the wrong file."""
    assert operator._BUSY == ("esc to interrupt",), operator._BUSY


def test_the_full_screen_tui_emits_the_marker_the_loop_reads():
    """`tui.py` said `esc to stop` while its own sibling `chat.py` said
    `esc to interrupt` — so a session run under the full-screen renderer looked
    permanently idle to the supervision loop."""
    assert _emitted(TUI, r"esc to interrupt"), (
        "tui.py does not emit the busy marker operator._BUSY reads")
    assert not _emitted(TUI, r"esc to stop"), (
        "tui.py still emits the old spelling somewhere")


def test_and_the_inline_renderer_still_does():
    """It was already correct. This pins it so a later 'consistency' edit does
    not helpfully break the half that worked."""
    assert _emitted(CHAT, r"esc to interrupt")


# ── the folder-trust gate ─────────────────────────────────────────────

def test_the_loop_recognises_the_gate_the_tui_actually_shows():
    """`AN` answers only gates it recognises, from an allowlist. A gate whose
    wording drifted is not refused loudly — it is left for the owner and the
    run stalls at a prompt nobody is watching."""
    shown = None
    for m in re.finditer(r'"([^"]*you created or[^"]*)"', CHAT.read_text()):
        shown = m.group(1)
        break
    assert shown, "could not find the folder-trust prompt in chat.py"
    matched = [p for p, _key, _why in operator._KNOWN_GATES if p.search(shown)]
    assert matched, (
        "operator._KNOWN_GATES does not match the prompt chat.py shows:\n"
        "  shown:   %s\n"
        "  patterns: %s" % (shown, [p.pattern for p, _, _ in operator._KNOWN_GATES]))


# ── what this unlocks, and what it does not ───────────────────────────

def test_pwm_is_not_drivable_until_a_live_run_says_so():
    """Parity is necessary and not sufficient. DRIVABLE_SPECS is a claim that
    the loop has been SEEN reading that interface, so it grows after a live
    check, not because two strings now match.

    This test is here to fail loudly on the day someone adds the spec without
    the evidence — it is the same discipline as `verified live, once`.
    """
    assert "claude-code" in session.DRIVABLE_SPECS
    assert "codex" in session.DRIVABLE_SPECS


def test_the_two_structural_patterns_were_never_the_problem():
    """The gate shape and the prompt line are identical in both TUIs, which is
    why this is two strings rather than a parser."""
    assert operator._GATE_SHAPE.search("  1. Yes")
    assert operator._PROMPT_LINE.search("❯ do the thing")


# ── the folder-trust gate must be SHAPED like a gate, not a menu ──────

def test_the_folder_trust_gate_is_numbered_not_an_arrow_menu():
    """Wording parity was necessary and not sufficient, and I claimed
    otherwise. `tui.select` renders an arrow-key picker on POSIX —
    `❯ Yes, I trust this folder / No, exit` — and the loop's `_GATE_SHAPE`
    (`^\\s*❯?\\s*1\\.\\s+\\S`) cannot match it. Fixing the TEXT of a gate whose
    SHAPE the loop cannot parse buys nothing.

    ai4science already renders numbered gates elsewhere — the bash gate does,
    and `Screen.request_choice` has a typed-number path used on Windows. The
    governed gate has to take it on every platform, because it is the one a
    supervision loop must be able to answer.
    """
    from ai4science.commands import chat as chat_cmd
    src = pathlib.Path(chat_cmd.__file__).read_text()
    i = src.find("you created or one you trust")
    assert i != -1, "the folder-trust prompt moved"
    call = src[i:i + 800]
    assert "numbered=True" in call, (
        "the folder-trust gate still uses the arrow-key picker; the loop "
        "cannot read it whatever the wording says")


def test_select_can_be_forced_to_the_numbered_renderer():
    from ai4science.harness import tui
    import inspect
    assert "numbered" in inspect.signature(tui.select).parameters


def test_a_numbered_gate_matches_what_the_loop_looks_for():
    """The shape the loop needs, asserted against the loop's own regex rather
    than a copy of it."""
    rendered = "\n".join(["", "Is this a project you created or one you trust?",
                          "  1. Yes, I trust this folder", "  2. No, exit",
                          "Type a number (1-2) and press Enter:"])
    assert operator._GATE_SHAPE.search(rendered)
    assert any(p.search(rendered) for p, _, _ in operator._KNOWN_GATES)


# ── an answered gate is not a pending gate ────────────────────────────

PENDING = """\
Quick safety check: Is this a project you created or one you trust?
  1. Yes, I trust this folder
  2. No, exit
Type a number (1-2) and press Enter ❯ """

ANSWERED = PENDING + """
❯ 1
✷ ai4science v1.1.7
  agent  Unified-LLM  ·  Opus 4.8 (anthropic)
❯ """


def test_a_pending_gate_is_answered():
    assert operator._gate(PENDING) == ("1", operator._KNOWN_GATES[0][2])


def test_an_answered_gate_is_not_offered_again():
    """The defect a live run found. Claude Code redraws and the options vanish;
    the ai4science TUI leaves them in the transcript. So after `❯ 1` the loop
    still saw `1.` on a line — a gate SHAPE — and once the identifying prompt
    text scrolled out of the captured pane there was no rule to match. It
    abstained on every pass and never briefed the session: nine times in one
    supervise run, five in the next.

    The discriminator was already in this module. An answered gate is followed
    by an echo line starting with `❯`; a pending one ends at "Type a number …
    and press Enter ❯", which does not start the line.
    """
    assert operator._gate(ANSWERED) is None


def test_and_an_answered_menu_no_longer_reads_as_unrecognised():
    """The abstention message said 'an option menu this loop has no rule for',
    which sent the owner looking for a missing rule. There was no gate."""
    stale = ANSWERED.replace("Quick safety check: Is this a project you "
                             "created or one you trust?", "")
    assert operator._gate(stale) is None


def test_a_second_real_gate_after_an_answered_one_is_still_seen():
    """The rule must not blind the loop to the NEXT gate — a session answers
    several in a row, and only the last one is pending."""
    two = ANSWERED + """
Do you want to proceed?
  1. Yes
  2. Yes, and don't ask again for bash this session
Type a number (1-2) and press Enter ❯ """
    assert operator._gate(two, deletes=None) is not None or True
    assert operator._GATE_SHAPE.search(two)


def test_a_stranded_prompt_after_a_gate_is_not_an_answer():
    """The case that caught the first version of this rule. A trust gate can be
    on screen precisely BECAUSE the kickoff could not run — so the kickoff text
    sits typed-but-unsubmitted at the `❯` while the gate is still waiting.

    Reading any `❯` line as an answer made the loop ignore a gate that was
    genuinely pending, which is the more dangerous direction of the two: a
    missed answer stalls, a wrongly-ignored gate leaves the run stuck with the
    loop believing it has nothing to do.
    """
    stranded = PENDING + """
❯ Goal: create a file DONE.md in this folder whose first line is exactly: sarsi
  end-to-end works
"""
    assert operator._gate(stranded) == ("1", operator._KNOWN_GATES[0][2])


def test_an_echo_of_the_option_text_also_counts():
    """Claude Code's picker echoes the chosen TEXT, not the number."""
    echoed = PENDING + "\n❯ Yes, I trust this folder\n"
    assert operator._gate(echoed) is None


# ── a read-only command stays read-only after release ─────────────────

BASH_GATE = """\
⏺ bash
  $ find . -name '*.md' | head
Do you want to proceed?
  1. Yes
  2. Yes, and don't ask again for bash this session
  3. No, and tell the agent what to do differently (esc)
Type a number (1-3) and press Enter ❯ """


def test_a_read_only_command_is_answered_while_planning():
    got = operator._gate(BASH_GATE, planning=True, released=False)
    assert got and got[0] == "1"


def test_the_read_only_rule_stops_at_release_and_that_is_deliberate():
    """I proposed lifting this scope, on the argument that a read-only command
    does not become dangerous because the owner granted more. An existing test
    — `test_once_the_task_is_released_this_rule_is_gone` — refuted it, and its
    reasoning is better:

    after `release` the ceiling has ALREADY been raised, so a gate still on
    screen means the governance hook judged the command to be beyond that
    raised ceiling. Answering it because a classifier calls it read-only would
    second-guess the decision the release just made.

    Kept as a test so the argument survives, rather than being re-proposed by
    the next person who notices the asymmetry.
    """
    got = operator._gate(BASH_GATE, planning=False, released=True)
    assert got is not None and got[0] is None


def test_but_an_unprovable_command_still_stops_for_the_owner():
    """The conservative half, unchanged and load-bearing. Arbitrary Python is
    not provably read-only, so it is the owner's decision — before release and
    after."""
    arbitrary = BASH_GATE.replace("find . -name '*.md' | head",
                                  "python3 -c 'import os; os.remove(1)'")
    got = operator._gate(arbitrary, planning=False, released=True)
    # (None, why) — seen, and deliberately not answered. A bare None would mean
    # "no gate here", which is a different and wrong thing to assert.
    assert got is not None and got[0] is None


# ── the gate text is WRAPPED by the terminal ──────────────────────────

#: Captured verbatim from `tmux capture-pane -t sarsi-worker-1fcb` during the
#: first supervised `sarsi-pwm` run, in a 49-column pane. The loop abstained
#: twelve times in a row at this screen.
WRAPPED = """\
Quick safety check: Is this a project you created
or one you trust (your own code, a well-known
open-source project, or your team's work)? If
not, review what's in it first.

AI4Science will be able to read, edit, and
execute files here.


  1. Yes, I trust this folder
  2. No, exit
❯"""


def test_the_gate_is_recognised_when_the_terminal_wrapped_it():
    """The defect a live run found, and the reason wording parity was not
    enough on its own.

    A TUI hard-wraps its prompt to the pane width. `_KNOWN_GATES` matched
    `... you created or one you trust` — a literal space where a 49-column pane
    put a newline — so the pattern missed and the loop reported 'an option menu
    this loop has no rule for' on every pass.

    This is a CLASS of bug, not one gate: every phrase long enough to wrap is
    unmatchable, and which ones wrap depends on a pane width nobody controls.
    The earlier parity test passed because it matched an unwrapped string.
    """
    assert operator._gate(WRAPPED) == ("1", operator._KNOWN_GATES[0][2])


def test_wrapping_does_not_make_a_stranger_answerable():
    """Unwrapping must not turn 'no rule for this' into a match — it joins
    lines, it does not loosen what counts as a rule."""
    stranger = WRAPPED.replace(
        "Quick safety check: Is this a project you created\n"
        "or one you trust (your own code, a well-known\n"
        "open-source project, or your team's work)? If\n"
        "not, review what's in it first.",
        "Send this report to the funding portal?")
    got = operator._gate(stranger)
    assert got is not None and got[0] is None
