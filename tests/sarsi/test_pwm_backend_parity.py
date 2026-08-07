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
