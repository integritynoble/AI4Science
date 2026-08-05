"""A dimmed hint is not a message from the owner.

Live on grace, `supervise` pressed Enter on **`granted, write report.md`** at a
session that was waiting for the owner to grant a write. The session refused
anyway — it wanted a formal grant and said so — so nothing was written. That is
the session's discipline holding, not the loop's.

The text was never typed by anyone. Captured with escape sequences the prompt
line reads:

    \\x1b[39m❯ \\x1b[2mgo ahead, write the report\\x1b[0m

`\\x1b[2m` is SGR **dim** — Claude Code's own placeholder. `tmux capture-pane -p`
strips it, and the loop's stranded-prompt reader has only ever seen the stripped
text, where a hint and a typed instruction are the same string.

There is already a filter for this, and it is calibrated on one shape:
`_SUGGESTION` matches `Try "…"` and nothing else. The hints are contextual now —
*"go ahead, write the report"*, *"granted, write report.md"*, *"add the min and
max PSNR too"* — text shaped exactly like an owner's authorisation, with no
wrapper to match on. The code comment beside that filter already says why this
keeps happening: *calibrating a filter on a single observation is how that
happens.* It happened again.

So the discriminator stops being the wording, which the tool controls and
changes, and becomes **the styling, which is what the terminal actually tells
us**: text the prompt renders dim was placed there by the tool, and the loop
does not submit it. What it cannot see the styling of, it still treats by the
old rule — an unstyled capture is not evidence that something was typed.
"""
from ai4science.harness.agents.sarsi import operator as op

#: A real capture, `tmux capture-pane -e -p`, of the live pane on grace.
STYLED_HINT = (
    "\x1b[38;5;244m" + "─" * 78 + "\n"
    "\x1b[39m❯ \x1b[2mgo ahead, write the report\x1b[0m\n"
    "\x1b[38;5;244m" + "─" * 78 + "\n"
    "\x1b[39m  \x1b[38;5;246m⏸ manual mode on · ? for shortcuts\x1b[39m\n"
)

#: The same pane with something the OWNER actually typed — not dim.
STYLED_TYPED = (
    "\x1b[38;5;244m" + "─" * 78 + "\n"
    "\x1b[39m❯ please use python3 on this host\n"
    "\x1b[38;5;244m" + "─" * 78 + "\n"
    "\x1b[39m  \x1b[38;5;246m⏸ manual mode on · ? for shortcuts\x1b[39m\n"
)


def _plain(styled: str) -> str:
    """What `capture-pane -p` gives — the same pane with the styling gone."""
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", styled)


# ── what the plain capture cannot tell apart ──────────────────────────

def test_the_two_panes_are_identical_once_stripped():
    """The premise. If these differed, wording would be enough."""
    assert _plain(STYLED_HINT).replace("go ahead, write the report",
                                       "please use python3 on this host") \
        == _plain(STYLED_TYPED)


def test_the_old_filter_does_not_catch_this_hint():
    """It matches `Try "…"` and this is not that shape."""
    assert op._SUGGESTION.match("go ahead, write the report") is None


# ── the styling is the discriminator ──────────────────────────────────

def test_a_dim_hint_is_not_stranded_text():
    assert op._stranded(_plain(STYLED_HINT), styled=STYLED_HINT) is None


def test_but_what_the_owner_typed_still_is():
    """The guard must not swallow the case it exists to serve."""
    assert op._stranded(_plain(STYLED_TYPED),
                        styled=STYLED_TYPED) == "please use python3 on this host"


def test_the_live_one_that_read_as_an_authorisation():
    """The exact string the loop submitted at a session awaiting a grant."""
    styled = STYLED_HINT.replace("go ahead, write the report",
                                 "granted, write report.md")
    assert op._stranded(_plain(styled), styled=styled) is None


def test_without_the_styling_it_falls_back_to_the_old_rule():
    """An unstyled capture is not evidence that something was typed, but it is
    all there is — the `Try "…"` filter still applies and nothing more is
    claimed."""
    assert op._stranded(_plain(STYLED_TYPED)) == "please use python3 on this host"
    assert op._stranded('❯ Try "fix typecheck errors"') is None
